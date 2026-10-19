import json
import os
import unittest
from unittest.mock import patch
import httpx
from title_generation import TitleClient, TitleError, generate_publish_title, valid_ai_title, TITLE_PROMPT, song_display_title, TITLE_MAX_ATTEMPTS, TITLE_TIMEOUT_SECONDS
from publishing import PublishPrepareError


class TitleTests(unittest.TestCase):
    title='☁️云层把心事压成低语｜《阴天》｜【芒芒_Mou】翻唱'

    def test_display_strips_both_nested_multiple_and_mixed_parentheses(self):
        for original,expected in [('牛仔很忙 (cover: 周杰伦)','牛仔很忙'),('公主殿下 (cover: 崔洋)(完整版)','公主殿下'),
                                  ('多余的解释（甜妹版)','多余的解释'),('遇见（现场(完整版)）','遇见'),('鱼仔','鱼仔')]:
            self.assertEqual(song_display_title(original),expected)
        for original in ('（完整版）','', '遇见（未闭合'):
            with self.assertRaises(PublishPrepareError):song_display_title(original)

    def test_parenthetical_song_ai_and_fallback_use_clean_display(self):
        class Client:
            model='test'
            def generate(self,prompt):
                self.prompt=prompt
                return '🐎轻快节拍，今天也很忙｜《牛仔很忙》｜【芒芒_Mou】翻唱'
        client=Client();original='牛仔很忙 (cover: 周杰伦)'
        title,record=generate_publish_title('芒芒_Mou',original,'周杰伦',lambda:client)
        self.assertEqual(record['source'],'ai');self.assertEqual(record['display_song_title'],'牛仔很忙')
        self.assertNotIn('cover:',client.prompt);self.assertIn('《牛仔很忙》',title)
        with patch.dict(os.environ,{'AI_TITLE_ENABLED':'0'}):
            fallback,_=generate_publish_title('芒芒_Mou',original)
        self.assertEqual(fallback,'芒芒_Mou《牛仔很忙》｜直播翻唱')
        self.assertEqual(original,'牛仔很忙 (cover: 周杰伦)')

    def run_response(self, handler):
        with patch.dict(os.environ,{'AI_TITLE_ENABLED':'1','TITLE_API_KEY':'private-test-key','TITLE_API_MODEL':'gpt-6.1-sol'}):
            return generate_publish_title('芒芒_Mou','阴天','',lambda:TitleClient(httpx.MockTransport(handler)))

    def test_success_and_wire_format(self):
        calls=[]
        def handler(request):
            calls.append(request)
            self.assertEqual(request.url.path,'/v1/chat/completions')
            body=json.loads(request.content)
            self.assertEqual(body['model'],'gpt-6.1-sol')
            self.assertEqual(request.extensions['timeout']['read'],120)
            self.assertFalse(body['stream'])
            self.assertEqual(body['messages'][0]['content'],TITLE_PROMPT.format(identified_title='阴天',identified_artist='',streamer='芒芒_Mou'))
            return httpx.Response(200,json={'choices':[{'message':{'content':self.title}}]})
        title,record=self.run_response(handler)
        self.assertEqual(title,self.title);self.assertEqual(record['source'],'ai');self.assertEqual(len(calls),1)
        self.assertNotIn('private-test-key',json.dumps(record))

    def test_http_failures_one_request_and_classified_retries(self):
        for status in (400,401,403,422,429,500,503):
            calls=[]
            def handler(request):
                calls.append(request);return httpx.Response(status,text='private-test-key')
            title,record=self.run_response(handler)
            self.assertEqual(title,'芒芒_Mou《阴天》｜直播翻唱')
            self.assertEqual(record['error'],'http_'+str(status));self.assertEqual(len(calls),1)
            self.assertEqual(record['retry_pending'],status==429 or status>=500)

    def test_durable_retry_limit_three_then_fallback(self):
        calls=[]; persisted=[]
        class Client:
            model='gpt-6.1-sol'
            def generate(self,prompt):
                calls.append(prompt)
                self_test.assertEqual(persisted[-1]['attempts'],len(calls))
                self_test.assertTrue(persisted[-1]['in_flight'])
                raise TitleError('timeout')
        self_test=self;record=None
        for attempt in range(1,4):
            title,record=generate_publish_title('芒芒_Mou','阴天',client_factory=Client,
                previous_record=record,persist_record=lambda r:persisted.append(json.loads(json.dumps(r))))
            self.assertEqual(record['attempts'],attempt)
            self.assertEqual(record['retry_pending'],attempt<3)
            self.assertEqual(title,'芒芒_Mou《阴天》｜直播翻唱')
        generate_publish_title('芒芒_Mou','阴天',client_factory=Client,previous_record=record)
        self.assertEqual(len(calls),3)
        self.assertEqual(len(record['history']),3)
        self.assertEqual(TITLE_MAX_ATTEMPTS,3);self.assertEqual(TITLE_TIMEOUT_SECONDS,120)

    def test_interrupted_attempt_and_legacy_record_keep_counts(self):
        class Client:
            model='gpt-6.1-sol'
            def generate(self,prompt): return TitleTests.title
        for prior,expected in [({'attempts':2,'in_flight':True},3),({'requested_model':'old','error':'timeout'},2)]:
            _,record=generate_publish_title('芒芒_Mou','阴天',client_factory=Client,previous_record=prior)
            self.assertEqual(record['attempts'],expected);self.assertEqual(record['source'],'ai')
            self.assertFalse(record['retry_pending'])

    def test_lyrics_reference_and_persistence_failure_prevents_request(self):
        client=unittest.mock.Mock(model='gpt-6.1-sol');client.generate.return_value=self.title
        _,record=generate_publish_title('芒芒_Mou','阴天',client_factory=lambda:client,lyrics='已匹配的歌词短句')
        self.assertIn('已匹配的歌词短句',client.generate.call_args.args[0]);self.assertIn('副歌',record['prompt'])
        client.generate.reset_mock()
        with self.assertRaises(RuntimeError):
            generate_publish_title('芒芒_Mou','阴天',client_factory=lambda:client,
                persist_record=lambda record:(_ for _ in ()).throw(RuntimeError('database unavailable')))
        client.generate.assert_not_called()

    def test_timeout_and_connection_fallback(self):
        for exception in (httpx.ReadTimeout,httpx.ConnectError):
            def handler(request): raise exception('private-test-key',request=request)
            title,record=self.run_response(handler)
            self.assertEqual(record['source'],'fallback');self.assertNotIn('private-test-key',json.dumps(record))

    def test_invalid_responses_fallback(self):
        for data in ({},{'choices':[]},{'choices':[{'message':{'content':None}}]}):
            title,record=self.run_response(lambda request:httpx.Response(200,json=data))
            self.assertEqual(record['error'],'invalid_response')

    def test_identity_length_multiline_protection(self):
        for value in (self.title.replace('阴天','晴天'),self.title.replace('芒芒_Mou','管珩心'),self.title+'\n另一条', '☁️'+'字'*81+'｜《阴天》｜【芒芒_Mou】翻唱','阴天真好听','☁️'+self.title+'｜解释'):
            title,record=self.run_response(lambda request:httpx.Response(200,json={'choices':[{'message':{'content':value}}]}))
            self.assertEqual(title,'芒芒_Mou《阴天》｜直播翻唱');self.assertEqual(record['error'],'invalid_title')

    def test_disabled_and_missing_key_do_not_request(self):
        with patch.dict(os.environ,{'AI_TITLE_ENABLED':'0','TITLE_API_KEY':''}):
            title,record=generate_publish_title('芒芒_Mou','阴天')
            self.assertEqual(record['error'],'disabled')
        with patch.dict(os.environ,{'AI_TITLE_ENABLED':'1','TITLE_API_KEY':''}):
            title,record=generate_publish_title('芒芒_Mou','阴天')
            self.assertEqual(record['error'],'missing_key')

    def test_unexpected_error_never_leaks_or_blocks(self):
        def factory(): raise RuntimeError('private-test-key')
        title,record=generate_publish_title('芒芒_Mou','阴天',client_factory=factory)
        self.assertEqual(record['source'],'fallback');self.assertNotIn('private-test-key',json.dumps(record))


if __name__=='__main__':unittest.main()
