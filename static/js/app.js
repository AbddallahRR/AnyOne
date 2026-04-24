// static/js/app.js
(function () {
  // ── Estado global ──────────────────────────────────────────────────────
  let currentType = 'library';

  // ── Elementos DOM ─────────────────────────────────────────────────────
  const animePanel      = document.getElementById('anime-panel');
  const mangaPanel      = document.getElementById('manga-panel');
  const libraryPanel    = document.getElementById('library-panel');
  const tabAnime        = document.getElementById('tab-anime');
  const tabManga        = document.getElementById('tab-manga');
  const tabLibrary      = document.getElementById('tab-library');
  const animeSearchBtn  = document.getElementById('anime-search-btn');
  const mangaSearchBtn  = document.getElementById('manga-search-btn');
  const animeRefreshBtn = document.getElementById('anime-refresh-btn');
  const mangaRefreshBtn = document.getElementById('manga-refresh-btn');
  const animeSearchInput = document.getElementById('anime-search-input');
  const mangaSearchInput = document.getElementById('manga-search-input');

  // ── Tab switching ──────────────────────────────────────────────────────
  // index.html también tiene un listener de tabs; este bloque lo reemplaza
  // completamente para mantener un único punto de control.
  const TAB_MAP = [
    { btn: tabAnime,   panel: animePanel,   type: 'anime'   },
    { btn: tabManga,   panel: mangaPanel,   type: 'manga'   },
    { btn: tabLibrary, panel: libraryPanel, type: 'library' },
  ];

  function setActiveTab(type) {
    currentType = type;
    TAB_MAP.forEach(({ btn, panel, type: t }) => {
      const active = t === type;
      btn.classList.toggle('active', active);
      panel.classList.toggle('hidden', !active);
      if (active) {
        // Re-trigger CSS animation
        panel.style.animation = 'none';
        requestAnimationFrame(() => { panel.style.animation = ''; });
      }
    });
    if (type === 'library') loadLibrary();
  }

  TAB_MAP.forEach(({ btn, type }) => {
    btn.addEventListener('click', () => setActiveTab(type));
  });

  // ── Media card builder (design system) ────────────────────────────────
  function buildMediaCard({ id, title, cover, source, type, badge, extra }) {
    const safeTitle  = (title || '').replace(/"/g, '&quot;').replace(/</g, '&lt;');
    const coverUrl   = cover || 'https://via.placeholder.com/200x280/18181f/7a7a8a?text=Sin+portada';
    const badgeHtml  = badge
      ? `<span class="card-badge ${badge.class}">${badge.label}</span>`
      : '';

    return `
      <div class="media-card-wrapper">
        <div class="media-card"
          data-id="${id}"
          data-title="${safeTitle}"
          data-source="${source || ''}"
          data-type="${type || ''}">
          <img src="${coverUrl}"
               alt="${safeTitle}"
               loading="lazy"
               onerror="this.src='https://via.placeholder.com/200x280/18181f/7a7a8a?text=Sin+portada'">
          <div class="card-overlay">
            ${badgeHtml}
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
    const source = type === 'anime'
      ? document.getElementById('anime-source').value
      : document.getElementById('manga-source').value;
    const query  = type === 'anime'
      ? animeSearchInput.value.trim()
      : mangaSearchInput.value.trim();
    if (!query) return;

    const container = document.getElementById(`${type}-results`);
    container.innerHTML = `
      <div class="empty-state">
        <div class="loading-spinner"></div>
        <p>Buscando…</p>
      </div>`;

    try {
      let url = source === 'all'
        ? `/api/search-all?type=${type}&q=${encodeURIComponent(query)}`
        : `/api/search?type=${type}&source=${source}&q=${encodeURIComponent(query)}`;
      if (refresh) url += '&refresh=1';

      const res   = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const items = await res.json();
      renderSearchResults(items, type, source === 'all' ? 'all' : source);
    } catch (err) {
      container.innerHTML = `
        <div class="empty-state">
          <i class="fas fa-exclamation-circle" style="color:var(--accent2);"></i>
          <p>Error al buscar: ${err.message}</p>
        </div>`;
    }
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
      const badgeClass = type === 'anime' ? 'badge-anime' : 'badge-manga';
      return buildMediaCard({
        id:     item.id,
        title:  item.title,
        cover:  item.cover,
        source: itemSource,
        type,
        badge:  { class: 'badge-source', label: itemSource },
        extra:  `<button class="download-btn" style="
                    margin-top:6px; width:100%;
                    background:rgba(196,107,255,0.18);
                    border:1px solid rgba(196,107,255,0.3);
                    color:var(--accent);
                    border-radius:6px; padding:5px 8px;
                    font-size:11px; cursor:pointer;
                    display:flex; align-items:center; justify-content:center; gap:5px;
                    transition:background .15s;">
                  <i class="fas fa-download"></i> Descargar todo
                 </button>`,
      });
    }).join('');

    // Stagger animation
    if (window.animateCards) window.animateCards(`#${type}-results`);

    // Click en card → detalle
    container.querySelectorAll('.media-card').forEach(card => {
      card.addEventListener('click', e => {
        if (e.target.closest('.download-btn')) return;
        const { id, source: src, type: typ } = card.dataset;
        window.location.href = `/serie/${typ}/${src}/${id}`;
      });
    });

    // Click en botón descargar
    container.querySelectorAll('.download-btn').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const card  = btn.closest('.media-card');
        const { id, title, source: src, type: typ } = card.dataset;
        downloadSeries(typ, src, id, title);
      });
    });
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
        showNotification(`Descarga encolada`, 'success');
        if (window.showDownloadIndicator) window.showDownloadIndicator();
      }
    } catch (err) {
      showNotification(`Error al encolar: ${err.message}`, 'error');
    }
  }

  // ── Biblioteca local ───────────────────────────────────────────────────
  async function loadLibrary() {
    const container = document.getElementById('library-results');
    if (!container) return;
    container.innerHTML = `
      <div class="empty-state">
        <div class="loading-spinner"></div>
        <p>Cargando biblioteca…</p>
      </div>`;
    try {
      const res   = await fetch('/api/library');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const items = await res.json();
      renderLibrary(items);
    } catch (err) {
      container.innerHTML = `
        <div class="empty-state">
          <i class="fas fa-exclamation-circle" style="color:var(--accent2);"></i>
          <p>Error al cargar biblioteca: ${err.message}</p>
        </div>`;
    }
  }

  function renderLibrary(items) {
    const container = document.getElementById('library-results');
    if (!container) return;

    if (!items || !items.length) {
      container.innerHTML = `
        <div class="empty-state">
          <i class="fas fa-folder-open"></i>
          <p>Tu biblioteca está vacía. Usa la búsqueda para descargar series.</p>
        </div>`;
      return;
    }

    container.innerHTML = items.map(item => {
      const lastChapter = item.last_chapter || '1';
      const typeClass   = item.type === 'anime' ? 'badge-anime' : 'badge-manga';
      const typeLabel   = item.type === 'anime' ? 'Anime' : 'Manga';
      return buildMediaCard({
        id:     item.id || '',
        title:  item.title,
        cover:  item.cover,
        source: 'local',
        type:   item.type || '',
        badge:  { class: typeClass, label: typeLabel },
        extra:  `<div style="display:flex; gap:5px; margin-top:6px;">
                   <button class="resume-btn" data-last-chapter="${lastChapter}" style="
                     flex:1; background:rgba(74,222,128,0.15);
                     border:1px solid rgba(74,222,128,0.25);
                     color:#4ade80; border-radius:6px; padding:5px 8px;
                     font-size:11px; cursor:pointer;
                     display:flex; align-items:center; justify-content:center; gap:5px;
                     transition:background .15s;">
                     <i class="fas fa-play"></i> Cap. ${lastChapter}
                   </button>
                 </div>`,
      });
    }).join('');

    if (window.animateCards) window.animateCards('#library-results');

    // Click en card → detalle
    container.querySelectorAll('.media-card').forEach(card => {
      card.addEventListener('click', e => {
        if (e.target.closest('.resume-btn')) return;
        const { type, id } = card.dataset;
        if (type && id) window.location.href = `/serie/${type}/local/${id}`;
      });
    });

    // Click en reanudar → lector
    container.querySelectorAll('.resume-btn').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const card = btn.closest('.media-card');
        const { type, id } = card.dataset;
        const lastChapter  = btn.dataset.lastChapter;
        if (type && id && lastChapter)
          window.location.href = `/reader/${type}/local/${id}/${lastChapter}`;
      });
    });
  }

  // ── Notificaciones ─────────────────────────────────────────────────────
  // Expuesta globalmente para que serie.js y queue-indicator.js la usen
  window.showNotification = function(message, type = 'info', duration = 3500) {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      Object.assign(container.style, {
        position:      'fixed',
        bottom:        '24px',
        right:         '24px',
        zIndex:        '10001',
        display:       'flex',
        flexDirection: 'column',
        gap:           '8px',
        pointerEvents: 'none',
        maxWidth:      '320px',
      });
      document.body.appendChild(container);
    }

    const colors = {
      success: { bg: 'rgba(74,222,128,0.15)',  border: 'rgba(74,222,128,0.3)',  icon: '✓' },
      error:   { bg: 'rgba(248,113,113,0.15)', border: 'rgba(248,113,113,0.3)', icon: '✕' },
      info:    { bg: 'rgba(196,107,255,0.12)', border: 'rgba(196,107,255,0.25)', icon: 'ℹ' },
    };
    const c = colors[type] || colors.info;

    const toast = document.createElement('div');
    Object.assign(toast.style, {
      background:    c.bg,
      border:        `1px solid ${c.border}`,
      backdropFilter: 'blur(12px)',
      color:         'var(--text)',
      padding:       '10px 14px',
      borderRadius:  '10px',
      fontSize:      '13px',
      fontFamily:    'var(--ff-body)',
      pointerEvents: 'auto',
      boxShadow:     '0 4px 20px rgba(0,0,0,0.3)',
      opacity:       '0',
      transform:     'translateX(20px)',
      transition:    'opacity 0.22s ease, transform 0.22s ease',
      display:       'flex',
      alignItems:    'center',
      gap:           '8px',
    });
    toast.innerHTML = `<span style="flex-shrink:0; opacity:0.8;">${c.icon}</span><span>${message}</span>`;
    container.appendChild(toast);

    requestAnimationFrame(() => requestAnimationFrame(() => {
      toast.style.opacity   = '1';
      toast.style.transform = 'translateX(0)';
    }));

    setTimeout(() => {
      toast.style.opacity   = '0';
      toast.style.transform = 'translateX(20px)';
      setTimeout(() => toast.remove(), 250);
    }, duration);
  };

  // ── Eventos de búsqueda ────────────────────────────────────────────────
  animeSearchBtn?.addEventListener('click',  () => search(false));
  mangaSearchBtn?.addEventListener('click',  () => search(false));
  animeRefreshBtn?.addEventListener('click', () => search(true));
  mangaRefreshBtn?.addEventListener('click', () => search(true));
  animeSearchInput?.addEventListener('keypress', e => { if (e.key === 'Enter') search(false); });
  mangaSearchInput?.addEventListener('keypress', e => { if (e.key === 'Enter') search(false); });

  // ── Inicializar en biblioteca ──────────────────────────────────────────
  setActiveTab('library');
})();