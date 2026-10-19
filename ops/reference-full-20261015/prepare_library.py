"""Copy manually reviewed whole PNG assets, never crop/edit/delete originals."""
import hashlib
import json
from pathlib import Path
import shutil

records=json.loads(Path('C:/Users/34862/Documents/飞牛/output/reference-review-20261015/assets.json').read_text(encoding='utf-8'))
excluded={'0-01','0-02','0-06','0-07','1-04'}  # Visually reviewed microphone-bearing images.
stage=Path(__file__).parent/'stage/assets'
pool=[];review=[]
for record in records:
    allowed=record['id'] not in excluded
    item={'id':record['id'],'name':record['name'],'sha256':record['sha256'],'dimensions':record['dimensions'],
          'has_microphone':not allowed,'active':allowed and record['id'].startswith('0-')}
    review.append(item)
    if not allowed:continue
    group='normal' if record['id'].startswith('0-') else 'q'
    source=Path(record['path']);target=stage/group/source.name
    target.parent.mkdir(parents=True,exist_ok=True)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==record['sha256']
    shutil.copy2(source,target)
    assert target.read_bytes()==source.read_bytes()
    if group=='normal':pool.append({'id':record['id'],'path':'/data/cover-references/full-v1/normal/'+source.name,
                                  'sha256':record['sha256'],'has_microphone':False})
assert len(pool)==6 and len(excluded)==5
stage.mkdir(parents=True,exist_ok=True)
(stage/'references.json').write_text(json.dumps({'bilibili:2516117':{'references':pool}},ensure_ascii=False,indent=2),encoding='utf-8')
(stage/'reviewed.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
print('6 active normal full PNGs, 5 inactive Q PNGs, 5 mic images excluded; all original files preserved')
