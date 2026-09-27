/* Folia Tempera image controls. Each project owns an independent image library. */
window.createTemperaImageControls = function createTemperaImageControls(onChange, showMessage) {
  const box = document.querySelector('#temperaImageControls');
  const library = box.querySelector('#temperaImageLibrary');
  const selected = box.querySelector('#temperaImageSelected');
  const depth = box.querySelector('#temperaImageDepth');
  const frequency = box.querySelector('#temperaImageFrequency');
  const frequencyOut = box.querySelector('#temperaImageFrequencyOut');
  let projectId = null;
  let images = [];
  let pool = [];
  let loadVersion = 0;
  const escapeHtml = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const imageUrl = id => `/images/${projectId}/${id}`;

  function repaint() {
    frequencyOut.textContent = `${Math.round(Number(frequency.value) * 100)}%`;
    library.innerHTML = '';
    for (const image of images) {
      const card = document.createElement('div');
      card.className = 'tempera-image-card';
      card.innerHTML = `<img src="${imageUrl(image.id)}" alt=""><span title="${escapeHtml(image.name)}">${escapeHtml(image.name)}</span><div class="tempera-image-actions"><button class="add" type="button">加入</button><button class="delete" type="button" title="从当前项目永久删除">删除</button></div>`;
      const add = card.querySelector('.add');
      add.disabled = pool.some(item => item.id === image.id) || pool.length >= 16;
      add.textContent = pool.some(item => item.id === image.id) ? '已选' : '加入';
      add.onclick = () => {
        pool.push({id:image.id,name:image.name,align:'free',verticalAlign:'bottom',scale:0.7,opacity:1});
        repaint(); onChange();
      };
      card.querySelector('.delete').onclick = () => removeImage(image);
      library.append(card);
    }
    if (!images.length) library.textContent = projectId ? '当前项目尚未上传图片' : '请先选择视频项目';
    selected.innerHTML = '';
    pool.forEach((item, index) => {
      const row = document.createElement('div');
      row.className = 'tempera-image-row';
      row.innerHTML = `<img src="${imageUrl(item.id)}" alt=""><div><b>${escapeHtml(item.name || item.id.slice(0,12))}</b><div class="tempera-image-grid"><label>水平<select class="horizontal"><option value="free">自由</option><option value="left">左</option><option value="center">中</option><option value="right">右</option></select></label><label>垂直<select class="vertical"><option value="bottom">下</option><option value="top">上</option><option value="center">中</option><option value="free">自由</option></select></label><label>大小 <output class="size-out"></output><input class="size" type="range" min="10" max="150" value="${Math.round(item.scale * 100)}"></label><label>透明度 <output class="opacity-out"></output><input class="opacity" type="range" min="0" max="100" value="${Math.round(item.opacity * 100)}"></label></div><button class="remove sub" type="button">从本片移出</button></div>`;
      const horizontal = row.querySelector('.horizontal');
      const vertical = row.querySelector('.vertical');
      horizontal.value = item.align;
      vertical.value = item.verticalAlign;
      horizontal.onchange = () => { item.align = horizontal.value; onChange(); };
      vertical.onchange = () => { item.verticalAlign = vertical.value; onChange(); };
      const size = row.querySelector('.size');
      const opacity = row.querySelector('.opacity');
      const updateLabels = () => {
        row.querySelector('.size-out').textContent = `${size.value}%`;
        row.querySelector('.opacity-out').textContent = `${opacity.value}%`;
      };
      updateLabels();
      size.oninput = () => { item.scale = Number(size.value) / 100; updateLabels(); onChange(); };
      opacity.oninput = () => { item.opacity = Number(opacity.value) / 100; updateLabels(); onChange(); };
      row.querySelector('.remove').onclick = () => { pool.splice(index, 1); repaint(); onChange(); };
      selected.append(row);
    });
    if (!pool.length) selected.textContent = '当前项目未选图片';
    box.querySelector('#temperaImageCount').textContent = `${pool.length}/16`;
  }

  async function loadLibrary() {
    if (!projectId) return;
    const jid = projectId;
    const version = ++loadVersion;
    const response = await fetch(`/api/jobs/${jid}/folia-images`);
    if (!response.ok) throw Error('当前项目图片库读取失败');
    const result = await response.json();
    if (jid === projectId && version === loadVersion) {
      images = result.images || [];
      repaint();
    }
  }
  async function upload() {
    const jid = projectId;
    if (!jid) return showMessage('请先选择视频项目');
    const input = box.querySelector('#temperaImageFile');
    const file = input.files[0];
    if (!file) return showMessage('请选择 PNG、JPEG 或 WebP 图片');
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`/api/jobs/${jid}/folia-images`, {method:'POST',body:form});
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw Error(result.detail || '图片上传失败');
    if (jid !== projectId) return;
    input.value = '';
    await loadLibrary();
    if (!pool.some(item => item.id === result.id) && pool.length < 16) {
      pool.push({id:result.id,name:result.name,align:'free',verticalAlign:'bottom',scale:0.7,opacity:1});
      repaint(); onChange();
    }
    showMessage('图片已加入当前项目');
  }
  async function removeImage(image) {
    const jid = projectId;
    if (!jid || !window.confirm(`从当前项目永久删除「${image.name}」？`)) return;
    try {
      const response = await fetch(`/api/jobs/${jid}/folia-images/${image.id}`, {method:'DELETE'});
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw Error(result.detail || '删除失败');
      if (jid !== projectId) return;
      pool = pool.filter(item => item.id !== image.id);
      images = images.filter(item => item.id !== image.id);
      repaint(); onChange();
      showMessage('已从当前项目删除图片');
    } catch (error) { showMessage(error.message); }
  }
  box.querySelector('#temperaImageUpload').onclick = () => upload().catch(error => showMessage(error.message));
  depth.onchange = onChange;
  frequency.oninput = () => { repaint(); onChange(); };
  repaint();
  return {
    async setProject(jid, tuning) {
      projectId = jid;
      images = [];
      pool = Array.isArray(tuning?.layerImages) ? tuning.layerImages.slice(0,16).map(item => ({...item})) : [];
      depth.value = tuning?.layerImageDepth === 'front' ? 'front' : 'back';
      frequency.value = Number.isFinite(Number(tuning?.layerImageFrequency)) ? tuning.layerImageFrequency : 0.6;
      repaint();
      await loadLibrary();
    },
    tuning() { return {layerImages:pool.map(item => ({...item})),layerImageDepth:depth.value,layerImageFrequency:Number(frequency.value)}; },
    setVisible(visible) { box.hidden = !visible; },
  };
};
