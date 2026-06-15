// static/js/serie.js
(function () {
  'use strict';

  if (!window.serieData) {
    console.error('serie.js: window.serieData no definido');
    return;
  }

  const { type, source, id, canStream: canStreamData } = window.serieData;
  const isLocal = source === 'local';
  const canStream = !isLocal && (type === 'manga' || canStreamData);

  let chapters        = [];
  let sortAsc         = true;
  let originalSource  = null;   // fuente real (e.g. "jkanime") para series locales
  let originalId      = null;   // content_id real para series locales

  // ── Elementos DOM ──────────────────────────────────────────────────────
  const coverImg            = document.getElementById('serie-cover');
  const titleEl             = document.getElementById('serie-title');
  const synopsisEl          = document.getElementById('serie-synopsis');
  const downloadAllBtn      = document.getElementById('download-all-btn');
  const continueBtn         = document.getElementById('continue-btn');
  const deleteWatchedBtn    = document.getElementById('delete-watched-btn');
  const currentChapterSpan  = document.getElementById('current-chapter');
  const progressPercentSpan = document.getElementById('progress-percent');
  const progressBarFill     = document.getElementById('progress-bar-fill');
  const chaptersContainer   = document.getElementById('chapters-list');
  const sortBtn             = document.getElementById('sort-btn');
  const chaptersCount       = document.getElementById('chapters-count');
  const badgeEl             = document.getElementById('serie-type-badge');
  const checkUpdatesBtn = document.getElementById('check-updates-btn');

  function notify(msg, t = 'info') {
    if (window.showNotification) window.showNotification(msg, t);
    else console.log(`[${t}] ${msg}`);
  }

  // ── Detalles de la serie ───────────────────────────────────────────────
  async function loadSerieDetails() {
    try {
      const url = isLocal
        ? `/api/content/local/${type}/${id}`
        : `/api/content/${type}/${source}/${id}`;
      const res  = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      titleEl.textContent    = data.title    || 'Sin título';
      synopsisEl.textContent = data.synopsis || 'Sin descripción disponible.';
      if (data.cover) { coverImg.dataset.src = data.cover; coverImg.src = data.cover; }

      // Guardar la fuente real de series descargadas localmente
      if (isLocal && data.source) {
        originalSource = data.source;
        originalId     = data.remote_id || null;
      }

      if (badgeEl) {
        badgeEl.textContent = type === 'anime' ? 'Anime' : 'Manga';
        badgeEl.className   = `card-badge ${type === 'anime' ? 'badge-anime' : 'badge-manga'}`;
      }
    } catch (err) {
      console.error('loadSerieDetails:', err);
      titleEl.textContent    = 'Error al cargar';
      synopsisEl.textContent = 'No se pudieron obtener los detalles.';
    }
  }

  // ── Capítulos ──────────────────────────────────────────────────────────
  async function loadChapters() {
    chaptersContainer.innerHTML = `
      <div style="grid-column:1/-1; display:flex; align-items:center; justify-content:center;
                  gap:12px; padding:48px 20px; color:var(--muted);">
        <div class="loading-spinner"></div>
        <span style="font-size:14px;">Cargando capítulos…</span>
      </div>`;

    try {
      let remote     = [];
      let localSet   = new Set();
      let watchedSet = new Set();

      if (isLocal) {
        // [OPT-1] Capítulos + watched en paralelo
        const [chapRes, watchRes] = await Promise.all([
          fetch(`/api/chapters/local/${type}/${id}`),
          fetch(`/api/watched/local:${id}`),
        ]);
        remote = chapRes.ok ? await chapRes.json() : [];
        remote = remote.map(ch => ({ ...ch, is_downloaded: true }));
        if (watchRes.ok) {
          const data = await watchRes.json();
          watchedSet = new Set((data.watched || []).map(Number));
        }
      } else {
        // [OPT-1] Remote + local en paralelo
        const [remoteRes, localRes] = await Promise.all([
          fetch(`/api/chapters/${type}/${source}/${id}`),
          fetch(`/api/chapters/local/${type}/${id}`),
        ]);
        remote = remoteRes.ok ? await remoteRes.json() : [];
        const localChaps = localRes.ok ? await localRes.json() : [];
        localSet = new Set(localChaps.map(ch => String(ch.number)));
        remote = remote.map(ch => ({ ...ch, is_downloaded: localSet.has(String(ch.number)) }));
      }

      chapters = remote.map(ch => ({
        ...ch,
        is_watched: watchedSet.has(Number(ch.number)),
      }));

      renderChapters();
    } catch (err) {
      console.error('loadChapters:', err);
      chaptersContainer.innerHTML = `
        <div class="empty-state" style="grid-column:1/-1;">
          <i class="fas fa-exclamation-circle" style="color:var(--accent2);"></i>
          <p>Error al cargar capítulos: ${err.message}</p>
        </div>`;
    }
  }

  // ── Virtualización por lotes ───────────────────────────────────────────
  // En lugar de volcar todo el HTML de golpe, se renderizan BATCH_SIZE pills
  // iniciales y se añaden más conforme el sentinel entra en el viewport.
  // Esto evita el spike de GPU/layout que ocurre al pintar 100-500 nodos
  // simultáneamente.

  const BATCH_SIZE = 30;          // pills por lote
  let   _sorted    = [];          // orden actual de chapters
  let   _rendered  = 0;           // cuántas pills ya están en el DOM
  let   _sentinel  = null;        // nodo observado por IntersectionObserver
  let   _observer  = null;        // instancia activa del observer

  function _teardownObserver() {
    if (_observer) { _observer.disconnect(); _observer = null; }
    if (_sentinel) { _sentinel.remove();     _sentinel = null; }
  }

  function _appendBatch() {
    const end   = Math.min(_rendered + BATCH_SIZE, _sorted.length);
    const frag  = document.createDocumentFragment();

    for (let i = _rendered; i < end; i++) {
      const temp = document.createElement('div');
      temp.innerHTML = buildPillHtml(_sorted[i]);
      frag.appendChild(temp.firstElementChild);
    }

    // Mover el sentinel al final (o añadirlo si aún no está)
    _teardownObserver();
    chaptersContainer.appendChild(frag);
    _rendered = end;

    if (_rendered < _sorted.length) {
      // Hay más pills por renderizar: colocar el sentinel y observarlo
      _sentinel = document.createElement('div');
      _sentinel.style.cssText = 'grid-column:1/-1; height:1px; pointer-events:none;';
      chaptersContainer.appendChild(_sentinel);

      _observer = new IntersectionObserver(entries => {
        if (entries[0].isIntersecting) _appendBatch();
      }, { rootMargin: '200px' });  // pre-carga 200 px antes de ser visible
      _observer.observe(_sentinel);
    }

    if (window.animateCards) window.animateCards('#chapters-list', '.chapter-pill');
  }

  // ── Render completo de capítulos ───────────────────────────────────────
  // Se llama solo en la carga inicial y al cambiar el orden.
  // Las acciones individuales (toggle watched, delete) actualizan el DOM
  // en sitio sin pasar por aquí.
  function renderChapters() {
    _teardownObserver();

    if (!chapters.length) {
      chaptersContainer.innerHTML = `
        <div class="empty-state" style="grid-column:1/-1;">
          <i class="fas fa-inbox"></i>
          <p>No se encontraron capítulos.</p>
        </div>`;
      return;
    }

    if (chaptersCount) chaptersCount.textContent = `${chapters.length} capítulos`;

    _sorted   = sortAsc ? [...chapters] : [...chapters].reverse();
    _rendered = 0;
    chaptersContainer.innerHTML = '';

    // [OPT-3] Un solo listener por acción en el contenedor, no uno por botón
    bindChapterEvents();

    _appendBatch();
  }

  // ── HTML de una pill (sin listeners) ──────────────────────────────────
  function buildPillHtml(ch) {
    const { number, id: chId, is_downloaded, is_watched } = ch;

    const watchedDot = is_watched
      ? `<span class="watched-dot"></span>`
      : '';

    const actionBtn = is_downloaded
      ? `<button class="play-chapter-btn chapter-action-btn" data-chapter="${number}" title="Reproducir">
           <i class="fas fa-play"></i>
         </button>`
      : canStream
        ? `<button class="stream-chapter-btn chapter-action-btn" data-chapter="${number}" title="Reproducir en streaming">
             <i class="fas fa-play"></i>
           </button>
           <button class="download-chapter-btn chapter-action-btn" data-chapter="${number}" data-chapter-id="${chId}" title="Descargar">
             <i class="fas fa-download"></i>
           </button>`
        : `<button class="download-chapter-btn chapter-action-btn" data-chapter="${number}" data-chapter-id="${chId}" title="Descargar">
             <i class="fas fa-download"></i>
           </button>`;

    const localBtns = isLocal ? `
      <button class="watched-toggle-btn chapter-action-btn ${is_watched ? 'is-watched' : ''}"
              data-chapter="${number}" title="${is_watched ? 'Quitar visto' : 'Marcar visto'}">
        <i class="fas fa-check"></i>
      </button>
      <button class="delete-chapter-btn chapter-action-btn" data-chapter="${number}" title="Eliminar">
        <i class="fas fa-trash-alt"></i>
      </button>` : '';

    return `
      <div class="chapter-pill ${is_downloaded ? 'downloaded' : ''} ${is_watched ? 'watched' : ''}"
           data-chapter="${number}">
        <div class="pill-label">
          <span class="pill-num ${is_watched ? 'muted' : ''}">Cap. ${number}</span>
          ${watchedDot}
        </div>
        <div class="pill-actions">
          ${actionBtn}
          ${localBtns}
        </div>
      </div>`;
  }

  // ── Event delegation ──────────────────────────────────────────────────
  // [OPT-3] Un bloque único que maneja todos los clics del contenedor.
  // No se re-registra en cada render de una pill individual.
  let _delegationBound = false;
  function bindChapterEvents() {
    if (_delegationBound) return;
    _delegationBound = true;

    chaptersContainer.addEventListener('click', e => {
      const btn = e.target.closest('.chapter-action-btn');
      if (!btn) return;
      e.stopPropagation();
      const { chapter, chapterId } = btn.dataset;

      if (btn.classList.contains('play-chapter-btn') || btn.classList.contains('stream-chapter-btn')) {
        window.location.href = `/reader/${type}/${source}/${id}/${chapter}`;
      } else if (btn.classList.contains('download-chapter-btn')) {
        downloadSingleChapter(chapter, chapterId);
      } else if (btn.classList.contains('watched-toggle-btn')) {
        toggleWatched(chapter);
      } else if (btn.classList.contains('delete-chapter-btn')) {
        (async function () {
          const confirmed = await window.showConfirm(
            'Eliminar capítulo',
            `¿Eliminar el capítulo ${chapter}? Esta acción no se puede deshacer.`,
            'Eliminar', 'danger'
          );
          if (confirmed) deleteChapter(chapter);
        })();
      }
    });
  }

  // ── Actualizar una pill en sitio (sin re-render completo) ─────────────
  // [OPT-2] toggleWatched y deleteChapter ya no llaman loadChapters().
  // Modifican el array chapters[] y parchean el nodo DOM existente.
  function patchPillInDOM(chapterNum) {
    const ch = chapters.find(c => String(c.number) === String(chapterNum));
    if (!ch) return;
    const pill = chaptersContainer.querySelector(`.chapter-pill[data-chapter="${chapterNum}"]`);
    if (!pill) return;

    pill.classList.toggle('watched', ch.is_watched);
    pill.classList.toggle('downloaded', ch.is_downloaded);
    const numEl = pill.querySelector('.pill-num');
    if (numEl) numEl.classList.toggle('muted', ch.is_watched);
    let dot = pill.querySelector('.watched-dot');
    if (ch.is_watched && !dot) {
      dot = document.createElement('span');
      dot.className = 'watched-dot';
      numEl?.after(dot);
    } else if (!ch.is_watched && dot) {
      dot.remove();
    }
    const toggleBtn = pill.querySelector('.watched-toggle-btn');
    if (toggleBtn) {
      toggleBtn.classList.toggle('is-watched', ch.is_watched);
      toggleBtn.title = ch.is_watched ? 'Quitar visto' : 'Marcar visto';
    }
  }

  // ── Confirm dialog ─────────────────────────────────────────────────────
  function showConfirm(message, onConfirm) {
    window.showConfirm(
      'Confirmar acción',
      message,
      'Eliminar', 'danger'
    ).then(function (confirmed) {
      if (confirmed) onConfirm();
    });
  }

  // ── Acciones sobre capítulos ───────────────────────────────────────────

  async function toggleWatched(chapterNum) {
    try {
      const res  = await fetch('/api/watched/toggle', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ content_ref: `local:${id}`, chapter: chapterNum }),
      });
      const data = await res.json();
      if (res.ok) {
        const wasWatched = data.status === 'watched';
        // [OPT-2] Actualizar estado local y parchar solo esa pill
        const ch = chapters.find(c => String(c.number) === String(chapterNum));
        if (ch) ch.is_watched = wasWatched;
        patchPillInDOM(chapterNum);
        updateProgress();
        notify(`Cap. ${chapterNum} marcado como ${wasWatched ? 'visto' : 'no visto'}`, 'success');
      } else {
        notify(`Error: ${data.error}`, 'error');
      }
    } catch (err) {
      notify(`Error: ${err.message}`, 'error');
    }
  }

  async function deleteChapter(chapterNum) {
    try {
      const res  = await fetch('/api/delete-chapter', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ content_ref: `local:${id}`, type, chapter: chapterNum }),
      });
      const data = await res.json();
      if (res.ok) {
        notify(`Capítulo ${chapterNum} eliminado`, 'success');
        // [OPT-2] Eliminar del array local y del DOM sin re-fetch
        chapters = chapters.filter(c => String(c.number) !== String(chapterNum));
        chaptersContainer.querySelector(`.chapter-pill[data-chapter="${chapterNum}"]`)?.remove();
        if (chaptersCount) chaptersCount.textContent = `${chapters.length} capítulos`;
        await loadProgress();
      } else {
        notify(`Error: ${data.error}`, 'error');
      }
    } catch (err) {
      notify(`Error: ${err.message}`, 'error');
    }
  }

  async function downloadSingleChapter(chapterNum, chapterId) {
    if (isLocal) { notify('Este contenido ya está descargado localmente.', 'info'); return; }
    try {
      const res  = await fetch('/api/download/chapter', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          type, source, content_id: id,
          chapter_id: chapterId,
          title: titleEl.textContent,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        notify(`Cap. ${chapterNum} encolado para descarga`, 'success');
        if (window.showDownloadIndicator) window.showDownloadIndicator();
      } else {
        notify(`Error: ${data.error}`, 'error');
      }
    } catch (err) {
      notify(`Error: ${err.message}`, 'error');
    }
  }

  async function downloadFullSeries() {
    if (isLocal) { notify('Esta serie ya está descargada localmente.', 'info'); return; }
    try {
      const res  = await fetch('/api/download', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ type, source, content_id: id, title: titleEl.textContent }),
      });
      const data = await res.json();
      if (res.ok) {
        notify(`Descarga de serie completa encolada (ID: ${data.job_id})`, 'success');
        if (window.showDownloadIndicator) window.showDownloadIndicator();
      } else {
        notify(`Error: ${data.error}`, 'error');
      }
    } catch (err) {
      notify(`Error: ${err.message}`, 'error');
    }
  }

  async function checkForUpdates() {
    if (!isLocal) return;
  
    checkUpdatesBtn.disabled = true;
    const icon = checkUpdatesBtn.querySelector('i');
    if (icon) {
      icon.className = 'fas fa-spinner fa-spin';
    }
    checkUpdatesBtn.querySelector('.btn-label').textContent = 'Buscando…';
  
    try {
      const refSource = originalSource || source;
      const refId     = originalId     || id;
      const contentRef = `${refSource}:${refId}`;
      const res  = await fetch(`/api/library/check-updates/${contentRef}`, {
        method: 'POST',
      });
      const data = await res.json();
  
      if (!res.ok || data.error) {
        notify(`Error al buscar actualizaciones: ${data.error || res.status}`, 'error');
        return;
      }
  
      const newChaps     = data.new_chapters     || [];
      const newChapIds   = data.new_chapter_ids  || [];
      if (newChaps.length === 0) {
        notify('✓ Serie al día, no hay episodios nuevos', 'success');
      } else {
        const label = newChaps.length === 1
          ? `1 capítulo nuevo (cap. ${newChaps[0]})`
          : `${newChaps.length} capítulos nuevos (${newChaps[0]}–${newChaps[newChaps.length - 1]})`;
        notify(`🆕 ${label} — descargando…`, 'info');
  
        _showUpdateBadge(newChaps.length);
  
        // Descargar automáticamente los nuevos capítulos
        await downloadNewChapters(refSource, refId, newChapIds);
      }
  
      checkUpdatesBtn.title = `Última comprobación: ${new Date().toLocaleTimeString()}`;
  
    } catch (err) {
      notify(`Error: ${err.message}`, 'error');
    } finally {
      _restoreCheckBtn(/* skipIconRestore */ false);
    }
  }

  async function downloadNewChapters(refSource, refId, chapterIds) {
    if (!chapterIds.length) return;

    _restoreCheckBtn(true);
    const icon = checkUpdatesBtn.querySelector('i');
    if (icon) icon.className = 'fas fa-spinner fa-spin';
    checkUpdatesBtn.querySelector('.btn-label').textContent = 'Descargando…';

    try {
      const res  = await fetch('/api/download/chapters', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type:        type,
          source:      refSource,
          content_id:  refId,
          title:       titleEl.textContent,
          chapter_ids: chapterIds,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        notify(`${data.message}`, 'success');
        if (window.showDownloadIndicator) window.showDownloadIndicator();
        // Quitar badge de novedades
        _showUpdateBadge(0);
      } else {
        notify(`Error al descargar: ${data.error}`, 'error');
      }
    } catch (err) {
      notify(`Error al descargar: ${err.message}`, 'error');
    }
  }

  function _restoreCheckBtn(skipIconRestore) {
    checkUpdatesBtn.disabled = false;
    if (!skipIconRestore) {
      const icon = checkUpdatesBtn.querySelector('i');
      if (icon) icon.className = 'fas fa-sync-alt';
    }
    checkUpdatesBtn.querySelector('.btn-label').textContent = 'Actualizar';
  }

  function _showUpdateBadge(count) {
    // Eliminar badge anterior si existe
    checkUpdatesBtn.querySelector('.update-badge')?.remove();
    if (count <= 0) return;
    const badge = document.createElement('span');
    badge.className = 'update-badge';
    badge.textContent = count;
    badge.style.cssText = `
      position: absolute;
      top: -6px; right: -6px;
      background: var(--accent2, #f59e0b);
      color: #000;
      font-size: 10px;
      font-weight: 700;
      border-radius: 999px;
      padding: 1px 5px;
      line-height: 1.4;
      pointer-events: none;
    `;
    checkUpdatesBtn.style.position = 'relative';
    checkUpdatesBtn.appendChild(badge);
  }

  // ── Progreso ───────────────────────────────────────────────────────────
  // [OPT-5] updateProgress() calcula el progreso desde los datos ya en memoria
  // cuando sea posible, sin fetches extra.
  async function loadProgress() {
    try {
      const url = isLocal
        ? `/api/progress/local/${type}/${id}`
        : `/api/progress/${type}/${source}/${id}`;
      const res  = await fetch(url);
      const prog = await res.json();

      if (currentChapterSpan) currentChapterSpan.textContent = prog.chapter;
      _progressData = prog; // cachear para updateProgress()
      await _renderProgress(prog);
    } catch (err) {
      console.error('loadProgress:', err);
      showNotification('Error al cargar progreso', 'error');
    }
  }

  let _progressData = null;

  // Actualiza la barra de progreso desde los datos cacheados.
  // Solo recalcula con fetch si el capítulo actual cambió.
  async function updateProgress() {
    if (!_progressData) return;
    await _renderProgress(_progressData);
  }

  async function _renderProgress(prog) {
    if (currentChapterSpan) currentChapterSpan.textContent = prog.chapter;

    if (type === 'anime') {
      const savedTime = parseInt(prog.progress) || 0;
      if (isLocal) {
        try {
          const durRes = await fetch(`/api/video-duration/anime/${id}/${prog.chapter}`);
          if (durRes.ok) {
            const { duration } = await durRes.json();
            if (duration > 0) {
              const pct = Math.round((savedTime / duration) * 100);
              if (progressPercentSpan) progressPercentSpan.textContent = `${pct}%`;
              if (progressBarFill)     progressBarFill.style.width     = `${pct}%`;
              return;
            }
          }
        } catch (e) { console.warn(e); }
      }
      const mins = Math.floor(savedTime / 60);
      const secs = savedTime % 60;
      if (progressPercentSpan)
        progressPercentSpan.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
    } else {
      const savedIndex = parseInt(prog.progress) || 0;
      if (isLocal) {
        // total = número de imágenes del capítulo actual (no de capítulos de la serie)
        const total = await getTotalImagesInChapter(prog.chapter);
        if (total > 1) {
          // Proteger contra división por cero cuando total - 1 = 0
          const pct = Math.min(100, Math.round((savedIndex / (total - 1)) * 100));
          if (progressPercentSpan) progressPercentSpan.textContent = `${pct}%`;
          if (progressBarFill)     progressBarFill.style.width     = `${pct}%`;
        } else if (total === 1) {
          if (progressPercentSpan) progressPercentSpan.textContent = '100%';
          if (progressBarFill)     progressBarFill.style.width     = '100%';
        } else {
          if (progressPercentSpan) progressPercentSpan.textContent = '?%';
        }
      } else {
        if (progressPercentSpan) progressPercentSpan.textContent = `Pág. ${savedIndex + 1}`;
      }
    }
  }

  async function getTotalImagesInChapter(chapterNum) {
    try {
      const res = await fetch(`/api/play/local/manga/${id}/${chapterNum}`);
      if (!res.ok) return 0;
      const paths = await res.json();
      return paths.length;
    } catch { return 0; }
  }

  // ── Init ──────────────────────────────────────────────────────────────
  // [OPT-1] Detalles + capítulos en paralelo; progreso después de capítulos
  // (necesita chapters[] para el cálculo de manga).
  async function init() {
    await Promise.all([
      loadSerieDetails(),
      loadChapters(),     // ya incluye watched en paralelo dentro
    ]);
    await loadProgress(); // ahora chapters[] está listo

    // ── Acknowledge updates ────────────────────────────────────────────
    // Al visitar una serie local con fuente remota, limpiar el flag de
    // novedades para que el badge global se actualice.
    if (isLocal && originalSource) {
      const contentRef = `${originalSource}:${originalId}`;
      fetch('/api/library/acknowledge-updates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content_ref: contentRef }),
      }).catch(() => {});
    }

    // Botones según contexto
    if (isLocal) {
      if (downloadAllBtn)   downloadAllBtn.classList.add('hidden');
      if (continueBtn)      continueBtn.classList.remove('hidden');
      if (deleteWatchedBtn) deleteWatchedBtn.classList.remove('hidden');
      if (checkUpdatesBtn) {
        if (originalSource) {
          checkUpdatesBtn.classList.remove('hidden');
          checkUpdatesBtn.addEventListener('click', checkForUpdates);
        } else {
          checkUpdatesBtn.classList.add('hidden');
        }
      }
    } else {
      if (downloadAllBtn)   downloadAllBtn.classList.remove('hidden');
      if (continueBtn)      continueBtn.classList.remove('hidden');
    }

    continueBtn?.addEventListener('click', () => {
      let last = currentChapterSpan?.textContent;
      if (!last || last === '—') last = '1';
      const src = isLocal ? 'local' : source;
      window.location.href = `/reader/${type}/${src}/${id}/${last}`;
    });

    downloadAllBtn?.addEventListener('click', downloadFullSeries);

    deleteWatchedBtn?.addEventListener('click', () => {
      showConfirm(
        '¿Eliminar todos los capítulos vistos (excepto el último)? Esta acción no se puede deshacer.',
        async () => {
          try {
            const ref = isLocal ? `local:${id}` : `${source}:${id}`;
            const res  = await fetch('/api/delete-watched', {
              method:  'POST',
              headers: { 'Content-Type': 'application/json' },
              body:    JSON.stringify({ content_ref: ref, type }),
            });
            const data = await res.json();
            if (res.ok) {
              const n = data.deleted?.length ?? 0;
              notify(`Se eliminaron ${n} capítulo${n !== 1 ? 's' : ''}`, 'success');
              // [OPT-2] Eliminar del array + DOM sin re-fetch
              const deletedNums = new Set((data.deleted || []).map(String));
              chapters = chapters.filter(c => !deletedNums.has(String(c.number)));
              deletedNums.forEach(num => {
                chaptersContainer.querySelector(`.chapter-pill[data-chapter="${num}"]`)?.remove();
              });
              if (chaptersCount) chaptersCount.textContent = `${chapters.length} capítulos`;
              await loadProgress();
            } else {
              notify(`Error: ${data.error || 'Error desconocido'}`, 'error');
            }
          } catch (err) {
            notify(`Error: ${err.message}`, 'error');
          }
        }
      );
    });

    sortBtn?.addEventListener('click', () => {
      sortAsc = !sortAsc;
      sortBtn.classList.toggle('sorted', !sortAsc);
      _teardownObserver();
      renderChapters();
    });

    // ── Download progress polling ──
    const contentRef = isLocal ? `local:${id}` : `${source}:${id}`;
    const dlProgress    = document.getElementById('serie-dl-progress');
    const dlLabel       = document.getElementById('serie-dl-label');
    const dlCount       = document.getElementById('serie-dl-count');
    const dlFill        = document.getElementById('serie-dl-fill');

    async function pollSerieDownloadProgress() {
      try {
        const res  = await fetch('/api/queue/status');
        const data = await res.json();
        const all   = [...(data.active || []), ...(data.queue || [])];
        const match = all.filter(j => j.content_ref === contentRef && (j.status === 'downloading' || j.status === 'pending'));

        if (match.length === 0) {
          dlProgress?.classList.add('hidden');
          return;
        }

        dlProgress?.classList.remove('hidden');

        const activeJob = match.find(j => j.status === 'downloading') || match[0];
        if (dlLabel) dlLabel.textContent = activeJob.status === 'downloading' ? 'Descargando…' : 'En cola';
        if (dlCount) dlCount.textContent = activeJob.total_chapters > 0 ? `${activeJob.current_chapter || 0}/${activeJob.total_chapters}` : '';
        if (dlFill) dlFill.style.width = `${activeJob.progress || 0}%`;
      } catch { /* ignore polling errors */ }
    }

    pollSerieDownloadProgress();
    setInterval(pollSerieDownloadProgress, 3000);
  }

  init();
})();