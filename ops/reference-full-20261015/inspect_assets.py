"""Local visual-QA contact sheets only; never edit supplied assets or upload previews."""
import hashlib
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

output=Path('C:/Users/34862/Documents/飞牛/output/reference-review-20261015')
output.mkdir(parents=True,exist_ok=True)
roots=[Path('D:/360安全浏览器下载/Live2D-正比高清'),Path('D:/360安全浏览器下载/Live2D-Q版高清')]
records=[]
for group,root in enumerate(roots):
    files=sorted(root.rglob('*.png'))
    sheet=Image.new('RGB',(1600,760*((len(files)+3)//4)),(225,228,232))
    draw=ImageDraw.Draw(sheet);font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
    for index,path in enumerate(files):
        raw=path.read_bytes()
        with Image.open(path) as im:
            im.load();bbox=im.getchannel('A').getbbox();preview=im.crop(bbox)
            preview.thumbnail((380,680))
            x=(index%4)*400+(400-preview.width)//2;y=(index//4)*760+50
            sheet.paste(preview,(x,y),preview)
            draw.text(((index%4)*400+8,(index//4)*760+8),f'{group}-{index+1:02d} {path.stem[-8:]}',font=font,fill='black')
            records.append({'id':f'{group}-{index+1:02d}','path':str(path),'name':path.name,'sha256':hashlib.sha256(raw).hexdigest(),
                'dimensions':list(im.size),'alpha_bbox':bbox,'size':len(raw)})
    sheet.save(output/f'contact-{group}.jpg',quality=94)
(output/'assets.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(records,ensure_ascii=False))
