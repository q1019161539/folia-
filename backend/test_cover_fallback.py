import base64
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx
from PIL import Image
from cover_fallback import (GeminiCoverClient, CoverError, should_use_fallback,
                            provided_reference, HALF_BODY_INSTRUCTION, use_gemini_for_cover, primary_cover_configured)


class GeminiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ref = self.root / 'reference.png'
        Image.new('RGBA', (900, 900), (255, 128, 128, 0)).save(self.ref)
        out = io.BytesIO(); Image.new('RGB', (2752, 1536), 'pink').save(out, format='JPEG')
        self.raw = out.getvalue()
        self.env = patch.dict(os.environ, {'COVER_FALLBACK_API_KEY':'test-secret-not-stored',
            'COVER_FALLBACK_ENABLED':'1', 'COVER_FALLBACK_BASE_URL':'https://provider.test/v1',
            'COVER_FALLBACK_MODEL':'gemini-3-pro-image-preview','COVER_FALLBACK_PROXY':''})
        self.env.start()

    def tearDown(self):
        self.env.stop(); self.tmp.cleanup()

    def test_threshold_strictly_over_five_and_disabled_is_gpt(self):
        for count in (0, 1, 5): self.assertFalse(should_use_fallback(count))
        for count in (6, 8, 9): self.assertTrue(should_use_fallback(count))
        with patch.dict(os.environ, {'COVER_FALLBACK_ENABLED':'0'}): self.assertFalse(should_use_fallback(8))
        with patch.dict(os.environ, {'COVER_FALLBACK_API_KEY':''}): self.assertFalse(should_use_fallback(8))

    def test_gemini_primary_from_first_request_and_no_silent_gpt_fallback(self):
        with patch.dict(os.environ, {'COVER_PRIMARY_PROVIDER':'gemini','COVER_API_KEY':''}):
            self.assertTrue(primary_cover_configured())
            for count in (0,1,5,6,9):self.assertTrue(use_gemini_for_cover(count))
            with patch.dict(os.environ, {'COVER_FALLBACK_API_KEY':''}):
                self.assertFalse(primary_cover_configured())
                with self.assertRaises(CoverError):use_gemini_for_cover(0)
            with patch.dict(os.environ, {'COVER_FALLBACK_ENABLED':'0'}):
                with self.assertRaises(CoverError):use_gemini_for_cover(0)
        with patch.dict(os.environ, {'COVER_PRIMARY_PROVIDER':'invalid'}):
            self.assertFalse(primary_cover_configured())
            with self.assertRaises(CoverError):use_gemini_for_cover(0)
        with patch.dict(os.environ, {'COVER_PRIMARY_PROVIDER':'gpt'}):
            self.assertFalse(use_gemini_for_cover(0));self.assertTrue(use_gemini_for_cover(6))

    def test_verified_wire_reference_and_one_image_no_hidden_retries(self):
        calls=[]
        def handler(req):
            calls.append(req)
            payload=json.loads(req.content)
            self.assertEqual(req.url.path,'/v1beta/models/gemini-3-pro-image-preview:generateContent')
            self.assertEqual(payload['generationConfig']['candidateCount'],1)
            self.assertEqual(payload['generationConfig']['imageConfig'],{'aspectRatio':'16:9','imageSize':'2K'})
            content=payload['contents'][0]['parts']
            self.assertEqual(content[0]['text'],'《游园惊梦》'+HALF_BODY_INSTRUCTION)
            self.assertEqual(base64.b64decode(content[1]['inlineData']['data']),self.ref.read_bytes())
            return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'inlineData':{'mimeType':'image/jpeg','data':base64.b64encode(self.raw).decode()}}]}}]})
        result=GeminiCoverClient(httpx.MockTransport(handler)).generate(self.ref,'《游园惊梦》'+HALF_BODY_INSTRUCTION)
        self.assertEqual(result,self.raw);self.assertEqual(len(calls),1)

    def test_http_classification_and_only_one_request(self):
        for status,retry in ((400,False),(401,False),(403,False),(429,True),(502,True),(503,True)):
            calls=[]
            def handler(req): calls.append(req);return httpx.Response(status,json={'error':{'message':'test-secret-not-stored'}})
            with self.assertRaises(CoverError) as raised:
                GeminiCoverClient(httpx.MockTransport(handler)).generate(self.ref,'test')
            self.assertEqual(raised.exception.retryable,retry)
            self.assertNotIn('test-secret-not-stored',str(raised.exception));self.assertEqual(len(calls),1)

    def test_invalid_or_multiple_images_are_retryable(self):
        for parts in ([{'text':'no image'}],[{'inlineData':{'mimeType':'image/png','data':'a==='}}],
                      [{'inlineData':{'mimeType':'image/png','data':'YWJj'}},{'inlineData':{'mimeType':'image/png','data':'YWJj'}}]):
            transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'candidates':[{'content':{'parts':parts}}]}))
            with self.assertRaises(CoverError) as raised: GeminiCoverClient(transport).generate(self.ref,'test')
            self.assertTrue(raised.exception.retryable)

    def test_thought_images_not_used_and_no_artifact_download(self):
        calls=[]
        def handler(req):
            calls.append(req)
            return httpx.Response(200,json={'candidates':[{'content':{'parts':[
                {'thought':True,'inlineData':{'mimeType':'image/png','data':'YWJj'}},
                {'inlineData':{'mimeType':'image/jpeg','data':base64.b64encode(self.raw).decode()}}]}}]})
        self.assertEqual(GeminiCoverClient(httpx.MockTransport(handler)).generate(self.ref,'test'),self.raw)
        self.assertEqual(len(calls),1)

    def test_low_resolution_or_corrupt_image_is_not_silently_accepted(self):
        low=io.BytesIO();Image.new('RGB',(1376,768)).save(low,format='PNG')
        for raw in (low.getvalue(),b'broken image'):
            transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'candidates':[{'content':{'parts':[
                {'inlineData':{'mimeType':'image/png','data':base64.b64encode(raw).decode()}}]}}]}))
            with self.assertRaises(CoverError) as raised:GeminiCoverClient(transport).generate(self.ref,'test')
            self.assertTrue(raised.exception.retryable)

    def test_supplied_reference_only_exact_identity_preserves_original_and_alpha(self):
        original=self.ref.read_bytes();sourcehash=hashlib.sha256(original).hexdigest()
        config=self.root/'references.json'
        config.write_text(json.dumps({'bilibili:2516117':{'path':str(self.ref),'sha256':sourcehash,'crop':[50,40,850,800]}}))
        with patch.dict(os.environ,{'COVER_REFERENCE_CONFIG':str(config)}):
            self.assertIsNone(provided_reference('bilibili:25984441',self.root/'cached'))
            frame=provided_reference('bilibili:2516117',self.root/'cached')
            self.assertEqual(frame['type'],'provided-transparent-halfbody')
            with Image.open(frame['frame_path']) as im:self.assertEqual(im.size,(800,760));self.assertEqual(im.mode,'RGBA')
            self.assertEqual(self.ref.read_bytes(),original)
            self.ref.write_bytes(b'changed')
            with self.assertRaises(CoverError):provided_reference('bilibili:2516117',self.root/'cached')

    def test_disabled_reference_and_configured_bad_crop(self):
        with patch.dict(os.environ,{'COVER_REFERENCE_CONFIG':''}):self.assertIsNone(provided_reference('id',self.root))
        config=self.root/'bad.json';config.write_text('{invalid')
        with patch.dict(os.environ,{'COVER_REFERENCE_CONFIG':str(config)}):
            with self.assertRaises(CoverError):provided_reference('id',self.root)

    def full_pool(self):
        items=[]
        for index in range(3):
            source=self.root/f'full-{index}.png'
            Image.new('RGBA',(900+index,950),(index*30,70,120,100)).save(source)
            items.append({'id':str(index),'path':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'has_microphone':False})
        config=self.root/'pool.json';config.write_text(json.dumps({'room':{'references':items}}))
        return config,items

    def test_full_pool_preserves_exact_bytes_dimensions_and_transparency(self):
        config,items=self.full_pool()
        with patch.dict(os.environ,{'COVER_REFERENCE_CONFIG':str(config)}):
            frame=provided_reference('room',self.root/'cache',selection_key='song')
            source=next(item for item in items if item['sha256']==frame['source_sha256'])
            self.assertEqual(Path(frame['frame_path']).read_bytes(),Path(source['path']).read_bytes())
            self.assertEqual(frame['frame_sha256'],frame['source_sha256']);self.assertIsNone(frame['crop'])
            self.assertEqual(frame['type'],'provided-transparent-full')
            with Image.open(frame['frame_path']) as image:self.assertEqual(image.mode,'RGBA');self.assertEqual(image.height,950)
            self.assertIsNone(provided_reference('other-room',self.root/'cache',selection_key='song'))

    def test_full_pool_selection_stable_across_order_and_song_variety(self):
        config,items=self.full_pool()
        with patch.dict(os.environ,{'COVER_REFERENCE_CONFIG':str(config)}):
            first=provided_reference('room',self.root/'cache',selection_key='song')
            config.write_text(json.dumps({'room':{'references':list(reversed(items))}}))
            second=provided_reference('room',self.root/'cache',selection_key='song')
            self.assertEqual(first['source_sha256'],second['source_sha256'])
            selected={provided_reference('room',self.root/'cache',selection_key=str(index))['source_sha256'] for index in range(12)}
            self.assertGreater(len(selected),1)

    def test_full_pool_rejects_mic_unreviewed_empty_and_corrupt_sources(self):
        config,items=self.full_pool()
        with patch.dict(os.environ,{'COVER_REFERENCE_CONFIG':str(config)}):
            for pool in ([],[dict(items[0],has_microphone=True)],[{key:value for key,value in items[0].items() if key!='has_microphone'}]):
                config.write_text(json.dumps({'room':{'references':pool}}))
                with self.assertRaises(CoverError):provided_reference('room',self.root/'cache',selection_key='song')
            config.write_text(json.dumps({'room':{'references':[items[0]]}}));Path(items[0]['path']).write_bytes(b'changed')
            with self.assertRaises(CoverError):provided_reference('room',self.root/'cache',selection_key='song')

    def test_framing_prefers_halfbody_without_forbidding_fullbody(self):
        self.assertIn('构图优先半身近景',HALF_BODY_INSTRUCTION)
        self.assertIn('也可以采用全身构图',HALF_BODY_INSTRUCTION)
        self.assertNotIn('不出现腿部',HALF_BODY_INSTRUCTION)


if __name__=='__main__':unittest.main()
