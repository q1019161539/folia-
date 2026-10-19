let publishInitialized = false, publishLoading = null;
let publishProfiles = [], publishPresets = [], publishPresetError = '', publishFonts = [];
let publishControl = null, publishControlSaving = false;
const publishJobStatus = {pending:'等待准备',preparing:'选帧 / 生成 / 校验',ready:'等待自动提交',submitting:'提交中',uploading:'上传中',completed:'投稿完成',failed:'失败'};
function publishCollectionInfo(job) {
  if (!job?.collection_status) return ''; // Historical/user-fixed archives are not backfilled.
  const names={pending:'等待加入合集',processing:'正在核对并加入合集',verifying:'等待确认合集归属',retry:'合集失败，等待退避重试',joined:'已加入合集',failed:'合集失败，需人工核对'};
  return `<small class="${job.collection_status==='failed'?'publish-error':''}">合集：${esc(names[job.collection_status]||job.collection_status)} · ${Number(job.collection_attempts)||0}/6 次${job.collection_error?' · '+esc(job.collection_error):''}</small>`;
}
const publishDefaultRegions = {'芒芒_Mou':[.32,.08,.74,.78], '小红泡-管珩心':[.37,.18,.69,.74]};

function publishPresetSummary(id) {
  const preset = publishPresets.find(item => item.id === id);
  if (!id) return '未绑定模板，不会自动生图或投稿。';
  if (!preset) return publishPresetError ? '模板暂时无法读取，已保存的选择不受影响。' : '已保存模板不存在，请重新选择。';
  const text = String(preset.description || '').replace(/\s+/g, ' ');
  return text ? `继承简介：${text.slice(0,120)}${text.length>120?'…':''}` : '模板没有简介，将使用固定简介。';
}

function renderPublishStreamers() {
  $('#publishStreamerList').innerHTML = publishProfiles.map(profile => {
    let region=[];
    try {region=JSON.parse(profile.cover_region_json || '[]');} catch (_) {}
    if (!region.length) region=publishDefaultRegions[profile.publish_streamer || profile.name] || [];
    const options='<option value="">未选择</option>'+publishPresets.map(p=>`<option value="${esc(p.id)}">${esc(p.name||p.id)}</option>`).join('')+
      (profile.bililive_preset_id && !publishPresets.some(p=>p.id===profile.bililive_preset_id)?`<option value="${esc(profile.bililive_preset_id)}">${esc(profile.bililive_preset_name||profile.bililive_preset_id)}（暂不可读）</option>`:'');
    return `<div class="publish-streamer" data-profile="${esc(profile.id)}"><div class="automation-card-head"><div><b>${esc(profile.publish_streamer||profile.name)}</b><small>${esc(profile.recorder_identity?.platform||'规则')} · ${esc(profile.recorder_identity?.room_id||profile.id)}</small></div><span class="automation-status ${profile.bililive_preset_id?'completed':'failed'}">${profile.bililive_preset_id?'模板已绑定':'未绑定模板'}</span></div><label>BililiveTool 投稿模板<select data-preset>${options}</select></label><small data-hint>${esc(publishPresetSummary(profile.bililive_preset_id))}</small><p>免费选帧人物区域（0–1，左 / 上 / 右 / 下）</p><div class="publish-settings">${['左','上','右','下'].map((label,i)=>`<label>${label}<input data-region="${i}" type="number" min="0" max="1" step="0.01" value="${region[i]??''}"></label>`).join('')}</div><small class="muted">${region.length?'按配置区域评分；不保证识别遮挡、闭眼。':'未配置：只按全画面画质评分，可能选中背景而非人物。'}</small><button data-save type="button">保存模板和人物区域</button></div>`;
  }).join('') || '<p class="muted">请先在自动流水线锁定主播。</p>';
  $('#publishPresetState').textContent=publishPresetError ? `模板读取失败：${publishPresetError}` : `BililiveTool ${publishPresets.length} 个模板 · 封面无需底图和字体库`;
  for (const card of $$('#publishStreamerList .publish-streamer')) {
    const p=publishProfiles.find(p=>p.id===card.dataset.profile), select=card.querySelector('[data-preset]');
    select.value=p.bililive_preset_id||'';
    select.onchange=()=>card.querySelector('[data-hint]').textContent=publishPresetSummary(select.value);
    card.querySelector('[data-save]').onclick=async()=>{
      const values=[...card.querySelectorAll('[data-region]')].map(input=>input.value);
      if (values.some(v=>v==='') && !values.every(v=>v==='')) {toast('请填完整四个人物区域坐标');return;}
      const body={bililive_preset_id:select.value,cover_font_id:p.cover_font_id||''};
      if (!values.every(v=>v==='')) body.cover_region=values.map(Number);
      try {Object.assign(p,await api(`/api/automation/profiles/${encodeURIComponent(p.id)}/publish`,{method:'PUT',body:JSON.stringify(body)}));renderPublishStreamers();toast('投稿设置已保存');}
      catch(e){toast(e.message);}
    };
  }
}

function renderPublishFonts() {
  $('#publishFontList').innerHTML=publishFonts.map(font=>`<div class="publish-font"><div><b>${esc(font.label||font.family)}</b><small>${font.builtin?'内置字体':esc(font.filename||'')}</small></div>${font.builtin?'':`<button type="button" class="danger" data-font-delete="${esc(font.id)}">删除</button>`}</div>`).join('');
  $$('#publishFontList [data-font-delete]').forEach(button=>button.onclick=async()=>{
    if (!confirm('删除该字体？正在使用的字体不能删除。')) return;
    try {await api(`/api/fonts/${encodeURIComponent(button.dataset.fontDelete)}`,{method:'DELETE'});await reloadPublishFonts();}catch(e){toast(e.message);}
  });
}
function syncStudioFonts() {
  if (typeof foliaFonts!=='undefined' && typeof renderFonts==='function') {foliaFonts=publishFonts;renderFonts($('#foliaFont')?.value);}
}
async function reloadPublishFonts() {publishFonts=(await api('/api/fonts')).fonts||[];syncStudioFonts();renderPublishFonts();}
async function uploadPublishFont(file) {
  if (!file) return;
  const form=new FormData();form.append('file',file);form.append('family','');
  try {const response=await fetch('/api/fonts',{method:'POST',body:form}),data=await response.json();if(!response.ok)throw Error(data.detail||response.statusText);await reloadPublishFonts();toast('字体已添加');}catch(e){toast(e.message);}
}

function renderPublishControl(control) {
  publishControl=control;
  const state=control.rollout||{}, active=state.mode==='active', paused=state.mode==='paused';
  const available=control.publish_enabled && control.auto_publish_enabled && control.cover_configured;
  const label=active?'新成片自动投稿已开启':paused?'自动投稿已暂停':'测试模式（仅指定两首）';
  const provider=control.cover_primary_provider==='gemini'?'Gemini':'GPT';
  $('#publishControlStatus').textContent=label;
  $('#publishJobState').textContent=`${label} · ${provider}主用 · ${control.cover_configured?'密钥已配置':'密钥未配置'}`;
  const toggle=$('#publishAutoToggle');
  toggle.textContent=active?'暂停自动投稿':paused?'恢复新成片自动投稿':'启用新成片自动投稿';
  toggle.setAttribute('aria-checked',String(active));
  toggle.disabled=publishControlSaving || (!active && !available);
  const deployment=!control.publish_enabled || !control.auto_publish_enabled?'部署总开关关闭，页面不能启用。':!control.cover_configured?`${provider}封面通道未配置，不能启用。`:'';
  const batches=state.authorized_render_batches||[];
  const batchScope=batches.length?` 另有 ${batches.length} 个已授权逐帧重制批次，按原录播日期新到旧优先投稿；仍受高置信、响度和去重检查。`:'';
  $('#publishControlScope').textContent=deployment || (active?'范围：首次启用之后完成的新高置信成片；暂停期间完成的成片不自动补投。'+batchScope:paused?'不启动新生成或新上传；已提交任务继续查询，原队列保留。':'目前只放行测试清单，不处理其他新成片。点击启用后，才开始接收新完成的合格成片。');
  const format=value=>new Date(value*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
  $('#publishControlTime').textContent=[state.cutover?`首次启用时间（上海）：${format(state.cutover)}`:'尚未正式启用',state.paused_at?`暂停时间：${format(state.paused_at)}`:state.enabled_at && state.enabled_at!==state.cutover?`最近启用时间：${format(state.enabled_at)}`:''].filter(Boolean).join(' · ');
  $('#publishPauseAcceptance').hidden=state.mode!=='acceptance';
  $('#publishPauseAcceptance').disabled=publishControlSaving;
}

async function changePublishControl(enabled) {
  if (!publishControl || publishControlSaving) return;
  const message=enabled?'启用新成片自动投稿？\n只处理启用后的合格成片，不自动补投历史或暂停期间成片；原队列恢复。会产生 AI 费用并真实投稿 B 站。':'暂停自动投稿？\n不再启动新的生成或上传；已经发出的请求及已提交上传不会取消，仍会跟踪结果。';
  if (!confirm(message)) return;
  publishControlSaving=true; renderPublishControl(publishControl);
  try {
    renderPublishControl(await api('/api/publish-v2/control',{method:'POST',body:JSON.stringify({enabled})}));
    toast(enabled?'新成片自动投稿已开启，历史库存不补投':'自动投稿已暂停，已提交任务继续跟踪');
  } catch(e) {
    toast(e.message);
    try {renderPublishControl(await api('/api/publish-v2/control'));} catch(_) {}
  } finally {publishControlSaving=false;renderPublishControl(publishControl);}
}

async function loadPublishJobs() {
  const [data,legacy,control]=await Promise.all([api('/api/song-projects?limit=100'),api('/api/publish-jobs?limit=200'),api('/api/publish-v2/control')]);
  renderPublishControl(control);
  $('#publishJobList').innerHTML=(data.items||[]).map(song=>{
    const job=song.publish_job, base=`/api/song-projects/${encodeURIComponent(song.id)}/cover`, performances=song.performances||[];
    const status=job?(job.status==='completed' && job.collection_status && job.collection_status!=='joined'?(job.collection_status==='failed'?'上传完成 · 合集失败':'上传完成 · 合集待完成'):publishJobStatus[job.status]||job.status):'尚未放行';
    const coverLimit=Number(control.cover_max_attempts)||0;
    const retry=job?.pipeline_version===2 && job.status==='failed' && !job.bililive_task_id && !job.aid && !job.bvid && !job.submit_attempts && (song.cover_path||song.cover_attempts<coverLimit);
    return `<div class="automation-run">${publishCollectionInfo(job)}<div class="automation-run-head"><b>${esc(song.streamer)}《${esc(song.identified_title)}》</b><span class="automation-status ${job?.status==='completed'?'completed':song.conflict||job?.status==='failed'?'failed':'running'}">${esc(status)}</span></div>${song.cover_path?`<a href="${base}?original=true" target="_blank" rel="noopener"><img src="${base}" loading="lazy" alt="AI封面" style="width:100%;max-width:480px;border-radius:8px"></a>`:''}<small>标题 ${Number(job?.title_generation?.attempts ?? (job?.title_generation?.requested_model?1:0))}/${Number(control.title_max_attempts)||'—'} 次 · ${esc(job?.title_generation?.source==='ai'?'AI标题':job?.title_generation?.retry_pending?'等待标题重试':'固定标题兜底')}</small><small>生图 ${song.cover_attempts}/${coverLimit||'—'} 次 · AI文字未自动核对${song.conflict?' · 身份冲突，暂停自动处理':''}</small>${song.reference_json?`<a href="${base}?reference=true" target="_blank" rel="noopener">参考帧</a> · `:''}<a href="/api/song-projects/${encodeURIComponent(song.id)}" target="_blank" rel="noopener">详情与请求快照</a>${job?`<p>${esc(job.title||'等待生成标题')}</p><details><summary>模板简介 / 标签</summary><p style="white-space:pre-wrap">${esc(job.description||'尚未准备')}</p><small>${esc(JSON.stringify(job.tags||[]))}</small></details><small>上传 ${Math.round(job.upload_progress||0)}%${job.bililive_task_id?' · '+esc(job.bililive_task_id):''}</small>${job.bvid?`<a target="_blank" rel="noopener" href="https://www.bilibili.com/video/${encodeURIComponent(job.bvid)}">${esc(job.bvid)}</a>`:''}<small>${esc(job.review_state_desc||'')}${job.aid?' · AID '+esc(job.aid):''}</small>`:''}<details><summary>关联演唱 ${performances.length} 次</summary>${performances.map(p=>`<small>${esc(p.identified_title)} · ${esc(p.reason||'投稿候选')} · ${esc(p.source_job_id)}</small>`).join('')}</details>${song.cover_error||job?.publish_error?`<small class="publish-error">${esc(job?.status==='completed'?'审核查询异常':job?.failure_stage==='upload'||job?.failure_stage==='submit'?'上传失败':'准备失败')}：${esc(job?.publish_error||song.cover_error)}</small>`:''}${retry?`<button data-job-retry="${esc(job.id)}">重试准备（保留成功封面）</button>`:''}</div>`;
  }).join('') || '<p class="muted">暂无歌曲项目。</p>';
  const old=(legacy.items||[]).filter(job=>job.pipeline_version!==2);
  $('#publishJobList').insertAdjacentHTML('beforeend',`<details><summary>隔离的旧投稿记录 ${old.length} 条（不会自动运行）</summary>${old.map(j=>`<small>${esc(j.streamer)}《${esc(j.identified_title)}》 · ${esc(publishJobStatus[j.status]||j.status)}</small>`).join('')}</details>`);
  $$('#publishJobList [data-job-retry]').forEach(button=>button.onclick=async()=>{
    try {await api(`/api/publish-jobs/${encodeURIComponent(button.dataset.jobRetry)}/retry`,{method:'POST',body:'{}'});toast('已重新排队，成功封面不会清空');await loadPublishJobs();}catch(e){toast(e.message);}
  });
}
async function refreshPublish() {
  const [profiles,presets,fonts]=await Promise.all([api('/api/automation/profiles'),api('/api/publish-presets').catch(e=>({items:[],error:e.message})),api('/api/fonts')]);
  publishProfiles=profiles.profiles||[];publishPresets=presets.items||[];publishPresetError=presets.error||'';publishFonts=fonts.fonts||[];
  renderPublishStreamers();renderPublishFonts();await loadPublishJobs();
}
function openPublish() {
  if (publishInitialized) {loadPublishJobs().catch(e=>toast(e.message));return;}
  if (publishLoading)return;
  publishLoading=refreshPublish().then(()=>{publishInitialized=true;}).catch(e=>toast(e.message)).finally(()=>{publishLoading=null;});
}
$('#showPublish').onclick=()=>showWorkspace('publish');
$('#publishRefresh').onclick=()=>refreshPublish().catch(e=>toast(e.message));
$('#publishAutoToggle').onclick=()=>changePublishControl(publishControl?.rollout?.mode!=='active');
$('#publishPauseAcceptance').onclick=()=>changePublishControl(false);
$('#publishFontUpload').onchange=event=>{uploadPublishFont(event.target.files[0]);event.target.value='';};
setInterval(()=>{if(publishInitialized&&!$('#publishPage').hidden)loadPublishJobs().catch(()=>{});},15000);
