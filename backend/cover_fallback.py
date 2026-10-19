"""Optional Gemini cover provider and identity-bound supplied references.

No Bilibili calls, worker, retry loop, credentials on disk, or identity updates.
"""
from __future__ import annotations
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re

import httpx
from PIL import Image
from publishing import PublishPrepareError

MAX_IMAGE_BYTES = 50_000_000
FALLBACK_AFTER_FAILURES = 5
# Keep the imported name compatible; framing is a preference, not a hard body crop.
HALF_BODY_INSTRUCTION = '参考图为完整人物设定，不要求照搬全身构图。构图优先半身近景，突出脸部与表情；如果歌曲内容与氛围更适合全身，也可以采用全身构图。完整头饰与画面顶部留出安全距离，不要裁切头饰。仅生成一张完整封面，输出2K横版图片。'


class CoverError(PublishPrepareError):
    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def fallback_configured():
    return os.getenv('COVER_FALLBACK_ENABLED', '0') == '1' and bool(os.getenv('COVER_FALLBACK_API_KEY', '').strip())


def primary_cover_configured():
    primary = os.getenv('COVER_PRIMARY_PROVIDER', 'gpt').strip().lower()
    if primary == 'gemini':return fallback_configured()
    return primary == 'gpt' and bool(os.getenv('COVER_API_KEY', '').strip())


def should_use_fallback(attempts):
    # Strictly >5 failed/uncertain requests, not >=5. Total budget is unchanged.
    return int(attempts) > FALLBACK_AFTER_FAILURES and fallback_configured()


def use_gemini_for_cover(attempts):
    primary = os.getenv('COVER_PRIMARY_PROVIDER', 'gpt').strip().lower()
    if primary not in ('gpt', 'gemini'):
        raise CoverError('封面主通道配置不合法，请检查COVER_PRIMARY_PROVIDER')
    if primary == 'gemini':
        if not fallback_configured():
            raise CoverError('Gemini主用生图未启用或密钥未配置')
        return True  # No automatic return to a known-broken GPT channel.
    return should_use_fallback(attempts)


def provided_reference(identity_key, directory, *, selection_key=''):
    config = os.getenv('COVER_REFERENCE_CONFIG', '').strip()
    if not config:
        return None
    try:
        settings = json.loads(Path(config).read_text(encoding='utf-8'))
        entry = settings.get(identity_key)
        if entry is None:
            return None  # Never substitute another broadcaster's character.
        full = 'references' in entry
        if full:
            pool = entry['references']
            if (not isinstance(pool,list) or not pool or
                    any(not isinstance(item,dict) or item.get('has_microphone') is not False for item in pool)):
                raise ValueError('reference pool must be explicitly reviewed as microphone-free')
            pool = sorted(pool,key=lambda item:item['sha256'])
            index = int(hashlib.sha256((identity_key+'\0'+selection_key).encode('utf-8')).hexdigest(),16)%len(pool)
            entry = pool[index]
        source = Path(entry['path'])
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if len(raw) > MAX_IMAGE_BYTES or digest != entry['sha256']:
            raise ValueError('reference fingerprint mismatch')
        crop = None if full else entry['crop']
        if not full and (len(crop) != 4 or any(type(x) is not int for x in crop)):
            raise ValueError('invalid crop')
        with Image.open(io.BytesIO(raw)) as image:
            if image.format!='PNG' or image.width * image.height > 40_000_000 or 'A' not in image.getbands():
                raise ValueError('not a transparent character asset')
            if not full and not (0 <= crop[0] < crop[2] <= image.width and 0 <= crop[1] < crop[3] <= image.height):
                raise ValueError('crop outside image')
            image.load()
            directory = Path(directory)
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / ('provided-full.png' if full else 'provided-halfbody.png')
            temp = target.with_suffix('.partial')
            if full:temp.write_bytes(raw)  # Byte-identical whole PNG: no crop, resize or re-encode.
            else:image.crop(tuple(crop)).save(temp, format='PNG')
            temp.replace(target)
        return {'status': 'selected', 'type': 'provided-transparent-full' if full else 'provided-transparent-halfbody',
                'broadcaster_key': identity_key, 'source_sha256': digest, 'crop': crop,
                'frame_path': str(target), 'frame_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                'reference_id':entry.get('id'),'selection':'sha256-song-v1' if full else 'legacy-crop'}
    except Exception as exc:
        # A configured-but-broken reference is a terminal error, not a silent screenshot fallback.
        raise CoverError('已绑定的人物透明参考图不可用或校验失败，请人工检查') from exc


class GeminiCoverClient:
    def __init__(self, transport=None):
        self.key = os.getenv('COVER_FALLBACK_API_KEY', '').strip()
        self.base = os.getenv('COVER_FALLBACK_BASE_URL', 'https://www.codex789.com/v1').rstrip('/')
        self.model = os.getenv('COVER_FALLBACK_MODEL', 'gemini-3-pro-image-preview')
        self.proxy = os.getenv('COVER_FALLBACK_PROXY', '').strip() or None
        self.transport = transport
        self.request_config = {'responseModalities':['TEXT','IMAGE'],
            'imageConfig':{'aspectRatio':'16:9','imageSize':'2K'},'candidateCount':1}

    def generate(self, reference, prompt):
        if not self.key:
            raise CoverError('Gemini备用生图密钥未配置')
        raw = Path(reference).read_bytes()
        if len(raw) > MAX_IMAGE_BYTES:
            raise CoverError('人物参考图文件过大')
        if not re.fullmatch(r'[A-Za-z0-9._-]+', self.model):
            raise CoverError('Gemini备用模型名称不合法')
        # The verified gateway accepts the native Gemini route. /v1 was its chat base.
        base = self.base.removesuffix('/v1').removesuffix('/v1beta')
        endpoint = base+'/v1beta/models/'+self.model+':generateContent'
        try:
            with httpx.Client(timeout=600, transport=self.transport, proxy=self.proxy, follow_redirects=False) as client:
                response = client.post(endpoint,
                    headers={'Authorization': 'Bearer ' + self.key},
                    json={'contents':[{'role':'user','parts':[{'text':prompt},{'inlineData':{
                              'mimeType':'image/png','data':base64.b64encode(raw).decode('ascii')}}]}],
                          'generationConfig':self.request_config})
                if response.status_code != 200:
                    raise CoverError(f'Gemini 生图 HTTP {response.status_code}，请检查服务或账号额度',
                                     response.status_code >= 500 or response.status_code == 429)
                try:
                    parts = [part for candidate in response.json()['candidates']
                             for part in candidate.get('content',{}).get('parts',[]) if not part.get('thought')]
                    images = [part.get('inlineData') or part.get('inline_data') for part in parts
                              if part.get('inlineData') or part.get('inline_data')]
                    if len(images) != 1:
                        raise ValueError('expected one image')
                    source=images[0]
                    if source.get('mimeType',source.get('mime_type')) not in ('image/png','image/jpeg','image/webp'):
                        raise ValueError('invalid media type')
                    if len(source['data'])>70_000_000:raise ValueError('image too large')
                    raw=base64.b64decode(source['data'],validate=True)
                    if not raw or len(raw) > MAX_IMAGE_BYTES:
                        raise ValueError('invalid image length')
                    with Image.open(io.BytesIO(raw)) as image:
                        if image.width*image.height>40_000_000:raise ValueError('too many pixels')
                        image.load()
                        if image.width<2048 or image.height<1152 or abs(image.width/image.height-16/9)>.03:
                            raise CoverError(f'Gemini未返回要求的2K横版原图：{image.width}×{image.height}',True)
                    return raw
                except (KeyError, IndexError, ValueError, TypeError, OSError, httpx.HTTPError) as exc:
                    raise CoverError('Gemini 返回无效图片结果', True) from exc
        except httpx.RequestError as exc:
            raise CoverError('Gemini 生图连接失败或超时', True) from exc
