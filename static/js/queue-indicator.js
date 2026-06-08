// static/js/queue-indicator.js
(function () {
  if (window.location.pathname.startsWith('/reader/')) return;

  // ── Inyectar estilos ───────────────────────────────────────────────────
  if (!document.getElementById('qi-styles')) {
    const style = document.createElement('style');
    style.id = 'qi-styles';
    style.textContent = `
      #qi-indicator {
        position: fixed;
        top: var(--qi-top, 14px);
        right: 14px;
        background: rgba(10,10,15,0.88);
        border: 1px solid rgba(255,255,255,0.12);
        color: var(--text, #e8e8f0);
        border-radius: 10px;
        padding: 6px 12px;
        font-size: 12px;
        font-family: var(--ff-body, sans-serif);
        z-index: 10000;
        cursor: pointer;
        backdrop-filter: blur(12px);
        box-shadow: 0 4px 20px rgba(0,0,0,0.4);
        display: none;
        align-items: center;
        gap: 8px;
        max-width: 220px;
        opacity: 0;
        transform: translateY(-8px);
        transition: opacity 0.22s ease, transform 0.22s ease;
      }
      #qi-indicator.visible {
        display: flex;
        opacity: 1;
        transform: translateY(0);
      }
      #qi-indicator i {
        color: var(--accent, #c46bff);
        font-size: 13px;
        flex-shrink: 0;
      }
      #qi-label {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        flex: 1;
        min-width: 0;
      }
      #qi-count {
        background: rgba(196,107,255,0.2);
        color: var(--accent, #c46bff);
        border-radius: 5px;
        padding: 1px 6px;
        font-size: 11px;
        font-weight: 600;
        flex-shrink: 0;
      }

      /* ── Popup ── */
      #qi-popup {
        position: fixed;
        top: var(--qi-popup-top, 58px);
        right: 14px;
        background: rgba(10,10,15,0.95);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 14px;
        padding: 14px;
        min-width: 280px;
        max-width: 360px;
        max-height: 420px;
        overflow-y: auto;
        z-index: 9999;
        backdrop-filter: blur(16px);
        box-shadow: 0 8px 32px rgba(0,0,0,0.5);
        font-size: 12px;
        font-family: var(--ff-body, sans-serif);
        color: var(--text, #e8e8f0);
        display: none;
        flex-direction: column;
        gap: 10px;
        opacity: 0;
        transform: translateY(-8px) scale(0.97);
        transition: opacity 0.2s ease, transform 0.2s ease;
      }
      #qi-popup.open {
        opacity: 1;
        transform: translateY(0) scale(1);
      }
      .qi-section-title {
        font-size: 11px;
        font-weight: 600;
        color: var(--muted, #7a7a8a);
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 6px;
      }
      .qi-job {
        background: var(--raised, #18181f);
        border: 1px solid rgba(255,255,255,0.07);
        border-radius: 9px;
        padding: 8px 10px;
        display: flex;
        flex-direction: column;
        gap: 5px;
      }
      .qi-job-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
      }
      .qi-job-title {
        font-weight: 500;
        font-size: 12px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        flex: 1;
        min-width: 0;
      }
      .qi-job-status {
        font-size: 10px;
        padding: 2px 7px;
        border-radius: 5px;
        flex-shrink: 0;
        font-weight: 500;
      }
      .qi-status-downloading {
        background: rgba(196,107,255,0.15);
        color: var(--accent, #c46bff);
      }
      .qi-status-pending {
        background: rgba(255,255,255,0.07);
        color: var(--muted, #7a7a8a);
      }
      .qi-status-failed {
        background: rgba(248,113,113,0.15);
        color: #f87171;
      }
      .qi-progress-bar {
        height: 2px;
        background: rgba(255,255,255,0.07);
        border-radius: 2px;
        overflow: hidden;
      }
      .qi-progress-fill {
        height: 100%;
        background: linear-gradient(90deg, var(--accent, #c46bff), #ff6b9d);
        border-radius: 2px;
        transition: width 0.4s ease;
      }
      .qi-progress-text {
        font-size: 10px;
        color: var(--muted, #7a7a8a);
        display: flex;
        justify-content: space-between;
      }
      .qi-error-text {
        font-size: 11px;
        color: #f87171;
        background: rgba(248,113,113,0.08);
        border: 1px solid rgba(248,113,113,0.2);
        border-radius: 6px;
        padding: 5px 8px;
        line-height: 1.4;
        word-break: break-word;
      }
      .qi-empty {
        text-align: center;
        color: var(--muted, #7a7a8a);
        padding: 16px;
        font-size: 12px;
      }
      .qi-popup-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding-bottom: 8px;
        border-bottom: 1px solid rgba(255,255,255,0.07);
        margin-bottom: 2px;
      }
      .qi-popup-title {
        font-family: var(--ff-head, sans-serif);
        font-size: 13px;
        font-weight: 700;
        color: var(--text, #e8e8f0);
      }
      .qi-close {
        width: 24px; height: 24px;
        border-radius: 6px;
        border: 1px solid rgba(255,255,255,0.08);
        background: transparent;
        color: var(--muted, #7a7a8a);
        font-size: 14px;
        cursor: pointer;
        display: flex; align-items: center; justify-content: center;
        transition: background 0.15s, color 0.15s, transform 0.15s;
      }
      .qi-close:hover { background: rgba(255,255,255,0.07); color: var(--text); transform: rotate(90deg); }

      @media (max-width: 640px) {
        #qi-indicator { right: 10px; }
        #qi-popup { right: 10px; left: 10px; max-width: none; }
      }
    `;
    document.head.appendChild(style);
  }

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
        <span class="qi-popup-title">Cola de descarga</span>
        <button class="qi-close" id="qi-close-btn">×</button>
      </div>
      <div id="qi-list"></div>`;
    document.body.appendChild(popup);
  }

  // ── Estado ─────────────────────────────────────────────────────────────
  let pollingTimer     = null;
  let forceUntil       = 0;
  let popupOpen        = false;

  // ── Helpers ────────────────────────────────────────────────────────────
  function showIndicator() {
    indicator.style.display = 'flex';
    requestAnimationFrame(() => requestAnimationFrame(() => indicator.classList.add('visible')));
  }
  function hideIndicator() {
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
    const pct           = job.progress || 0;
    const cap           = job.current_chapter || 0;
    const total         = job.total_chapters || '?';

    let statusBadge = '';
    if (isDownloading) statusBadge = `<span class="qi-job-status qi-status-downloading">Descargando</span>`;
    else if (isFailed)  statusBadge = `<span class="qi-job-status qi-status-failed">Error</span>`;
    else                statusBadge = `<span class="qi-job-status qi-status-pending">En cola</span>`;

    let progressHtml = '';
    if (isDownloading) {
      progressHtml = `
        <div class="qi-progress-bar">
          <div class="qi-progress-fill" style="width:${pct}%"></div>
        </div>
        <div class="qi-progress-text">
          <span>Cap. ${cap}/${total}</span>
          <span>${pct}%</span>
        </div>`;
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
        ${errorHtml}
      </div>`;
  }

  // ── Fetch y render del estado de la cola ──────────────────────────────
  async function fetchQueueStatus() {
    try {
      const res  = await fetch('/api/queue/status');
      const data = await res.json();
      const active  = data.active  || [];
      const pending = (data.queue  || []).filter(j => j.status === 'pending');
      const failed  = (data.queue  || []).filter(j => j.status === 'failed');

      const hasActivity = active.length > 0 || pending.length > 0;
      const label       = document.getElementById('qi-label');
      const countBadge  = document.getElementById('qi-count');

      // ── Texto del indicador (truncado) ──
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

      // ── Contenido del popup ──
      const listDiv = document.getElementById('qi-list');
      if (listDiv) {
        let html = '';

        if (active.length) {
          html += `<div class="qi-section-title">Descargando ahora</div>`;
          html += active.map(buildJobHtml).join('');
        }
        if (pending.length) {
          html += `<div class="qi-section-title" style="margin-top:${active.length ? 10 : 0}px;">En cola</div>`;
          html += pending.map(buildJobHtml).join('');
        }
        if (failed.length) {
          html += `<div class="qi-section-title" style="margin-top:${active.length || pending.length ? 10 : 0}px; color:#f87171;">Errores recientes</div>`;
          html += failed.map(buildJobHtml).join('');
        }
        if (!active.length && !pending.length && !failed.length) {
          html = `<div class="qi-empty"><i class="fas fa-check-circle" style="margin-right:6px; color:#4ade80;"></i>Sin actividad</div>`;
        }
        listDiv.innerHTML = html;
      }

      // ── Polling ──
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
  indicator.addEventListener('click', e => {
    e.stopPropagation();
    if (popupOpen) closePopup();
    else { fetchQueueStatus().then(openPopup); }
  });

  document.getElementById('qi-close-btn')?.addEventListener('click', closePopup);

  document.addEventListener('click', e => {
    if (popupOpen && !indicator.contains(e.target) && !popup.contains(e.target))
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