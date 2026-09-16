"""Correct short, timestamped ASR spans against lyrics; never invent whole rows."""
import difflib
import re


def normalized(text):
    return re.sub(r'[^\w\u3400-\u9fff]+', '', str(text or '').lower().replace('臺', '台'))


def candidate(heard, target, allow_weak=False):
    """Find a supported substring, preserving partial lines instead of expanding them."""
    blocks = [b for b in difflib.SequenceMatcher(None, heard, target, autojunk=False).get_matching_blocks() if b.size]
    if not blocks:
        return None
    exact = sum(b.size for b in blocks)
    strong = exact >= 2 and exact / max(1, len(heard)) >= .6
    length_ratio = len(target) / max(1, len(heard))
    same_shape = len(heard) >= 6 and exact >= 2 and .75 <= length_ratio <= 1.25
    weak = (allow_weak and not strong and len(heard) >= 5 and exact >= 2
            and ((exact / max(1, len(heard)) >= .25 and .6 <= length_ratio <= 1.4) or same_shape))
    if not strong and not weak:
        return None
    first, last = blocks[0], blocks[-1]
    # Ordered weak evidence may have several wrong leading/trailing characters
    # (common with sung homophones).  Its safety comes from the recent previous
    # lyric anchor and next-line-only rule in align(), not from literal edges.
    edge_limit = len(heard) if weak and same_shape else (max(2, len(heard)//2) if weak else 1)
    if first.a > edge_limit or len(heard)-last.a-last.size > edge_limit:
        return None
    # Correct a short ASR prefix/suffix only when characters actually exist there.
    left = max(0, first.b - min(first.a, 1))
    right = min(len(target), last.b + last.size + min(len(heard)-last.a-last.size, 1))
    part = target[left:right]
    if weak and abs(len(target) - len(heard)) <= 2:
        left, right, part = 0, len(target), target
    if (not weak and exact / max(1, len(part)) < .6) or len(part) > len(heard) + 2:
        return None
    if len(heard) <= 3 and exact != len(heard):
        return None
    # At most two missing internal letters; never fill a long unrecognized clause.
    if not weak:
        for a, b in zip(blocks, blocks[1:]):
            if b.b - a.b - a.size > b.a - a.a - a.size + 2:
                return None
    return left, right, exact, 3*exact - (len(heard)-exact)*2 - (len(part)-exact), weak


def align(lyrics, segments, normalize_words, character_anchors):
    tokens = []
    for index, segment in enumerate(segments):
        words = character_anchors(normalize_words(segment))
        if not words:
            chars = list(normalized(segment.get('text', '')))
            start, end = int(segment.get('start_ms', 0)), int(segment.get('end_ms', 0))
            words = [{'text': c, 'start_ms': start+round((end-start)*k/max(1,len(chars))),
                      'end_ms': start+round((end-start)*(k+1)/max(1,len(chars))), 'interpolated': True}
                     for k,c in enumerate(chars)] if end > start else []
        for word in words:
            if normalized(word['text']):
                tokens.append({**word, 'segment_id': segment.get('line_id', index)})
    tokens.sort(key=lambda w: (w['start_ms'], w['end_ms']))
    targets = [normalized(s) for s in lyrics]
    result, cursor, previous_lyric = [], 0, -1
    while cursor < len(tokens):
        best = None
        for stop in range(cursor+2, min(len(tokens), cursor+40)+1):
            window = tokens[cursor:stop]
            if any(b['start_ms']-a['end_ms'] > (3500 if a['segment_id']==b['segment_id'] else 1500) for a,b in zip(window,window[1:])):
                break
            if window[-1]['end_ms']-window[0]['start_ms'] > 15000:
                break
            heard = ''.join(normalized(w['text']) for w in window)
            for lyric_index, target in enumerate(targets):
                if previous_lyric >= 0 and lyric_index < previous_lyric:
                    continue
                boundary = stop == len(tokens) or tokens[stop]['segment_id'] != window[-1]['segment_id']
                near = lyric_index in (max(0, previous_lyric), previous_lyric + 1)
                next_line = lyric_index == previous_lyric + 1
                segment_count = len(set(w['segment_id'] for w in window))
                recent_anchor = previous_lyric >= 0 and result and window[0]['start_ms']-result[-1]['asr_end_ms'] <= 4000
                match = candidate(heard, target, allow_weak=boundary and next_line and segment_count <= 2 and recent_anchor)
                if match is None:
                    continue
                left, right, exact, score, weak = match
                short_edge = near and exact == len(heard) and exact >= 2 and (left == 0 or right == len(target))
                if not boundary and exact < 4 and not short_edge:
                    continue
                # Prefer the next occurrence on ties, but allow skipped/repeated verses.
                order = -abs(lyric_index-previous_lyric-1)
                close_whole = boundary and near and abs(len(target) - len(heard)) <= 2
                ordered_prefix = False
                if (previous_lyric >= 0 and next_line and not boundary
                        and exact == len(heard) == 2 and left == 0
                        and lyric_index + 1 < len(targets)):
                    segment_end = stop
                    while segment_end < len(tokens) and tokens[segment_end]['segment_id'] == window[-1]['segment_id']:
                        segment_end += 1
                    remainder = ''.join(normalized(w['text']) for w in tokens[stop:segment_end])
                    ordered_prefix = candidate(remainder, targets[lyric_index+1]) is not None
                key = (score + (5 if boundary else 0) + (10 if close_whole else 0)
                       + (30 if ordered_prefix else 0), exact, order)
                if best is None or key > best[0]:
                    best = (key, stop, lyric_index, left, right, window, heard, weak)
        if best is None:
            # A segment may start mid-line or contain an unrecognised prefix.  Do
            # not discard its remaining words just because the first token could
            # not anchor a lyric substring.
            cursor += 1
            continue
        _, stop, lyric_index, left, right, window, heard, weak = best
        target = targets[lyric_index][left:right]
        # Map each retained character to this local ASR span only.
        mapped = {}
        for tag,a,b,c,d in difflib.SequenceMatcher(None, target, heard, autojunk=False).get_opcodes():
            if tag == 'equal':
                for k in range(b-a): mapped[a+k] = c+k
            elif tag == 'replace' and d>c:
                for k in range(b-a): mapped[a+k] = c+min(d-c-1, k)
        words, corrections = [], []
        for k, char in enumerate(target):
            src = mapped.get(k)
            if src is not None:
                anchor = window[src]
                start,end = anchor['start_ms'],anchor['end_ms']
                original = normalized(anchor['text'])
            else:
                before = max((i for i in mapped if i<k),default=None)
                after = min((i for i in mapped if i>k),default=None)
                if before is None and after is not None:
                    lo, hi, count, position = window[0]['start_ms'], window[mapped[after]]['start_ms'], after, k
                elif after is None and before is not None:
                    lo, hi = window[mapped[before]]['end_ms'], window[-1]['end_ms']
                    count, position = len(target)-before-1, k-before-1
                elif before is not None and after is not None:
                    lo, hi = window[mapped[before]]['end_ms'], window[mapped[after]]['start_ms']
                    count, position = after-before-1, k-before-1
                else:
                    raise ValueError('unanchored lyric span')
                start = lo+round(max(0,hi-lo)*position/max(1,count))
                end = lo+round(max(0,hi-lo)*(position+1)/max(1,count))
                original = ''
            word = {'text':char,'start_ms':int(start),'end_ms':max(int(start)+1,int(end)),
                    'interpolated':src is None or bool(window[src].get('interpolated'))}
            if original != char:
                kind = 'replace' if original else 'insert'
                word.update(corrected=True, original_text=original, correction_kind=kind)
                corrections.append({'index':k,'text':char,'original_text':original,'kind':kind})
            words.append(word)
        for a,b in zip(words,words[1:]):
            a['end_ms'] = max(a['start_ms']+1,min(a['end_ms'],b['start_ms']))
        result.append({'line_id':len(result),'text':target,'recognized_text':heard,
                       'start_ms':words[0]['start_ms'],'end_ms':words[-1]['end_ms'],
                       'asr_start_ms':window[0]['start_ms'],'asr_end_ms':window[-1]['end_ms'],
                       'segment_ids':sorted(set(w['segment_id'] for w in window)),
                       'status':'corrected' if corrections else 'matched',
                       'timing_precision':'corrected-character','words':words,'anchors':words,
                       'corrections':corrections,'confidence':round(best[0][1]/max(len(target),len(heard)),2),
                       'standard_line_index':lyric_index,'standard_text':lyrics[lyric_index],
                       'partial':left>0 or right<len(targets[lyric_index]),
                       'evidence_strength':'ordered-weak' if weak else 'strong',
                       'evidence_version':'asr-spans-v2'})
        cursor, previous_lyric = stop, lyric_index
    return result
