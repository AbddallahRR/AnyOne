// static/js/queue-indicator.js
(function () {
  if (window.location.pathname.startsWith('/reader/')) return;

  // Estilos en queue-indicator.css (cargado desde base.html)

  // ── Posicionar bajo el nav ─────────────────────────────────────────────
  function positionUnderNav() {
    const nav = document.querySelector('.app-nav') || document.querySelector('nav');
    if (!nav) return;
    const navBottom = nav.getBoundingClientRect().bottom;
    const offset = navBottom + 10;
    document.documentElement.style.setProperty('--qi-top', offset + 'px');
    document.documentElement.style.setProperty('--qi-popup-top', (offset + 44) + 'px');
  }

  positionUnderNav();

  // Re-calcular si el nav cambia de altura (responsive wrap)
  if (window.ResizeObserver) {
    const nav = document.querySelector('.app-nav') || document.querySelector('nav');
    if (nav) new ResizeObserver(positionUnderNav).observe(nav);
  }

  // ── Crear indicador ────────────────────────────────────────────────────
  let indicator = document.getElementById('qi-indicator');
  if (!indicator) {
    indicator = document.createElement('div');
    indicator.id = 'qi-indicator';
    indicator.innerHTML = `
      <i class="fas fa-arrow-down"></i>
      <span id="qi-label">Descargando…</span>
      <span id="qi-count" style="display:none;"></span>`;
    document.body.appendChild(indicator);
  }

  // ── Crear popup ────────────────────────────────────────────────────────
  let popup = document.getElementById('qi-popup');
  if (!popup) {
    popup = document.createElement('div');
    popup.id = 'qi-popup';
    popup.innerHTML = `
      <div class="qi-popup-header">
        <span class="qi-popup-title">Descargas recientes</span>
        <button class="qi-close" id="qi-close-btn">×</button>
      </div>
      <div id="qi-list"></div>`;
    document.body.appendChild(popup);
  }

  // En Inicio hay un botón en la nav que abre la barra; en el resto de páginas
  // se usa el pill flotante de siempre.
  const downloadBtn = document.getElementById('nav-downloads');
  const useButton   = !!downloadBtn;

  function updateButtonBadge(n) {
    if (!downloadBtn) return;
    let b = downloadBtn.querySelector('.dl-badge');
    if (n > 0) {
      if (!b) {
        b = document.createElement('span');
        b.className = 'dl-badge';
        downloadBtn.appendChild(b);
      }
      b.textContent = n > 99 ? '99+' : n;
    } else if (b) {
      b.remove();
    }
  }

  // ── BroadcastChannel (compartir polling entre pestañas) ────────────────
  let _bc = null;
  try {
    _bc = new BroadcastChannel('anyone:queue');
    _bc.onmessage = (ev) => {
      if (ev.data?.type === 'queue') {
        const hasActivity = _applyQueueData(ev.data.data);
        forceUntil = Date.now() + 5000;
        handleQueueSnapshot(hasActivity);
        scheduleNext(3000);
      } else if (ev.data?.type === 'complete') {
        window.dispatchEvent(new CustomEvent('anyone:downloads-complete'));
      }
    };
  } catch (_) { /* BroadcastChannel no soportado */ }

  // ── Estado ─────────────────────────────────────────────────────────────
  let pollingTimer     = null;
  let forceUntil       = 0;
  let popupOpen        = false;
  let hadActivity      = false;

  // ── Helpers ────────────────────────────────────────────────────────────
  function showIndicator() {
    if (useButton) return;   // en Inicio el indicador es el badge del botón
    indicator.style.display = 'flex';
    requestAnimationFrame(() => requestAnimationFrame(() => indicator.classList.add('visible')));
  }
  function hideIndicator() {
    if (useButton) return;
    indicator.classList.remove('visible');
    setTimeout(() => { indicator.style.display = 'none'; }, 250);
  }
  function openPopup() {
    popupOpen = true;
    popup.style.display = 'flex';
    requestAnimationFrame(() => requestAnimationFrame(() => popup.classList.add('open')));
  }
  function closePopup() {
    popupOpen = false;
    popup.classList.remove('open');
    setTimeout(() => { popup.style.display = 'none'; }, 220);
  }

  function truncate(str, max = 28) {
    return str && str.length > max ? str.slice(0, max - 1) + '…' : (str || '');
  }

  // ── Construir HTML de un job ───────────────────────────────────────────
  function buildJobHtml(job) {
    const isDownloading = job.status === 'downloading';
    const isFailed      = job.status === 'failed';
    const fp            = job.file_progress || null;
    const singleChapter = !job.total_chapters || job.total_chapters <= 1;
    const pct           = job.progress || 0;
    const cap           = job.current_chapter || 0;
    const total         = job.total_chapters || '?';

    let statusBadge = '';
    if (isDownloading) statusBadge = `<span class="qi-job-status qi-status-downloading">Descargando</span>`;
    else if (isFailed)  statusBadge = `<span class="qi-job-status qi-status-failed">Error</span>`;
    else                statusBadge = `<span class="qi-job-status qi-status-pending">En cola</span>`;

    // Barra principal: progreso por capítulos. En descargas de 1 capítulo
    // (total_chapters <= 1) refleja el progreso del archivo en curso.
    let mainPct  = pct;
    let mainText = `Cap. ${cap}/${total}`;
    let mainIndeterminate = false;
    if (isDownloading && singleChapter && fp) {
      mainText           = fp.label || 'Descargando…';
      mainIndeterminate  = !!fp.indeterminate;
      if (!mainIndeterminate) mainPct = fp.percent;
    }

    let progressHtml = '';
    if (isDownloading) {
      const fill = mainIndeterminate
        ? '<div class="qi-progress-fill"></div>'
        : `<div class="qi-progress-fill" style="width:${mainPct}%"></div>`;
      progressHtml = `
        <div class="qi-progress-bar${mainIndeterminate ? ' indeterminate' : ''}">
          ${fill}
        </div>
        <div class="qi-progress-text">
          <span>${mainText}</span>
          <span>${mainIndeterminate ? '…' : mainPct + '%'}</span>
        </div>`;
    }

    // Barra del archivo en curso (descargas de serie con progreso de bytes)
    let fileProgressHtml = '';
    if (isDownloading && !singleChapter && fp) {
      if (fp.indeterminate) {
        fileProgressHtml = `
          <div class="qi-file-progress">
            <div class="qi-progress-bar indeterminate"><div class="qi-progress-fill"></div></div>
            <div class="qi-progress-text"><span>${fp.label || 'Descargando…'}</span><span>…</span></div>
          </div>`;
      } else {
        fileProgressHtml = `
          <div class="qi-file-progress">
            <div class="qi-progress-bar"><div class="qi-progress-fill" style="width:${fp.percent}%"></div></div>
            <div class="qi-progress-text"><span>${fp.label || 'Descargando…'}</span><span>${fp.percent}%</span></div>
          </div>`;
      }
    }

    let errorHtml = '';
    if (isFailed && job.error) {
      errorHtml = `<div class="qi-error-text"><i class="fas fa-exclamation-triangle" style="margin-right:5px;"></i>${job.error}</div>`;
    }

    return `
      <div class="qi-job">
        <div class="qi-job-header">
          <span class="qi-job-title" title="${(job.title || '').replace(/"/g,'&quot;')}">${job.title || '—'}</span>
          ${statusBadge}
        </div>
        ${progressHtml}
        ${fileProgressHtml}
        ${errorHtml}
      </div>`;
  }

  // ── Renderizar datos de cola (desde fetch o broadcast) ────────────────
  function _applyQueueData(data) {
    const active  = data.active  || [];
    const pending = (data.queue  || []).filter(j => j.status === 'pending');
    const failed  = (data.queue  || []).filter(j => j.status === 'failed');

    const hasActivity = active.length > 0 || pending.length > 0;
    const label       = document.getElementById('qi-label');
    const countBadge  = document.getElementById('qi-count');

    updateButtonBadge(active.length + pending.length);

    if (active.length > 0) {
      const best = active.reduce((a, b) => (a.progress > b.progress ? a : b), active[0]);
      if (label) label.textContent = truncate(best.title);
      if (countBadge) {
        countBadge.style.display = active.length > 1 ? 'inline' : 'none';
        countBadge.textContent   = `+${active.length - 1}`;
      }
      showIndicator();
    } else if (pending.length > 0) {
      if (label) label.textContent = `En cola: ${pending.length}`;
      if (countBadge) countBadge.style.display = 'none';
      showIndicator();
    } else if (failed.length > 0 && Date.now() < forceUntil) {
      if (label) label.textContent = `${failed.length} error${failed.length > 1 ? 'es' : ''}`;
      if (countBadge) countBadge.style.display = 'none';
      showIndicator();
    } else if (!hasActivity && Date.now() >= forceUntil) {
      hideIndicator();
    }

    const listDiv = document.getElementById('qi-list');
    if (listDiv) {
      // Solo las últimas descargas (activas primero, luego en cola), cap a 5.
      const latest = [...active, ...pending, ...failed].slice(0, 5);
      listDiv.innerHTML = latest.length
        ? latest.map(buildJobHtml).join('')
        : `<div class="qi-empty"><i class="fas fa-check-circle" style="margin-right:6px; color:#4ade80;"></i>Sin actividad</div>`;
    }

    return hasActivity;
  }

  // ── Aviso de descarga terminada ────────────────────────────────────────
  function onQueueFinished() {
    window.dispatchEvent(new CustomEvent('anyone:downloads-complete'));
    if (_bc) _bc.postMessage({ type: 'complete' });
  }

  // Detecta la transición cola activa → vacía. Se llama con cada snapshot
  // (fetch propio o broadcast de otra pestaña) sin depender de forceUntil.
  function handleQueueSnapshot(hasActivity) {
    if (hadActivity && !hasActivity) onQueueFinished();
    hadActivity = hasActivity;
  }

  // ── Fetch y render del estado de la cola ──────────────────────────────
  async function fetchQueueStatus() {
    try {
      const data = await api.get('/api/queue/status');
      const hasActivity = _applyQueueData(data);
      if (_bc) _bc.postMessage({ type: 'queue', data });

      handleQueueSnapshot(hasActivity);

      if (hasActivity) {
        forceUntil = Date.now() + 5000;
        scheduleNext(2000);
      } else if (Date.now() < forceUntil) {
        scheduleNext(2000);
      } else {
        clearPolling();
      }
    } catch (err) {
      console.error('queue-indicator:', err);
      showNotification('Error al consultar cola de descarga', 'error');
      scheduleNext(5000);
    }
  }

  function scheduleNext(ms) {
    clearPolling();
    pollingTimer = setTimeout(fetchQueueStatus, ms);
  }
  function clearPolling() {
    if (pollingTimer) { clearTimeout(pollingTimer); pollingTimer = null; }
  }

  // ── Eventos ────────────────────────────────────────────────────────────
  function togglePopup(e) {
    if (e) e.stopPropagation();
    if (popupOpen) closePopup();
    else { fetchQueueStatus().then(openPopup); }
  }

  indicator.addEventListener('click', togglePopup);
  downloadBtn?.addEventListener('click', togglePopup);

  document.getElementById('qi-close-btn')?.addEventListener('click', closePopup);

  document.addEventListener('click', e => {
    if (popupOpen && !indicator.contains(e.target) && !popup.contains(e.target)
        && !(downloadBtn && downloadBtn.contains(e.target)))
      closePopup();
  });

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && popupOpen) closePopup();
  });

  // ── API pública ────────────────────────────────────────────────────────
  window.showDownloadIndicator = function () {
    forceUntil = Date.now() + 10000;
    showIndicator();
    clearPolling();
    fetchQueueStatus();
  };

  // ── Arrancar ───────────────────────────────────────────────────────────
  fetchQueueStatus();
})();