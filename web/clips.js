let clipPath='',clipSelectedFile=null,clipSegments=[],clipBatch=null,clipWatchTimer=null;

function showWorkspace(name){
 const clips=name==='clips';
 const transcriber=name==='transcriber';
 const automation=name==='automation';
 const publish=name==='publish';
 const studio=!clips&&!transcriber&&!automation&&!publish;
 $('#studioPage').hidden=!studio;$('#studioNav').style.display=studio?'':'none';$('#clipPage').hidden=!clips;$('#transcriberPage').hidden=!transcriber;$('#automationPage').hidden=!automation;$('#publishPage').hidden=!publish;
 $('#showStudio').classList.toggle('active',studio);$('#showClips').classList.toggle('active',clips);$('#showTranscriber').classList.toggle('active',transcriber);$('#showAutomation').classList.toggle('active',automation);$('#showPublish').classList.toggle('active',publish);
 document.body.dataset.workspace=name;
 try{sessionStorage.setItem('folia-workspace',name)}catch{}
 for(const [key,id] of [['studio','showStudio'],['clips','showClips'],['transcriber','showTranscriber'],['automation','showAutomation'],['publish','showPublish']]){$('#'+id).setAttribute('aria-current',key===name?'page':'false')}
 if(clips)loadClipFiles().catch(e=>toast(e.message));
 if(automation)openAutomation();
 if(publish)openPublish();
}
function clipHms(value){let s=Math.max(0,Math.round(Number(value)||0));return `${String(Math.floor(s/3600)).padStart(2,'0')}:${String(Math.floor(s/60)%60).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`}
function clipSeconds(value){let p=String(value).trim().split(':').map(Number);if(p.length===2)return p[0]*60+p[1];if(p.length===3)return p[0]*3600+p[1]*60+p[2];return NaN}
function updateClipStartButton(){$('#startClipBatch').disabled=!(clipSelectedFile&&clipSegments.some(x=>x.enabled))}

async function loadClipFiles(reset=false){
 let q=$('#clipSearch').value.trim();if(reset&&q)clipPath='';
 let data=await api(`/api/browse?path=${encodeURIComponent(clipPath)}&q=${encodeURIComponent(q)}&clips_only=false`);clipPath=data.path||'';
 $('#clipFilePath').textContent='biliLive-tools / video'+(clipPath?' / '+clipPath:'');$('#clipUp').disabled=!clipPath||!!q;
 let box=$('#clipFileList');box.innerHTML='';
 data.items.forEach(file=>{let button=document.createElement('button');button.className='file '+file.type+(clipSelectedFile?.id===file.id?' active':'');
  if(file.type==='folder'){button.innerHTML=`<span class="file-icon">📁</span><b>${esc(file.name)}</b><small>文件夹</small>`;button.onclick=()=>{clipPath=file.path;$('#clipSearch').value='';loadClipFiles()}}
  else{button.innerHTML=`<span class="file-icon">🎬</span><b title="${esc(file.path)}">${esc(file.name)}</b><small>${fileSize(file.size)}</small>`;button.onclick=()=>selectClipSource(file,button)}box.append(button)});
 $('#clipFileEmpty').style.display=data.items.length?'none':'block';
}
function selectClipSource(file,button){clipSelectedFile=file;$('#clipFileList').querySelectorAll('.file').forEach(x=>x.classList.remove('active'));button.classList.add('active');$('#clipSelected').className='clip-selected ready';$('#clipSelected').innerHTML=`<b>${esc(file.name)}</b><br>${esc(file.path)}`;updateClipStartButton()}

async function parseTimelineDocument(){
 let text=$('#timelineText').value.trim();if(!text)return toast('请先导入或粘贴时间轴文档');
 try{let result=await api('/api/clips/parse',{method:'POST',body:JSON.stringify({text,include_suspected:$('#includeSuspected').checked})});clipSegments=result.segments;renderClipRows();$('#timelineSummary').textContent=`已解析 ${result.official_count} 首正式歌曲、${result.suspected_count} 个疑似片段，共 ${clipSegments.length} 段`;$('#timelineWarnings').innerHTML=(result.warnings||[]).map(x=>`<div class="timeline-warning">⚠ ${esc(x)}</div>`).join('');updateClipStartButton();toast('时间轴解析完成')}catch(e){toast(e.message)}
}
function renderClipRows(){
 let padding=Math.max(0,Math.min(30,Number($('#clipPadding').value)||0));let body=$('#clipRows');body.innerHTML='';
 clipSegments.forEach((item,index)=>{let row=document.createElement('tr');row.className=item.kind==='suspected'?'suspected':'';let effective=`${clipHms(Math.max(0,item.start_seconds-padding))}–${clipHms(item.end_seconds+padding)}`;
  row.innerHTML=`<td data-label="使用"><input class="enabled" type="checkbox" aria-label="使用这段" ${item.enabled?'checked':''}></td><td class="kind" data-label="类型">${item.kind==='official'?'正式':'疑似'}</td><td data-label="歌曲"><input class="clip-title" type="text" aria-label="歌曲名" value="${esc(item.title)}"></td><td data-label="开始"><input class="time start-time" aria-label="开始时间" value="${clipHms(item.start_seconds)}"></td><td data-label="结束"><input class="time end-time" aria-label="结束时间" value="${clipHms(item.end_seconds)}"></td><td class="effective" data-label="有效范围">${effective}</td>`;
  row.querySelector('.enabled').onchange=e=>{item.enabled=e.target.checked;updateClipStartButton()};row.querySelector('.clip-title').onchange=e=>item.title=e.target.value.trim();row.querySelector('.start-time').onchange=e=>{let value=clipSeconds(e.target.value);if(Number.isFinite(value))item.start_seconds=value;renderClipRows()};row.querySelector('.end-time').onchange=e=>{let value=clipSeconds(e.target.value);if(Number.isFinite(value))item.end_seconds=value;renderClipRows()};body.append(row)});
}
function collectClipRows(){
 return [...$('#clipRows').querySelectorAll('tr')].map((row,index)=>({title:row.querySelector('.clip-title').value.trim(),start_seconds:clipSeconds(row.querySelector('.start-time').value),end_seconds:clipSeconds(row.querySelector('.end-time').value),kind:clipSegments[index].kind,enabled:row.querySelector('.enabled').checked}));
}
async function startClipBatch(){
 if(!clipSelectedFile)return toast('请先选择完整录播');let segments=collectClipRows();if(segments.some(x=>x.enabled&&(!x.title||!Number.isFinite(x.start_seconds)||!Number.isFinite(x.end_seconds)||x.end_seconds<=x.start_seconds)))return toast('请检查歌名和起止时间');
 $('#startClipBatch').disabled=true;
 try{clipBatch=await api('/api/clip-batches',{method:'POST',body:JSON.stringify({file_id:clipSelectedFile.id,segments,padding_seconds:Number($('#clipPadding').value)||0,mode:'copy'})});renderClipBatch(clipBatch);watchClipBatch();toast('批量切片已开始')}catch(e){toast(e.message);updateClipStartButton()}
}
function renderClipBatch(batch){
 let names={queued:'等待执行',running:'正在切片',cancelling:'正在中止',cancelled:'已中止',completed:'已完成',completed_with_errors:'完成但有失败',failed:'失败',interrupted:'已中断'};$('#clipBatchStatus').textContent=names[batch.status]||batch.status;$('#clipProgressBar').style.width=(batch.progress||0)+'%';$('#clipProgressText').textContent=`${Math.round(batch.progress||0)}%`;let items=batch.items||[],complete=items.filter(x=>x.status==='completed').length,failed=items.filter(x=>x.status==='failed').length;$('#clipCounts').textContent=`成功 ${complete} · 失败 ${failed} · 共 ${items.filter(x=>x.enabled).length} 段`;$('#cancelClipBatch').hidden=!['queued','running','cancelling'].includes(batch.status);$('#cancelClipBatch').disabled=batch.status==='cancelling';$('#clipOutputDir').innerHTML=batch.output_dir_host?`保存到：<br>${esc(batch.output_dir_host)}`:'';$('#clipOutputs').innerHTML=items.map((x,i)=>x.status==='completed'?`<a href="${x.url}" target="_blank">▶ ${esc(x.output_name)}</a>`:x.status==='failed'?`<span class="failed">✕ ${esc(x.title)}：${esc(x.error||'失败')}</span>`:'').join('');$('#clipLog').textContent=batch.log||'暂无日志';$('#clipLog').scrollTop=$('#clipLog').scrollHeight;
 if(['completed','completed_with_errors','failed','cancelled','interrupted'].includes(batch.status))updateClipStartButton();
}
async function watchClipBatch(){clearTimeout(clipWatchTimer);if(!clipBatch)return;try{clipBatch=await api(`/api/clip-batches/${clipBatch.id}`);renderClipBatch(clipBatch);if(['queued','running','cancelling'].includes(clipBatch.status))clipWatchTimer=setTimeout(watchClipBatch,1000)}catch(e){toast(e.message)}}

$('#showStudio').onclick=()=>showWorkspace('studio');$('#showClips').onclick=()=>showWorkspace('clips');$('#showTranscriber').onclick=()=>showWorkspace('transcriber');$('#clipFind').onclick=()=>loadClipFiles(true);$('#clipSearch').onkeydown=e=>{if(e.key==='Enter')loadClipFiles(true)};$('#clipUp').onclick=()=>{let parts=clipPath.split('/');parts.pop();clipPath=parts.join('/');loadClipFiles()};$('#timelineFile').onchange=async e=>{let file=e.target.files[0];if(file){$('#timelineText').value=await file.text();parseTimelineDocument()}};$('#parseTimeline').onclick=parseTimelineDocument;$('#includeSuspected').onchange=parseTimelineDocument;$('#clipPadding').oninput=renderClipRows;$('#startClipBatch').onclick=startClipBatch;$('#cancelClipBatch').onclick=async()=>{if(!clipBatch||!confirm('确定中止批量切片吗？已完成的视频会保留。'))return;clipBatch=await api(`/api/clip-batches/${clipBatch.id}/cancel`,{method:'POST',body:'{}'});renderClipBatch(clipBatch);watchClipBatch()};
