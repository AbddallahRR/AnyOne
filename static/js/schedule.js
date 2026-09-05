// static/js/schedule.js
(function () {
  'use strict';

  const DAYS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
  const HOURS_START = 6;
  const HOURS_END = 23;
  const PLACEHOLDER = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="32" height="44"%3E%3Crect fill="%231a1a28" width="32" height="44" rx="4"/%3E%3C/svg%3E';

  let _schedules = [];
  let _libraryItems = [];
  let _editingRef = null;
  let _selectedRef = null;
  let _searchDebounce = null;
  let _lastSnapshot = null;
  const _coverByRef = new Map();
  const _autoAddRef = new URLSearchParams(location.search).get('add');
  let _autoAddHandled = false;

  const gridBody       = document.getElementById('sched-grid-body');
  const emptyMsg       = document.getElementById('sched-empty');
  const addBtn         = document.getElementById('sched-add-btn');
  const modal          = document.getElementById('sched-modal');
  const modalTitle     = document.getElementById('sched-modal-title');
  const modalClose     = document.getElementById('sched-modal-close');
  const modalCancel    = document.getElementById('sched-modal-cancel');
  const modalSave      = document.getElementById('sched-modal-save');
  const daySel         = document.getElementById('sched-day-select');
  const hourSel        = document.getElementById('sched-hour-select');
  const ctxMenu        = document.getElementById('sched-ctx-menu');
  const searchInput    = document.getElementById('sched-search-input');
  const searchResults  = document.getElementById('sched-search-results');
  const searchSelected = document.getElementById('sched-search-selected');
  const selectedCover  = document.getElementById('sched-selected-cover');
  const selectedTitle  = document.getElementById('sched-selected-title');
  const selectedType   = document.getElementById('sched-selected-type');
  const selectedClear  = document.getElementById('sched-selected-clear');

  // ── Init ──────────────────────────────────────────────────────────────
  function _toast(msg, type) {
    if (window.showNotification) window.showNotification(msg, type);
    else console.log(`[horario] ${type}: ${msg}`);
  }

  function init() {
    _populateHours();
    _bindEvents();
    _refresh({ silent: false });
    setInterval(() => {
      if (!document.hidden) _refresh();
    }, 4000);
    window.addEventListener('anyone:downloads-complete', () => _refresh());
  }

  function _populateHours() {
    for (let h = HOURS_START; h <= HOURS_END; h++) {
      const opt = document.createElement('option');
      opt.value = h;
      opt.textContent = `${String(h).padStart(2, '0')}:00`;
      hourSel.appendChild(opt);
    }
  }

  function _bindEvents() {
    addBtn.addEventListener('click', () => _openModal());
    modalClose.addEventListener('click', _closeModal);
    modalCancel.addEventListener('click', _closeModal);
    modal.addEventListener('click', e => { if (e.target === modal) _closeModal(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') { _closeModal(); _hideCtxMenu(); } });

    modalSave.addEventListener('click', _saveSchedule);

    // Search input
    searchInput.addEventListener('input', () => {
      clearTimeout(_searchDebounce);
      _searchDebounce = setTimeout(() => _renderSearchResults(searchInput.value), 150);
    });
    searchInput.addEventListener('focus', () => {
      if (!_selectedRef) _renderSearchResults(searchInput.value);
    });

    // Click outside search results → close
    document.addEventListener('click', e => {
      if (!e.target.closest('#sched-search-wrap')) {
        searchResults.classList.add('hidden');
      }
    });

    // Clear selected
    selectedClear.addEventListener('click', _clearSelection);

    // Click on grid cell → add
    gridBody.addEventListener('click', e => {
      const cell = e.target.closest('.sched-cell');
      if (cell && !e.target.closest('.sched-chip')) {
        const day = parseInt(cell.dataset.day);
        const hour = parseInt(cell.dataset.hour);
        _openModal(null, day, hour);
      }
    });

    // Right-click on chip → context menu
    gridBody.addEventListener('contextmenu', e => {
      const chip = e.target.closest('.sched-chip');
      if (!chip) return;
      e.preventDefault();
      _showCtxMenu(e.clientX, e.clientY, chip.dataset.ref);
    });

    // Click on chip → context menu
    gridBody.addEventListener('click', e => {
      const chip = e.target.closest('.sched-chip');
      if (!chip) return;
      e.stopPropagation();
      const rect = chip.getBoundingClientRect();
      _showCtxMenu(rect.right + 4, rect.top, chip.dataset.ref);
    });

    // Context menu actions
    ctxMenu.addEventListener('click', e => {
      const item = e.target.closest('.sched-ctx-item');
      if (!item) return;
      const action = item.dataset.action;
      const ref = ctxMenu.dataset.ref;
      _hideCtxMenu();
      if (action === 'edit') _openModal(ref);
      else if (action === 'delete') _deleteSchedule(ref);
    });

    // Close ctx menu on outside click
    document.addEventListener('click', e => {
      if (!ctxMenu.contains(e.target)) _hideCtxMenu();
    });
  }

  // ── Load data ─────────────────────────────────────────────────────────
  async function _refresh({ silent = true } = {}) {
    try {
      const [schedules, libData] = await Promise.all([
        api.get('/api/schedule'),
        api.get('/api/library'),
      ]);
      const snapshot = JSON.stringify({ s: schedules, l: libData.items });
      if (snapshot === _lastSnapshot) return;
      _lastSnapshot = snapshot;
      _schedules = schedules;
      _libraryItems = libData.items || [];
      _coverByRef.clear();
      for (const it of _libraryItems) _coverByRef.set(`local:${it.id}`, it.cover || '');
      _renderGrid();
      _autoOpenAddIfRequested();
    } catch (err) {
      if (!silent) {
        console.error('Error cargando horario:', err);
        _toast('Error al cargar el horario', 'error');
      }
    }
  }

  function _autoOpenAddIfRequested() {
    if (_autoAddHandled || !_autoAddRef) return;
    const item = _libraryItems.find(i => `local:${i.id}` === _autoAddRef);
    if (!item) return;
    _autoAddHandled = true;
    _openModal();
    _selectSeries(_autoAddRef, item);
  }

  // ── Search ────────────────────────────────────────────────────────────
  function _renderSearchResults(query) {
    if (_selectedRef) {
      searchResults.classList.add('hidden');
      return;
    }

    const q = (query || '').toLowerCase().trim();
    const scheduled = new Set(_schedules.map(s => s.content_ref));

    let items = _libraryItems.filter(item => {
      const ref = `local:${item.id}`;
      if (scheduled.has(ref)) return false;
      if (!q) return true;
      return (item.title || '').toLowerCase().includes(q)
          || (item.id || '').toLowerCase().includes(q);
    });

    searchResults.innerHTML = '';

    if (items.length === 0) {
      searchResults.innerHTML = `<div class="sched-search-empty">${q ? 'Sin resultados' : 'Tu biblioteca está vacía'}</div>`;
      searchResults.classList.remove('hidden');
      return;
    }

    items = items.slice(0, 20);

    for (const item of items) {
      const el = document.createElement('div');
      el.className = 'sched-search-item';
      el.dataset.ref = `local:${item.id}`;
      el.innerHTML = `
        <img class="sched-search-cover" src="${item.cover || PLACEHOLDER}"
             alt="" onerror="this.src='${PLACEHOLDER}'" />
        <div class="sched-search-info">
          <span class="sched-search-title">${_escapeHtml(item.title)}</span>
          <span class="sched-search-type">${item.type}</span>
        </div>
      `;
      el.addEventListener('click', () => _selectSeries(`local:${item.id}`, item));
      searchResults.appendChild(el);
    }

    searchResults.classList.remove('hidden');
  }

  function _selectSeries(ref, item) {
    _selectedRef = ref;
    searchInput.value = '';
    searchResults.classList.add('hidden');

    selectedCover.src = item.cover || PLACEHOLDER;
    selectedTitle.textContent = item.title || ref;
    selectedType.textContent = item.type || '';
    searchSelected.classList.remove('hidden');
    searchInput.classList.add('hidden');
  }

  function _clearSelection() {
    _selectedRef = null;
    searchSelected.classList.add('hidden');
    searchInput.classList.remove('hidden');
    searchInput.value = '';
    searchInput.focus();
  }

  // ── Render grid ───────────────────────────────────────────────────────
  function _renderGrid() {
    gridBody.innerHTML = '';

    const cellMap = {};
    for (const s of _schedules) {
      const key = `${s.day_of_week}:${s.check_hour}`;
      if (!cellMap[key]) cellMap[key] = [];
      cellMap[key].push(s);
    }

    let hasAny = false;

    for (let h = HOURS_START; h <= HOURS_END; h++) {
      const tr = document.createElement('tr');

      const tdTime = document.createElement('td');
      tdTime.className = 'sched-time-col';
      tdTime.textContent = `${String(h).padStart(2, '0')}:00`;
      tr.appendChild(tdTime);

      for (let d = 0; d < 7; d++) {
        const td = document.createElement('td');
        td.className = 'sched-cell';
        td.dataset.day = d;
        td.dataset.hour = h;

        const key = `${d}:${h}`;
        const entries = cellMap[key];
        if (entries && entries.length > 0) {
          hasAny = true;
          for (const s of entries) {
            td.appendChild(_buildChip(s));
          }
        }

        tr.appendChild(td);
      }

      gridBody.appendChild(tr);
    }

    emptyMsg.classList.toggle('hidden', hasAny);
  }

  function _buildChip(schedule) {
    const chip = document.createElement('span');
    chip.className = 'sched-chip';
    chip.dataset.ref = schedule.content_ref;
    chip.title = schedule.title;
    const cover = _coverByRef.get(schedule.content_ref) || '';
    chip.innerHTML = `
      ${cover
        ? `<img class="sched-chip-cover" src="${cover}" alt="" onerror="this.remove()" />`
        : `<i class="fas fa-hand-pointer sched-chip-icon"></i>`}
      <span class="sched-chip-label">${_escapeHtml(schedule.title)}</span>
    `;
    return chip;
  }

  function _escapeHtml(str) {
    return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ── Modal ─────────────────────────────────────────────────────────────
  function _openModal(contentRef, defaultDay, defaultHour) {
    _editingRef = contentRef || null;
    _selectedRef = null;

    if (_editingRef) {
      modalTitle.textContent = 'Editar horario';
      const existing = _schedules.find(s => s.content_ref === _editingRef);
      if (existing) {
        const item = _libraryItems.find(i => `local:${i.id}` === _editingRef);
        if (item) _selectSeries(_editingRef, item);
        daySel.value = existing.day_of_week;
        hourSel.value = existing.check_hour;
      }
    } else {
      modalTitle.textContent = 'Añadir serie al horario';
      _clearSelection();
      if (defaultDay !== undefined) daySel.value = defaultDay;
      if (defaultHour !== undefined) hourSel.value = defaultHour;
    }

    modal.classList.remove('hidden');
    requestAnimationFrame(() => requestAnimationFrame(() => modal.classList.add('open')));

    if (!_editingRef) {
      setTimeout(() => searchInput.focus(), 100);
    }
  }

  function _closeModal() {
    modal.classList.remove('open');
    setTimeout(() => modal.classList.add('hidden'), 250);
    _editingRef = null;
    _selectedRef = null;
    searchInput.classList.remove('hidden');
    searchInput.value = '';
    searchResults.classList.add('hidden');
    searchSelected.classList.add('hidden');
  }

  // ── Save ──────────────────────────────────────────────────────────────
  async function _saveSchedule() {
    if (!_selectedRef) {
      _toast('Selecciona una serie', 'error');
      return;
    }

    const day = parseInt(daySel.value);
    const hour = parseInt(hourSel.value);

    try {
      await api.post('/api/schedule', {
        content_ref: _selectedRef,
        day_of_week: day,
        check_hour: hour,
      });
      _toast('Horario guardado', 'success');
      _closeModal();
      await _refresh({ silent: false });
    } catch (err) {
      _toast(`Error: ${err.message}`, 'error');
    }
  }

  // ── Delete ────────────────────────────────────────────────────────────
  async function _deleteSchedule(contentRef) {
    try {
      await api.del(`/api/schedule/${encodeURIComponent(contentRef)}`);
      _toast('Horario eliminado', 'success');
      await _refresh({ silent: false });
    } catch (err) {
      _toast(`Error: ${err.message}`, 'error');
    }
  }

  // ── Context menu ──────────────────────────────────────────────────────
  function _showCtxMenu(x, y, ref) {
    ctxMenu.dataset.ref = ref;
    ctxMenu.classList.remove('hidden');

    const mw = 160, mh = 120;
    if (x + mw > window.innerWidth) x = window.innerWidth - mw - 8;
    if (y + mh > window.innerHeight) y = window.innerHeight - mh - 8;
    if (x < 0) x = 8;
    if (y < 0) y = 8;
    ctxMenu.style.left = `${x}px`;
    ctxMenu.style.top = `${y}px`;
  }

  function _hideCtxMenu() {
    ctxMenu.classList.add('hidden');
  }

  // ── Start ─────────────────────────────────────────────────────────────
  init();
})();