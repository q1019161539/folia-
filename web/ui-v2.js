(() => {
  const mobile = matchMedia('(max-width: 760px)');
  const $ = selector => document.querySelector(selector);
  const studio = $('#studioPage');
  const files = studio.querySelector('.files');
  const center = studio.querySelector('.center');
  const styles = studio.querySelector('.styles');
  const recognition = studio.querySelector('.recognition-panel');
  const preview = center.querySelector('.preview');

  const exportPanel = document.createElement('aside');
  exportPanel.className = 'panel export-panel';
  exportPanel.innerHTML = '<h3>输出成片</h3><p class="muted">使用当前歌词时间轴和画面效果</p>';
  const nativeOutput = document.createElement('section');
  nativeOutput.id = 'nativeOutputControls';
  const modeLabel = $('#renderOutputMode').closest('label');
  nativeOutput.append(modeLabel.previousElementSibling, modeLabel, $('#renderModeHint'));
  exportPanel.append(nativeOutput, $('#resolution').closest('label'), $('#render'), $('#cancelRender'), $('#output'));
  studio.append(exportPanel);
  const nativeControls = $('#foliaNativeControls');
  const syncNativeOutput = () => { nativeOutput.hidden = nativeControls.hidden; };
  new MutationObserver(syncNativeOutput).observe(nativeControls, {attributes:true,attributeFilter:['hidden']});
  syncNativeOutput();

  const overview = document.createElement('aside');
  overview.className = 'panel automation-overview';
  overview.innerHTML = '<h3>当前队列</h3>';
  overview.append($('#automationQueue'));
  $('#automationPage').prepend(overview);

  const savedSteps = (() => { try { return JSON.parse(sessionStorage.getItem('folia-mobile-steps') || '{}'); } catch { return {}; } })();
  const steps = [];
  function makeStep(element, key, title, number, defaultOpen) {
    element.classList.add('mobile-step');
    element.dataset.step = key;
    const body = document.createElement('div');
    body.className = 'step-body';
    body.id = `step-${key}-body`;
    while (element.firstChild) body.append(element.firstChild);
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'step-toggle';
    toggle.setAttribute('aria-controls', body.id);
    toggle.innerHTML = `<span class="step-number">${number}</span><span class="step-title">${title}</span><span class="step-chevron" aria-hidden="true">⌄</span>`;
    element.append(toggle, body);
    const state = {element,body,toggle,key,open:savedSteps[key] ?? defaultOpen};
    steps.push(state);
    toggle.onclick = () => { state.open = !state.open; syncSteps(); };
    return state;
  }
  makeStep(files, 'files', '选择视频', '01', true);
  const lyricsStep = makeStep(center, 'lyrics', '歌词与预览', '02', true);
  const effectsStep = makeStep(styles, 'effects', '画面效果', '03', false);
  makeStep(exportPanel, 'export', '导出视频', '04', false);

  const savedPanels = (() => { try { return JSON.parse(sessionStorage.getItem('folia-collapsible-panels') || '{}'); } catch { return {}; } })();
  const panels = [];
  function makePanel(element, key, {stepHeader=false, defaultOpen=true}={}) {
    const host = element.classList.contains('mobile-step') ? element.querySelector(':scope > .step-body') : element;
    const bar = host.querySelector(':scope > .bar, :scope > .automation-heading, :scope > .clip-heading');
    const title = bar ? bar.querySelector('h3, strong') : host.querySelector(':scope > h3');
    if (!title) return;
    const heading = bar || title;
    const content = document.createElement('div');
    content.className = 'panel-content';
    content.id = `panel-${key}-content`;
    while (heading.nextSibling) content.append(heading.nextSibling);
    host.append(content);
    const label = title.textContent.trim();
    title.textContent = '';
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'panel-collapse-toggle';
    toggle.setAttribute('aria-controls', content.id);
    toggle.innerHTML = `<span>${label}</span><span class="panel-collapse-chevron" aria-hidden="true">⌄</span>`;
    title.append(toggle);
    const state = {element,content,toggle,key,stepHeader,open:savedPanels[key] ?? defaultOpen};
    toggle.onclick = () => { state.open = !state.open; syncPanels(); };
    panels.push(state);
  }
  makePanel(files, 'files', {stepHeader:true});
  makePanel(recognition, 'recognition');
  makePanel(preview, 'preview');
  makePanel(center.querySelector('.song-panel'), 'song');
  makePanel(center.querySelector('.timeline-panel'), 'timeline');
  makePanel(styles, 'styles', {stepHeader:true});
  makePanel(exportPanel, 'export', {stepHeader:true});
  makePanel($('#clipPage .clip-source'), 'clip-source');
  makePanel($('#clipPage .clip-editor'), 'clip-editor');
  makePanel($('#clipPage .clip-progress-panel'), 'clip-progress');
  makePanel($('#automationPage .automation-browser'), 'automation-browser');
  makePanel($('#automationPage .automation-profiles'), 'automation-profiles');
  makePanel(overview, 'automation-queue');
  makePanel($('#automationPage .automation-runs'), 'automation-runs');
  makePanel($('#publishPage .publish-streamers'), 'publish-streamers');
  makePanel($('#publishPage .publish-fonts'), 'publish-fonts');
  makePanel($('#publishPage .publish-jobs'), 'publish-jobs');
  function syncPanels() {
    for (const panel of panels) {
      const shown = panel.open || (mobile.matches && panel.stepHeader);
      panel.content.hidden = !shown;
      panel.toggle.setAttribute('aria-expanded', String(shown));
      panel.element.classList.toggle('panel-collapsed', !shown);
    }
    try { sessionStorage.setItem('folia-collapsible-panels', JSON.stringify(Object.fromEntries(panels.map(panel => [panel.key,panel.open])))); } catch {}
  }
  syncPanels();
  function syncSteps() {
    if (mobile.matches) {
      if (recognition.parentElement !== steps[0].body) steps[0].body.append(recognition);
      if (effectsStep.open && preview.parentElement !== effectsStep.body) effectsStep.body.prepend(preview);
      if (!effectsStep.open && preview.parentElement !== lyricsStep.body) lyricsStep.body.prepend(preview);
    } else {
      if (recognition.parentElement !== studio) studio.insertBefore(recognition, styles);
      if (preview.parentElement !== lyricsStep.body) lyricsStep.body.prepend(preview);
    }
    for (const step of steps) {
      step.body.hidden = mobile.matches && !step.open;
      step.toggle.setAttribute('aria-expanded', String(step.open));
      step.element.classList.toggle('step-open', step.open);
    }
    try { sessionStorage.setItem('folia-mobile-steps', JSON.stringify(Object.fromEntries(steps.map(step => [step.key,step.open])))); } catch {}
  }

  const navIcons = {showStudio:'♫',showClips:'✂',showAutomation:'◉',showPublish:'↑'};
  for (const [id,icon] of Object.entries(navIcons)) {
    const button = $('#'+id),label = button.textContent;
    button.innerHTML = `<span class="workspace-icon" aria-hidden="true">${icon}</span><span class="workspace-label">${label}</span>`;
  }

  mobile.addEventListener('change', () => {
    if (mobile.matches && document.body.dataset.workspace === 'transcriber') showWorkspace('studio');
    syncSteps();
    syncPanels();
  });
  syncSteps();

  function setupMore(selector, limit) {
    const list = $(selector);
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'list-more';
    list.after(button);
    let expanded = false;
    const update = () => {
      const extra = Math.max(0, list.children.length - limit);
      button.hidden = !extra;
      button.textContent = expanded ? '收起列表' : `显示更多（${extra}）`;
      list.classList.toggle('list-collapsed', !expanded && !!extra);
    };
    button.onclick = () => { expanded = !expanded; update(); };
    new MutationObserver(update).observe(list, {childList:true});
    update();
  }
  setupMore('#clipFileList', 12);
  setupMore('#automationRunList', 10);

  document.addEventListener('focusin', event => {
    if (event.target.matches('input,select,textarea,[contenteditable="true"]')) document.body.classList.add('keyboard-active');
  });
  document.addEventListener('focusout', () => setTimeout(() => {
    if (!document.activeElement?.matches('input,select,textarea,[contenteditable="true"]')) document.body.classList.remove('keyboard-active');
  }, 100));

  let workspace = 'studio';
  try { workspace = sessionStorage.getItem('folia-workspace') || 'studio'; } catch {}
  if (mobile.matches && workspace === 'transcriber') workspace = 'studio';
  if (!['studio','clips','transcriber','automation','publish'].includes(workspace)) workspace = 'studio';
  showWorkspace(workspace);
})();
