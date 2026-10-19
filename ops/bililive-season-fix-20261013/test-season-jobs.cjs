'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {createQueue}=require('./folia-season-jobs.cjs');
const input={uid:1,aid:123,cid:456,seasonId:789,sectionId:321,title:'歌名',taskId:'task-1'};
function setup(t){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'folia-season-test-'));let time=1000,member=null,posts=0;
 const client={platform:{getArchive:async()=>{throw Error('must not query archive');},getSessionId:async()=>member==null?{}:{id:member},
  getSeasonList:async()=>({seasons:[{season:{id:789},sections:{sections:[{id:321,type:1}]}}]}),
  addMedia2Season:async data=>{posts++;assert.deepEqual(data,{sectionId:321,episodes:[{aid:123,cid:456,title:'歌名'}]});member=789;}}};
 const options={root,getClient:()=>client,now:()=>time,startTimer:false},queue=createQueue(options);
 t.after(()=>{queue.close();fs.rmSync(root,{recursive:true,force:true});});
 return {queue,root,client,options,posts:()=>posts,advance:()=>{time+=3600001;},member:id=>{member=id;}};
}
test('uses uploaded CID and persists no credentials',async t=>{
 const s=setup(t);s.queue.enqueue({...input,sectionId:null});await s.queue.drain();assert.equal(s.queue.read(1,123).status,'joined');assert.equal(s.posts(),1);
 assert(!/cookie|Authorization|passkey/.test(fs.readFileSync(path.join(s.root,'1-123.json'),'utf8')));
 s.queue.enqueue({...input,sectionId:null});await s.queue.drain();assert.equal(s.posts(),1);assert.throws(()=>s.queue.enqueue({...input,cid:999}),/conflict/);
});
test('already joined only verifies, never moves',async t=>{
 const s=setup(t);s.member(789);s.queue.enqueue(input);await s.queue.drain();assert.equal(s.posts(),0);assert.equal(s.queue.read(1,123).status,'joined');
});
test('observed empty season response is absence, not a 412 or login bypass',async t=>{
 const s=setup(t);let first=true;
 s.client.platform.getSessionId=async()=>{if(first){first=false;throw Error('啥都木有');}return {id:789};};
 s.queue.enqueue(input);await s.queue.drain();assert.equal(s.posts(),1);assert.equal(s.queue.read(1,123).status,'joined');
});
test('412 pauses one hour, no rapid retry or bypass',async t=>{
 const s=setup(t);s.client.platform.getSessionId=async()=>{throw {response:{status:412}};};s.queue.enqueue(input);await s.queue.drain();
 assert.equal(s.queue.read(1,123).status,'retry');assert.equal(s.posts(),0);assert.equal(s.queue.read(1,123).nextRetryAt,3601000);
 await s.queue.drain();assert.equal(s.queue.read(1,123).attempts,1);
});
test('lost response and restart verify membership without duplicate POST',async t=>{
 const s=setup(t);let calls=0;s.client.platform.addMedia2Season=async()=>{calls++;s.member(789);throw Error('response lost');};
 s.queue.enqueue(input);await s.queue.drain();s.advance();const q=createQueue(s.options);await q.drain();assert.equal(q.read(1,123).status,'joined');assert.equal(calls,1);q.close();
});
test('auth failure and wrong existing season stop',async t=>{
 const s=setup(t);s.member(999);s.queue.enqueue(input);await s.queue.drain();assert.equal(s.queue.read(1,123).status,'failed');assert.equal(s.posts(),0);
 const a=setup(t);a.client.platform.getSessionId=async()=>{throw {response:{status:401}};};a.queue.enqueue(input);await a.queue.drain();a.advance();await a.queue.drain();assert.equal(a.queue.read(1,123).attempts,1);
});
test('invalid CID and section refuse writes',async t=>{
 const s=setup(t);assert.throws(()=>s.queue.enqueue({...input,cid:0}),/cid/);s.queue.enqueue({...input,sectionId:444});await s.queue.drain();assert.equal(s.posts(),0);assert.equal(s.queue.read(1,123).status,'failed');
});
test('retry limit persists through restart',async t=>{
 const s=setup(t);s.client.platform.getSessionId=async()=>{throw {response:{status:500}};};s.queue.enqueue(input);
 for(let i=0;i<6;i++){await s.queue.drain();s.advance();}assert.equal(s.queue.read(1,123).attempts,6);assert.equal(s.queue.read(1,123).status,'failed');
 const q=createQueue(s.options);await q.drain();assert.equal(q.read(1,123).attempts,6);q.close();
});
test('single concurrent worker and persisted in-flight attempt',async t=>{
 const s=setup(t);let release;s.client.platform.getSessionId=()=>new Promise(r=>{release=()=>r({id:789});});s.queue.enqueue(input);
 const first=s.queue.drain();await s.queue.drain();assert.equal(s.queue.read(1,123).attempts,1);release();await first;
});
test('damaged receipt never kills the service or causes fresh collection POST',async t=>{
 const s=setup(t);fs.writeFileSync(path.join(s.root,'1-123.json'),'broken');const q=createQueue(s.options);
 await q.drain();assert.equal(q.read(1,123).status,'failed');assert.equal(s.posts(),0);assert.throws(()=>q.enqueue(input),/conflict/);q.close();
});
