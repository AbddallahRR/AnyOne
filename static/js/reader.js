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

  // ── Manga — visor virtual ──────────────────────────────────────────────
  //
  // Problema: cargar todas las imágenes en el DOM mantiene cada una decodificada
  // en VRAM aunque no sea visible, disparando el uso de memoria de video.
  //
  // Solución: visor virtual con ventana de ±WINDOW páginas alrededor del scroll
  // actual. Las imágenes fuera de la ventana se reemplazan por placeholders del
  // mismo alto (preservando la posición de scroll). Solo WINDOW*2+1 imágenes
  // viven en el DOM como <img> real en cualquier momento.
  //
  // Las alturas reales se aprenden la primera vez que cada imagen carga y se
  // guardan en pageHeights[]. Los placeholders usan esa altura para que el
  // scrollHeight total no cambie al intercambiar.

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

      // ── Constantes del visor virtual ──
      const WINDOW     = 2;   // páginas visibles a cada lado del índice actual
      const IMG_HEIGHT = 1200; // altura estimada (px) hasta que se aprende la real

      // Estado
      const pageHeights = new Array(total).fill(IMG_HEIGHT); // se actualiza al cargar
      let   currentPage = 0;  // índice de la página más cercana al tope del viewport
      let   hasMarked   = false;
      let   saveTimeout = null;
      let   rafId       = null;

      // ── Construir esqueleto del viewer ──
      // Cada slot es un <div> que contendrá un <img> real o será un placeholder.
      // Sin display:flex en el viewer ni en los slots — evita gaps entre imágenes.
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

      // ── Helpers ──────────────────────────────────────────────────────────

      /** Devuelve el índice de la página más cercana al tope del viewport */
      function getVisibleIndex() {
        const scrollTop = viewerDiv.scrollTop;
        let   best      = 0;
        let   bestDist  = Infinity;
        let   cumulative = 0;
        for (let i = 0; i < total; i++) {
          const slotMid = cumulative + pageHeights[i] / 2;
          const dist    = Math.abs(slotMid - scrollTop);
          if (dist < bestDist) { bestDist = dist; best = i; }
          cumulative += pageHeights[i];
        }
        return best;
      }

      /** Devuelve el acumulado de alturas desde el índice 0 hasta i-1 */
      function offsetBefore(i) {
        let s = 0;
        for (let k = 0; k < i; k++) s += pageHeights[k];
        return s;
      }

      /** Convierte un slot en <img> real y aprende su altura.
       *  La imagen se añade al DOM DESPUÉS de decodificarse para evitar
       *  el pantallazo de una imagen en estado intermedio. */
      function mountImage(i) {
        const slot = slots[i];
        if (slot.dataset.mounted === '1') return; // ya montada o en proceso
        slot.dataset.mounted = '1';               // marcar como en proceso

        const img = document.createElement('img');
        img.src           = imageUrls[i];
        img.style.cssText = 'width:100%; height:auto; display:block;';

        img.decode()
          .then(() => {
            if (slot.dataset.mounted !== '1') return; // desmontada mientras cargaba

            // Descartar imágenes demasiado pequeñas (iconos, separadores, logos)
            const MIN_PX = 80;
            if (img.naturalWidth < MIN_PX || img.naturalHeight < MIN_PX) {
              slot.style.height    = '0';
              slot.style.overflow  = 'hidden';
              slot.dataset.mounted = '0';
              pageHeights[i]       = 0;
              return;
            }

            slot.style.height = ''; // dejar que la imagen dicte la altura
            slot.innerHTML    = '';
            slot.appendChild(img);

            // Aprender altura real
            const slotW    = slot.offsetWidth || viewerDiv.clientWidth || 800;
            const rendered = img.naturalWidth > 0
              ? Math.round(img.naturalHeight * (slotW / img.naturalWidth))
              : img.offsetHeight;
            if (rendered > 0) {
              pageHeights[i]    = rendered;
              slot.style.height = '';
            }
          })
          .catch(() => {
            slot.dataset.mounted = '0';
          });
      }

      /** Convierte un slot en placeholder (libera la imagen de VRAM) */
      function unmountImage(i) {
        const slot = slots[i];
        if (slot.dataset.mounted === '0') return; // ya es placeholder

        // Fijar la altura aprendida ANTES de vaciar el slot
        slot.style.height    = pageHeights[i] + 'px';
        slot.innerHTML       = '';     // elimina <img> → browser libera VRAM
        slot.dataset.mounted = '0';
      }

      /** Actualiza qué slots tienen imagen real vs placeholder */
      function updateWindow(centerIdx) {
        const lo = Math.max(0,       centerIdx - WINDOW);
        const hi = Math.min(total-1, centerIdx + WINDOW);
        for (let i = 0; i < total; i++) {
          if (i >= lo && i <= hi) mountImage(i);
          else                    unmountImage(i);
        }
      }

      // ── Scroll handler (rAF-throttled) ───────────────────────────────────
      function onScroll() {
        if (rafId) return;
        rafId = requestAnimationFrame(() => {
          rafId = null;
          const idx = getVisibleIndex();

          if (idx !== currentPage) {
            currentPage = idx;
            updateWindow(idx);
          }

          // Guardar progreso (debounced)
          clearTimeout(saveTimeout);
          saveTimeout = setTimeout(() => {
            fetch(`/api/progress/local/manga/${content_id}`, {
              method:  'POST',
              headers: { 'Content-Type': 'application/json' },
              body:    JSON.stringify({ chapter: currentChapterNum, progress: idx }),
            }).catch(console.error);
          }, 500);

          // Marcar como visto al 90% de scroll
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

      // ── Restaurar posición guardada ───────────────────────────────────────
      let savedIndex = 0;
      try {
        const res  = await fetch(`/api/progress/local/manga/${content_id}`);
        const prog = await res.json();
        if (String(prog.chapter) === String(currentChapterNum) && prog.progress) {
          const idx = parseInt(prog.progress);
          if (!isNaN(idx) && idx < total) savedIndex = idx;
        }
      } catch (e) { console.warn(e); }

      // Montar ventana inicial y hacer scroll
      currentPage = savedIndex;
      updateWindow(savedIndex);

      // Scroll al offset acumulado del índice guardado
      viewerDiv.scrollTop = offsetBefore(savedIndex);

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