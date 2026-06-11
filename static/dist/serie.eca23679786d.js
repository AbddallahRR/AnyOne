(function () {
  'use strict';

  window.showNotification = function (message, type = 'info', duration = 3500) {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      Object.assign(container.style, {
        position: 'fixed',
        bottom: '24px',
        right: '24px',
        zIndex: '10001',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        pointerEvents: 'none',
        maxWidth: '320px',
      });
      document.body.appendChild(container);
    }

    const colors = {
      success: { bg: 'rgba(74,222,128,0.15)', border: 'rgba(74,222,128,0.3)', icon: '✓' },
      error: { bg: 'rgba(248,113,113,0.15)', border: 'rgba(248,113,113,0.3)', icon: '✕' },
      info: { bg: 'rgba(196,107,255,0.12)', border: 'rgba(196,107,255,0.25)', icon: 'ℹ' },
    };
    const c = colors[type] || colors.info;

    const toast = document.createElement('div');
    Object.assign(toast.style, {
      background: c.bg,
      border: `1px solid ${c.border}`,
      backdropFilter: 'blur(12px)',
      color: 'var(--text)',
      padding: '10px 14px',
      borderRadius: '10px',
      fontSize: '13px',
      fontFamily: 'var(--ff-body)',
      pointerEvents: 'auto',
      boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
      opacity: '0',
      transform: 'translateX(20px)',
      transition: 'opacity 0.22s ease, transform 0.22s ease',
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
    });
    toast.innerHTML = `<span style="flex-shrink:0;opacity:0.8;">${c.icon}</span><span>${message}</span>`;
    container.appendChild(toast);

    requestAnimationFrame(() => requestAnimationFrame(() => {
      toast.style.opacity = '1';
      toast.style.transform = 'translateX(0)';
    }));

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(20px)';
      setTimeout(() => toast.remove(), 250);
    }, duration);
  };
})();

(function () {
  'use strict';

  window.showConfirm = function (title, message, okLabel, okClass) {
    return new Promise(function (resolve) {
      var overlay = document.createElement('div');
      overlay.className = 'confirm-overlay';
      overlay.innerHTML =
        '<div class="confirm-dialog">' +
          '<h3>' + title + '</h3>' +
          '<p>' + message + '</p>' +
          '<div class="confirm-actions">' +
            '<button class="btn-ghost" id="confirm-cancel">Cancelar</button>' +
            '<button class="btn-primary' + (okClass ? ' ' + okClass : '') + '" id="confirm-ok">' + (okLabel || 'Continuar') + '</button>' +
          '</div>' +
        '</div>';
      document.body.appendChild(overlay);

      var resolveAndClose = function (value) {
        overlay.remove();
        resolve(value);
      };

      overlay.querySelector('#confirm-ok').onclick = function () { resolveAndClose(true); };
      overlay.querySelector('#confirm-cancel').onclick = function () { resolveAndClose(false); };
      overlay.onclick = function (e) { if (e.target === overlay) { resolveAndClose(false); } };
    });
  };
})();

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
// static/js/scraper-health.js
(function () {
  if (window.location.pathname.startsWith('/reader/')) return;

  // ── Estilos ─────────────────────────────────────────────────────────────
  if (!document.getElementById('sh-styles')) {
    const style = document.createElement('style');
    style.id = 'sh-styles';
    style.textContent = `
      #sh-indicator {
        position: fixed;
        top: var(--sh-top, 14px);
        left: 14px;
        background: rgba(10,10,15,0.88);
        border: 1px solid rgba(248,113,113,0.25);
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
        max-width: 260px;
        opacity: 0;
        transform: translateY(-8px);
        transition: opacity 0.22s ease, transform 0.22s ease;
      }
      #sh-indicator.visible {
        display: flex;
        opacity: 1;
        transform: translateY(0);
      }
      #sh-indicator i {
        color: #f87171;
        font-size: 13px;
        flex-shrink: 0;
      }
      #sh-label {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        flex: 1;
        min-width: 0;
      }
      #sh-count {
        background: rgba(248,113,113,0.2);
        color: #f87171;
        border-radius: 5px;
        padding: 1px 6px;
        font-size: 11px;
        font-weight: 600;
        flex-shrink: 0;
      }

      #sh-popup {
        position: fixed;
        top: var(--sh-popup-top, 58px);
        left: 14px;
        background: rgba(10,10,15,0.95);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 14px;
        padding: 14px;
        min-width: 300px;
        max-width: 400px;
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
      #sh-popup.open {
        opacity: 1;
        transform: translateY(0) scale(1);
      }
      .sh-entry {
        background: var(--raised, #18181f);
        border: 1px solid rgba(255,255,255,0.07);
        border-radius: 9px;
        padding: 10px 12px;
      }
      .sh-entry-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        margin-bottom: 6px;
      }
      .sh-entry-name {
        font-weight: 600;
        font-size: 12px;
      }
      .sh-entry-badge {
        font-size: 10px;
        padding: 2px 7px;
        border-radius: 5px;
        flex-shrink: 0;
        font-weight: 500;
      }
      .sh-badge-error {
        background: rgba(248,113,113,0.15);
        color: #f87171;
      }
      .sh-badge-disabled {
        background: rgba(251,191,36,0.15);
        color: #fbbf24;
      }
      .sh-entry-error {
        font-size: 11px;
        color: #f87171;
        background: rgba(248,113,113,0.08);
        border: 1px solid rgba(248,113,113,0.2);
        border-radius: 6px;
        padding: 5px 8px;
        line-height: 1.4;
        word-break: break-word;
        margin-bottom: 6px;
      }
      .sh-entry-meta {
        font-size: 10px;
        color: var(--muted, #7a7a8a);
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .sh-re-enable-btn {
        background: rgba(74,222,128,0.12);
        color: #4ade80;
        border: 1px solid rgba(74,222,128,0.25);
        border-radius: 6px;
        padding: 3px 10px;
        font-size: 10px;
        font-weight: 500;
        cursor: pointer;
        font-family: var(--ff-body, sans-serif);
        transition: background 0.15s;
      }
      .sh-re-enable-btn:hover {
        background: rgba(74,222,128,0.22);
      }
      .sh-popup-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding-bottom: 8px;
        border-bottom: 1px solid rgba(255,255,255,0.07);
        margin-bottom: 2px;
      }
      .sh-popup-title {
        font-family: var(--ff-head, sans-serif);
        font-size: 13px;
        font-weight: 700;
        color: var(--text, #e8e8f0);
      }
      .sh-close {
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
      .sh-close:hover { background: rgba(255,255,255,0.07); color: var(--text); transform: rotate(90deg); }
      .sh-empty {
        text-align: center;
        color: var(--muted, #7a7a8a);
        padding: 16px;
        font-size: 12px;
      }

      @media (max-width: 640px) {
        #sh-indicator { left: 10px; }
        #sh-popup { left: 10px; right: 10px; max-width: none; }
      }
    `;
    document.head.appendChild(style);
  }

  // ── Posicionamiento ───────────────────────────────────────────────────
  function positionUnderNav() {
    const nav = document.querySelector('.app-nav') || document.querySelector('nav');
    if (!nav) return;
    const navBottom = nav.getBoundingClientRect().bottom;
    const offset = navBottom + 10;
    document.documentElement.style.setProperty('--sh-top', offset + 'px');
    document.documentElement.style.setProperty('--sh-popup-top', (offset + 44) + 'px');
  }

  positionUnderNav();
  if (window.ResizeObserver) {
    const nav = document.querySelector('.app-nav') || document.querySelector('nav');
    if (nav) new ResizeObserver(positionUnderNav).observe(nav);
  }

  // ── DOM ────────────────────────────────────────────────────────────────
  let indicator = document.getElementById('sh-indicator');
  if (!indicator) {
    indicator = document.createElement('div');
    indicator.id = 'sh-indicator';
    indicator.innerHTML = `
      <i class="fas fa-exclamation-triangle"></i>
      <span id="sh-label">Errores</span>
      <span id="sh-count" style="display:none;"></span>`;
    document.body.appendChild(indicator);
  }

  let popup = document.getElementById('sh-popup');
  if (!popup) {
    popup = document.createElement('div');
    popup.id = 'sh-popup';
    popup.innerHTML = `
      <div class="sh-popup-header">
        <span class="sh-popup-title">Estado de fuentes</span>
        <button class="sh-close" id="sh-close-btn">×</button>
      </div>
      <div id="sh-list"></div>`;
    document.body.appendChild(popup);
  }

  // ── Estado ─────────────────────────────────────────────────────────────
  let pollingTimer = null;
  let forceUntil = 0;
  let popupOpen = false;
  let _lastStatus = {};

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

  function truncate(str, max = 32) {
    return str && str.length > max ? str.slice(0, max - 1) + '…' : (str || '');
  }

  function timeAgo(ts) {
    if (!ts) return '';
    const secs = Math.floor((Date.now() / 1000) - ts);
    if (secs < 60) return 'hace segundos';
    if (secs < 3600) return `hace ${Math.floor(secs / 60)} min`;
    return `hace ${Math.floor(secs / 3600)} h`;
  }

  function buildEntryHtml(name, state) {
    const isDisabled = state.temporarily_disabled;
    const badge = isDisabled
      ? '<span class="sh-entry-badge sh-badge-disabled">Desactivada</span>'
      : '<span class="sh-entry-badge sh-badge-error">Error</span>';

    let reEnableBtn = '';
    if (isDisabled) {
      let remaining = '';
      if (state.remaining_seconds > 0) {
        const m = Math.ceil(state.remaining_seconds / 60);
        remaining = ` · ${m} min restantes`;
      }
      reEnableBtn = `<button class="sh-re-enable-btn" data-source="${name}">Reactivar</button>`;
    }

    return `
      <div class="sh-entry">
        <div class="sh-entry-header">
          <span class="sh-entry-name">${name}</span>
          ${badge}
        </div>
        <div class="sh-entry-error"><i class="fas fa-exclamation-triangle" style="margin-right:5px;"></i>${state.last_error || 'Error desconocido'}</div>
        <div class="sh-entry-meta">
          <span>${timeAgo(state.last_error_time)} · ${state.consecutive_failures} fallos consecutivos</span>
          ${reEnableBtn}
        </div>
      </div>`;
  }

  async function fetchHealth() {
    try {
      const res = await fetch('/api/scraper-health');
      const data = await res.json();
      _lastStatus = data;

      const entries = Object.entries(data);
      const withErrors = entries.filter(([_, s]) => s.last_error || s.temporarily_disabled);
      const hasIssues = withErrors.length > 0;

      const label = document.getElementById('sh-label');
      const countBadge = document.getElementById('sh-count');
      const listDiv = document.getElementById('sh-list');

      // ── Indicador ──
      if (hasIssues) {
        const disabledCount = withErrors.filter(([_, s]) => s.temporarily_disabled).length;
        const errorCount = withErrors.length - disabledCount;
        let text = '';
        if (disabledCount > 0 && errorCount > 0) {
          text = `${disabledCount} desactivada(s), ${errorCount} error(es)`;
        } else if (disabledCount > 0) {
          text = `${disabledCount} fuente(s) desactivada(s)`;
        } else {
          text = `${errorCount} fuente(s) con error(es)`;
        }
        if (label) label.textContent = text;
        if (countBadge) {
          const total = withErrors.length;
          countBadge.style.display = total > 1 ? 'inline' : 'none';
          countBadge.textContent = `${total}`;
        }
        showIndicator();
      } else {
        if (label) label.textContent = '';
        if (countBadge) countBadge.style.display = 'none';
        if (Date.now() >= forceUntil) {
          hideIndicator();
        }
      }

      // ── Popup ──
      if (listDiv) {
        if (withErrors.length) {
          listDiv.innerHTML = withErrors.map(([name, state]) => buildEntryHtml(name, state)).join('');
          // Bind re-enable buttons
          listDiv.querySelectorAll('.sh-re-enable-btn').forEach(btn => {
            btn.addEventListener('click', async function () {
              const sourceName = this.dataset.source;
              try {
                const res = await fetch('/api/scraper-health/re-enable', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ name: sourceName }),
                });
                if (res.ok) {
                  fetchHealth();
                }
              } catch (err) {
                console.error('scraper-health: error re-enabling', err);
                showNotification('Error al reactivar fuente', 'error');
              }
            });
          });
        } else {
          listDiv.innerHTML = '<div class="sh-empty"><i class="fas fa-check-circle" style="margin-right:6px; color:#4ade80;"></i>Todas las fuentes funcionando</div>';
        }
      }

      // ── Polling ──
      if (hasIssues) {
        forceUntil = Date.now() + 30000;
        scheduleNext(5000);
      } else if (Date.now() < forceUntil) {
        scheduleNext(5000);
      } else {
        clearPolling();
      }

    } catch (err) {
      console.error('scraper-health:', err);
      showNotification('Error al consultar estado de fuentes', 'error');
      scheduleNext(10000);
    }
  }

  function scheduleNext(ms) {
    clearPolling();
    pollingTimer = setTimeout(fetchHealth, ms);
  }
  function clearPolling() {
    if (pollingTimer) { clearTimeout(pollingTimer); pollingTimer = null; }
  }

  // ── Eventos ────────────────────────────────────────────────────────────
  indicator.addEventListener('click', e => {
    e.stopPropagation();
    if (popupOpen) closePopup();
    else { fetchHealth().then(openPopup); }
  });

  document.getElementById('sh-close-btn')?.addEventListener('click', closePopup);

  document.addEventListener('click', e => {
    if (popupOpen && !indicator.contains(e.target) && !popup.contains(e.target))
      closePopup();
  });

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && popupOpen) closePopup();
  });

  // ── API pública ────────────────────────────────────────────────────────
  window.refreshScraperHealth = function () {
    forceUntil = Date.now() + 10000;
    clearPolling();
    fetchHealth();
  };

  // ── Arrancar ───────────────────────────────────────────────────────────
  fetchHealth();
})();

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
  }

  init();
})();