// static/js/reader.js
(function () {
  const { type, source, content_id, current_chapter } = window.readerData;

  let chaptersList       = [];
  let currentChapterIndex = -1;
  let currentChapterNum  = current_chapter;
  let progressInterval   = null;

  // ── Elementos DOM ──────────────────────────────────────────────────────
  const mediaContainer    = document.getElementById('media-content');
  const chapterWrapper    = document.getElementById('chapter-wrapper');
  const prevBtn           = document.getElementById('prev-btn');
  const nextBtn           = document.getElementById('next-btn');
  const fullscreenBtn     = document.getElementById('fullscreen-btn');
  const controlsDiv       = document.getElementById('controls');
  const chapterLabelNum   = document.getElementById('current-chapter-num');
  const backBtn           = document.getElementById('back-to-serie');

  // ── Helpers de UI ──────────────────────────────────────────────────────
  const UI_ELS = [controlsDiv, fullscreenBtn, backBtn].filter(Boolean);

  function showUI() {
    UI_ELS.forEach(el => el.classList.add('show'));
  }
  function hideUI() {
    UI_ELS.forEach(el => el.classList.remove('show'));
  }

  // ── Label del capítulo ─────────────────────────────────────────────────
  function updateChapterLabel() {
    if (chapterLabelNum) chapterLabelNum.textContent = currentChapterNum;
    if (prevBtn) prevBtn.disabled = currentChapterIndex <= 0;
    if (nextBtn) nextBtn.disabled = currentChapterIndex >= chaptersList.length - 1;
    if (window.animateChapterLabel) window.animateChapterLabel();
  }

  // ── Capítulos vistos ───────────────────────────────────────────────────
  async function markCurrentAsWatched() {
    if (source !== 'local') return;
    try {
      await fetch('/api/watched', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ content_ref: `local:${content_id}`, chapter: currentChapterNum }),
      });
    } catch (e) { console.warn('markCurrentAsWatched:', e); }
  }

  // ── Carga de capítulos ─────────────────────────────────────────────────
  async function loadChaptersList() {
    try {
      const url = source === 'local'
        ? `/api/chapters/local/${type}/${content_id}`
        : `/api/chapters/${type}/${source}/${content_id}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error('No se pudo obtener la lista de capítulos');
      chaptersList = await res.json();

      currentChapterIndex = chaptersList.findIndex(ch => String(ch.number) === String(current_chapter));
      if (currentChapterIndex === -1 && chaptersList.length) currentChapterIndex = 0;
      if (currentChapterIndex >= 0) currentChapterNum = chaptersList[currentChapterIndex].number;

      updateChapterLabel();
      loadCurrentChapter();
    } catch (err) {
      console.error(err);
      if (chapterWrapper) chapterWrapper.innerHTML =
        `<div style="color:var(--accent2); text-align:center; padding:20px;">
           Error al cargar capítulos: ${err.message}
         </div>`;
    }
  }

  // ── Cargar capítulo actual (con transición si está disponible) ─────────
  function loadCurrentChapter() {
    if (progressInterval) { clearInterval(progressInterval); progressInterval = null; }

    const doLoad = () => {
      if (chapterWrapper) chapterWrapper.innerHTML = `
        <div style="display:flex; align-items:center; justify-content:center; width:100%; height:100%;">
          <div class="loading-spinner"></div>
        </div>`;
      if (type === 'anime') loadAnimeChapter();
      else                  loadMangaChapter();
    };

    // Usar la transición del reader.html si está disponible
    if (window.chapterTransition) {
      window.chapterTransition(doLoad);
    } else {
      doLoad();
    }

    showUI();
  }

  // ── Navegación ─────────────────────────────────────────────────────────
  function prevChapter() {
    if (currentChapterIndex <= 0) return;
    currentChapterIndex--;
    currentChapterNum = chaptersList[currentChapterIndex].number;
    updateChapterLabel();
    loadCurrentChapter();
  }

  function nextChapter() {
    if (currentChapterIndex >= chaptersList.length - 1) return;
    markCurrentAsWatched();  // marcar antes de avanzar
    currentChapterIndex++;
    currentChapterNum = chaptersList[currentChapterIndex].number;
    updateChapterLabel();
    loadCurrentChapter();
  }

  // ── Anime ──────────────────────────────────────────────────────────────
  async function loadAnimeChapter() {
    const videoUrl = source === 'local'
      ? `/api/play/local/anime/${content_id}/${currentChapterNum}`
      : `/api/play/anime/${source}/${content_id}/${currentChapterNum}`;

    let savedTime = 0;
    let duration  = 0;
    let hasMarked = false;

    // Progreso guardado
    try {
      const res  = await fetch(`/api/progress/${type}/${source}/${content_id}`);
      const prog = await res.json();
      if (String(prog.chapter) === String(currentChapterNum) && prog.progress)
        savedTime = parseInt(prog.progress);
    } catch (e) { console.warn(e); }

    // Duración (solo local)
    if (source === 'local') {
      try {
        const res = await fetch(`/api/video-duration/anime/${content_id}/${currentChapterNum}`);
        if (res.ok) ({ duration } = await res.json());
      } catch (e) { console.warn(e); }
    }

    if (chapterWrapper) chapterWrapper.innerHTML = `
      <video id="anime-video" controls autoplay
             style="width:100%; height:100%; object-fit:contain;">
        <source src="${videoUrl}" type="video/mp4">
      </video>`;

    const video = document.getElementById('anime-video');
    if (!video) return;

    if (savedTime > 0)
      video.addEventListener('loadedmetadata', () => { video.currentTime = savedTime; }, { once: true });

    // Guardar progreso cada 2s
    progressInterval = setInterval(() => {
      const t = Math.floor(video.currentTime);
      fetch(`/api/progress/${type}/${source}/${content_id}`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ chapter: currentChapterNum, progress: t }),
      }).catch(console.error);

      if (!hasMarked && duration > 0 && t >= duration * 0.99) {
        hasMarked = true;
        markCurrentAsWatched();
      }
    }, 2000);

    video.addEventListener('ended', () => {
      if (!hasMarked) { hasMarked = true; markCurrentAsWatched(); }
      if (currentChapterIndex < chaptersList.length - 1) nextChapter();
    });
  }

  // ── Manga ──────────────────────────────────────────────────────────────
  async function loadMangaChapter() {
    if (source !== 'local') {
      if (chapterWrapper) chapterWrapper.innerHTML =
        `<div style="color:var(--accent2); text-align:center; padding:20px;">
           El visor de manga solo funciona con capítulos descargados localmente.
         </div>`;
      return;
    }

    try {
      const imgRes = await fetch(`/api/play/local/manga/${content_id}/${currentChapterNum}`);
      if (!imgRes.ok) throw new Error('No se pudieron cargar las imágenes');
      const relPaths = await imgRes.json();

      if (!relPaths.length) {
        if (chapterWrapper) chapterWrapper.innerHTML =
          `<div style="color:var(--muted); text-align:center; padding:20px;">
             No hay imágenes en este capítulo.
           </div>`;
        return;
      }

      const imageUrls = relPaths.map(p => `/api/manga/images/${p}`);
      if (chapterWrapper) chapterWrapper.innerHTML = `
        <div id="manga-viewer"
             style="width:100%; height:100%; overflow-y:auto;
                    display:flex; flex-direction:column; align-items:center;">
          ${imageUrls.map((url, i) =>
            `<img src="${url}" data-index="${i}"
                  style="max-width:100%; display:block;" loading="lazy">`
          ).join('')}
        </div>`;

      const viewerDiv = document.getElementById('manga-viewer');
      if (!viewerDiv) return;

      // Restaurar posición de scroll guardada
      let savedIndex = null;
      try {
        const res  = await fetch(`/api/progress/local/manga/${content_id}`);
        const prog = await res.json();
        if (String(prog.chapter) === String(currentChapterNum) && prog.progress) {
          const idx = parseInt(prog.progress);
          if (!isNaN(idx)) savedIndex = idx;
        }
      } catch (e) { console.warn(e); }

      const images = viewerDiv.querySelectorAll('img');

      // Esperar carga de imágenes para scroll correcto
      await Promise.all(Array.from(images).map(img =>
        img.complete ? Promise.resolve()
                     : new Promise(r => { img.onload = r; img.onerror = r; })
      ));

      if (savedIndex !== null && images[savedIndex])
        images[savedIndex].scrollIntoView({ behavior: 'auto', block: 'start' });

      // Guardar índice visible en scroll (debounced)
      let saveTimeout;
      const saveProgress = () => {
        const viewerRect = viewerDiv.getBoundingClientRect();
        let closestIdx = 0, closestDist = Infinity;
        images.forEach((img, i) => {
          const d = Math.abs(img.getBoundingClientRect().top - viewerRect.top);
          if (d < closestDist) { closestDist = d; closestIdx = i; }
        });
        fetch(`/api/progress/local/manga/${content_id}`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ chapter: currentChapterNum, progress: closestIdx }),
        }).catch(console.error);
      };

      viewerDiv.addEventListener('scroll', () => {
        clearTimeout(saveTimeout);
        saveTimeout = setTimeout(saveProgress, 500);
      });

      // Marcar como visto al llegar al 90% del scroll
      let hasMarked = false;
      viewerDiv.addEventListener('scroll', () => {
        if (hasMarked) return;
        const pct = (viewerDiv.scrollTop + viewerDiv.clientHeight) / viewerDiv.scrollHeight;
        if (pct >= 0.90) { hasMarked = true; markCurrentAsWatched(); }
      });

      window.addEventListener('beforeunload', saveProgress);

    } catch (err) {
      console.error(err);
      if (chapterWrapper) chapterWrapper.innerHTML =
        `<div style="color:var(--accent2); text-align:center; padding:20px;">
           Error: ${err.message}
         </div>`;
    }
  }

  // ── Pantalla completa ──────────────────────────────────────────────────
  // reader.html ya maneja toggleFullscreen; sincronizamos solo lo que JS
  // necesita internamente (fullscreen desde reader.js estaba roto porque
  // referenciaba 'reader-container' en lugar de 'reader-root').
  // El botón y las teclas ya están manejados en reader.html.

  // ── Inicializar ────────────────────────────────────────────────────────
  async function init() {
    await loadChaptersList();

    prevBtn?.addEventListener('click', prevChapter);
    nextBtn?.addEventListener('click', nextChapter);

    backBtn?.addEventListener('click', () => {
      window.location.href = `/serie/${type}/${source}/${content_id}`;
    });

    // Limpiar interval al salir
    window.addEventListener('beforeunload', () => {
      if (progressInterval) clearInterval(progressInterval);
    });

    showUI();
  }

  init();
})();