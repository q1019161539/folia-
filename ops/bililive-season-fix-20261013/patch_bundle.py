"""Deterministic overlay for the inspected 3.18.0 bundles; refuses changed anchors."""
from pathlib import Path
import hashlib
import sys

root=Path(sys.argv[1]);target=Path(sys.argv[2]);target.mkdir(parents=True,exist_ok=True)
core=(root/'index-CWUSa9VA.cjs').read_text(encoding='utf-8')
http=(root/'index-CYt93UQb.cjs').read_text(encoding='utf-8')
def replace_once(text,old,new):
    assert text.count(old)==1, 'bundle anchor changed: '+old[:60]
    return text.replace(old,new,1)
core=replace_once(core,'// 合集相关功能\n                if (formattedOptions.seasonId) {', '''// Folia: durable collection follow-up using the already uploaded CID.
                if (extraOptions?.foliaCollectionTracking && formattedOptions.seasonId) {
                    const part = pTask.taskList.find(t => t.status === "completed" && t.completedPart)?.completedPart;
                    foliaSeasonJobs.enqueue({uid,aid:data.aid,cid:part?.cid,seasonId:formattedOptions.seasonId,
                        sectionId:formattedOptions.sectionId,title:formattedOptions.title,taskId:pTask.taskId});
                } else if (formattedOptions.seasonId) {''')
core += '''\n// Folia addon: reuses BililiveTool's existing SDK/client and persisted login only.
const foliaSeasonJobs = require("./folia-season-jobs.cjs").createQueue({root:"/app/data/folia-season-jobs",getClient:createClient});
exports.foliaSeasonJobs = foliaSeasonJobs;
'''
http=replace_once(http,'const task = await index$1.biliApi.addMedia(data.videos, data.config, data.uid, {',
    'const task = await index$1.biliApi.addMedia(data.videos, data.config, data.uid, {\n            foliaCollectionTracking: data.options?.foliaCollectionTracking === true,')
http=replace_once(http,'// 验证视频上传参数\nrouter$9.post("/validUploadParams"', '''// Authenticated, read-only collection results. No historical enqueue/backfill endpoint.
router$9.get("/folia-season/capabilities", ctx => {ctx.body={version:1,durable:true};});
router$9.get("/folia-season/:aid", ctx => {
    const uid=Number(ctx.request.query.uid),aid=Number(ctx.params.aid);
    if (!Number.isSafeInteger(uid)||uid<=0||!Number.isSafeInteger(aid)||aid<=0) {ctx.status=400;ctx.body="invalid uid/aid";return;}
    const result=index$1.foliaSeasonJobs.read(uid,aid);
    if (!result) {ctx.status=404;ctx.body="collection receipt not found";return;}
    ctx.body=result;
});
// 验证视频上传参数
router$9.post("/validUploadParams"''')
for name,text in [('index-CWUSa9VA.cjs',core),('index-CYt93UQb.cjs',http)]:
    (target/name).write_text(text,encoding='utf-8')
    print(name,hashlib.sha256(text.encode()).hexdigest())
