// static/js/scraper-health.js
(function () {
  if (window.location.pathname.startsWith('/reader/')) return;

  const HIDE_KEY = 'anyone_hide_scraper_errors';
  function isHidden() { return localStorage.getItem(HIDE_KEY) === 'true'; }

  // Estilos en scraper-health.css (cargado desde base.html)

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

  // ── BroadcastChannel (compartir polling entre pestañas) ────────────────
  let _bc = null;
  try {
    _bc = new BroadcastChannel('anyone:health');
    _bc.onmessage = (ev) => {
      if (ev.data?.type === 'health') {
        _applyHealthData(ev.data.data);
        forceUntil = Date.now() + 10000;
        scheduleNext(8000);
      }
    };
  } catch (_) { /* BroadcastChannel no soportado */ }

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

  function _applyHealthData(data) {
    _lastStatus = data;
    const entries = Object.entries(data);
    const withErrors = entries.filter(([_, s]) => s.last_error || s.temporarily_disabled);
    const hasIssues = withErrors.length > 0;

    const label = document.getElementById('sh-label');
    const countBadge = document.getElementById('sh-count');
    const listDiv = document.getElementById('sh-list');

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

    if (listDiv) {
      if (withErrors.length) {
        listDiv.innerHTML = withErrors.map(([name, state]) => buildEntryHtml(name, state)).join('');
        listDiv.querySelectorAll('.sh-re-enable-btn').forEach(btn => {
          btn.addEventListener('click', async function () {
            const sourceName = this.dataset.source;
            try {
              await api.post('/api/scraper-health/re-enable', { name: sourceName });
              fetchHealth();
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

    return hasIssues;
  }

  async function fetchHealth() {
    try {
      const data = await api.get('/api/scraper-health');
      const hasIssues = _applyHealthData(data);
      if (_bc) _bc.postMessage({ type: 'health', data });

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
