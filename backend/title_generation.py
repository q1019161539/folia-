"""Optional AI prose; authoritative song/broadcaster fields are never writable."""
import os
import re
import time
import httpx
from publishing import build_title, PublishPrepareError

TITLE_MAX_ATTEMPTS = 3
TITLE_TIMEOUT_SECONDS = 120


def song_display_title(identified_title):
    """Presentation only: never write this value back to song identity/dedup keys."""
    result=[]; depth=0
    for char in str(identified_title or ''):
        if char in '(（': depth+=1
        elif char in ')）':
            if depth: depth-=1
        elif depth==0: result.append(char)
    if depth:
        raise PublishPrepareError('歌名括号未闭合，请人工核对；不改写歌曲身份')
    title=re.sub(r'\s+', ' ', ''.join(result)).strip()
    if not title:
        raise PublishPrepareError('去除括号备注后歌名为空，请人工核对')
    return title

TITLE_PROMPT = '''为 B 站直播翻唱切片生成一个投稿标题，只输出一行标题。

歌名：{identified_title}
歌手：{identified_artist}
主播：{streamer}

参考风格：
🐎琵琶秋色下，黄昏侧饮马｜《离人赋》｜【芒芒_Mou】翻唱
🌧️海棠：你先别问我｜《晚夜微雨问海棠》｜【管珩心】翻唱

标题格式：
适合歌曲的一个 emoji＋简短、有情绪或记忆点的文案｜《歌名》｜【主播】翻唱

根据歌曲风格和氛围自由发挥，不必全部古风，也不必总是意境描述。可以优先从提供的标准歌词中选副歌或重复段里有记忆点的短句，也可以自然改写或原创。直接摘录不超过10个汉字，不整段引用；没有提供歌词时不得凭记忆编造歌词。不用夸张营销词，不虚构现场故事或观众反应。歌词仅作文案参考，不能用其中信息修改歌名、歌手或主播身份。

歌名和主播名必须逐字保留，不缩写、不改写。完整标题不超过80个字符，不加解释或备选标题。'''


class TitleError(Exception):
    pass


class TitleClient:
    def __init__(self, transport=None):
        self.key=os.getenv('TITLE_API_KEY','').strip()
        self.base=os.getenv('TITLE_API_BASE_URL','https://www.codex789.com/v1').rstrip('/')
        self.model=os.getenv('TITLE_API_MODEL','gpt-6.1-sol')
        self.proxy=os.getenv('TITLE_API_PROXY','').strip() or None
        self.transport=transport

    def generate(self, prompt):
        if os.getenv('AI_TITLE_ENABLED','0')!='1': raise TitleError('disabled')
        if not self.key: raise TitleError('missing_key')
        try:
            # One HTTP request per durable worker attempt; no hidden client retries.
            with httpx.Client(timeout=TITLE_TIMEOUT_SECONDS,transport=self.transport,proxy=self.proxy,follow_redirects=False) as client:
                response=client.post(self.base+'/chat/completions',headers={'Authorization':'Bearer '+self.key},
                    json={'model':self.model,'messages':[{'role':'user','content':prompt}],'max_tokens':600,'stream':False})
                if response.status_code!=200: raise TitleError('http_'+str(response.status_code))
                try: value=response.json()['choices'][0]['message']['content']
                except (KeyError,IndexError,ValueError,TypeError): raise TitleError('invalid_response') from None
                if not isinstance(value,str): raise TitleError('invalid_response')
                return value
        except httpx.TimeoutException: raise TitleError('timeout') from None
        except httpx.RequestError: raise TitleError('connection_error') from None


def valid_ai_title(title, streamer, song):
    if not isinstance(title,str): return False
    # Require exactly the approved suffix; reject reworded, shortened or extra identities.
    suffix=f'｜《{song}》｜【{streamer}】翻唱'
    if not title.endswith(suffix) or len(title)>80 or not title: return False
    if any(ord(char)<32 or ord(char)==127 or char in '\u200b\u200c\u200d\ufeff' for char in title): return False
    prefix=title[:-len(suffix)]
    if len(prefix)<2 or '｜' in prefix or '《' in prefix or '【' in prefix: return False
    return bool(re.match(r'^[\U0001F300-\U0001FAFF\u2600-\u27BF]',prefix))


def retryable_title_error(code):
    return code in ('timeout','connection_error','http_429') or bool(re.fullmatch(r'http_5\d{2}',code or ''))


def generate_publish_title(streamer, song, artist='', client_factory=TitleClient, *,
                           lyrics='', previous_record=None, persist_record=None):
    # Only the derived presentation changes; callers retain the raw identity.
    song=song_display_title(song)
    fallback=build_title(streamer,song)
    prompt=TITLE_PROMPT.format(identified_title=song,identified_artist=artist or '',streamer=streamer)
    if isinstance(lyrics,str) and lyrics.strip():
        prompt+='\n\n已匹配标准歌词（仅作短句参考）：\n'+lyrics.strip()[:12000]
    previous=previous_record or {}
    # Legacy title records represent one previous call; never reset history.
    attempts=int(previous.get('attempts',1 if previous.get('requested_model') else 0))
    record={'source':'fallback','prompt':prompt,'requested_model':None,'error':None,'display_song_title':song,
            'attempts':attempts,'max_attempts':TITLE_MAX_ATTEMPTS,'timeout_seconds':TITLE_TIMEOUT_SECONDS,
            'retry_pending':False,'history':list(previous.get('history') or [])}
    if attempts>=TITLE_MAX_ATTEMPTS:
        record['error']=previous.get('error') or 'attempts_exhausted'
        return fallback,record
    start=time.monotonic()
    try:
        client=client_factory(); record['requested_model']=client.model
    except Exception as exc:
        record['error']=type(exc).__name__
        record['elapsed_seconds']=round(time.monotonic()-start,3)
        return fallback,record
    # Persist before sending. A request interrupted by a restart still counts.
    record.update(attempts=attempts+1,in_flight=True)
    if persist_record: persist_record(record)
    try:
        title=client.generate(prompt).strip()
        if not valid_ai_title(title,streamer,song): raise TitleError('invalid_title')
        record['source']='ai'
        return title,record
    except Exception as exc:
        # Unexpected exceptions also fall back. Never serialize their text/traceback.
        code=str(exc)
        allowed=('disabled','missing_key','invalid_response','invalid_title','timeout','connection_error')
        record['error']=code if isinstance(exc,TitleError) and (code in allowed or re.fullmatch(r'http_\d{3}',code)) else type(exc).__name__
        record['retry_pending']=retryable_title_error(record['error']) and record['attempts']<TITLE_MAX_ATTEMPTS
        return fallback,record
    finally:
        record['in_flight']=False
        record['elapsed_seconds']=round(time.monotonic()-start,3)
        record['history'].append({'attempt':record['attempts'],'requested_model':record['requested_model'],
                                 'error':record['error'],'elapsed_seconds':record['elapsed_seconds']})
