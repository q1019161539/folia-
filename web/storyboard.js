/* Read-only visual index for the selected source. Preview and exports still use the saved alignment. */
(() => {
  const video = document.querySelector('#video');
  const strip = document.querySelector('.filmstrip');
  const frames = document.querySelector('#filmstripFrames');
  const lyrics = document.querySelector('#filmstripLyrics');
  const empty = document.querySelector('#filmstripEmpty');
  const playhead = document.createElement('i');
  playhead.className = 'filmstrip-playhead';
  playhead.setAttribute('aria-hidden', 'true');
  strip.append(playhead);
  let generation = 0;
  const thumbnailObserver = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      thumbnailObserver.unobserve(entry.target);
      const node = entry.target;
      const icon = node.querySelector('.file-icon');
      if (icon && node.dataset.fileId) loadThumbnail(node.dataset.fileId, 1000, icon, () => node.isConnected);
    }
  }, {rootMargin: '120px'});

  async function loadThumbnail(id, atMs, host, stillCurrent) {
    const url = `/api/media/${encodeURIComponent(id)}/thumbnail?at_ms=${atMs}`;
    host.classList.add('thumbnail-loading');
    for (let attempt = 0; attempt < 35 && stillCurrent(); attempt++) {
      try {
        const response = await fetch(url);
        if (response.status === 202) {
          await new Promise(resolve => setTimeout(resolve, 1800));
          continue;
        }
        if (!response.ok) break;
        const blob = await response.blob();
        if (!stillCurrent()) return;
        const image = document.createElement('img');
        image.alt = '';
        image.src = URL.createObjectURL(blob);
        image.onload = () => URL.revokeObjectURL(image.src);
        host.replaceChildren(image);
        host.classList.remove('thumbnail-loading');
        host.classList.add('thumbnail-ready');
        return;
      } catch { break; }
    }
    host.classList.remove('thumbnail-loading');
    host.classList.add('thumbnail-failed');
  }

  const fileList = document.querySelector('#fileList');
  function observeFiles() {
    for (const item of fileList.querySelectorAll('.file.file[data-file-id]')) {
      if (!item.dataset.thumbnailObserved) {
        item.dataset.thumbnailObserved = '1';
        thumbnailObserver.observe(item);
      }
    }
  }
  new MutationObserver(observeFiles).observe(fileList, {childList:true});
  observeFiles();

  function frameCount() { return innerWidth <= 390 ? 5 : innerWidth <= 760 ? 6 : innerWidth <= 1160 ? 8 : 12; }
  function draw() {
    const current = ++generation;
    const duration = Number(video.duration);
    const file = typeof selected === 'object' ? selected : null;
    if (!file?.id || !Number.isFinite(duration) || duration <= 0) {
      frames.replaceChildren(); lyrics.replaceChildren();
      empty.hidden = false; playhead.hidden = true;
      return;
    }
    empty.hidden = true; playhead.hidden = false;
    const count = frameCount();
    frames.style.setProperty('--frame-count', count);
    frames.replaceChildren(); lyrics.replaceChildren();
    for (let index = 0; index < count; index++) {
      // Every viewport reuses one of the same 12 source positions.
      const sample = Math.floor((index + .5) * 12 / count);
      const atMs = Math.max(0, Math.round(duration * 1000 * (sample + .5) / 12));
      const frame = document.createElement('span');
      frame.className = 'filmstrip-frame thumbnail-loading';
      frame.title = fmt(atMs);
      frame.dataset.time = fmt(atMs);
      frames.append(frame);
      loadThumbnail(file.id, atMs, frame, () => current === generation && frame.isConnected);
    }
    const saved = (typeof previewLines === 'object' ? previewLines : [])
      .filter(line => !line.deleted && line.text && line.status !== 'asr')
      .sort((a,b) => a.start_ms - b.start_ms);
    if (!saved.length) {
      const note = document.createElement('span');
      note.className = 'filmstrip-note';
      note.textContent = '尚无已保存的逐句歌词';
      lyrics.append(note);
    } else {
      for (const line of saved) {
        const start = Math.max(0, Number(line.start_ms) + previewOffset);
        const end = Math.min(duration * 1000, Number(line.end_ms) + previewOffset);
        if (end <= start) continue;
        const segment = document.createElement('span');
        segment.className = 'filmstrip-segment';
        segment.style.left = `${100 * start / (duration * 1000)}%`;
        segment.style.width = `${Math.max(.3, 100 * (end - start) / (duration * 1000))}%`;
        segment.textContent = line.text;
        segment.title = `${fmt(start)}–${fmt(end)} ${line.text}`;
        lyrics.append(segment);
      }
    }
    syncFilmstripPlayhead();
  }

  window.refreshFilmstrip = draw;
  window.syncFilmstripPlayhead = () => {
    const duration = Number(video.duration);
    if (!Number.isFinite(duration) || duration <= 0) return;
    playhead.style.left = `${Math.max(0, Math.min(100, video.currentTime / duration * 100))}%`;
  };
  function seekFromPointer(event) {
    const rect = strip.getBoundingClientRect();
    if (!Number.isFinite(video.duration) || video.duration <= 0 || rect.width <= 0) return;
    video.currentTime = Math.max(0, Math.min(video.duration, (event.clientX - rect.left) / rect.width * video.duration));
    syncFilmstripPlayhead();
  }
  strip.addEventListener('click', seekFromPointer);
  strip.tabIndex = 0;
  strip.setAttribute('role', 'slider');
  strip.setAttribute('aria-label', '视频缩略图时间条，左右方向键定位');
  strip.addEventListener('keydown', event => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    video.currentTime = Math.max(0, Math.min(video.duration || 0, video.currentTime + (event.key === 'ArrowRight' ? 5 : -5)));
    syncFilmstripPlayhead();
  });
  video.addEventListener('loadedmetadata', draw);
  video.addEventListener('timeupdate', syncFilmstripPlayhead);
  addEventListener('resize', () => {
    if (frames.children.length !== frameCount()) draw();
  });
})();
