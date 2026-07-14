// static/js/reader.js
(function () {
  'use strict';

  const { type, source, content_id, current_chapter } = window.readerData;

  let chaptersList        = [];
  let currentChapterIndex = -1;
  let currentChapterNum   = current_chapter;
  let progressInterval    = null;
  var _unloadSaveHandler  = null;
  var _unloadClearHandler = null;

  // ── Elementos DOM ──────────────────────────────────────────────────────
  const mediaContainer  = document.getElementById('media-content');
  const chapterWrapper  = document.getElementById('chapter-wrapper');
  const prevBtn         = document.getElementById('prev-btn');
  const nextBtn         = document.getElementById('next-btn');
  const fullscreenBtn   = document.getElementById('fullscreen-btn');
  const controlsDiv     = document.getElementById('controls');
  const chapterLabelNum = document.getElementById('current-chapter-num');
  const backBtn         = document.getElementById('back-to-serie');

  const UI_ELS = [controlsDiv, fullscreenBtn, backBtn].filter(Boolean);
  function showUI() { UI_ELS.forEach(el => el.classList.add('show')); }

  // ── Player overlay helpers (anime) ─────────────────────────────────────
  const poPlayBtn    = document.getElementById('po-play');
  const poPlaySvg    = document.getElementById('po-play-svg');
  const poCenterBtn  = document.getElementById('po-center-play');
  const poCenterSvg  = document.getElementById('po-center-svg');
  const poProgress   = document.getElementById('po-progress');
  const poProgressPlayed = document.getElementById('po-progress-played');
  const poTime       = document.getElementById('po-time');
  const poSubs       = document.getElementById('po-subs');
  const poSpeed      = document.getElementById('po-speed');
  const poVolBtn     = document.getElementById('po-vol');
  const poVolSvg     = document.getElementById('po-vol-svg');
  const poVolSlider  = document.getElementById('po-vol-slider');
  const poChapterNum = document.getElementById('po-chapter-num');
  const poOverlay    = document.getElementById('player-overlay');

  // ── Label del capítulo ─────────────────────────────────────────────────
  function updateChapterLabel() {
    const text = String(currentChapterNum);
    if (chapterLabelNum) chapterLabelNum.textContent = text;
    if (poChapterNum)    poChapterNum.textContent    = text;
    if (prevBtn) prevBtn.disabled = currentChapterIndex <= 0;
    if (nextBtn) nextBtn.disabled = currentChapterIndex >= chaptersList.length - 1;
    if (window.animateChapterLabel) window.animateChapterLabel();
  }

  // ── Marcar visto ───────────────────────────────────────────────────────
  async function markCurrentAsWatched() {
    const ref = source === 'local' ? `local:${content_id}` : `${source}:${content_id}`;
    try {
      await api.post('/api/watched', { content_ref: ref, chapter: currentChapterNum });
    } catch (e) { 
      console.warn('markCurrentAsWatched:', e); 
      showNotification('Error al marcar como visto', 'error');
    }
  }

  // ── Lista de capítulos ─────────────────────────────────────────────────
  async function loadChaptersList() {
    try {
      const url = source === 'local'
        ? `/api/chapters/local/${type}/${content_id}`
        : `/api/chapters/${type}/${source}/${content_id}`;
      chaptersList = await api.get(url);

      currentChapterIndex = chaptersList.findIndex(
        ch => String(ch.number) === String(current_chapter)
      );
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

  // ── Cargar capítulo actual ─────────────────────────────────────────────
  function loadCurrentChapter() {
    if (progressInterval) { clearInterval(progressInterval); progressInterval = null; }

    const doLoad = () => {
      if (chapterWrapper) chapterWrapper.innerHTML = `
        <div style="display:flex; align-items:center; justify-content:center;
                    width:100%; height:100%;">
          <div class="loading-spinner"></div>
        </div>`;
      if (type === 'anime') loadAnimeChapter();
      else                  loadMangaChapter();
    };

    if (window.chapterTransition) window.chapterTransition(doLoad);
    else doLoad();
    showUI();
  }

  // ── Navegación ─────────────────────────────────────────────────────────
  function updateUrl() {
    const url = `/reader/${type}/${source}/${content_id}/${currentChapterNum}`;
    history.pushState({}, '', url);
  }

  function prevChapter() {
    if (currentChapterIndex <= 0) return;
    currentChapterIndex--;
    currentChapterNum = chaptersList[currentChapterIndex].number;
    updateUrl();
    updateChapterLabel();
    loadCurrentChapter();
  }

  function nextChapter() {
    if (currentChapterIndex >= chaptersList.length - 1) return;
    markCurrentAsWatched();
    currentChapterIndex++;
    currentChapterNum = chaptersList[currentChapterIndex].number;
    updateUrl();
    updateChapterLabel();
    loadCurrentChapter();
  }

  function currentChapterId() {
    return chaptersList[currentChapterIndex]?.id || currentChapterNum;
  }

  // ── Anime ──────────────────────────────────────────────────────────────
  async function loadAnimeChapter() {
    try {
      const chapterArg = source === 'local' ? currentChapterNum : currentChapterId();
      const videoUrl = source === 'local'
        ? `/api/play/local/anime/${content_id}/${chapterArg}`
        : `/api/play/remote/anime/${source}/${content_id}/${chapterArg}`;

      let savedTime = 0;
      let duration  = 0;
    let hasMarked = false;

    // [OPT-1] Progreso + duración en paralelo (eran secuenciales)
    const fetches = [
      api.get(`/api/progress/${type}/${source}/${content_id}`).catch(() => null),
    ];
    if (source === 'local') {
      fetches.push(
        api.get(`/api/video-duration/anime/${content_id}/${currentChapterNum}`).catch(() => null)
      );
    }

    const [prog, durData] = await Promise.all(fetches);
    if (prog && String(prog.chapter) === String(currentChapterNum) && prog.progress)
      savedTime = parseInt(prog.progress);
    if (durData?.duration > 0) duration = durData.duration;

    if (chapterWrapper) chapterWrapper.innerHTML = `
      <video id="anime-video" autoplay playsinline
             style="width:100%; height:100%; object-fit:contain;">
        <source src="${videoUrl}" type="video/mp4">
      </video>`;

    const video = document.getElementById('anime-video');
    if (!video) return;

    // ── Wire custom controls ──
    wirePlayerControls(video, duration);

    if (savedTime > 0)
      video.addEventListener('loadedmetadata', () => {
        video.currentTime = savedTime;
      }, { once: true });

    // [OPT-4] Guardar progreso solo cuando el video está reproduciendo,
    // suspender si está en pausa o la pestaña no es visible
    let intervalActive = false;

    function startInterval() {
      if (intervalActive) return;
      intervalActive = true;
      progressInterval = setInterval(() => {
        if (document.hidden || video.paused) return; // no gastar fetches en pausa
        const t = Math.floor(video.currentTime);
        api.post(`/api/progress/${type}/${source}/${content_id}`, { chapter: currentChapterNum, progress: t }).catch(console.error);

        if (!hasMarked && duration > 0 && t >= duration * 0.99) {
          hasMarked = true;
          markCurrentAsWatched();
        }
      }, 15000);
    }

    function stopInterval() {
      if (progressInterval) { clearInterval(progressInterval); progressInterval = null; }
      intervalActive = false;
    }

    video.addEventListener('play',  startInterval);
    video.addEventListener('pause', stopInterval);
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) stopInterval(); else if (!video.paused) startInterval();
    }, { once: false });

    video.addEventListener('ended', () => {
      stopInterval();
      if (!hasMarked) { hasMarked = true; markCurrentAsWatched(); }
      if (currentChapterIndex < chaptersList.length - 1) nextChapter();
    });
    } catch (err) {
      console.error(err);
      if (chapterWrapper) chapterWrapper.innerHTML =
        `<div style="color:var(--accent2); text-align:center; padding:20px;">
           Error al cargar capítulo: ${err.message}
         </div>`;
    }
  }

  // ── Player controls wiring (anime) ─────────────────────────────────────
  function wirePlayerControls(video, duration) {
    if (!poPlayBtn || !poProgress) return;

    // Format time helper
    function fmt(sec) {
      if (!isFinite(sec) || sec < 0) return '0:00';
      const m = Math.floor(sec / 60);
      const s = Math.floor(sec % 60);
      return `${m}:${String(s).padStart(2, '0')}`;
    }

    function updateUI() {
      const t = video.currentTime;
      const d = duration > 0 ? duration : (video.duration || 0);
      const pct = d > 0 ? (t / d) * 100 : 0;
      poProgress.value = d > 0 ? (t / d) * 1000 : 0;
      if (poProgressPlayed) poProgressPlayed.style.width = pct + '%';
      if (poTime) poTime.textContent = `${fmt(t)} / ${fmt(d)}`;

      // Play/pause icons
      const playing = !video.paused;
      const pauseSvg = '<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>';
      const playSvg  = '<polygon points="6 3 20 12 6 21 6 3"/>';
      if (poPlaySvg) poPlaySvg.innerHTML = playing ? pauseSvg : playSvg;
      if (poCenterSvg) {
        poCenterSvg.innerHTML = playing ? pauseSvg : playSvg;
        poCenterBtn?.classList.toggle('hidden', playing);
      }
    }

    // ── Play / Pause ──
    const togglePlay = () => {
      if (video.paused) video.play(); else video.pause();
    };
    poPlayBtn?.addEventListener('click', togglePlay);
    poCenterBtn?.addEventListener('click', togglePlay);
    video.addEventListener('play', updateUI);
    video.addEventListener('pause', updateUI);

    // ── Progress bar references ──
    const progressWrap = document.querySelector('.po-progress-wrap');
    const progressTooltip = document.getElementById('po-progress-tooltip');

    // ── Progress bar (click / drag directo) ──
    function getDurationSec() {
      return (duration > 0 ? duration : (video.duration || 0));
    }
    function seekFromClientX(clientX) {
      const d = getDurationSec();
      if (d <= 0 || !isFinite(d)) return;
      const rect = progressWrap.getBoundingClientRect();
      const x    = Math.max(0, Math.min(clientX - rect.left, rect.width));
      const pct  = x / rect.width;
      const target = pct * d;
      video.currentTime = target;
      // Update visual directly (no dependemos de video.currentTime aún)
      poProgress.value = Math.round(pct * 1000);
      if (poProgressPlayed) poProgressPlayed.style.width = (pct * 100) + '%';
      if (poTime) poTime.textContent = `${fmt(target)} / ${fmt(d)}`;
    }

    let _drag = false;

    function onDown(clientX) { _drag = true; seekFromClientX(clientX); }
    function onMove(clientX) { if (_drag) { seekFromClientX(clientX); } }
    function onUp()          { _drag = false; updateUI(); }

    progressWrap.addEventListener('mousedown',  e => onDown(e.clientX));
    document.addEventListener('mousemove',      e => { if (_drag) e.preventDefault(); onMove(e.clientX); });
    document.addEventListener('mouseup',        onUp);
    progressWrap.addEventListener('touchstart', e => { e.preventDefault(); onDown(e.touches[0].clientX); }, { passive: false });
    document.addEventListener('touchmove',      e => { if (_drag) e.preventDefault(); onMove(e.touches[0].clientX); }, { passive: false });
    document.addEventListener('touchend',       onUp);

    video.addEventListener('timeupdate', () => { if (!_drag) updateUI(); });
    video.addEventListener('loadedmetadata', () => { updateUI(); });
    video.addEventListener('seeked',      () => { updateUI(); });

    // ── Volume ──
    function updateVolUI() {
      const v = video.muted ? 0 : video.volume;
      if (poVolSlider) {
        poVolSlider.value = v;
        poVolSlider.style.setProperty('--vol-pct', (v * 100) + '%');
      }
      if (poVolSvg) {
        const muted = video.muted || v === 0;
        const half  = !muted && v < 0.5;
        poVolSvg.innerHTML = muted
          ? '<line x1="1" y1="1" x2="23" y2="23"/><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>'
          : half
            ? '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>'
            : '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>';
      }
    }
    poVolSlider?.addEventListener('input', () => {
      video.volume = parseFloat(poVolSlider.value);
      video.muted = false;
      updateVolUI();
    });
    poVolBtn?.addEventListener('click', () => {
      video.muted = !video.muted;
      updateVolUI();
    });
    video.addEventListener('volumechange', updateVolUI);
    updateVolUI();

    // ── Speed ──
    const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];
    poSpeed?.addEventListener('click', () => {
      const cur = video.playbackRate;
      let idx = SPEEDS.indexOf(cur);
      if (idx === -1 || idx >= SPEEDS.length - 1) idx = 0; else idx++;
      video.playbackRate = SPEEDS[idx];
      poSpeed.textContent = SPEEDS[idx] + '×';
    });

    // ── Subtitles ──
    poSubs?.addEventListener('click', () => cycleSubtitles(video));

    // ── Click on empty overlay area → toggle play ──
    poOverlay?.addEventListener('click', e => {
      if (e.target === poOverlay || e.target.classList.contains('po-top') || e.target.classList.contains('po-bottom')) {
        if (video.paused) video.play(); else video.pause();
      }
    });

    // ── Progress tooltip ──
    if (progressWrap && progressTooltip) {
      function fmtTooltip(sec) {
        if (!isFinite(sec) || sec < 0) return '0:00';
        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);
        return `${m}:${String(s).padStart(2, '0')}`;
      }
      function onProgressMove(clientX) {
        const d = duration > 0 ? duration : (video.duration || 0);
        if (d <= 0) return;
        const rect = progressWrap.getBoundingClientRect();
        const x    = Math.max(0, Math.min(clientX - rect.left, rect.width));
        const pct  = x / rect.width;
        const sec  = pct * d;
        progressTooltip.textContent = fmtTooltip(sec);
        progressTooltip.style.left  = (pct * 100) + '%';
      }
      progressWrap.addEventListener('mousemove', e => onProgressMove(e.clientX));
      progressWrap.addEventListener('touchmove', e => {
        const touch = e.touches[0];
        if (touch) onProgressMove(touch.clientX);
      });
    }

    // ── Keyboard ──
    if (!window.__readerKeys) {
      window.__readerKeys = true;
      document.addEventListener('keydown', e => {
        const v = document.getElementById('anime-video');
        if (!v || type !== 'anime') return;

        if (e.key === ' ' || e.key === 'Space') {
          e.preventDefault();
          if (v.paused) v.play(); else v.pause();
        }
        if (e.key === 'c' || e.key === 'C') {
          e.preventDefault();
          cycleSubtitles(v);
        }
        if (e.key === 'ArrowLeft') {
          e.preventDefault();
          v.currentTime = Math.max(0, v.currentTime - 5);
        }
        if (e.key === 'ArrowRight') {
          e.preventDefault();
          v.currentTime = Math.min(v.duration || Infinity, v.currentTime + 5);
        }
      });
    }

    updateUI();
  }

  // ── Subtitle cycling ──────────────────────────────────────────────────
  function cycleSubtitles(video) {
    if (!video) return;
    const tracks = video.textTracks;
    if (!tracks || tracks.length === 0) {
      showNotification('No hay subtítulos disponibles', 'info');
      return;
    }

    // Find currently showing track
    let showingIdx = -1;
    for (let i = 0; i < tracks.length; i++) {
      if (tracks[i].mode === 'showing') { showingIdx = i; break; }
    }

    // Hide all
    for (let i = 0; i < tracks.length; i++) tracks[i].mode = 'hidden';

    const nextIdx = showingIdx + 1;
    if (nextIdx < tracks.length) {
      tracks[nextIdx].mode = 'showing';
      const label = tracks[nextIdx].label || `Track ${nextIdx + 1}`;
      showNotification(`Subtítulos: ${label}`, 'info');
      poSubs?.classList.add('active');
    } else {
      showNotification('Subtítulos: desactivados', 'info');
      poSubs?.classList.remove('active');
    }
  }

  // ── Manga — visor virtual con búsqueda binaria ─────────────────────────
  //
  // Mejoras sobre la versión anterior:
  //
  // [OPT-2] getVisibleIndex() usa búsqueda binaria sobre un array de offsets
  //         acumulados en vez de recorrer todo el array en cada frame de scroll.
  //
  // [OPT-3] prefixSums[] se construye una vez y se actualiza solo cuando
  //         pageHeights[i] cambia (al aprender la altura real de una imagen).
  //         offsetBefore(i) pasa de O(n) a O(1).
  //
  // [OPT-5] updateWindow() guarda el rango [prevLo, prevHi] y solo procesa
  //         los slots que entran o salen de la ventana (delta), no todos.
  //
  // [OPT-6] mountImage() tiene un timeout de 12 s; si decode() tarda más,
  //         libera el slot para que se pueda reintentar.

  async function loadMangaChapter() {
    try {
      const isRemote = source !== 'local';
      const chapterArg = isRemote ? currentChapterId() : currentChapterNum;
      const imgUrl  = isRemote
        ? `/api/play/remote/manga/${source}/${content_id}/${chapterArg}`
        : `/api/play/local/manga/${content_id}/${chapterArg}`;
      const rawData = await api.get(imgUrl);

      if (!rawData.length) {
        if (chapterWrapper) chapterWrapper.innerHTML =
          `<div style="color:var(--muted); text-align:center; padding:20px;">
             No hay imágenes en este capítulo.
           </div>`;
        return;
      }

      const imageUrls = isRemote ? rawData : rawData.map(p => `/api/manga/images/${p}`);
      const total     = imageUrls.length;

      const WINDOW     = 2;
      const IMG_HEIGHT = 1200;

      // Estado
      const pageHeights = new Array(total).fill(IMG_HEIGHT);
      let   currentPage = 0;
      let   hasMarked   = false;
      let   saveTimeout = null;
      let   rafId       = null;
      let   _initialScrollApplied = false;
      let   _pendingDecode = 0;

      // [OPT-3] Array de sumas de prefijo: prefixSums[i] = suma de pageHeights[0..i-1]
      // prefixSums[0] = 0, prefixSums[total] = altura total
      const prefixSums = new Array(total + 1).fill(0);
      function rebuildSums(fromIdx = 0) {
        // Reconstruir solo desde el índice modificado hacia adelante
        const start = fromIdx === 0 ? 0 : fromIdx;
        prefixSums[start] = start === 0 ? 0 : prefixSums[start];
        for (let i = start; i < total; i++) {
          prefixSums[i + 1] = prefixSums[i] + pageHeights[i];
        }
      }
      rebuildSums(0);

      // O(1) gracias a prefixSums
      function offsetBefore(i) { return prefixSums[i]; }

      // Corrige el scroll después de que imágenes pequeñas colapsan durante la carga inicial
      function _fixInitialScroll() {
        if (_initialScrollApplied) return;
        if (_pendingDecode > 0) return; // esperar a que terminen de decodificar
        _initialScrollApplied = true;

        // Buscar la primera imagen con altura real > 0 empezando desde savedIndex
        let target = savedIndex;
        while (target < total && pageHeights[target] === 0) target++;
        if (target >= total) {
          // Todas las imágenes son pequeñas — buscar desde el inicio
          for (let j = 0; j < total; j++) {
            if (pageHeights[j] > 0) { target = j; break; }
          }
        }
        target = Math.min(target, total - 1);

        currentPage = target;
        viewerDiv.scrollTop = offsetBefore(target);

        // Forzar re-montaje de la ventana con las alturas reales
        prevLo = -1;
        prevHi = -1;
        updateWindow(target);
      }

      // [OPT-2] Búsqueda binaria: O(log n) en vez de O(n)
      function getVisibleIndex() {
        const scrollMid = viewerDiv.scrollTop + viewerDiv.clientHeight / 2;
        let lo = 0, hi = total - 1;
        while (lo < hi) {
          const mid    = (lo + hi) >> 1;
          const midEnd = prefixSums[mid + 1];
          if (midEnd < scrollMid) lo = mid + 1;
          else                    hi = mid;
        }
        return lo;
      }

      // ── Construir esqueleto del viewer ──
      if (chapterWrapper) chapterWrapper.innerHTML = `
        <div id="manga-viewer"
             style="width:100%; height:100%; overflow-y:auto; overflow-x:hidden;
                    background:#000; font-size:0; line-height:0;">
          ${imageUrls.map((_, i) =>
            `<div class="manga-slot" data-index="${i}"
                  style="width:100%; height:${IMG_HEIGHT}px;
                         background:#0a0a0f; font-size:0; line-height:0;">
             </div>`
          ).join('')}
        </div>`;

      const viewerDiv = document.getElementById('manga-viewer');
      if (!viewerDiv) return;
      const slots = Array.from(viewerDiv.querySelectorAll('.manga-slot'));

      // ── Mount / unmount ─────────────────────────────────────────────────

      function mountImage(i) {
        const slot = slots[i];
        if (slot.dataset.mounted === '1') return;
        slot.dataset.mounted = '1';
        _pendingDecode++;

        const img = document.createElement('img');
        img.src           = imageUrls[i];
        img.style.cssText = 'width:100%; height:auto; display:block;';

        // [OPT-6] Timeout de 12 s para decode — evita bloqueos permanentes
        let settled = false;
        const decodeTimeout = setTimeout(() => {
          if (!settled) {
            settled = true;
            slot.dataset.mounted = '0'; // liberar para reintentos
            if (pageHeights[i] !== 0) {
              pageHeights[i] = 0;
              rebuildSums(i);
            }
            _pendingDecode--;
            _fixInitialScroll();
          }
        }, 12000);

        img.decode()
          .then(() => {
            settled = true;
            clearTimeout(decodeTimeout);
            if (slot.dataset.mounted !== '1') return;

            // Filter small images (logos, ads, thumbnails) that slip past server filter
            if (img.naturalWidth < 300 || img.naturalHeight < 300) {
              slot.style.height    = '0';
              slot.style.overflow  = 'hidden';
              slot.dataset.mounted = '0';
              if (pageHeights[i] !== 0) {
                pageHeights[i] = 0;
                rebuildSums(i);
              }
              _pendingDecode--;
              _fixInitialScroll();
              return;
            }

            slot.style.height = '';
            slot.innerHTML    = '';

            // [OPT-7] En PC, si la imagen es más angosta que el contenedor
            // se muestra a tamaño natural centrada en vez de estirarse.
            // En móvil (< 768 px) se mantiene el fill completo.
            const slotW      = slot.offsetWidth || viewerDiv.clientWidth || 800;
            const naturalW   = img.naturalWidth;
            const IS_DESKTOP = window.innerWidth >= 768;
            const fitNatural = IS_DESKTOP && naturalW > 0 && naturalW < slotW;

            if (fitNatural) {
              img.style.cssText = `width:${naturalW}px; height:auto; display:block; margin:0 auto;`;
            } else {
              img.style.cssText = 'width:100%; height:auto; display:block;';
            }

            slot.appendChild(img);

            const rendered = naturalW > 0
              ? Math.round(img.naturalHeight * (fitNatural ? 1 : slotW / naturalW))
              : img.offsetHeight;
            if (rendered > 0 && rendered !== pageHeights[i]) {
              pageHeights[i] = rendered;
              rebuildSums(i); // [OPT-3]
            }
            _pendingDecode--;
            _fixInitialScroll();
          })
          .catch(() => {
            settled = true;
            clearTimeout(decodeTimeout);
            slot.dataset.mounted = '0';
            slot.style.height    = '0';
            slot.style.overflow  = 'hidden';
            if (pageHeights[i] !== 0) {
              pageHeights[i] = 0;
              rebuildSums(i);
            }
            _pendingDecode--;
            _fixInitialScroll();
          });
      }

      function unmountImage(i) {
        const slot = slots[i];
        if (slot.dataset.mounted === '0') return;
        slot.style.height    = pageHeights[i] + 'px';
        slot.innerHTML       = '';
        slot.dataset.mounted = '0';
      }

      // [OPT-5] Rango previo — solo procesar deltas
      let prevLo = -1, prevHi = -1;
      let _prefetchTimers = [];

      function _clearPrefetch() {
        _prefetchTimers.forEach(t => clearTimeout(t));
        _prefetchTimers = [];
      }

      function _prefetchNextBatch(centerIdx, count = 3) {
        _clearPrefetch();
        const start = Math.min(centerIdx + WINDOW + 1, total);
        const end   = Math.min(start + count, total);
        for (let i = start; i < end; i++) {
          const timer = setTimeout(() => {
            const img = new Image();
            img.src = imageUrls[i];
          }, i * 200);
          _prefetchTimers.push(timer);
        }
      }

      function updateWindow(centerIdx) {
        const lo = Math.max(0,       centerIdx - WINDOW);
        const hi = Math.min(total-1, centerIdx + WINDOW);
        if (lo === prevLo && hi === prevHi) return; // nada cambió

        // Desmontar lo que salió de la ventana
        const oldLo = prevLo < 0 ? lo : prevLo;
        const oldHi = prevHi < 0 ? hi : prevHi;
        for (let i = oldLo; i < lo;  i++) unmountImage(i);
        for (let i = hi + 1; i <= oldHi; i++) unmountImage(i);

        // Montar lo que entró en la ventana
        const newLo = prevLo < 0 ? lo : Math.min(lo, oldLo);
        const newHi = prevHi < 0 ? hi : Math.max(hi, oldHi);
        for (let i = newLo; i <= newHi; i++) {
          if (i >= lo && i <= hi) mountImage(i);
        }

        prevLo = lo;
        prevHi = hi;

        // Precargar las siguientes imágenes
        _prefetchNextBatch(centerIdx);
      }

      // ── Scroll handler (rAF-throttled) ────────────────────────────────
      function onScroll() {
        if (rafId) return;
        rafId = requestAnimationFrame(() => {
          rafId = null;
          const idx = getVisibleIndex();
          if (idx !== currentPage) {
            currentPage = idx;
            updateWindow(idx);
          }

          clearTimeout(saveTimeout);
          saveTimeout = setTimeout(() => {
            api.post(`/api/progress/manga/${source}/${content_id}`, { chapter: currentChapterNum, progress: idx }).catch(console.error);
          }, 500);

          if (!hasMarked) {
            const pct = (viewerDiv.scrollTop + viewerDiv.clientHeight) / viewerDiv.scrollHeight;
            if (pct >= 0.90) { hasMarked = true; markCurrentAsWatched(); }
          }
        });
      }

      viewerDiv.addEventListener('scroll', onScroll, { passive: true });

      if (_unloadSaveHandler) window.removeEventListener('beforeunload', _unloadSaveHandler);
      _unloadSaveHandler = function() {
        clearTimeout(saveTimeout);
        api.post(`/api/progress/manga/${source}/${content_id}`, { chapter: currentChapterNum, progress: currentPage }).catch(() => {});
      };
      window.addEventListener('beforeunload', _unloadSaveHandler);

      // ── Restaurar posición guardada ────────────────────────────────────
      let savedIndex = 0;
      try {
        const progUrl = isRemote
          ? `/api/progress/manga/${source}/${content_id}`
          : `/api/progress/local/manga/${content_id}`;
        const prog = await api.get(progUrl);
        if (String(prog.chapter) === String(currentChapterNum) && prog.progress) {
          const idx = parseInt(prog.progress);
          if (!isNaN(idx) && idx < total) savedIndex = idx;
        }
      } catch (e) { console.warn(e); }

      currentPage = savedIndex;
      updateWindow(savedIndex);

    } catch (err) {
      console.error(err);
      if (chapterWrapper) chapterWrapper.innerHTML =
        `<div style="color:var(--accent2); text-align:center; padding:20px;">
           Error: ${err.message}
         </div>`;
    }
  }

  // ── Init ──────────────────────────────────────────────────────────────
  async function init() {
    await loadChaptersList();

    prevBtn?.addEventListener('click', prevChapter);
    nextBtn?.addEventListener('click', nextChapter);

    const goBack = () => {
      window.location.href = `/serie/${type}/${source}/${content_id}`;
    };
    backBtn?.addEventListener('click', goBack);
    document.getElementById('po-back')?.addEventListener('click', goBack);

    document.getElementById('po-prev')?.addEventListener('click', prevChapter);
    document.getElementById('po-next')?.addEventListener('click', nextChapter);

    if (_unloadClearHandler) window.removeEventListener('beforeunload', _unloadClearHandler);
    _unloadClearHandler = function() {
      if (progressInterval) clearInterval(progressInterval);
    };
    window.addEventListener('beforeunload', _unloadClearHandler);

    showUI();
  }

  init();
})();