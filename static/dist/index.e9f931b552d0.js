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
  const HIDE_KEY = 'anyone_hide_scraper_errors'; function isHidden() { return localStorage.getItem(HIDE_KEY) === 'true'; }

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
      if (hasIssues && !isHidden()) {
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
                if (!isHidden()) showNotification('Error al reactivar fuente', 'error');
              }
            });
          });
        } else {
          listDiv.innerHTML = '<div class="sh-empty"><i class="fas fa-check-circle" style="margin-right:6px; color:#4ade80;"></i>Todas las fuentes funcionando</div>';
        }
      }

      // ── Polling ──
      if (hasIssues && !isHidden()) {
        forceUntil = Date.now() + 30000;
        scheduleNext(5000);
      } else if (Date.now() < forceUntil) {
        scheduleNext(5000);
      } else {
        clearPolling();
      }

    } catch (err) {
      console.error('scraper-health:', err);
      if (!isHidden()) showNotification('Error al consultar estado de fuentes', 'error');
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

// static/js/app.js
(function () {
  'use strict';

  // ── Estado global ──────────────────────────────────────────────────────
  let currentType      = 'library';
  let _libraryItems    = [];
  let _libraryStatuses = {};
  let _libraryFilter   = 'all';
  let _libraryQuery    = '';
  let _libraryLoaded   = false;

  // ── Elementos DOM ─────────────────────────────────────────────────────
  const animePanel       = document.getElementById('anime-panel');
  const mangaPanel       = document.getElementById('manga-panel');
  const libraryPanel     = document.getElementById('library-panel');
  const tabAnime         = document.getElementById('tab-anime');
  const tabManga         = document.getElementById('tab-manga');
  const tabLibrary       = document.getElementById('tab-library');
  const animeSearchBtn   = document.getElementById('anime-search-btn');
  const mangaSearchBtn   = document.getElementById('manga-search-btn');
  const animeRefreshBtn  = document.getElementById('anime-refresh-btn');
  const mangaRefreshBtn  = document.getElementById('manga-refresh-btn');
  const animeSearchInput = document.getElementById('anime-search-input');
  const mangaSearchInput = document.getElementById('manga-search-input');

  // ── Tab switching ──────────────────────────────────────────────────────
  // [OPT-6] Un único punto de control. index.html tiene un bloque de tabs
  // que se ejecuta antes de este script; los listeners que añade son
  // sobrescritos porque este módulo llama a setActiveTab() directamente
  // desde los mismos botones. Para evitar la ejecución doble de ese bloque,
  // index.html debería eliminarlo — mientras tanto este guard es suficiente.
  const TAB_MAP = [
    { btn: tabAnime,   panel: animePanel,   type: 'anime'   },
    { btn: tabManga,   panel: mangaPanel,   type: 'manga'   },
    { btn: tabLibrary, panel: libraryPanel, type: 'library' },
  ];

  function setActiveTab(type) {
    if (currentType === type && type !== 'library') return; // evitar re-render innecesario
    currentType = type;
    TAB_MAP.forEach(({ btn, panel, type: t }) => {
      const active = t === type;
      btn.classList.toggle('active', active);
      panel.classList.toggle('hidden', !active);
      if (active) {
        panel.style.animation = 'none';
        requestAnimationFrame(() => { panel.style.animation = ''; });
      }
    });
    // [OPT-3] Solo cargar biblioteca la primera vez que se abre esa tab
    if (type === 'library' && !_libraryLoaded) {
      _libraryLoaded = true;
      loadLibrary();
    }
  }

  TAB_MAP.forEach(({ btn, type }) => {
    btn.addEventListener('click', () => setActiveTab(type));
  });

  // ── CoverObserver — lazy load + liberación de VRAM ────────────────────
  // [OPT-7] unobserve tras cargar: una vez que la imagen cargó al menos una
  // vez ya no necesitamos seguir rastreando su entrada; solo rastreamos
  // salida para liberar src. El observer principal solo carga; uno secundario
  // (releaseObserver) solo libera. Así evitamos acumular entradas infinitas.

  const PLACEHOLDER = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" '
    + 'width="2" height="3"%3E%3C/svg%3E';

  // Observer de carga: entra en viewport → asigna src real → unobserve
  const loadObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const img  = entry.target;
      const real = img.dataset.src;
      if (real && img.src !== real) {
        img.src = real;
        img.addEventListener('load', () => {
          // Una vez cargada, traspasar al observer de liberación
          releaseObserver.observe(img);
        }, { once: true });
      }
      loadObserver.unobserve(img); // ya no necesitamos rastrear entrada
    });
  }, { rootMargin: '200px 0px 200px 0px', threshold: 0 });

  // Observer de liberación: sale del viewport (margen amplio) → borra src
  const releaseObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) return;
      const img = entry.target;
      if (img.complete && img.naturalWidth > 0) {
        img.src = PLACEHOLDER;
        // Volver a registrar para que se recargue si el usuario vuelve a scrollear
        loadObserver.observe(img);
        releaseObserver.unobserve(img);
      }
    });
  }, { rootMargin: '0px 0px 800px 0px', threshold: 0 });

  function observeCovers(container) {
    container.querySelectorAll('img.cover-lazy').forEach(img => {
      loadObserver.observe(img);
    });
  }

  // ── Media card builder — Samsung One UI style ─────────────────────────
  // Layout: image (2/3 aspect) with type chip top-right overlay,
  //         title + chips in card-body below the image.
  function buildMediaCard({ id, title, cover, source, type, badge, extra, bottomChip }) {
    const safeTitle = (title || '').replace(/"/g, '&quot;').replace(/</g, '&lt;');
    const dataSrc   = cover || '';

    // Map legacy badge class to new chip class
    let chipClass = 'chip-source';
    if (badge) {
      if (badge.class === 'badge-anime')  chipClass = 'chip-anime';
      if (badge.class === 'badge-manga')  chipClass = 'chip-manga';
    }
    const typeChipHtml = badge
      ? `<span class="chip ${chipClass} type-chip">${badge.label}</span>`
      : '';

    return `
      <div class="media-card-wrapper">
        <div class="media-card"
          data-id="${id}"
          data-title="${safeTitle}"
          data-source="${source || ''}"
          data-type="${type || ''}">
          <!-- Image area -->
          <div class="card-image">
            <img class="cover-lazy"
                 src="${PLACEHOLDER}"
                 data-src="${dataSrc}"
                 alt="${safeTitle}"
                 style="background:var(--surface);">
            ${typeChipHtml}
            ${bottomChip || ''}
          </div>
          <!-- Text area below image -->
          <div class="card-body">
            <p class="card-title">${safeTitle}</p>
            ${extra || ''}
          </div>
        </div>
      </div>`;
  }

  // ── Búsqueda online ────────────────────────────────────────────────────
  async function search(refresh = false) {
    if (currentType === 'library') return;
    const type   = currentType;
    const source = document.getElementById(`${type}-source`).value;
    const query  = type === 'anime'
      ? animeSearchInput.value.trim()
      : mangaSearchInput.value.trim();
    if (!query) return;

    const container = document.getElementById(`${type}-results`);

    if (source === 'all') {
      searchAllStream(type, query, container);
      return;
    }

    container.innerHTML = `
      <div class="empty-state">
        <div class="loading-spinner"></div>
        <p>Buscando…</p>
      </div>`;

    try {
      let url = `/api/search?type=${type}&source=${source}&q=${encodeURIComponent(query)}`;
      if (refresh) url += '&refresh=1';

      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      renderSearchResults(await res.json(), type, source);
    } catch (err) {
      container.innerHTML = `
        <div class="empty-state">
          <i class="fas fa-exclamation-circle" style="color:var(--accent2);"></i>
          <p>Error al buscar: ${err.message}</p>
        </div>`;
    }
  }

  function searchAllStream(type, query, container) {
    container.innerHTML = `
      <div class="empty-state" id="stream-loading">
        <div class="loading-spinner"></div>
        <p>Buscando en todas las fuentes…</p>
      </div>`;

    const seen = new Set();
    const es = new EventSource(`/api/search-all-stream?type=${type}&q=${encodeURIComponent(query)}`);

    // Bind persistent click delegation once per container
    if (!container.dataset.streamBound) {
      container.dataset.streamBound = '1';
      container.addEventListener('click', e => {
        const downloadBtn = e.target.closest('.download-btn');
        const card        = e.target.closest('.media-card');
        if (!card) return;

        if (downloadBtn) {
          e.stopPropagation();
          const { id, title, source: src, type: typ } = card.dataset;
          downloadSeries(typ, src, id, title);
          return;
        }
        const { id, source: src, type: typ } = card.dataset;
        window.location.href = `/serie/${typ}/${src}/${id}`;
      });
    }

    function showEmpty() {
      container.innerHTML = `
        <div class="empty-state">
          <i class="fas fa-search"></i>
          <p>Sin resultados para esa búsqueda.</p>
        </div>`;
    }

    function showError(msg) {
      container.innerHTML = `
        <div class="empty-state">
          <i class="fas fa-exclamation-circle" style="color:var(--accent2);"></i>
          <p>${msg}</p>
        </div>`;
    }

    es.addEventListener('source_error', e => {
      if (localStorage.getItem('anyone_hide_scraper_errors') === 'true') return;
      const data = JSON.parse(e.data);
      const msg = data.disabled
        ? `${data.source} desactivada temporalmente: ${data.error}`
        : `${data.source}: ${data.error}`;
      showNotification(msg, 'error', 4000);
      if (window.refreshScraperHealth) window.refreshScraperHealth();
    });

    es.addEventListener('results', e => {
      const data = JSON.parse(e.data);
      const items = data.results;
      if (!items.length) return;

      const newItems = [];
      for (const item of items) {
        const key = `${item.source}:${item.id}`;
        if (!seen.has(key)) {
          seen.add(key);
          newItems.push(item);
        }
      }
      if (!newItems.length) return;

      // Remove loading state on first batch
      const loadingEl = document.getElementById('stream-loading');
      if (loadingEl) loadingEl.remove();

      const html = newItems.map(item =>
        buildMediaCard({
          id:     item.id,
          title:  item.title,
          cover:  item.cover,
          source: item.source,
          type,
          badge:  { class: 'badge-source', label: item.source },
          extra:  `<div class="card-chips">
                     <span class="chip chip-source" style="font-size:10px; height:22px; padding:0 8px;">${item.source}</span>
                   </div>
                   <div class="card-actions">
                      <button class="download-btn card-dl-btn">
                      <i class="fas fa-download"></i> Descargar todo
                      </button>
                   </div>`,
        })
      ).join('');

      container.insertAdjacentHTML('beforeend', html);
      observeCovers(container);
      if (window.animateCards) window.animateCards(`#${type}-results`);
    });

    es.addEventListener('done', () => {
      es.close();
      if (seen.size === 0) showEmpty();
    });

    es.addEventListener('error', () => {
      if (es.readyState === EventSource.CLOSED) {
        if (seen.size === 0) showError('Error al conectar con el servidor.');
      }
    });
  }

  function renderSearchResults(items, type, source) {
    const container = document.getElementById(`${type}-results`);
    if (!items.length) {
      container.innerHTML = `
        <div class="empty-state">
          <i class="fas fa-search"></i>
          <p>Sin resultados para esa búsqueda.</p>
        </div>`;
      return;
    }

    container.innerHTML = items.map(item => {
      const itemSource = item.source || source;
      return buildMediaCard({
        id:     item.id,
        title:  item.title,
        cover:  item.cover,
        source: itemSource,
        type,
        badge:  { class: 'badge-source', label: itemSource },
        extra:  `<div class="card-chips">
                   <span class="chip chip-source" style="font-size:10px; height:22px; padding:0 8px;">${itemSource}</span>
                 </div>
                  <div class="card-actions">
                    <button class="download-btn card-dl-btn">
                    <i class="fas fa-download"></i> Descargar todo
                    </button>
                  </div>`,
      });
    }).join('');

    observeCovers(container);
    if (window.animateCards) window.animateCards(`#${type}-results`);

    // Event delegation — un listener por contenedor
    if (!container.dataset.listenerBound) {
      container.addEventListener('click', e => {
        const downloadBtn = e.target.closest('.download-btn');
        const card        = e.target.closest('.media-card');
        if (!card) return;

        if (downloadBtn) {
          e.stopPropagation();
          const { id, title, source: src, type: typ } = card.dataset;
          downloadSeries(typ, src, id, title);
          return;
        }
        const { id, source: src, type: typ } = card.dataset;
        window.location.href = `/serie/${typ}/${src}/${id}`;
      });
      container.dataset.listenerBound = '1';
    }
  }

  // ── Descarga de serie completa ─────────────────────────────────────────
  async function downloadSeries(type, source, contentId, title) {
    try {
      const res  = await fetch('/api/download', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ type, source, content_id: contentId, title, exclude_watched: true }),
      });
      const data = await res.json();
      if (!res.ok) {
        showNotification(`Error: ${data.error}`, 'error');
      } else {
        showNotification('Descarga encolada', 'success');
        if (window.showDownloadIndicator) window.showDownloadIndicator();
      }
    } catch (err) {
      showNotification(`Error al encolar: ${err.message}`, 'error');
    }
  }

  // ── Biblioteca local ───────────────────────────────────────────────────

  const STATUS_META = {
    watching:  { label: 'Mirando',   color: 'var(--accent)',  border: 'rgba(196,107,255,0.4)', bg: 'rgba(196,107,255,0.12)', icon: 'fa-eye' },
    completed: { label: 'Visto',     color: '#4ade80',        border: 'rgba(74,222,128,0.4)',  bg: 'rgba(74,222,128,0.12)',  icon: 'fa-check-circle' },
    pending:   { label: 'Pendiente', color: '#fbbf24',        border: 'rgba(251,191,36,0.4)',  bg: 'rgba(251,191,36,0.12)', icon: 'fa-clock' },
    none:      { label: '',          color: '',               border: '',                      bg: '',                      icon: '' },
  };

  const STATUS_ORDER = { watching: 0, completed: 1, pending: 2, none: 3 };

  async function loadLibrary() {
    const container = document.getElementById('library-results');
    if (!container) return;
    container.innerHTML = `
      <div class="empty-state">
        <div class="loading-spinner"></div>
        <p>Cargando biblioteca…</p>
      </div>`;
    try {
      const [itemsRes, statusRes] = await Promise.all([
        fetch('/api/library'),
        fetch('/api/library/status'),
      ]);
      if (!itemsRes.ok) throw new Error(`HTTP ${itemsRes.status}`);
      _libraryItems    = await itemsRes.json();
      _libraryStatuses = statusRes.ok ? await statusRes.json() : {};
      _initLibraryControls();
      applyLibraryView();
      fetchUpdatesBadge();
    } catch (err) {
      container.innerHTML = `
        <div class="empty-state">
          <i class="fas fa-exclamation-circle" style="color:var(--accent2);"></i>
          <p>Error al cargar biblioteca: ${err.message}</p>
        </div>`;
    }
  }

  // ── Badge global de novedades ─────────────────────────────────────────
  async function fetchUpdatesBadge() {
    try {
      const res  = await fetch('/api/library/updates');
      const data = await res.json();
      const total = data.total || 0;

      // Quitar badge anterior si existe
      const oldBadge = tabLibrary.querySelector('.update-badge-global');
      if (oldBadge) oldBadge.remove();

      if (total > 0) {
        const badge = document.createElement('span');
        badge.className = 'update-badge-global';
        badge.textContent = total > 99 ? '99+' : total;
        badge.title = `${total} serie${total !== 1 ? 's' : ''} con capítulos nuevos`;
        Object.assign(badge.style, {
          position: 'absolute',
          top: '-5px',
          right: '-6px',
          background: 'var(--accent2, #f59e0b)',
          color: '#000',
          fontSize: '9px',
          fontWeight: '700',
          borderRadius: '999px',
          padding: '1px 5px',
          lineHeight: '1.5',
          pointerEvents: 'none',
          zIndex: '5',
        });
        tabLibrary.style.position = 'relative';
        tabLibrary.appendChild(badge);
      }
    } catch (err) {
      console.warn('fetchUpdatesBadge:', err);
      showNotification('Error al cargar actualizaciones', 'error');
    }
  }

  // [OPT-5] _initLibraryControls se llama una sola vez (desde loadLibrary)
  // sin necesidad de guards dataset.bound
  function _initLibraryControls() {
    // Búsqueda local con debounce para no re-renderizar en cada tecla
    const searchInput = document.getElementById('library-search-input');
    if (searchInput) {
      let debounceTimer;
      searchInput.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          _libraryQuery = searchInput.value.toLowerCase();
          applyLibraryView();
        }, 150); // 150 ms de debounce — imperceptible para el usuario
      });
    }

    // [OPT-4] Event delegation para filtros
    const filtersBar = document.getElementById('library-status-filters');
    if (filtersBar) {
      filtersBar.addEventListener('click', e => {
        const btn = e.target.closest('.lib-filter');
        if (!btn) return;
        _libraryFilter = btn.dataset.filter;
        filtersBar.querySelectorAll('.lib-filter').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        applyLibraryView();
      });
    }
  }

  // ── Render diferencial de la biblioteca ───────────────────────────────
  // [OPT-1] En vez de destruir y reconstruir todos los cards, calculamos qué
  // items se añaden, cuáles se eliminan y cuáles ya estaban. Solo tocamos el
  // DOM para los que cambiaron. El resultado es que filtrar/buscar en una
  // biblioteca grande es instantáneo.

  // Mapa: id → elemento wrapper actualmente en el DOM
  let _renderedCards = new Map();

  function applyLibraryView() {
    const container = document.getElementById('library-results');
    if (!container) return;

    // 1. Filtrar por etiqueta
    let filtered = _libraryItems.filter(item => {
      const status = _libraryStatuses[`local:${item.id}`] || 'none';
      return _libraryFilter === 'all' || status === _libraryFilter;
    });

    // 2. Filtrar por búsqueda
    if (_libraryQuery) {
      filtered = filtered.filter(item =>
        (item.title || '').toLowerCase().includes(_libraryQuery) ||
        (item.id    || '').toLowerCase().includes(_libraryQuery)
      );
    }

    // 3. Ordenar
    filtered.sort((a, b) => {
      const sa = STATUS_ORDER[_libraryStatuses[`local:${a.id}`] || 'none'];
      const sb = STATUS_ORDER[_libraryStatuses[`local:${b.id}`] || 'none'];
      return sa !== sb ? sa - sb : (a.title || '').localeCompare(b.title || '');
    });

    // 4. Actualizar contador
    const countEl = document.getElementById('library-count');
    if (countEl) countEl.textContent = `${filtered.length} serie${filtered.length !== 1 ? 's' : ''}`;

    // 5. Estado vacío
    if (!filtered.length) {
      container.innerHTML = _libraryItems.length
        ? `<div class="empty-state" style="grid-column:1/-1;">
             <i class="fas fa-filter"></i>
             <p>Ninguna serie coincide con el filtro.</p>
           </div>`
        : `<div class="empty-state" style="grid-column:1/-1;">
             <i class="fas fa-folder-open"></i>
             <p>Tu biblioteca está vacía. Usa la búsqueda para descargar series.</p>
           </div>`;
      _renderedCards.clear();
      return;
    }

    // 6. Render diferencial
    const nextIds    = new Set(filtered.map(i => i.id));
    const prevIds    = new Set(_renderedCards.keys());

    // Eliminar cards que ya no están en la vista filtrada
    for (const id of prevIds) {
      if (!nextIds.has(id)) {
        _renderedCards.get(id).remove();
        _renderedCards.delete(id);
      }
    }

    // Añadir cards nuevas y reordenar usando un DocumentFragment
    const frag = document.createDocumentFragment();
    filtered.forEach(item => {
      if (!_renderedCards.has(item.id)) {
        const wrapper = _buildLibraryCard(item);
        _renderedCards.set(item.id, wrapper);
        frag.appendChild(wrapper);
      }
    });
    if (frag.childElementCount > 0) {
      // Limpiar cualquier nodo residual (spinner de carga, empty-state previo)
      // que no sea un card gestionado por _renderedCards
      Array.from(container.children).forEach(child => {
        if (!child.classList.contains('media-card-wrapper')) child.remove();
      });
      container.appendChild(frag);
      // Lazy load de portadas solo para las recién añadidas
      observeCovers(container);
      if (window.animateCards) window.animateCards('#library-results');
    }

    // Reordenar nodos según filtered (solo si el orden cambió)
    filtered.forEach(item => {
      const node = _renderedCards.get(item.id);
      if (node && node.parentNode === container) {
        container.appendChild(node); // mover al final en orden correcto
      }
    });
  }

  function _buildLibraryCard(item) {
    const ref         = `local:${item.id}`;
    const status      = _libraryStatuses[ref] || 'none';
    const meta        = STATUS_META[status];
    const resumeChapter = item.progress_chapter && item.progress_chapter !== '0'
      ? item.progress_chapter : (item.last_chapter || '1');
    const isAnime     = item.type === 'anime';
    const typeLabel   = isAnime ? 'Anime' : 'Manga';

    // Status chip (bottom-right overlay on cover)
    const statusChipHtml  = meta.label
      ? `<span class="chip chip-sm chip-${status} status-chip">
           <i class="fas ${meta.icon}"></i>${meta.label}
         </span>`
      : '';

    const statusBtn = `
      <button class="status-tag-btn" data-ref="${ref}" title="Cambiar etiqueta"
        style="background:${meta.bg || 'rgba(255,255,255,0.05)'}; border-color:${meta.border || 'var(--border)'}; color:${meta.color || 'var(--muted)'};">
        <i class="fas ${meta.icon || 'fa-tag'}"></i>
      </button>`;

    const html = buildMediaCard({
      id:     item.id || '',
      title:  item.title,
      cover:  item.cover,
      source: 'local',
      type:   item.type || '',
      badge:  { class: `badge-${item.type}`, label: typeLabel },
      bottomChip: statusChipHtml,
      extra:  `<div class="card-actions-row">
                  <button class="resume-btn" data-last-chapter="${resumeChapter}">
                    <i class="fas fa-play" style="font-size:9px;"></i> Cap. ${resumeChapter}
                  </button>
                  ${statusBtn}
                </div>`,
    });

    const div = document.createElement('div');
    div.innerHTML = html;
    const wrapper = div.firstElementChild;

    // [OPT-4] Los eventos se añaden una vez por card al crearla,
    // no en cada re-render.
    const card = wrapper.querySelector('.media-card');
    card.addEventListener('click', e => {
      if (e.target.closest('.resume-btn, .status-tag-btn')) return;
      const { type, id } = card.dataset;
      if (type && id) window.location.href = `/serie/${type}/local/${id}`;
    });

    wrapper.querySelector('.resume-btn')?.addEventListener('click', e => {
      e.stopPropagation();
      const { type, id } = card.dataset;
      const ch = e.currentTarget.dataset.lastChapter;
      if (type && id && ch) window.location.href = `/reader/${type}/local/${id}/${ch}`;
    });

    wrapper.querySelector('.status-tag-btn')?.addEventListener('click', e => {
      e.stopPropagation();
      openStatusPopup(e.currentTarget, ref);
    });

    return wrapper;
  }

  // ── Popup contextual de etiqueta ───────────────────────────────────────
  let _statusPopup       = null;
  let _popupCloseHandler = null;

  const STATUS_OPTIONS = [
    { value: 'watching',  label: 'Mirando',      icon: 'fa-eye',          color: 'var(--accent)', border: 'rgba(196,107,255,0.35)', bg: 'rgba(196,107,255,0.1)' },
    { value: 'completed', label: 'Visto',         icon: 'fa-check-circle', color: '#4ade80',       border: 'rgba(74,222,128,0.35)',  bg: 'rgba(74,222,128,0.1)'  },
    { value: 'pending',   label: 'Pendiente',     icon: 'fa-clock',        color: '#fbbf24',       border: 'rgba(251,191,36,0.35)', bg: 'rgba(251,191,36,0.1)'  },
    { value: 'none',      label: 'Sin etiqueta',  icon: 'fa-tag',          color: 'var(--muted)',  border: 'var(--border)',         bg: 'transparent'           },
  ];

  function openStatusPopup(anchorBtn, ref) {
    closeStatusPopup();
    const current = _libraryStatuses[ref] || 'none';

    const popup = document.createElement('div');
    popup.id = 'status-popup';
    Object.assign(popup.style, {
      position:       'fixed',
      zIndex:         '10002',
      background:     'rgba(10,10,15,0.97)',
      border:         '1px solid rgba(255,255,255,0.12)',
      borderRadius:   '12px',
      padding:        '6px',
      display:        'flex',
      flexDirection:  'column',
      gap:            '3px',
      backdropFilter: 'blur(16px)',
      boxShadow:      '0 8px 32px rgba(0,0,0,0.5)',
      minWidth:       '160px',
      opacity:        '0',
      transform:      'scale(0.95) translateY(-4px)',
      transition:     'opacity 0.15s ease, transform 0.15s ease',
    });

    STATUS_OPTIONS.forEach(opt => {
      const row      = document.createElement('button');
      const isActive = opt.value === current;
      Object.assign(row.style, {
        display:      'flex',
        alignItems:   'center',
        gap:          '9px',
        padding:      '7px 10px',
        borderRadius: '8px',
        border:       isActive ? `1px solid ${opt.border}` : '1px solid transparent',
        background:   isActive ? opt.bg : 'transparent',
        color:        isActive ? opt.color : 'var(--muted)',
        fontSize:     '13px',
        fontFamily:   'var(--ff-body)',
        cursor:       'pointer',
        textAlign:    'left',
        width:        '100%',
        transition:   'background 0.12s, color 0.12s',
      });
      row.innerHTML = `
        <i class="fas ${opt.icon}" style="font-size:11px; width:14px; text-align:center; flex-shrink:0;"></i>
        <span>${opt.label}</span>
        ${isActive ? '<i class="fas fa-check" style="margin-left:auto; font-size:10px; opacity:0.7;"></i>' : ''}`;

      row.addEventListener('mouseenter', () => {
        row.style.background = opt.bg || 'rgba(255,255,255,0.05)';
        row.style.color      = opt.color || 'var(--text)';
      });
      row.addEventListener('mouseleave', () => {
        if (opt.value !== current) {
          row.style.background = 'transparent';
          row.style.color      = 'var(--muted)';
        }
      });
      row.addEventListener('click', async e => {
        e.stopPropagation();
        closeStatusPopup();
        if (opt.value === current) return;
        try {
          const res = await fetch('/api/library/status', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ content_ref: ref, status: opt.value }),
          });
          if (res.ok) {
            _libraryStatuses[ref] = opt.value;
            showNotification(
              opt.value === 'none' ? 'Etiqueta eliminada' : `Marcado como ${opt.label}`,
              'success', 2000
            );
            // Actualizar solo la card afectada (sin re-render completo)
            const id = ref.replace('local:', '');
            const oldNode = _renderedCards.get(id);
            if (oldNode) oldNode.remove(); // quitar del DOM primero
            _renderedCards.delete(id);     // luego del mapa
            applyLibraryView();
          } else {
            showNotification('Error al guardar etiqueta', 'error');
          }
        } catch (err) {
          showNotification(`Error: ${err.message}`, 'error');
        }
      });

      popup.appendChild(row);
    });

    document.body.appendChild(popup);
    _statusPopup = popup;

    // Posicionar sin salirse de pantalla
    const rect = anchorBtn.getBoundingClientRect();
    const pw   = 160;
    const ph   = 4 * 38;
    let top    = rect.bottom + 6;
    let left   = rect.left;
    if (left + pw > window.innerWidth  - 8) left = window.innerWidth  - pw - 8;
    if (top  + ph > window.innerHeight - 8) top  = rect.top - ph - 6;
    if (left < 8) left = 8;
    popup.style.top  = `${top}px`;
    popup.style.left = `${left}px`;

    requestAnimationFrame(() => requestAnimationFrame(() => {
      popup.style.opacity   = '1';
      popup.style.transform = 'scale(1) translateY(0)';
    }));

    _popupCloseHandler = e => {
      if (!popup.contains(e.target) && e.target !== anchorBtn) closeStatusPopup();
    };
    setTimeout(() => {
      document.addEventListener('click',   _popupCloseHandler);
      document.addEventListener('keydown', _escCloseHandler);
    }, 0);
  }

  function _escCloseHandler(e) {
    if (e.key === 'Escape') closeStatusPopup();
  }

  function closeStatusPopup() {
    if (!_statusPopup) return;
    const popup  = _statusPopup;
    _statusPopup = null;
    popup.style.opacity   = '0';
    popup.style.transform = 'scale(0.95) translateY(-4px)';
    setTimeout(() => popup.remove(), 150);
    document.removeEventListener('click',   _popupCloseHandler);
    document.removeEventListener('keydown', _escCloseHandler);
  }

  // ── Poblar selectores de fuentes dinámicamente ─────────────────────────
  async function populateSourceDropdowns() {
    try {
      const res = await fetch('/api/settings/sources');
      if (!res.ok) return;
      const sources = await res.json();
      const animeSelect = document.getElementById('anime-source');
      const mangaSelect = document.getElementById('manga-source');

      animeSelect.innerHTML = '';
      mangaSelect.innerHTML = '';

      sources.forEach(src => {
        if (!src.enabled) return;
        const opt = document.createElement('option');
        opt.value = src.name;
        opt.textContent = src.label;
        if (src.type === 'anime') {
          animeSelect.appendChild(opt);
        } else {
          mangaSelect.appendChild(opt);
        }
      });

      const allOpt = document.createElement('option');
      allOpt.value = 'all';
      allOpt.textContent = 'Todas las fuentes';
      mangaSelect.insertBefore(allOpt, mangaSelect.firstChild);
    } catch (err) {
      console.warn('Error cargando fuentes:', err);
      showNotification('Error al cargar fuentes de búsqueda', 'error');
    }
  }

  // ── Eventos de búsqueda ────────────────────────────────────────────────
  animeSearchBtn?.addEventListener('click',  () => search(false));
  mangaSearchBtn?.addEventListener('click',  () => search(false));
  animeRefreshBtn?.addEventListener('click', () => search(true));
  mangaRefreshBtn?.addEventListener('click', () => search(true));
  animeSearchInput?.addEventListener('keypress', e => { if (e.key === 'Enter') search(false); });
  mangaSearchInput?.addEventListener('keypress', e => { if (e.key === 'Enter') search(false); });

  // ── Inicializar en Biblioteca por defecto ─────────────────────────────
  setActiveTab('library');
  populateSourceDropdowns();
})();