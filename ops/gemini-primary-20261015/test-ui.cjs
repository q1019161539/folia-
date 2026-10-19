const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[2]||'web/publish.js','utf8');
const fn=source.slice(source.indexOf('function renderPublishControl('),source.indexOf('async function changePublishControl('));
for(const provider of ['gemini','gpt'])for(const configured of [true,false]){
  const elements=new Map(),$=key=>{
    if(!elements.has(key))elements.set(key,{setAttribute(){}});
    return elements.get(key);
  };
  const ctx={$,publishControlSaving:false,Date};vm.createContext(ctx);
  vm.runInContext(fn,ctx);
  ctx.renderPublishControl({rollout:{mode:'paused'},publish_enabled:true,auto_publish_enabled:true,
    cover_configured:configured,cover_primary_provider:provider});
  assert(elements.get('#publishJobState').textContent.includes(provider==='gemini'?'Gemini主用':'GPT主用'));
  assert.strictEqual(elements.get('#publishAutoToggle').disabled,!configured);
}
console.log('4 UI provider/configuration cases passed');
