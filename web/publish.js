let publishInitialized = false, publishLoading = null;
let publishProfiles = [], publishPresets = [], publishPresetError = '', publishFonts = [], publishCovers = {};
const publishJobStatus = {pending:'等待准备',preparing:'准备中',ready:'已就绪',submitting:'提交中',uploading:'上传中',completed:'已完成',failed:'准备失败'};

function publishCoverFonts() {
  return [{id:'', label:'思源黑体（默认）'}, {id:'builtin-serif', label:'思源宋体'},
    ...publishFonts.filter(font => !font.builtin).map(font => ({id:font.id, label:font.label || font.family}))];
}

function publishPresetSummary(id) {
  const preset = publishPresets.find(item => item.id === id);
  if (!id) return '未选择模板时，这位主播的成片不会创建投稿准备任务。';
  if (!preset) return publishPresetError ? '模板暂时无法读取，已保存的选择不受影响。' : `已保存模板 ${id} 在 BililiveTool 中不存在，请重新选择。`;
  const text = String(preset.description || '').replace(/\s+/g, ' ');
  return text ? `简介：${text.slice(0, 90)}${text.length > 90 ? '…' : ''}` : '该模板没有简介，将使用 Folia 固定简介。';
}

function publishReadiness(profile) {
  const missing = [];
  if (!profile.bililive_preset_id) missing.push('投稿模板');
  if (!(publishCovers[profile.id] || []).length) missing.push('封面底图');
  return missing.length ? {ready:false, text:'缺' + missing.join('、')} : {ready:true, text:'已就绪'};
}

function renderPublishStreamer(profile) {
  const covers = publishCovers[profile.id] || [], state = publishReadiness(profile);
  const presetOptions = '<option value="">未选择</option>' + publishPresets.map(item => `<option value="${esc(item.id)}">${esc(item.name || item.id)}</option>`).join('')
    + (profile.bililive_preset_id && !publishPresets.some(item => item.id === profile.bililive_preset_id) ? `<option value="${esc(profile.bililive_preset_id)}">${esc(profile.bililive_preset_name || profile.bililive_preset_id)}（暂时无法读取）</option>` : '');
  const fontOptions = publishCoverFonts().map(font => `<option value="${esc(font.id)}">${esc(font.label)}</option>`).join('')
    + (profile.cover_font_id && !publishCoverFonts().some(font => font.id === profile.cover_font_id) ? `<option value="${esc(profile.cover_font_id)}">已删除的字体</option>` : '');
  const coverBase = `/api/automation/profiles/${encodeURIComponent(profile.id)}/covers`;
  return `<div class="publish-streamer" data-profile="${esc(profile.id)}">
    <div class="automation-card-head"><div><b>${esc(profile.publish_streamer || profile.name)}</b><small>${esc(profile.name)}${profile.recorder_identity?.room_id ? ' · 房间 ' + esc(profile.recorder_identity.room_id) : ''} · ${profile.enabled ? '监听中' : '已停用'}</small></div><span class="automation-status ${state.ready ? 'completed' : 'failed'}">${state.text}</span></div>
    <div class="publish-settings">
      <label>BililiveTool 投稿模板<select data-field="preset">${presetOptions}</select></label>
      <label>封面标题字体<select data-field="font">${fontOptions}</select></label>
    </div>
    <small class="publish-hint" data-preset-hint>${esc(publishPresetSummary(profile.bililive_preset_id))}</small>
    <button type="button" class="publish-save" data-save disabled>保存模板和字体</button>
    <div class="publish-cover-head"><strong>封面底图 · ${covers.length} 张</strong><label class="publish-upload">上传底图<input type="file" accept="image/png,image/jpeg,image/webp" multiple hidden data-cover-upload></label></div>
    <div class="publish-cover-grid">${covers.map(cover => `<figure class="publish-cover" data-cover="${esc(cover.id)}"><img loading="lazy" src="${coverBase}/${esc(cover.id)}" alt="${esc(cover.name)}"><figcaption>${esc(cover.name)} · ${cover.width}×${cover.height}</figcaption><button type="button" data-cover-preview title="用这张底图预览">预览</button><button type="button" class="danger" data-cover-delete title="删除这张底图">删除</button></figure>`).join('') || '<p class="muted">还没有封面底图。成片会因此准备失败，上传后可在右侧任务里重试。</p>'}</div>
    <div class="publish-preview"><input type="text" maxlength="60" placeholder="试用歌名，例如：离人赋" data-preview-title><button type="button" data-preview>生成封面预览</button></div>
    <img class="publish-preview-image" data-preview-image alt="封面预览" hidden>
  </div>`;
}

function renderPublishStreamers() {
  const list = $('#publishStreamerList');
  list.innerHTML = publishProfiles.map(renderPublishStreamer).join('') || '<p class="muted">还没有锁定的主播。请先在「自动流水线」里锁定主播。</p>';
  $('#publishPresetState').textContent = publishPresetError ? `BililiveTool 模板暂时无法读取：${publishPresetError}` : `BililiveTool 共 ${publishPresets.length} 个视频投稿模板`;
  for (const card of $$('#publishStreamerList .publish-streamer')) {
    const profile = publishProfiles.find(item => item.id === card.dataset.profile);
    const preset = card.querySelector('[data-field=preset]'), font = card.querySelector('[data-field=font]'), save = card.querySelector('[data-save]');
    preset.value = profile.bililive_preset_id; font.value = profile.cover_font_id;
    const dirty = () => { save.disabled = preset.value === profile.bililive_preset_id && font.value === profile.cover_font_id; card.querySelector('[data-preset-hint]').textContent = publishPresetSummary(preset.value); };
    preset.onchange = dirty; font.onchange = dirty;
    save.onclick = () => savePublishSettings(profile, preset.value, font.value, save);
    card.querySelector('[data-cover-upload]').onchange = event => uploadPublishCovers(profile, [...event.target.files]);
    card.querySelectorAll('[data-cover-delete]').forEach(button => button.onclick = () => deletePublishCover(profile, button.closest('[data-cover]').dataset.cover));
    card.querySelectorAll('[data-cover-preview]').forEach(button => button.onclick = () => previewPublishCover(card, profile, button.closest('[data-cover]').dataset.cover));
    card.querySelector('[data-preview]').onclick = () => previewPublishCover(card, profile, '');
  }
}

async function savePublishSettings(profile, presetId, fontId, button) {
  button.disabled = true;
  try {
    const saved = await api(`/api/automation/profiles/${encodeURIComponent(profile.id)}/publish`, {method:'PUT', body:JSON.stringify({bililive_preset_id:presetId, cover_font_id:fontId})});
    Object.assign(profile, {bililive_preset_id:saved.bililive_preset_id, bililive_preset_name:saved.bililive_preset_name, cover_font_id:saved.cover_font_id});
    toast(`已保存「${profile.publish_streamer || profile.name}」的投稿设置`);
    renderPublishStreamers();
  } catch (e) { button.disabled = false; toast(e.message); }
}

async function uploadPublishCovers(profile, files) {
  if (!files.length) return;
  let done = 0;
  for (const file of files) {
    const form = new FormData(); form.append('file', file);
    try {
      const response = await fetch(`/api/automation/profiles/${encodeURIComponent(profile.id)}/covers`, {method:'POST', body:form});
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw Error(result.detail || response.statusText);
      done++;
    } catch (e) { toast(`${file.name}：${e.message}`); }
  }
  await loadPublishCovers(profile.id);
  renderPublishStreamers();
  if (done) toast(`已上传 ${done} 张封面底图`);
}

async function deletePublishCover(profile, coverId) {
  if (!confirm('确定永久删除这张封面底图？已经准备好的投稿封面不受影响。')) return;
  try {
    await api(`/api/automation/profiles/${encodeURIComponent(profile.id)}/covers/${encodeURIComponent(coverId)}`, {method:'DELETE'});
    await loadPublishCovers(profile.id);
    renderPublishStreamers();
    toast('封面底图已删除');
  } catch (e) { toast(e.message); }
}

async function previewPublishCover(card, profile, coverId) {
  const title = card.querySelector('[data-preview-title]').value.trim() || '离人赋';
  const image = card.querySelector('[data-preview-image]');
  try {
    const response = await fetch(`/api/automation/profiles/${encodeURIComponent(profile.id)}/cover-preview`, {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({title, cover_id:coverId, cover_font_id:card.querySelector('[data-field=font]').value})});
    if (!response.ok) throw Error((await response.json().catch(() => ({}))).detail || response.statusText);
    if (image.src.startsWith('blob:')) URL.revokeObjectURL(image.src);
    image.src = URL.createObjectURL(await response.blob());
    image.hidden = false;
  } catch (e) { toast(e.message); }
}

function renderPublishFonts() {
  $('#publishFontList').innerHTML = publishFonts.map(font => `<div class="publish-font"><div><b>${esc(font.label || font.family)}</b><small>${font.builtin ? '内置字体' : `${esc(font.filename || '')} · ${(Number(font.size || 0) / 1048576).toFixed(1)} MB`}</small></div>${font.builtin ? '' : `<button type="button" class="danger" data-font-delete="${esc(font.id)}">删除</button>`}</div>`).join('');
  $$('#publishFontList [data-font-delete]').forEach(button => button.onclick = () => deletePublishFont(button.dataset.fontDelete));
}

function syncStudioFonts() {
  if (typeof foliaFonts === 'undefined' || typeof renderFonts !== 'function') return;
  foliaFonts = publishFonts;
  renderFonts($('#foliaFont')?.value);
}

async function reloadPublishFonts() {
  publishFonts = (await api('/api/fonts')).fonts || [];
  syncStudioFonts();
  renderPublishFonts();
  renderPublishStreamers();
}

async function uploadPublishFont(file) {
  if (!file) return;
  const form = new FormData(); form.append('file', file); form.append('family', '');
  try {
    const response = await fetch('/api/fonts', {method:'POST', body:form});
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw Error(result.detail || response.statusText);
    await reloadPublishFonts();
    toast(result.deduplicated ? `字体「${result.label}」已在库中` : `已添加字体「${result.label}」`);
  } catch (e) { toast(e.message); }
}

async function deletePublishFont(fontId) {
  const font = publishFonts.find(item => item.id === fontId);
  if (!confirm(`确定永久删除字体「${font?.label || fontId}」？`)) return;
  try {
    await api(`/api/fonts/${encodeURIComponent(fontId)}`, {method:'DELETE'});
    await reloadPublishFonts();
    toast('字体已删除');
  } catch (e) { toast(e.message); }
}

async function loadPublishCovers(profileId) {
  publishCovers[profileId] = (await api(`/api/automation/profiles/${encodeURIComponent(profileId)}/covers`)).covers || [];
}

async function loadPublishJobs() {
  const data = await api('/api/publish-jobs?limit=20');
  $('#publishJobState').textContent = data.auto_publish_enabled ? '自动上传已开启' : '自动上传未开启';
  $('#publishJobList').innerHTML = (data.items || []).map(job => `<div class="automation-run"><div class="automation-run-head"><b>${esc(job.identified_title || '未识别歌名')}</b><span class="automation-status ${job.status === 'ready' || job.status === 'completed' ? 'completed' : job.status === 'failed' ? 'failed' : 'running'}">${publishJobStatus[job.status] || job.status}</span></div><small>${esc(job.streamer)} · ${new Date(job.created_at * 1000).toLocaleString('zh-CN', {hour12:false})}${job.bvid ? ' · ' + esc(job.bvid) : ''}</small>${job.publish_error ? `<small class="publish-error">${esc(job.publish_error)}</small>` : ''}${job.status === 'failed' ? `<div class="automation-actions"><button type="button" data-job-retry="${esc(job.id)}">重新准备</button></div>` : ''}</div>`).join('') || '<p class="muted">还没有投稿准备任务。</p>';
  $$('#publishJobList [data-job-retry]').forEach(button => button.onclick = async () => {
    try { await api(`/api/publish-jobs/${encodeURIComponent(button.dataset.jobRetry)}/retry`, {method:'POST', body:'{}'}); toast('已重新排队准备'); await loadPublishJobs(); }
    catch (e) { toast(e.message); }
  });
}

async function refreshPublish() {
  const [profiles, presets, fonts] = await Promise.all([
    api('/api/automation/profiles'),
    api('/api/publish-presets').catch(e => ({items:[], error:e.message})),
    api('/api/fonts'),
  ]);
  publishProfiles = profiles.profiles || [];
  publishPresets = presets.items || []; publishPresetError = presets.error || '';
  publishFonts = fonts.fonts || [];
  await Promise.all(publishProfiles.map(profile => loadPublishCovers(profile.id)));
  renderPublishStreamers();
  renderPublishFonts();
  await loadPublishJobs();
}

function openPublish() {
  if (publishInitialized) { loadPublishJobs().catch(e => toast(e.message)); return; }
  if (publishLoading) return;
  publishLoading = refreshPublish().then(() => { publishInitialized = true; }).catch(e => toast(e.message)).finally(() => { publishLoading = null; });
}

$('#showPublish').onclick = () => showWorkspace('publish');
$('#publishRefresh').onclick = () => refreshPublish().catch(e => toast(e.message));
$('#publishFontUpload').onchange = event => { uploadPublishFont(event.target.files[0]); event.target.value = ''; };
