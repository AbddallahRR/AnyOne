// static/js/reader.js
(function () {
  'use strict';

  const { type, source, content_id, current_chapter } = window.readerData;

  let chaptersList        = [];
  let currentChapterIndex = -1;
  let currentChapterNum   = current_chapter;
  let progressInterval    = null;

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
  function hideUI() { UI_ELS.forEach(el => el.classList.remove('show')); }

  // ── Label del capítulo ─────────────────────────────────────────────────
  function updateChapterLabel() {
    if (chapterLabelNum) chapterLabelNum.textContent = currentChapterNum;
    if (prevBtn) prevBtn.disabled = currentChapterIndex <= 0;
    if (nextBtn) nextBtn.disabled = currentChapterIndex >= chaptersList.length - 1;
    if (window.animateChapterLabel) window.animateChapterLabel();
  }

  // ── Marcar visto ───────────────────────────────────────────────────────
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

  // ── Lista de capítulos ─────────────────────────────────────────────────
  async function loadChaptersList() {
    try {
      const url = source === 'local'
        ? `/api/chapters/local/${type}/${content_id}`
        : `/api/chapters/${type}/${source}/${content_id}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error('No se pudo obtener la lista de capítulos');
      chaptersList = await res.json();

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
  function prevChapter() {
    if (currentChapterIndex <= 0) return;
    currentChapterIndex--;
    currentChapterNum = chaptersList[currentChapterIndex].number;
    updateChapterLabel();
    loadCurrentChapter();
  }

  function nextChapter() {
    if (currentChapterIndex >= chaptersList.length - 1) return;
    markCurrentAsWatched();
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

    // [OPT-1] Progreso + duración en paralelo (eran secuenciales)
    const fetches = [
      fetch(`/api/progress/${type}/${source}/${content_id}`)
        .then(r => r.ok ? r.json() : null)
        .catch(() => null),
    ];
    if (source === 'local') {
      fetches.push(
        fetch(`/api/video-duration/anime/${content_id}/${currentChapterNum}`)
          .then(r => r.ok ? r.json() : null)
          .catch(() => null)
      );
    }

    const [prog, durData] = await Promise.all(fetches);
    if (prog && String(prog.chapter) === String(currentChapterNum) && prog.progress)
      savedTime = parseInt(prog.progress);
    if (durData?.duration > 0) duration = durData.duration;

    if (chapterWrapper) chapterWrapper.innerHTML = `
      <video id="anime-video" controls autoplay
             style="width:100%; height:100%; object-fit:contain;">
        <source src="${videoUrl}" type="video/mp4">
      </video>`;

    const video = document.getElementById('anime-video');
    if (!video) return;

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
      const total     = imageUrls.length;

      const WINDOW     = 2;
      const IMG_HEIGHT = 1200;

      // Estado
      const pageHeights = new Array(total).fill(IMG_HEIGHT);
      let   currentPage = 0;
      let   hasMarked   = false;
      let   saveTimeout = null;
      let   rafId       = null;

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

        const img = document.createElement('img');
        img.src           = imageUrls[i];
        img.style.cssText = 'width:100%; height:auto; display:block;';

        // [OPT-6] Timeout de 12 s para decode — evita bloqueos permanentes
        let settled = false;
        const decodeTimeout = setTimeout(() => {
          if (!settled) {
            settled = true;
            slot.dataset.mounted = '0'; // liberar para reintentos
          }
        }, 12000);

        img.decode()
          .then(() => {
            settled = true;
            clearTimeout(decodeTimeout);
            if (slot.dataset.mounted !== '1') return;

            const MIN_PX = 80;
            if (img.naturalWidth < MIN_PX || img.naturalHeight < MIN_PX) {
              slot.style.height    = '0';
              slot.style.overflow  = 'hidden';
              slot.dataset.mounted = '0';
              if (pageHeights[i] !== 0) {
                pageHeights[i] = 0;
                rebuildSums(i); // [OPT-3] actualizar sumas desde este índice
              }
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
          })
          .catch(() => {
            settled = true;
            clearTimeout(decodeTimeout);
            slot.dataset.mounted = '0';
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
            fetch(`/api/progress/local/manga/${content_id}`, {
              method:  'POST',
              headers: { 'Content-Type': 'application/json' },
              body:    JSON.stringify({ chapter: currentChapterNum, progress: idx }),
            }).catch(console.error);
          }, 500);

          if (!hasMarked) {
            const pct = (viewerDiv.scrollTop + viewerDiv.clientHeight) / viewerDiv.scrollHeight;
            if (pct >= 0.90) { hasMarked = true; markCurrentAsWatched(); }
          }
        });
      }

      viewerDiv.addEventListener('scroll', onScroll, { passive: true });

      window.addEventListener('beforeunload', () => {
        clearTimeout(saveTimeout);
        fetch(`/api/progress/local/manga/${content_id}`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ chapter: currentChapterNum, progress: currentPage }),
        }).catch(() => {});
      });

      // ── Restaurar posición guardada ────────────────────────────────────
      let savedIndex = 0;
      try {
        const res  = await fetch(`/api/progress/local/manga/${content_id}`);
        const prog = await res.json();
        if (String(prog.chapter) === String(currentChapterNum) && prog.progress) {
          const idx = parseInt(prog.progress);
          if (!isNaN(idx) && idx < total) savedIndex = idx;
        }
      } catch (e) { console.warn(e); }

      currentPage = savedIndex;
      updateWindow(savedIndex);
      viewerDiv.scrollTop = offsetBefore(savedIndex); // O(1) con prefixSums

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

    backBtn?.addEventListener('click', () => {
      window.location.href = `/serie/${type}/${source}/${content_id}`;
    });

    window.addEventListener('beforeunload', () => {
      if (progressInterval) clearInterval(progressInterval);
    });

    showUI();
  }

  init();
})();