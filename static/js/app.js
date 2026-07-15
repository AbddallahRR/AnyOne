// static/js/app.js
(function () {
  'use strict';

  // ── Estado global ──────────────────────────────────────────────────────
  let currentType      = 'library';
  let _libraryItems    = [];
  let _libraryStatuses = {};
  let _libraryFilter   = 'all';
  let _libraryTypeFilter = 'all';
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

  // ── Bell button → open updates popup ──────────────────────────────────
  document.getElementById('nav-bell')?.addEventListener('click', () => {
    _showUpdatesPopup();
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

      const data = await api.get(url);
      renderSearchResults(data, type, source);
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
      const data = JSON.parse(e.data);
      if (localStorage.getItem('anyone_hide_scraper_errors') === 'true') return;
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
      const data = await api.post('/api/download', { type, source, content_id: contentId, title, exclude_watched: true });
      showNotification('Descarga encolada', 'success');
      if (window.showDownloadIndicator) window.showDownloadIndicator();
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
      const [libData, statusData] = await Promise.all([
        api.get('/api/library'),
        api.get('/api/library/status').catch(() => ({})),
      ]);
      _libraryItems    = libData.items;
      _libraryStatuses = statusData;
      _initLibraryControls();
      applyLibraryView();
      fetchUpdatesBadge();
      renderRecentSeries(libData.recent || []);
    } catch (err) {
      container.innerHTML = `
        <div class="empty-state">
          <i class="fas fa-exclamation-circle" style="color:var(--accent2);"></i>
          <p>Error al cargar biblioteca: ${err.message}</p>
        </div>`;
    }
  }

  // ── Badge global de novedades ─────────────────────────────────────────
  let _lastUpdatesData = null;

  async function fetchUpdatesBadge() {
    try {
      const data = await api.get('/api/library/updates');
      const total = data.total || 0;

      const oldBadge = tabLibrary.querySelector('.update-badge-global');
      if (oldBadge) oldBadge.remove();

      _lastUpdatesData = (total > 0) ? data : null;
      _updateBellBadge(total);

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

  function _updateBellBadge(total) {
    const bell = document.getElementById('nav-bell');
    if (!bell) return;
    let b = bell.querySelector('.bell-badge');
    if (total > 0) {
      if (!b) {
        b = document.createElement('span');
        b.className = 'bell-badge';
        Object.assign(b.style, {
          position: 'absolute',
          top: '-3px',
          right: '-3px',
          background: 'var(--accent2, #f59e0b)',
          color: '#000',
          fontSize: '8px',
          fontWeight: '700',
          borderRadius: '999px',
          minWidth: '14px',
          height: '14px',
          lineHeight: '14px',
          textAlign: 'center',
          padding: '0 3px',
          pointerEvents: 'none',
        });
        bell.style.position = 'relative';
        bell.appendChild(b);
      }
      b.textContent = total > 99 ? '99+' : total;
    } else if (b) {
      b.remove();
    }
  }

  function _showUpdatesPopup() {
    const existing = document.getElementById('updates-popup');
    if (existing) {
      if (!existing.classList.contains('updates-popup-visible')) {
        existing.classList.add('updates-popup-visible');
      }
      return;
    }

    const data = _lastUpdatesData;
    const series = data ? data.series : [];
    const total = data ? data.total : 0;

    const items = series.slice(0, 5).map(s => {
      const chs = Array.isArray(s.new_chapters) ? s.new_chapters : [];
      const chText = chs.length > 0
        ? (chs.length <= 3 ? chs.join(', ') : `${chs.slice(0, 2).join(', ')} y ${chs.length - 2} más`)
        : '';
      return `<div class="updates-popup-item">
        <span class="updates-popup-title">${s.title}</span>
        ${chText ? `<span class="updates-popup-chs">Cap. ${chText}</span>` : ''}
      </div>`;
    }).join('');

    const extra = total > 5 ? `<div class="updates-popup-more">y ${total - 5} serie${total - 5 !== 1 ? 's' : ''} más…</div>` : '';
    const bodyContent = total > 0 ? items + extra : '<div class="updates-popup-empty">No hay capítulos nuevos por ahora</div>';

    const popup = document.createElement('div');
    popup.id = 'updates-popup';
    popup.innerHTML = `
      <div class="updates-popup-content">
        <div class="updates-popup-header">
          <i class="fas fa-inbox"></i>
          <span>Notificaciones</span>
          <button class="updates-popup-close">&times;</button>
        </div>
        <div class="updates-popup-body">${bodyContent}</div>
        <div class="updates-popup-footer">
          <button class="updates-popup-check"><i class="fas fa-sync-alt"></i> Buscar actualizaciones</button>
        </div>
      </div>`;
    document.body.appendChild(popup);

    popup.addEventListener('click', (e) => {
      if (e.target === popup) {
        popup.classList.add('updates-popup-hiding');
        setTimeout(() => popup.remove(), 300);
      }
    });

    popup.querySelector('.updates-popup-close').addEventListener('click', () => {
      popup.classList.add('updates-popup-hiding');
      setTimeout(() => popup.remove(), 300);
    });

    popup.querySelector('.updates-popup-check').addEventListener('click', async () => {
      const btn = popup.querySelector('.updates-popup-check');
      btn.disabled = true;
      btn.innerHTML = '<i class="fas fa-spinner"></i> Buscando\u2026';
      try {
        const result = await api.post('/api/library/check-all-updates');
        await fetchUpdatesBadge();
        const newData = _lastUpdatesData;
        const newSeries = newData ? newData.series : [];
        const newTotal = newData ? newData.total : 0;
        const results = result.results || [];
        const totalQueued = results.reduce((sum, r) => sum + (r.queued || 0), 0);
        const body = popup.querySelector('.updates-popup-body');
        if (newTotal > 0) {
          const newItems = newSeries.slice(0, 5).map(s => {
            const chs = Array.isArray(s.new_chapters) ? s.new_chapters : [];
            const chText = chs.length > 0
              ? (chs.length <= 3 ? chs.join(', ') : `${chs.slice(0, 2).join(', ')} y ${chs.length - 2} más`)
              : '';
            return `<div class="updates-popup-item">
              <span class="updates-popup-title">${s.title}</span>
              ${chText ? `<span class="updates-popup-chs">Cap. ${chText}</span>` : ''}
            </div>`;
          }).join('');
          const newExtra = newTotal > 5 ? `<div class="updates-popup-more">y ${newTotal - 5} serie${newTotal - 5 !== 1 ? 's' : ''} más…</div>` : '';
          body.innerHTML = newItems + newExtra;
          const msg = totalQueued > 0
            ? `${newTotal} serie${newTotal !== 1 ? 's' : ''} con novedades — ${totalQueued} capítulo${totalQueued !== 1 ? 's' : ''} encolado${totalQueued !== 1 ? 's' : ''}`
            : `${newTotal} serie${newTotal !== 1 ? 's' : ''} con capítulos nuevos`;
          showNotification(msg, 'success');
        } else {
          body.innerHTML = '<div class="updates-popup-empty">No hay capítulos nuevos</div>';
          showNotification('No se encontraron actualizaciones', 'info');
        }
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-sync-alt"></i> Buscar actualizaciones';
      } catch (err) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-sync-alt"></i> Buscar actualizaciones';
        showNotification('Error al buscar actualizaciones', 'error');
      }
    });

    requestAnimationFrame(() => popup.classList.add('updates-popup-visible'));
  }

  // ── Series recientes ──────────────────────────────────────────────────
  function renderRecentSeries(recent) {
    const section = document.getElementById('recent-section');
    const list    = document.getElementById('recent-list');
    if (!section || !list) return;

    if (!recent || recent.length === 0) {
      section.classList.add('hidden');
      return;
    }
    section.classList.remove('hidden');

    list.innerHTML = recent.map(item => {
      const isAnime   = item.type === 'anime';
      const typeLabel = isAnime ? 'Anime' : 'Manga';
      const chapter   = item.chapter || '1';
      const cover = item.cover || '';
      const total = item.total_episodes || 0;
      const progress = parseInt(item.progress) || 0;
      const chapterTotal = item.chapter_total || 0;
      let metaText;
      let pct = 0;
      if (isAnime) {
        const mins = Math.floor(progress / 60);
        const secs = progress % 60;
        metaText = total > 0 ? `Cap. ${chapter}/${total} · ${mins}:${secs.toString().padStart(2, '0')}` : `Cap. ${chapter} · ${mins}:${secs.toString().padStart(2, '0')}`;
        if (chapterTotal > 0) pct = Math.min(Math.round((progress / chapterTotal) * 100), 100);
      } else {
        const pageInfo = progress > 0 ? ` · Pág. ${progress}` : '';
        metaText = total > 0 ? `Cap. ${chapter}/${total}${pageInfo}` : `Cap. ${chapter}${pageInfo}`;
        if (chapterTotal > 1) pct = Math.min(Math.round((progress / (chapterTotal - 1)) * 100), 100);
      }
      return `
        <div class="recent-card" data-id="${item.id}" data-type="${item.type}" data-chapter="${chapter}">
          <div class="recent-cover-wrap">
            <img class="recent-cover cover-lazy" data-src="${cover}"
              src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='180'%3E%3Crect fill='%2313131e' width='120' height='180'/%3E%3C/svg%3E"
              alt="${item.title}" loading="lazy"
              onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22120%22 height=%22180%22%3E%3Crect fill=%22%2313131e%22 width=%22120%22 height=%22180%22/%3E%3Ctext x=%2260%22 y=%2290%22 text-anchor=%22middle%22 fill=%22%236e6e88%22 font-size=%2210%22%3ESin portada%3C/text%3E%3C/svg%3E'">
            <span class="chip chip-sm chip-${item.type} type-chip">${typeLabel}</span>
            <span class="recent-badge"></span>
          </div>
          <div class="recent-info">
            <div class="recent-card-title" title="${item.title}">${item.title}</div>
            <div class="recent-meta">${metaText}</div>
            ${chapterTotal > 0 ? `<div class="recent-progress-bar"><div class="recent-progress-fill" style="width:${pct}%"></div></div>` : ''}
          </div>
        </div>`;
    }).join('');

    // Click → navegar directo al episodio
    list.addEventListener('click', e => {
      const card = e.target.closest('.recent-card');
      if (!card) return;
      const { id, type, chapter } = card.dataset;
      if (type && id) window.location.href = `/reader/${type}/local/${id}/${chapter || '1'}`;
    });

    // Lazy load covers
    observeCovers(list);
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

    // [OPT-4] Event delegation para filtros de etiqueta
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

    // Event delegation para filtros de tipo
    const typeFiltersBar = document.getElementById('library-type-filters');
    if (typeFiltersBar) {
      typeFiltersBar.addEventListener('click', e => {
        const btn = e.target.closest('.type-filter');
        if (!btn) return;
        _libraryTypeFilter = btn.dataset.typeFilter;
        typeFiltersBar.querySelectorAll('.type-filter').forEach(b => b.classList.remove('active'));
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

    // 1b. Filtrar por tipo (anime / manga)
    if (_libraryTypeFilter !== 'all') {
      filtered = filtered.filter(item => item.type === _libraryTypeFilter);
    }

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
      // Reordenar nodos existentes según filtered
      const node = _renderedCards.get(item.id);
      if (node && node.parentNode === container) {
        frag.appendChild(node);
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
  }

  function _buildLibraryCard(item) {
    const ref         = `local:${item.id}`;
    const status      = _libraryStatuses[ref] || 'none';
    const meta        = STATUS_META[status];
    const resumeChapter = item.progress_chapter && item.progress_chapter !== '0'
      ? item.progress_chapter : (item.first_chapter || '1');
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
                    <i class="fas fa-play" style="font-size:9px;"></i> Cap. ${resumeChapter}/${item.last_chapter || '?'}
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
          await api.post('/api/library/status', { content_ref: ref, status: opt.value });
          _libraryStatuses[ref] = opt.value;
          showNotification(
            opt.value === 'none' ? 'Etiqueta eliminada' : `Marcado como ${opt.label}`,
            'success', 2000
          );
          const id = ref.replace('local:', '');
          const oldNode = _renderedCards.get(id);
          if (oldNode) oldNode.remove();
          _renderedCards.delete(id);
          applyLibraryView();
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
      const sources = await api.get('/api/settings/sources');
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