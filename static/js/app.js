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
  function buildMediaCard({ id, title, cover, source, type, badge, extra }) {
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

    // [OPT-4] Event delegation — un listener por contenedor en vez de uno por card
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
    }, { once: false }); // se reemplaza con cada render porque container.innerHTML se pisa
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
    const lastChapter = item.last_chapter || '1';
    const isAnime     = item.type === 'anime';
    const typeClass   = isAnime ? 'chip-anime' : 'chip-manga';
    const typeLabel   = isAnime ? 'Anime' : 'Manga';

    // Status chip
    const statusChipClass = status !== 'none' ? `chip-${status}` : '';
    const statusChipHtml  = meta.label
      ? `<span class="chip-sep"></span>
         <span class="chip ${statusChipClass}" style="font-size:10px; height:22px; padding:0 8px;">
           <i class="fas ${meta.icon}" style="font-size:9px; margin-right:3px;"></i>${meta.label}
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
      extra:  `<div class="card-chips card-chips-nowrap">
                  <span class="chip ${typeClass} chip-sm">${typeLabel}</span>
                  ${statusChipHtml}
                </div>
                <div class="card-actions-row">
                  <button class="resume-btn" data-last-chapter="${lastChapter}">
                    <i class="fas fa-play" style="font-size:9px;"></i> Cap. ${lastChapter}
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

  // ── Settings popup (activar/desactivar fuentes) ─────────────────────────
  let _settingsPopup       = null;
  let _settingsBtnRef      = null;
  let _settingsCloseHandler = null;
  let _settingsEscHandler  = null;

  const SOURCE_ICONS = {
    anime: 'fa-film',
    manga: 'fa-book',
  };

  window.toggleSettingsPopup = function(btn) {
    if (_settingsPopup) {
      closeSettingsPopup();
    } else {
      openSettingsPopup(btn);
    }
  };

  async function openSettingsPopup(anchorBtn) {
    closeSettingsPopup();
    _settingsBtnRef = anchorBtn;

    const popup = document.createElement('div');
    popup.id = 'settings-popup';
    Object.assign(popup.style, {
      position:       'fixed',
      zIndex:         '10002',
      background:     'rgba(10,10,15,0.97)',
      border:         '1px solid rgba(255,255,255,0.12)',
      borderRadius:   '12px',
      padding:        '4px',
      display:        'flex',
      flexDirection:  'column',
      gap:            '2px',
      backdropFilter: 'blur(16px)',
      boxShadow:      '0 8px 32px rgba(0,0,0,0.5)',
      minWidth:       '200px',
      opacity:        '0',
      transform:      'scale(0.95) translateY(-4px)',
      transition:     'opacity 0.15s ease, transform 0.15s ease',
    });

    // Header
    const header = document.createElement('div');
    header.className = 'settings-header';
    header.innerHTML = '<span>Fuentes</span>';
    popup.appendChild(header);

    // Loading state
    const loadingRow = document.createElement('div');
    loadingRow.style.cssText = 'padding:12px 10px; text-align:center; font-size:12px; color:var(--muted);';
    loadingRow.textContent = 'Cargando…';
    popup.appendChild(loadingRow);
    document.body.appendChild(popup);

    requestAnimationFrame(() => requestAnimationFrame(() => {
      popup.style.opacity   = '1';
      popup.style.transform = 'scale(1) translateY(0)';
    }));

    _settingsPopup = popup;

    _settingsEscHandler = e => {
      if (e.key === 'Escape') closeSettingsPopup();
    };
    _settingsCloseHandler = e => {
      if (!popup.contains(e.target) && e.target !== anchorBtn) closeSettingsPopup();
    };
    setTimeout(() => {
      document.addEventListener('keydown', _settingsEscHandler);
      document.addEventListener('click', _settingsCloseHandler);
    }, 0);

    // Position
    positionSettingsPopup(anchorBtn, popup);

    // Fetch sources
    try {
      const res = await fetch('/api/settings/sources');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const sources = await res.json();
      loadingRow.remove();
      renderSourceSettings(popup, sources);
    } catch (err) {
      loadingRow.textContent = 'Error al cargar';
      loadingRow.style.color = 'var(--danger)';
    }
  }

  function positionSettingsPopup(anchorBtn, popup) {
    const rect = anchorBtn.getBoundingClientRect();
    const pw   = 200;
    const ph   = 220;
    let top    = rect.bottom + 6;
    let left   = rect.right - pw;
    if (left < 8) left = 8;
    if (top + ph > window.innerHeight - 8) top = rect.top - ph - 6;
    if (top < 8) top = 8;
    popup.style.top  = `${top}px`;
    popup.style.left = `${left}px`;
  }

  function renderSourceSettings(popup, sources) {
    sources.forEach(src => {
      const row = document.createElement('div');
      row.className = 'settings-source-row';

      const icon = document.createElement('i');
      icon.className = `fas ${SOURCE_ICONS[src.type] || 'fa-globe'} settings-source-icon`;
      icon.style.color = src.type === 'anime' ? 'var(--accent-lt)' : '#ff94b8';

      const label = document.createElement('span');
      label.className = 'settings-source-label';
      label.textContent = src.label;

      const toggle = document.createElement('label');
      toggle.className = 'settings-toggle';

      const input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = src.enabled;

      const track = document.createElement('span');
      track.className = 'toggle-track';

      toggle.appendChild(input);
      toggle.appendChild(track);

      input.addEventListener('change', async function() {
        const newVal = this.checked;
        try {
          const res = await fetch('/api/settings/sources', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ [src.name]: newVal }),
          });
          if (!res.ok) {
            this.checked = !newVal;
            if (window.showNotification) window.showNotification('Error al guardar', 'error');
          } else {
            src.enabled = newVal;
            populateSourceDropdowns();
          }
        } catch (err) {
          this.checked = !newVal;
          if (window.showNotification) window.showNotification(`Error: ${err.message}`, 'error');
        }
      });

      row.appendChild(icon);
      row.appendChild(label);
      row.appendChild(toggle);
      popup.appendChild(row);
    });
  }

  function closeSettingsPopup() {
    if (!_settingsPopup) return;
    const popup  = _settingsPopup;
    _settingsPopup = null;
    _settingsBtnRef = null;
    popup.style.opacity   = '0';
    popup.style.transform = 'scale(0.95) translateY(-4px)';
    setTimeout(() => popup.remove(), 150);
    document.removeEventListener('click',   _settingsCloseHandler);
    document.removeEventListener('keydown', _settingsEscHandler);
  }

  // ── Notificaciones (global) ────────────────────────────────────────────
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
      success: { bg: 'rgba(74,222,128,0.15)',   border: 'rgba(74,222,128,0.3)',   icon: '✓' },
      error:   { bg: 'rgba(248,113,113,0.15)',  border: 'rgba(248,113,113,0.3)',  icon: '✕' },
      info:    { bg: 'rgba(196,107,255,0.12)',  border: 'rgba(196,107,255,0.25)', icon: 'ℹ' },
    };
    const c = colors[type] || colors.info;

    const toast = document.createElement('div');
    Object.assign(toast.style, {
      background:     c.bg,
      border:         `1px solid ${c.border}`,
      backdropFilter: 'blur(12px)',
      color:          'var(--text)',
      padding:        '10px 14px',
      borderRadius:   '10px',
      fontSize:       '13px',
      fontFamily:     'var(--ff-body)',
      pointerEvents:  'auto',
      boxShadow:      '0 4px 20px rgba(0,0,0,0.3)',
      opacity:        '0',
      transform:      'translateX(20px)',
      transition:     'opacity 0.22s ease, transform 0.22s ease',
      display:        'flex',
      alignItems:     'center',
      gap:            '8px',
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