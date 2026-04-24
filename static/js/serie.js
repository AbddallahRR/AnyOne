// static/js/serie.js
(function () {
  if (!window.serieData) {
    console.error('serie.js: window.serieData no definido');
    return;
  }

  const { type, source, id } = window.serieData;
  const isLocal = source === 'local';

  let chapters     = [];
  let sortAsc      = true;

  // ── Elementos DOM ──────────────────────────────────────────────────────
  const coverImg          = document.getElementById('serie-cover');
  const titleEl           = document.getElementById('serie-title');
  const synopsisEl        = document.getElementById('serie-synopsis');
  const downloadAllBtn    = document.getElementById('download-all-btn');
  const continueBtn       = document.getElementById('continue-btn');
  const deleteWatchedBtn  = document.getElementById('delete-watched-btn');
  const currentChapterSpan = document.getElementById('current-chapter');
  const progressPercentSpan = document.getElementById('progress-percent');
  const progressBarFill   = document.getElementById('progress-bar-fill');
  const chaptersContainer = document.getElementById('chapters-list');
  const sortBtn           = document.getElementById('sort-btn');
  const chaptersCount     = document.getElementById('chapters-count');
  const badgeEl           = document.getElementById('serie-type-badge');

  function notify(msg, type = 'info') {
    if (window.showNotification) window.showNotification(msg, type);
    else console.log(`[${type}] ${msg}`);
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
      if (data.cover) coverImg.src = data.cover;

      if (badgeEl) {
        badgeEl.textContent  = type === 'anime' ? 'Anime' : 'Manga';
        badgeEl.className    = `card-badge ${type === 'anime' ? 'badge-anime' : 'badge-manga'}`;
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
      <div style="grid-column:1/-1; display:flex; align-items:center; justify-content:center; gap:12px; padding:48px 20px; color:var(--muted);">
        <div class="loading-spinner"></div>
        <span style="font-size:14px;">Cargando capítulos…</span>
      </div>`;

    try {
      let remote = [];
      let localSet = new Set();

      if (isLocal) {
        const res  = await fetch(`/api/chapters/local/${type}/${id}`);
        const data = res.ok ? await res.json() : [];
        remote = data.map(ch => ({ ...ch, is_downloaded: true }));
      } else {
        const [remoteRes, localRes] = await Promise.all([
          fetch(`/api/chapters/${type}/${source}/${id}`),
          fetch(`/api/chapters/local/${type}/${id}`),
        ]);
        remote = remoteRes.ok ? await remoteRes.json() : [];
        const localChaps = localRes.ok ? await localRes.json() : [];
        localSet = new Set(localChaps.map(ch => String(ch.number)));
        remote = remote.map(ch => ({ ...ch, is_downloaded: localSet.has(String(ch.number)) }));
      }

      // Capítulos vistos (solo local)
      let watchedSet = new Set();
      if (isLocal) {
        try {
          const res  = await fetch(`/api/watched/local:${id}`);
          const data = res.ok ? await res.json() : {};
          watchedSet = new Set((data.watched || []).map(Number));
        } catch (e) { console.warn(e); }
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

  // ── Render capítulos ───────────────────────────────────────────────────
  function renderChapters() {
    if (!chapters.length) {
      chaptersContainer.innerHTML = `
        <div class="empty-state" style="grid-column:1/-1;">
          <i class="fas fa-inbox"></i>
          <p>No se encontraron capítulos.</p>
        </div>`;
      return;
    }

    if (chaptersCount) chaptersCount.textContent = `${chapters.length} capítulos`;

    const sorted = sortAsc ? [...chapters] : [...chapters].reverse();

    chaptersContainer.innerHTML = sorted.map(ch => {
      const { number, id: chId, is_downloaded, is_watched } = ch;

      const watchedDot = is_watched
        ? `<span style="width:6px;height:6px;border-radius:50%;background:#4ade80;
                        flex-shrink:0;box-shadow:0 0 5px rgba(74,222,128,0.5);"></span>`
        : '';

      const playBtn = is_downloaded ? `
        <button class="play-chapter-btn" data-chapter="${number}" title="Reproducir" style="
          background:rgba(196,107,255,0.12); border:1px solid rgba(196,107,255,0.25);
          color:var(--accent); width:30px; height:30px; border-radius:7px; cursor:pointer;
          display:flex; align-items:center; justify-content:center; font-size:11px;
          transition:background .15s, transform .12s;">
          <i class="fas fa-play"></i>
        </button>` : `
        <button class="download-chapter-btn" data-chapter="${number}" data-chapter-id="${chId}" title="Descargar" style="
          background:rgba(255,255,255,0.05); border:1px solid var(--border);
          color:var(--muted); width:30px; height:30px; border-radius:7px; cursor:pointer;
          display:flex; align-items:center; justify-content:center; font-size:11px;
          transition:background .15s, color .15s, transform .12s;">
          <i class="fas fa-download"></i>
        </button>`;

      const localBtns = isLocal ? `
        <button class="watched-toggle-btn" data-chapter="${number}"
          title="${is_watched ? 'Quitar visto' : 'Marcar visto'}" style="
          background:${is_watched ? 'rgba(74,222,128,0.1)' : 'rgba(255,255,255,0.05)'};
          border:1px solid ${is_watched ? 'rgba(74,222,128,0.25)' : 'var(--border)'};
          color:${is_watched ? '#4ade80' : 'var(--muted)'};
          width:30px; height:30px; border-radius:7px; cursor:pointer;
          display:flex; align-items:center; justify-content:center; font-size:11px;
          transition:background .15s, color .15s, transform .12s;">
          <i class="fas fa-check"></i>
        </button>
        <button class="delete-chapter-btn" data-chapter="${number}" title="Eliminar" style="
          background:rgba(255,255,255,0.05); border:1px solid var(--border);
          color:var(--muted); width:30px; height:30px; border-radius:7px; cursor:pointer;
          display:flex; align-items:center; justify-content:center; font-size:11px;
          transition:background .15s, color .15s, transform .12s;">
          <i class="fas fa-trash-alt"></i>
        </button>` : '';

      return `
        <div class="chapter-pill ${is_downloaded ? 'downloaded' : ''}"
             style="border-color:${is_watched ? 'rgba(74,222,128,0.2)' : 'var(--border)'};">
          <div style="display:flex; align-items:center; gap:8px; min-width:0; flex:1;">
            <span style="font-size:13px; font-weight:500;
                         color:${is_watched ? 'var(--muted)' : 'var(--text)'};
                         white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
              Cap. ${number}
            </span>
            ${watchedDot}
          </div>
          <div style="display:flex; align-items:center; gap:6px; flex-shrink:0;">
            ${playBtn}
            ${localBtns}
          </div>
        </div>`;
    }).join('');

    bindChapterEvents();

    // Stagger animation (MutationObserver en serie.html lo dispara, pero por si acaso)
    if (window.animateCards) window.animateCards('#chapters-list', '.chapter-pill');
  }

  function bindChapterEvents() {
    chaptersContainer.querySelectorAll('.play-chapter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        window.location.href = `/reader/${type}/${source}/${id}/${btn.dataset.chapter}`;
      });
      btn.addEventListener('mouseenter', () => { btn.style.transform = 'scale(1.08)'; btn.style.background = 'rgba(196,107,255,0.22)'; });
      btn.addEventListener('mouseleave', () => { btn.style.transform = '';             btn.style.background = 'rgba(196,107,255,0.12)'; });
    });

    chaptersContainer.querySelectorAll('.download-chapter-btn').forEach(btn => {
      btn.addEventListener('click', () => downloadSingleChapter(btn.dataset.chapter, btn.dataset.chapterId));
      btn.addEventListener('mouseenter', () => { btn.style.transform = 'scale(1.08)'; btn.style.color = 'var(--text)'; });
      btn.addEventListener('mouseleave', () => { btn.style.transform = '';             btn.style.color = 'var(--muted)'; });
    });

    chaptersContainer.querySelectorAll('.watched-toggle-btn').forEach(btn => {
      btn.addEventListener('click', e => { e.stopPropagation(); toggleWatched(btn.dataset.chapter); });
    });

    chaptersContainer.querySelectorAll('.delete-chapter-btn').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        showConfirm(
          `¿Eliminar el capítulo ${btn.dataset.chapter}? Esta acción no se puede deshacer.`,
          () => deleteChapter(btn.dataset.chapter)
        );
      });
      btn.addEventListener('mouseenter', () => { btn.style.color = '#f87171'; btn.style.borderColor = 'rgba(248,113,113,0.3)'; });
      btn.addEventListener('mouseleave', () => { btn.style.color = 'var(--muted)'; btn.style.borderColor = 'var(--border)'; });
    });
  }

  // ── Confirm dialog (reemplaza window.confirm) ──────────────────────────
  function showConfirm(message, onConfirm) {
    // Usar el modal existente de base.html como diálogo de confirmación
    const modalTitle = document.getElementById('modal-title');
    const modalBody  = document.getElementById('modal-body');
    if (!modalTitle || !modalBody) {
      // Fallback si el modal no está disponible
      if (window.confirm(message)) onConfirm();
      return;
    }
    modalTitle.textContent = 'Confirmar acción';
    modalBody.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:20px;">
        <p style="color:var(--text); font-size:14px; line-height:1.6;">${message}</p>
        <div style="display:flex; gap:10px; justify-content:flex-end;">
          <button id="confirm-cancel" class="btn-ghost">Cancelar</button>
          <button id="confirm-ok" class="btn-primary" style="background:#f87171;">
            <i class="fas fa-trash-alt"></i> Eliminar
          </button>
        </div>
      </div>`;
    if (window.openModal) window.openModal();

    document.getElementById('confirm-cancel').addEventListener('click', () => {
      if (window.closeModal) window.closeModal();
    });
    document.getElementById('confirm-ok').addEventListener('click', () => {
      if (window.closeModal) window.closeModal();
      onConfirm();
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
        notify(`Cap. ${chapterNum} marcado como ${data.status === 'watched' ? 'visto' : 'no visto'}`, 'success');
        await loadChapters();
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
        await loadChapters();
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

  // ── Progreso ───────────────────────────────────────────────────────────
  async function loadProgress() {
    try {
      const url  = isLocal
        ? `/api/progress/local/${type}/${id}`
        : `/api/progress/${type}/${source}/${id}`;
      const res  = await fetch(url);
      const prog = await res.json();

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
        // Manga
        const savedIndex = parseInt(prog.progress) || 0;
        if (isLocal) {
          const total = await getTotalImagesInChapter(prog.chapter);
          if (total > 0) {
            const pct = Math.round((savedIndex / (total - 1)) * 100);
            if (progressPercentSpan) progressPercentSpan.textContent = `${pct}%`;
            if (progressBarFill)     progressBarFill.style.width     = `${pct}%`;
          } else {
            if (progressPercentSpan) progressPercentSpan.textContent = '?%';
          }
        } else {
          if (progressPercentSpan) progressPercentSpan.textContent = '—';
        }
      }
    } catch (err) {
      console.error('loadProgress:', err);
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

  // ── Inicializar ────────────────────────────────────────────────────────
  async function init() {
    await loadSerieDetails();
    await loadChapters();
    await loadProgress();

    // Visibilidad de botones según contexto
    if (isLocal) {
      downloadAllBtn?.style && (downloadAllBtn.style.display = 'none');
      if (continueBtn)  continueBtn.style.display  = 'inline-flex';
      if (deleteWatchedBtn) deleteWatchedBtn.style.display = 'inline-flex';
    } else {
      if (downloadAllBtn) downloadAllBtn.style.display = 'inline-flex';
      if (continueBtn)    continueBtn.style.display    = 'none';
      if (deleteWatchedBtn) deleteWatchedBtn.style.display = 'none';
      const progressSection = document.getElementById('progress-section');
      if (progressSection) progressSection.style.display = 'none';
    }

    // Continuar
    continueBtn?.addEventListener('click', () => {
      let last = currentChapterSpan?.textContent;
      if (!last || last === '—') last = '1';
      window.location.href = `/reader/${type}/local/${id}/${last}`;
    });

    // Descargar serie
    downloadAllBtn?.addEventListener('click', downloadFullSeries);

    // Borrar vistos
    deleteWatchedBtn?.addEventListener('click', () => {
      showConfirm(
        '¿Eliminar todos los capítulos vistos (excepto el último)? Esta acción no se puede deshacer.',
        async () => {
          try {
            const res  = await fetch('/api/delete-watched', {
              method:  'POST',
              headers: { 'Content-Type': 'application/json' },
              body:    JSON.stringify({ content_ref: `local:${id}`, type }),
            });
            const data = await res.json();
            if (res.ok) {
              const n = data.deleted?.length ?? 0;
              notify(`Se eliminaron ${n} capítulo${n !== 1 ? 's' : ''}`, 'success');
              await loadChapters();
            } else {
              notify(`Error: ${data.error || 'Error desconocido'}`, 'error');
            }
          } catch (err) {
            notify(`Error: ${err.message}`, 'error');
          }
        }
      );
    });

    // Ordenar capítulos
    sortBtn?.addEventListener('click', () => {
      sortAsc = !sortAsc;
      sortBtn.classList.toggle('sorted', !sortAsc);
      renderChapters();
    });
  }

  init();
})();