'use strict';
// Runs inside BililiveTool. Authentication and Bilibili requests remain its SDK's responsibility.
const fs = require('node:fs');
const path = require('node:path');
const POSITIVE = n => Number.isSafeInteger(Number(n)) && Number(n) > 0;

function createQueue({root, getClient, now = Date.now, startTimer = true}) {
  fs.mkdirSync(root, {recursive:true});
  const jobs = new Map();
  let busy = false;
  const report = error => console.error('[folia-season]',error.stack || String(error));
  const key = (uid, aid) => `${Number(uid)}-${Number(aid)}`;
  const save = job => {
    const file = path.join(root, key(job.uid, job.aid) + '.json');
    const temporary = file + '.partial';
    const fd = fs.openSync(temporary, 'w', 0o600);
    try {fs.writeFileSync(fd, JSON.stringify(job)); fs.fsyncSync(fd);} finally {fs.closeSync(fd);}
    fs.renameSync(temporary, file);
    jobs.set(key(job.uid, job.aid), job);
  };
  for (const name of fs.readdirSync(root).filter(n => /^\d+-\d+\.json$/.test(n))) {
    try {
      const job = JSON.parse(fs.readFileSync(path.join(root, name), 'utf8'));
      if (key(job.uid,job.aid)+'.json' !== name || !['uid','aid','cid','seasonId'].every(k=>POSITIVE(job[k]))
          || !Number.isInteger(job.attempts) || job.attempts<0
          || !['pending','processing','verifying','retry','joined','failed'].includes(job.status))
        throw new Error('invalid collection receipt identity/state');
      jobs.set(key(job.uid, job.aid), job);
    } catch (error) {
      report(error); // Do not kill recordings or overwrite a damaged receipt with a fresh POST.
      const [uid,aid]=name.slice(0,-5).split('-').map(Number);
      jobs.set(key(uid,aid),{uid,aid,status:'failed',error:'合集恢复记录损坏，请人工核对',attempts:0});
    }
  }
  function enqueue(input) {
    for (const field of ['uid','aid','cid','seasonId']) if (!POSITIVE(input[field])) throw new Error('invalid collection '+field);
    if (input.sectionId != null && !POSITIVE(input.sectionId)) throw new Error('invalid collection sectionId');
    if (!input.taskId || typeof input.title !== 'string') throw new Error('invalid collection upload receipt');
    const frozen = {...Object.fromEntries(['uid','aid','cid','seasonId'].map(f => [f,Number(input[f])])),
      sectionId: input.sectionId == null ? null : Number(input.sectionId), title: input.title, taskId:input.taskId};
    const existing = jobs.get(key(input.uid,input.aid));
    if (existing) {
      for (const field of ['uid','aid','cid','seasonId','title','taskId'])
        if (existing[field] !== frozen[field]) throw new Error('collection receipt conflict');
      if (frozen.sectionId != null && existing.sectionId != null && frozen.sectionId !== existing.sectionId)
        throw new Error('collection section conflict');
      return existing;
    }
    const job = {...frozen,status:'pending',attempts:0,error:'',createdAt:now(),updatedAt:now(),nextRetryAt:now()};
    save(job);
    // The durable receipt exists before background network operations begin.
    if (startTimer) setImmediate(() => drain().catch(report));
    return job;
  }
  function absent(error) {
    // Observed response from BililiveTool's real season lookup. Never treat 412/5xx as absence.
    return !error?.response?.status || error.response.status === 200
      ? [error?.message,error?.response?.data?.message].includes('啥都木有') : false;
  }
  async function membership(client, job) {
    try {
      const result = await client.platform.getSessionId(job.aid);
      if (result == null || !Object.keys(result).length) return null;
      if (!POSITIVE(result.id)) throw new Error('invalid collection lookup response');
      return Number(result.id);
    } catch (error) {if (absent(error)) return null; throw error;}
  }
  async function processJob(original) {
    if (['joined','failed'].includes(original.status) || original.nextRetryAt > now()) return;
    if (original.attempts >= 6) {save({...original,status:'failed',error:'合集重试达到6次，请人工核对',updatedAt:now()}); return;}
    const job = {...original,attempts:original.attempts+1,status:'processing',updatedAt:now()};
    save(job); // Crash/in-flight attempts still count.
    try {
      const client = getClient(job.uid);
      const current = await membership(client,job);
      if (current != null) {
        if (current !== job.seasonId) {save({...job,status:'failed',error:'稿件已属于其他合集，不自动移动',updatedAt:now()});return;}
        save({...job,status:'joined',error:'',nextRetryAt:null,updatedAt:now()});return;
      }
      const seasons = await client.platform.getSeasonList({pn:1,ps:100});
      const season = seasons.seasons?.find(s => Number(s.season?.id) === job.seasonId);
      if (!season) {save({...job,status:'failed',error:'目标合集不存在或无权限',updatedAt:now()});return;}
      const sections = season.sections?.sections || [];
      if (job.sectionId == null) {
        const candidates = sections.filter(s => Number(s.type)===1);
        if (candidates.length !== 1) {save({...job,status:'failed',error:'合集小节不唯一，请在模板指定',updatedAt:now()});return;}
        job.sectionId = Number(candidates[0].id);
      }
      if (!sections.some(s => Number(s.id)===job.sectionId)) {save({...job,status:'failed',error:'小节不属于目标合集',updatedAt:now()});return;}
      // Existing uploaded CID, no getArchive() and no second video upload.
      save({...job,status:'verifying',nextRetryAt:now()+120000,updatedAt:now()});
      await client.platform.addMedia2Season({sectionId:job.sectionId,episodes:[{aid:job.aid,cid:job.cid,title:job.title}]});
      const verified = await membership(client,job);
      if (verified === job.seasonId) save({...job,status:'joined',error:'',nextRetryAt:null,updatedAt:now()});
      else if (verified != null) save({...job,status:'failed',error:'加入后的合集归属冲突，请人工核对',updatedAt:now()});
      else save({...job,status:'verifying',error:'加入请求已返回，等待确认合集归属',nextRetryAt:now()+120000,updatedAt:now()});
    } catch (error) {
      const status = Number(error?.response?.status || 0);
      const blocked = [400,401,403].includes(status);
      const exhausted = job.attempts >= 6;
      const delay = status === 412 ? 3600000 : Math.min(3600000,120000*2**(job.attempts-1));
      save({...job,status:blocked||exhausted?'failed':'retry',
        error:status ? `合集接口 HTTP ${status}${status===412?'，暂停60分钟后再核对':''}` : '合集请求或确认失败',
        nextRetryAt:blocked||exhausted?null:now()+delay,updatedAt:now()});
    }
  }
  async function drain() {
    if (busy) return;
    busy = true;
    try {for (const job of jobs.values()) await processJob(job);} finally {busy=false;}
  }
  const timer = startTimer ? setInterval(() => drain().catch(report),60000) : null;
  timer?.unref();
  return {enqueue,drain,read:(uid,aid)=>jobs.get(key(uid,aid)) || null,close:()=>{if(timer)clearInterval(timer);}};
}
module.exports = {createQueue};
