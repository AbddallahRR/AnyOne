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

  // ── CoverObserver — lazy load + VRAM release ──────────────────────────
  //
  // El browser mantiene cada <img> decodificada en VRAM aunque esté a miles
  // de píxeles fuera del viewport. Con grids grandes (búsqueda global,
  // biblioteca) esto dispara el uso de memoria de video al hacer scroll.
  //
  // Solución: las cards usan data-src en lugar de src. Este observer:
  //   • Asigna src cuando la card ENTRA al viewport + margen de 200px  → carga
  //   • Borra src cuando la card SALE del viewport + margen de 800px   → libera VRAM
  //
  // El margen asimétrico (200 entrada / 800 salida) evita parpadeos: la imagen
  // se precarga antes de ser visible y se libera solo cuando está muy lejos.

  const PLACEHOLDER = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" '
    + 'width="2" height="3"%3E%3C/svg%3E'; // 2×3px transparent — preserva aspect-ratio

  const coverObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      const img = entry.target;
      if (entry.isIntersecting) {
        // Entró: cargar imagen real
        const real = img.dataset.src;
        if (real && img.src !== real) img.src = real;
      } else {
        // Salió: liberar VRAM (solo si ya cargó, para no cortar descargas en curso)
        if (img.complete && img.naturalWidth > 0) {
          img.src = PLACEHOLDER;
        }
      }
    });
  }, {
    rootMargin: '200px 0px 800px 0px', // top/bottom asimétrico
    threshold:  0,
  });

  /** Registra todas las .cover-lazy de un contenedor en el observer */
  function observeCovers(container) {
    container.querySelectorAll('img.cover-lazy').forEach(img => {
      coverObserver.observe(img);
    });
  }

  // ── Media card builder (design system) ────────────────────────────────
  function buildMediaCard({ id, title, cover, source, type, badge, extra }) {
    const safeTitle = (title || '').replace(/"/g, '&quot;').replace(/</g, '&lt;');
    const dataSrc   = cover || '';
    const badgeHtml = badge
      ? `<span class="card-badge ${badge.class}">${badge.label}</span>`
      : '';

    // src empieza como placeholder — CoverObserver asigna el real al entrar al viewport
    return `
      <div class="media-card-wrapper">
        <div class="media-card"
          data-id="${id}"
          data-title="${safeTitle}"
          data-source="${source || ''}"
          data-type="${type || ''}">
          <img class="cover-lazy"
               src="${PLACEHOLDER}"
               data-src="${dataSrc}"
               alt="${safeTitle}"
               style="background:var(--raised);">
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

    // Lazy load + VRAM release de portadas
    observeCovers(container);

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

  // Estado de la biblioteca
  let _libraryItems    = [];   // todos los items cargados de la API
  let _libraryStatuses = {};   // content_ref → status
  let _libraryFilter   = 'all';
  let _libraryQuery    = '';

  const STATUS_META = {
    watching:  { label: 'Mirando',   color: 'var(--accent)',  border: 'rgba(196,107,255,0.4)', bg: 'rgba(196,107,255,0.12)', icon: 'fa-eye' },
    completed: { label: 'Visto',     color: '#4ade80',        border: 'rgba(74,222,128,0.4)',  bg: 'rgba(74,222,128,0.12)',  icon: 'fa-check-circle' },
    pending:   { label: 'Pendiente', color: '#fbbf24',        border: 'rgba(251,191,36,0.4)',  bg: 'rgba(251,191,36,0.12)', icon: 'fa-clock' },
    none:      { label: '',          color: '',               border: '',                      bg: '',                      icon: '' },
  };

  // Orden de prioridad para mostrar
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
    } catch (err) {
      container.innerHTML = `
        <div class="empty-state">
          <i class="fas fa-exclamation-circle" style="color:var(--accent2);"></i>
          <p>Error al cargar biblioteca: ${err.message}</p>
        </div>`;
    }
  }

  function _initLibraryControls() {
    // Búsqueda local
    const searchInput = document.getElementById('library-search-input');
    if (searchInput && !searchInput.dataset.bound) {
      searchInput.dataset.bound = '1';
      searchInput.addEventListener('input', () => {
        _libraryQuery = searchInput.value.toLowerCase();
        applyLibraryView();
      });
    }

    // Filtros de etiqueta
    document.querySelectorAll('.lib-filter').forEach(btn => {
      if (btn.dataset.bound) return;
      btn.dataset.bound = '1';
      btn.addEventListener('click', () => {
        _libraryFilter = btn.dataset.filter;
        document.querySelectorAll('.lib-filter').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        applyLibraryView();
      });
    });
  }

  function applyLibraryView() {
    const container = document.getElementById('library-results');
    if (!container) return;

    // 1. Filtrar por etiqueta
    let filtered = _libraryItems.filter(item => {
      const ref    = `local:${item.id}`;
      const status = _libraryStatuses[ref] || 'none';
      if (_libraryFilter === 'all') return true;
      return status === _libraryFilter;
    });

    // 2. Filtrar por búsqueda
    if (_libraryQuery) {
      filtered = filtered.filter(item =>
        (item.title || '').toLowerCase().includes(_libraryQuery) ||
        (item.id    || '').toLowerCase().includes(_libraryQuery)
      );
    }

    // 3. Ordenar: watching → completed → pending → none
    filtered.sort((a, b) => {
      const sa = STATUS_ORDER[_libraryStatuses[`local:${a.id}`] || 'none'];
      const sb = STATUS_ORDER[_libraryStatuses[`local:${b.id}`] || 'none'];
      if (sa !== sb) return sa - sb;
      return (a.title || '').localeCompare(b.title || '');
    });

    // 4. Actualizar contador
    const countEl = document.getElementById('library-count');
    if (countEl) countEl.textContent = `${filtered.length} serie${filtered.length !== 1 ? 's' : ''}`;

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
      return;
    }

    renderLibrary(filtered);
  }

  function renderLibrary(items) {
    const container = document.getElementById('library-results');
    if (!container) return;

    container.innerHTML = items.map(item => {
      const ref         = `local:${item.id}`;
      const status      = _libraryStatuses[ref] || 'none';
      const meta        = STATUS_META[status];
      const lastChapter = item.last_chapter || '1';
      const typeClass   = item.type === 'anime' ? 'badge-anime' : 'badge-manga';
      const typeLabel   = item.type === 'anime' ? 'Anime' : 'Manga';

      // Badge de etiqueta (encima de la portada si tiene)
      const statusBadge = meta.label ? `
        <span class="card-badge" style="
          background:${meta.bg}; color:${meta.color};
          border:1px solid ${meta.border}; margin-bottom:4px;">
          <i class="fas ${meta.icon}" style="margin-right:3px; font-size:9px;"></i>${meta.label}
        </span>` : '';

      // Botón de etiqueta — abre popup contextual
      const statusBtn = `
        <button class="status-tag-btn" data-ref="${ref}"
          title="Cambiar etiqueta"
          style="
            width:28px; height:28px; border-radius:6px; flex-shrink:0;
            background:${meta.bg || 'rgba(255,255,255,0.05)'};
            border:1px solid ${meta.border || 'var(--border)'};
            color:${meta.color || 'var(--muted)'};
            cursor:pointer; display:flex; align-items:center; justify-content:center;
            font-size:10px; transition:background .15s, transform .12s;">
          <i class="fas ${meta.icon || 'fa-tag'}"></i>
        </button>`;

      return buildMediaCard({
        id:     item.id || '',
        title:  item.title,
        cover:  item.cover,
        source: 'local',
        type:   item.type || '',
        badge:  { class: typeClass, label: typeLabel },
        extra:  `<div style="display:flex; gap:5px; margin-top:6px;">
                   ${statusBadge}
                 </div>
                 <div style="display:flex; gap:5px; margin-top:4px;">
                   <button class="resume-btn" data-last-chapter="${lastChapter}" style="
                     flex:1; background:rgba(74,222,128,0.15);
                     border:1px solid rgba(74,222,128,0.25);
                     color:#4ade80; border-radius:6px; padding:5px 8px;
                     font-size:11px; cursor:pointer;
                     display:flex; align-items:center; justify-content:center; gap:5px;
                     transition:background .15s;">
                     <i class="fas fa-play"></i> Cap. ${lastChapter}
                   </button>
                   ${statusBtn}
                 </div>`,
      });
    }).join('');

    if (window.animateCards) window.animateCards('#library-results');
    observeCovers(container);

    // Click en card → detalle
    container.querySelectorAll('.media-card').forEach(card => {
      card.addEventListener('click', e => {
        if (e.target.closest('.resume-btn, .status-cycle-btn')) return;
        const { type, id } = card.dataset;
        if (type && id) window.location.href = `/serie/${type}/local/${id}`;
      });
    });

    // Reanudar
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

    // Botón de etiqueta → popup contextual
    container.querySelectorAll('.status-tag-btn').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        openStatusPopup(btn, btn.dataset.ref);
      });
    });
  }

  // ── Popup contextual de etiqueta ───────────────────────────────────────

  let _statusPopup   = null;
  let _popupRef      = null;
  let _popupCloseHandler = null;

  const STATUS_OPTIONS = [
    { value: 'watching',  label: 'Mirando',   icon: 'fa-eye',          color: 'var(--accent)', border: 'rgba(196,107,255,0.35)', bg: 'rgba(196,107,255,0.1)' },
    { value: 'completed', label: 'Visto',      icon: 'fa-check-circle', color: '#4ade80',       border: 'rgba(74,222,128,0.35)',  bg: 'rgba(74,222,128,0.1)'  },
    { value: 'pending',   label: 'Pendiente',  icon: 'fa-clock',        color: '#fbbf24',       border: 'rgba(251,191,36,0.35)', bg: 'rgba(251,191,36,0.1)'  },
    { value: 'none',      label: 'Sin etiqueta', icon: 'fa-tag',        color: 'var(--muted)',  border: 'var(--border)',         bg: 'transparent'           },
  ];

  function openStatusPopup(anchorBtn, ref) {
    closeStatusPopup();
    _popupRef = ref;
    const current = _libraryStatuses[ref] || 'none';

    // Crear popup
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

    // Opciones
    STATUS_OPTIONS.forEach(opt => {
      const row = document.createElement('button');
      const isActive = opt.value === current;
      Object.assign(row.style, {
        display:        'flex',
        alignItems:     'center',
        gap:            '9px',
        padding:        '7px 10px',
        borderRadius:   '8px',
        border:         isActive ? `1px solid ${opt.border}` : '1px solid transparent',
        background:     isActive ? opt.bg : 'transparent',
        color:          isActive ? opt.color : 'var(--muted)',
        fontSize:       '13px',
        fontFamily:     'var(--ff-body)',
        cursor:         'pointer',
        textAlign:      'left',
        width:          '100%',
        transition:     'background 0.12s, color 0.12s',
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
        if (opt.value === current) return; // sin cambio
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

    // Posicionar el popup junto al botón, sin salirse de la pantalla
    const rect   = anchorBtn.getBoundingClientRect();
    const pw     = 160; // min-width
    const ph     = 4 * 38; // aprox alto
    let   top    = rect.bottom + 6;
    let   left   = rect.left;

    if (left + pw > window.innerWidth - 8)  left  = window.innerWidth  - pw - 8;
    if (top  + ph > window.innerHeight - 8) top   = rect.top - ph - 6;
    if (left < 8) left = 8;

    popup.style.top  = `${top}px`;
    popup.style.left = `${left}px`;

    // Animar entrada
    requestAnimationFrame(() => requestAnimationFrame(() => {
      popup.style.opacity   = '1';
      popup.style.transform = 'scale(1) translateY(0)';
    }));

    // Cerrar al hacer clic fuera o presionar Escape
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
    const popup = _statusPopup;
    _statusPopup = null;
    _popupRef    = null;
    popup.style.opacity   = '0';
    popup.style.transform = 'scale(0.95) translateY(-4px)';
    setTimeout(() => popup.remove(), 150);
    document.removeEventListener('click',   _popupCloseHandler);
    document.removeEventListener('keydown', _escCloseHandler);
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