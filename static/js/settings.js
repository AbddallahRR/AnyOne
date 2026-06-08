(function () {
  'use strict';

  let _wizardData = {};
  let _editingName = null;
  let _currentStep = 1;

  const $ = id => document.getElementById(id);
  const sourcesList = $('sources-list');
  const dynamicList = $('dynamic-sources-list');
  const wizard = $('scraper-wizard');

  document.querySelectorAll('.settings-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.settings-tab').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.settings-tab-content').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      $(`tab-${btn.dataset.tab}`).classList.add('active');
    });
  });

  async function loadSources() {
    sourcesList.innerHTML = '<div class="loading-spinner"></div>';
    try {
      const res = await fetch('/api/scraper-configs');
      const configs = await res.json();
      renderSources(configs);
    } catch (err) {
      sourcesList.innerHTML = `<p style="color:var(--danger);font-size:13px;">Error: ${err.message}</p>`;
    }
  }

  function renderSources(configs) {
    if (!configs.length) {
      sourcesList.innerHTML = '<p style="color:var(--muted);font-size:13px;">No hay fuentes configuradas.</p>';
      return;
    }
    sourcesList.innerHTML = configs.map(cfg => {
      const isBuiltIn = cfg.built_in;
      const typeIcon = cfg.type === 'anime' ? 'fa-film' : 'fa-book';
      return `
        <div class="source-card${isBuiltIn ? ' built-in' : ''}" data-name="${cfg.name}">
          <div class="source-icon ${cfg.type}"><i class="fas ${typeIcon}"></i></div>
          <div class="source-info">
            <span class="source-label">${cfg.label}</span>
            <span class="source-meta">
              ${cfg.type} &middot; ${cfg.base_url || 'sin URL'}
              ${isBuiltIn ? '<span class="built-in-badge">built-in</span>' : ''}
            </span>
          </div>
          <div class="source-actions">
            <button class="btn-icon edit-btn" title="Editar" data-name="${cfg.name}">
              <i class="fas fa-pen"></i>
            </button>
            ${!isBuiltIn ? `
              <button class="btn-icon danger delete-btn" title="Eliminar" data-name="${cfg.name}">
                <i class="fas fa-trash-alt"></i>
              </button>
            ` : ''}
            <label class="source-toggle">
              <input type="checkbox" class="toggle-input" data-name="${cfg.name}" ${cfg.enabled ? 'checked' : ''}>
              <span class="toggle-track"></span>
            </label>
          </div>
        </div>`;
    }).join('');

    sourcesList.querySelectorAll('.toggle-input').forEach(input => {
      input.addEventListener('change', async function () {
        const name = this.dataset.name;
        try {
          const res = await fetch(`/api/scraper-configs/${name}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: this.checked }),
          });
          if (!res.ok) {
            this.checked = !this.checked;
            showToast('Error al cambiar estado', 'error');
          }
        } catch (err) {
          this.checked = !this.checked;
          showToast(`Error: ${err.message}`, 'error');
        }
      });
    });

    sourcesList.querySelectorAll('.edit-btn').forEach(btn => {
      btn.addEventListener('click', () => openWizardFor(btn.dataset.name));
    });

    sourcesList.querySelectorAll('.delete-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!confirm('Eliminar esta fuente?')) return;
        try {
          const res = await fetch(`/api/scraper-configs/${btn.dataset.name}`, { method: 'DELETE' });
          if (res.ok) {
            showToast('Fuente eliminada', 'success');
            loadSources();
            loadDynamicSources();
          } else {
            const data = await res.json();
            showToast(data.detail || 'Error al eliminar', 'error');
          }
        } catch (err) {
          showToast(`Error: ${err.message}`, 'error');
        }
      });
    });
  }

  async function loadDynamicSources() {
    try {
      const res = await fetch('/api/scraper-configs');
      const all = await res.json();
      const dyn = all.filter(c => !c.built_in);
      if (!dyn.length) {
        dynamicList.innerHTML = '<p style="color:var(--muted);font-size:13px;">No hay fuentes generadas aun. Crea una nueva!</p>';
        return;
      }
      dynamicList.innerHTML = dyn.map(c => {
        const typeIcon = c.type === 'anime' ? 'fa-film' : 'fa-book';
        return `
          <div class="source-card" data-name="${c.name}">
            <div class="source-icon ${c.type}"><i class="fas ${typeIcon}"></i></div>
            <div class="source-info">
              <span class="source-label">${c.label}</span>
              <span class="source-meta">${c.type} &middot; ${c.base_url || 'sin URL'}</span>
            </div>
            <div class="source-actions">
              <button class="btn-icon edit-btn" title="Editar" data-name="${c.name}">
                <i class="fas fa-pen"></i>
              </button>
              <button class="btn-icon danger delete-btn" title="Eliminar" data-name="${c.name}">
                <i class="fas fa-trash-alt"></i>
              </button>
            </div>
          </div>`;
      }).join('');

      dynamicList.querySelectorAll('.edit-btn').forEach(btn => {
        btn.addEventListener('click', () => openWizardFor(btn.dataset.name));
      });
      dynamicList.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
          if (!confirm('Eliminar esta fuente?')) return;
          try {
            const res = await fetch(`/api/scraper-configs/${btn.dataset.name}`, { method: 'DELETE' });
            if (res.ok) {
              showToast('Fuente eliminada', 'success');
              loadDynamicSources();
              loadSources();
            } else {
              const data = await res.json();
              showToast(data.detail || 'Error al eliminar', 'error');
            }
          } catch (err) {
            showToast(`Error: ${err.message}`, 'error');
          }
        });
      });
    } catch (err) {
      dynamicList.innerHTML = `<p style="color:var(--danger);font-size:13px;">Error: ${err.message}</p>`;
    }
  }

  async function openWizardFor(name) {
    _editingName = name;
    _currentStep = 1;

    if (name) {
      const cfg = await fetchConfig(name);
      if (!cfg) return;

      if (cfg.built_in) {
        const ok = await showConfirm(
          'Fuente incorporada',
          'Esta es una fuente incorporada. Al editarla se convertirá en fuente personalizada. ¿Continuar?'
        );
        if (!ok) {
          _editingName = null;
          return;
        }
      }

      _wizardData = cfg.config || {};
      $('wiz-type').value = cfg.type;
      $('wiz-name').value = cfg.name;
      $('wiz-name').readOnly = true;
      $('wiz-label').value = cfg.label;
      $('wiz-base-url').value = cfg.base_url;
      fillWizardFromData(_wizardData);
    } else {
      _editingName = null;
      _wizardData = {};
      resetWizard();
    }

    wizard.classList.remove('hidden');
    wizard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    showStep(1);
  }

  async function fetchConfig(name) {
    try {
      const res = await fetch(`/api/scraper-configs/${name}`);
      return await res.json();
    } catch (err) {
      showToast(`Error al cargar config: ${err.message}`, 'error');
      return null;
    }
  }

  function fillWizardFromData(data) {
    setVal('wiz-search-url', data.search_url_template || '');
    setVal('wiz-search-result', data.search_result_selector || '');
    setVal('wiz-search-title', data.search_title_selector || '');
    setVal('wiz-search-title-attr', data.search_title_attr || 'text');
    setVal('wiz-search-url-sel', data.search_url_selector || '');
    setVal('wiz-search-url-attr', data.search_url_attr || 'href');
    setVal('wiz-search-cover', data.search_cover_selector || '');
    setVal('wiz-search-cover-attr', data.search_cover_attr || 'src');

    setVal('wiz-details-url', data.details_url_template || '');
    setVal('wiz-details-title', data.details_title_selector || '');
    setVal('wiz-details-title-attr', data.details_title_attr || 'text');
    setVal('wiz-details-cover', data.details_cover_selector || '');
    setVal('wiz-details-cover-attr', data.details_cover_attr || 'src');
    setVal('wiz-details-synopsis', data.details_synopsis_selector || '');

    setVal('wiz-chapters-url', data.chapters_url_template || '');
    setVal('wiz-chapters-item', data.chapters_item_selector || '');
    setVal('wiz-chapters-num', data.chapters_num_selector || '');
    setVal('wiz-chapters-num-attr', data.chapters_num_attr || 'text');
    setVal('wiz-chapters-url-sel', data.chapters_url_selector || '');
    setVal('wiz-chapters-url-attr', data.chapters_url_attr || 'href');

    setVal('wiz-content-type', data.content_type || 'image');
    setVal('wiz-content-url', data.content_page_template || '');
    setVal('wiz-content-img', data.content_image_selector || '');
    setVal('wiz-content-img-attr', data.content_image_attr || 'src');
    setVal('wiz-content-vid', data.content_video_selector || '');
    setVal('wiz-content-vid-attr', data.content_video_attr || 'src');

    toggleContentConfig();
  }

  function resetWizard() {
    document.querySelectorAll('#scraper-wizard .input-field').forEach(el => {
      if (el.tagName === 'SELECT') {
        el.selectedIndex = 0;
      } else {
        el.value = '';
      }
    });
    $('wiz-name').readOnly = false;
    $('wiz-type').value = 'manga';
    toggleContentConfig();
  }

  function setVal(id, val) {
    const el = $(id);
    if (el) el.value = val;
  }

  function getVal(id) {
    const el = $(id);
    return el ? el.value : '';
  }

  function showStep(step) {
    _currentStep = step;
    document.querySelectorAll('.wizard-step').forEach(s => s.classList.add('hidden'));
    const target = document.querySelector(`.wizard-step[data-step="${step}"]`);
    if (target) target.classList.remove('hidden');

    document.querySelectorAll('.wp-step').forEach(s => {
      s.classList.remove('active', 'done');
      const num = parseInt(s.dataset.step);
      if (num === step) s.classList.add('active');
      else if (num < step) s.classList.add('done');
    });
  }

  document.querySelectorAll('.wiz-next').forEach(btn => {
    btn.addEventListener('click', () => {
      const next = parseInt(btn.dataset.next);
      collectStepData(_currentStep);
      showStep(next);
    });
  });

  document.querySelectorAll('.wiz-prev').forEach(btn => {
    btn.addEventListener('click', () => {
      showStep(parseInt(btn.dataset.prev));
    });
  });

  $('wiz-content-type').addEventListener('change', toggleContentConfig);
  function toggleContentConfig() {
    const isVideo = $('wiz-content-type').value === 'video';
    $('wiz-image-config').classList.toggle('hidden', isVideo);
    $('wiz-video-config').classList.toggle('hidden', !isVideo);
  }

  function collectStepData(step) {
    switch (step) {
      case 1:
        _wizardData.type = getVal('wiz-type');
        _wizardData.label = getVal('wiz-label');
        _wizardData.base_url = getVal('wiz-base-url');
        if (!_editingName) _wizardData.name = getVal('wiz-name');
        break;
      case 2:
        _wizardData.search_url_template = getVal('wiz-search-url');
        _wizardData.search_result_selector = getVal('wiz-search-result');
        _wizardData.search_title_selector = getVal('wiz-search-title');
        _wizardData.search_title_attr = getVal('wiz-search-title-attr');
        _wizardData.search_url_selector = getVal('wiz-search-url-sel');
        _wizardData.search_url_attr = getVal('wiz-search-url-attr');
        _wizardData.search_cover_selector = getVal('wiz-search-cover');
        _wizardData.search_cover_attr = getVal('wiz-search-cover-attr');
        break;
      case 3:
        _wizardData.details_url_template = getVal('wiz-details-url');
        _wizardData.details_title_selector = getVal('wiz-details-title');
        _wizardData.details_title_attr = getVal('wiz-details-title-attr');
        _wizardData.details_cover_selector = getVal('wiz-details-cover');
        _wizardData.details_cover_attr = getVal('wiz-details-cover-attr');
        _wizardData.details_synopsis_selector = getVal('wiz-details-synopsis');
        break;
      case 4:
        _wizardData.chapters_url_template = getVal('wiz-chapters-url');
        _wizardData.chapters_item_selector = getVal('wiz-chapters-item');
        _wizardData.chapters_num_selector = getVal('wiz-chapters-num');
        _wizardData.chapters_num_attr = getVal('wiz-chapters-num-attr');
        _wizardData.chapters_url_selector = getVal('wiz-chapters-url-sel');
        _wizardData.chapters_url_attr = getVal('wiz-chapters-url-attr');
        break;
      case 5:
        _wizardData.content_type = getVal('wiz-content-type');
        _wizardData.content_page_template = getVal('wiz-content-url');
        _wizardData.content_image_selector = getVal('wiz-content-img');
        _wizardData.content_image_attr = getVal('wiz-content-img-attr');
        _wizardData.content_video_selector = getVal('wiz-content-vid');
        _wizardData.content_video_attr = getVal('wiz-content-vid-attr');
        break;
    }
  }

  // ── Search test with improved preview ──
  $('wiz-search-test-btn').addEventListener('click', async () => {
    const query = getVal('wiz-search-test-query');
    const baseUrl = getVal('wiz-base-url');
    if (!query || !baseUrl) {
      showToast('Completa la URL base y el query de prueba', 'error');
      return;
    }
    const config = getSearchConfig();
    const results = $('wiz-search-test-results');
    results.innerHTML = '<div class="loading-spinner"></div>';
    try {
      const res = await fetch('/api/scraper-configs/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config, base_url: baseUrl, query, stage: 'search' }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'HTTP error');
      const data = await res.json();
      let html = `<div class="test-url"><strong>URL:</strong> <code>${escHtml(data.url)}</code></div>`;
      if (data.warning) {
        html += `<div class="test-warning">${escHtml(data.warning)}</div>`;
      }
      html += `<div class="test-stat"><strong>Cards encontradas:</strong> ${data.total_cards}</div>`;
      if (data.extracted && data.extracted.length) {
        html += '<div class="test-card-grid">';
        data.extracted.forEach(item => {
          const coverHtml = item.cover
            ? `<img src="${item.cover}" class="test-thumb" onerror="this.style.display='none'" alt="">`
            : '';
          html += `<div class="test-card-visual">${coverHtml}<div class="test-card-body"><span class="tt">${escHtml(item.title || '?')}</span><code>${escHtml(item.url || '')}</code></div></div>`;
        });
        html += '</div>';
      }
      if (data.html_preview) {
        html += `<details class="test-details"><summary>HTML preview</summary><pre>${escHtml(data.html_preview.substring(0, 3000))}</pre></details>`;
      }
      results.innerHTML = html;
    } catch (err) {
      results.innerHTML = `<p style="color:var(--danger);">Error: ${err.message}</p>`;
    }
  });

  $('wiz-details-test-btn').addEventListener('click', async () => {
    const contentId = getVal('wiz-details-test-id');
    const baseUrl = getVal('wiz-base-url');
    if (!contentId || !baseUrl) {
      showToast('Completa la URL base y el ID de contenido', 'error');
      return;
    }
    const config = getDetailsConfig();
    const results = $('wiz-details-test-results');
    results.innerHTML = '<div class="loading-spinner"></div>';
    try {
      const res = await fetch('/api/scraper-configs/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config, base_url: baseUrl, content_id: contentId, stage: 'details' }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'HTTP error');
      const data = await res.json();
      let html = `<div class="test-url"><strong>URL:</strong> <code>${escHtml(data.url)}</code></div>`;
      html += '<div class="test-details-visual">';
      if (data.cover) html += `<div class="test-cover-wrap"><img src="${data.cover}" class="test-cover-img" onerror="this.style.display='none'" alt=""></div>`;
      html += '<div class="test-details-body">';
      if (data.title) html += `<h4 class="test-details-title">${escHtml(data.title)}</h4>`;
      if (data.synopsis) html += `<p class="test-details-synopsis">${escHtml(data.synopsis.substring(0, 500))}</p>`;
      html += '</div></div>';
      if (data.html_preview) {
        html += `<details class="test-details"><summary>HTML preview</summary><pre>${escHtml(data.html_preview.substring(0, 3000))}</pre></details>`;
      }
      results.innerHTML = html;
    } catch (err) {
      results.innerHTML = `<p style="color:var(--danger);">Error: ${err.message}</p>`;
    }
  });

  $('wiz-chapters-test-btn').addEventListener('click', async () => {
    const contentId = getVal('wiz-chapters-test-id');
    const baseUrl = getVal('wiz-base-url');
    if (!contentId || !baseUrl) {
      showToast('Completa la URL base y el ID de contenido', 'error');
      return;
    }
    const config = getChaptersConfig();
    const results = $('wiz-chapters-test-results');
    results.innerHTML = '<div class="loading-spinner"></div>';
    try {
      const res = await fetch('/api/scraper-configs/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config, base_url: baseUrl, content_id: contentId, stage: 'chapters' }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'HTTP error');
      const data = await res.json();
      let html = `<div class="test-url"><strong>URL:</strong> <code>${escHtml(data.url)}</code></div>`;
      if (data.warning) {
        html += `<div class="test-warning">${escHtml(data.warning)}</div>`;
      }
      if (data.chapters && data.chapters.length) {
        html += `<div class="test-stat"><strong>Capítulos encontrados:</strong> ${data.chapters.length}</div>`;
        html += '<div class="test-chapter-table"><table><thead><tr><th>#</th><th>Número</th><th>URL</th></tr></thead><tbody>';
        data.chapters.slice(0, 20).forEach((ch, i) => {
          html += `<tr><td>${i + 1}</td><td><span class="tt">${escHtml(ch.number || '?')}</span></td><td><code>${escHtml(ch.url || '')}</code></td></tr>`;
        });
        html += '</tbody></table></div>';
        if (data.chapters.length > 20) html += `<div class="test-more">... y ${data.chapters.length - 20} más</div>`;
      } else {
        html += '<div style="color:var(--danger);">No se encontraron capítulos</div>';
      }
      if (data.html_preview) {
        html += `<details class="test-details"><summary>HTML preview</summary><pre>${escHtml(data.html_preview.substring(0, 3000))}</pre></details>`;
      }
      results.innerHTML = html;
    } catch (err) {
      results.innerHTML = `<p style="color:var(--danger);">Error: ${err.message}</p>`;
    }
  });

  $('wiz-content-test-btn').addEventListener('click', async () => {
    const chapterId = getVal('wiz-content-test-chapter');
    const baseUrl = getVal('wiz-base-url');
    const contentId = getVal('wiz-details-test-id') || getVal('wiz-chapters-test-id') || '';
    if (!chapterId || !baseUrl || !contentId) {
      showToast('Completa URL base, contenido de prueba y chapter_id', 'error');
      return;
    }
    const config = getContentConfig();
    const results = $('wiz-content-test-results');
    results.innerHTML = '<div class="loading-spinner"></div>';
    try {
      const res = await fetch('/api/scraper-configs/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config, base_url: baseUrl, content_id: contentId, chapter_id: chapterId, stage: 'content' }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'HTTP error');
      const data = await res.json();
      let html = `<div class="test-url"><strong>URL:</strong> <code>${escHtml(data.url)}</code></div>`;
      if (data.images && data.images.length) {
        html += `<div class="test-stat"><strong>Imágenes encontradas:</strong> ${data.images.length}</div>`;
        html += '<div class="test-image-grid">';
        data.images.forEach((url, i) => {
          html += `<div class="test-image-item"><img src="${url}" onerror="this.style.display='none'" alt=""><code>${escHtml(url)}</code></div>`;
        });
        html += '</div>';
      }
      if (data.video_url) {
        html += `<div class="test-card-visual" style="padding:12px;"><strong>Video URL:</strong> <code>${escHtml(data.video_url)}</code></div>`;
      }
      if (data.html_preview) {
        html += `<details class="test-details"><summary>HTML preview</summary><pre>${escHtml(data.html_preview.substring(0, 3000))}</pre></details>`;
      }
      results.innerHTML = html;
    } catch (err) {
      results.innerHTML = `<p style="color:var(--danger);">Error: ${err.message}</p>`;
    }
  });

  // ── Auto-detect search (magic wand in step 2) ──
  $('wiz-search-detect-btn').addEventListener('click', async () => {
    const query = getVal('wiz-search-test-query');
    const baseUrl = getVal('wiz-base-url');
    const urlTemplate = getVal('wiz-search-url');
    if (!query || !baseUrl || !urlTemplate) {
      showToast('Completa URL base, URL de búsqueda y query de prueba', 'error');
      return;
    }
    const url = urlTemplate.replace('{base}', baseUrl).replace('{query}', encodeURIComponent(query));
    const resultsEl = $('wiz-search-test-results');
    resultsEl.innerHTML = '<div class="loading-spinner"></div>';

    try {
      const res = await fetch('/api/scraper-configs/auto-detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, stage: 'search', base_url: baseUrl }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'HTTP error');
      const data = await res.json();

      if (data.suggestions && data.suggestions.length) {
        const best = data.suggestions[0];
        setVal('wiz-search-result', best.result_selector);
        setVal('wiz-search-title', best.title_selector);
        setVal('wiz-search-title-attr', best.title_attr);
        setVal('wiz-search-url-sel', best.url_selector);
        setVal('wiz-search-url-attr', best.url_attr);
        setVal('wiz-search-cover', best.cover_selector);
        setVal('wiz-search-cover-attr', best.cover_attr);
        openAdvanced();
        resultsEl.innerHTML = `
          <div class="detect-success">
            <strong>Selectores detectados:</strong>
            <div class="detect-grid">
              <span>Resultado:</span><code>${escHtml(best.result_selector)}</code>
              <span>Título:</span><code>${escHtml(best.title_selector)} (${best.title_attr})</code>
              <span>Enlace:</span><code>${escHtml(best.url_selector)} (${best.url_attr})</code>
              <span>Portada:</span><code>${escHtml(best.cover_selector)} (${best.cover_attr})</code>
            </div>
            <small>Confianza: ${best.confidence} &middot; ${data.suggestions.length} sugerencia(s)</small>
          </div>`;
      } else {
        resultsEl.innerHTML = '<p style="color:var(--warning);">No se pudieron detectar selectores automáticamente. Verifica la URL de búsqueda.</p>';
      }
    } catch (err) {
      resultsEl.innerHTML = `<p style="color:var(--danger);">Error: ${err.message}</p>`;
    }
  });

  function getSearchConfig() {
    return {
      search_url_template: getVal('wiz-search-url'),
      search_result_selector: getVal('wiz-search-result'),
      search_title_selector: getVal('wiz-search-title'),
      search_title_attr: getVal('wiz-search-title-attr'),
      search_url_selector: getVal('wiz-search-url-sel'),
      search_url_attr: getVal('wiz-search-url-attr'),
      search_cover_selector: getVal('wiz-search-cover'),
      search_cover_attr: getVal('wiz-search-cover-attr'),
    };
  }

  function getDetailsConfig() {
    return {
      details_url_template: getVal('wiz-details-url'),
      details_title_selector: getVal('wiz-details-title'),
      details_title_attr: getVal('wiz-details-title-attr'),
      details_cover_selector: getVal('wiz-details-cover'),
      details_cover_attr: getVal('wiz-details-cover-attr'),
      details_synopsis_selector: getVal('wiz-details-synopsis'),
    };
  }

  function getChaptersConfig() {
    return {
      chapters_url_template: getVal('wiz-chapters-url'),
      chapters_item_selector: getVal('wiz-chapters-item'),
      chapters_num_selector: getVal('wiz-chapters-num'),
      chapters_num_attr: getVal('wiz-chapters-num-attr'),
      chapters_url_selector: getVal('wiz-chapters-url-sel'),
      chapters_url_attr: getVal('wiz-chapters-url-attr'),
    };
  }

  function getContentConfig() {
    return {
      content_type: getVal('wiz-content-type'),
      content_page_template: getVal('wiz-content-url'),
      content_image_selector: getVal('wiz-content-img'),
      content_image_attr: getVal('wiz-content-img-attr'),
      content_video_selector: getVal('wiz-content-vid'),
      content_video_attr: getVal('wiz-content-vid-attr'),
    };
  }

  $('wiz-save-btn').addEventListener('click', async () => {
    collectStepData(5);
    const name = _editingName || getVal('wiz-name');
    const type = getVal('wiz-type');
    const label = getVal('wiz-label');
    const baseUrl = getVal('wiz-base-url');

    if (!name || !label || !baseUrl) {
      showToast('Completa los campos basicos (paso 1)', 'error');
      showStep(1);
      return;
    }

    const config = {
      ...getSearchConfig(),
      ...getDetailsConfig(),
      ...getChaptersConfig(),
      ...getContentConfig(),
    };

    const isEdit = !!_editingName;
    const url = isEdit ? `/api/scraper-configs/${name}` : '/api/scraper-configs';
    const method = isEdit ? 'PUT' : 'POST';
    const body = isEdit
      ? JSON.stringify({ label, base_url: baseUrl, config })
      : JSON.stringify({ name, type, label, base_url: baseUrl, config });

    try {
      const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'HTTP error');
      }
      showToast(isEdit ? 'Fuente actualizada!' : 'Fuente creada!', 'success');
      wizard.classList.add('hidden');
      _editingName = null;
      loadSources();
      loadDynamicSources();
    } catch (err) {
      showToast(`Error: ${err.message}`, 'error');
    }
  });

  $('new-scraper-btn').addEventListener('click', () => openWizardFor(null));

  document.querySelector('.wiz-next[data-next="6"]').addEventListener('click', () => {
    collectStepData(5);
    renderSummary();
  });

  function renderSummary() {
    const name = _editingName || getVal('wiz-name');
    const type = getVal('wiz-type');
    const label = getVal('wiz-label');
    const baseUrl = getVal('wiz-base-url');

    const items = [
      ['Nombre interno', name || '—'],
      ['Tipo', type],
      ['Etiqueta', label || '—'],
      ['URL base', baseUrl || '—'],
      ['URL busqueda', getVal('wiz-search-url') || '—'],
      ['URL detalles', getVal('wiz-details-url') || '—'],
      ['URL capitulos', getVal('wiz-chapters-url') || '—'],
      ['Tipo contenido', getVal('wiz-content-type') === 'video' ? 'Video' : 'Imagenes'],
      ['URL contenido', getVal('wiz-content-url') || '—'],
    ];

    $('wiz-summary').innerHTML = items.map(([label, value]) =>
      `<div class="summary-row"><span class="summary-label">${label}</span><span class="summary-value">${value}</span></div>`
    ).join('');
  }

  // ── Confirm Dialog ──
  function showConfirm(title, message) {
    return new Promise(resolve => {
      const overlay = document.createElement('div');
      overlay.className = 'confirm-overlay';
      overlay.innerHTML = `
        <div class="confirm-dialog">
          <h3>${title}</h3>
          <p>${message}</p>
          <div class="confirm-actions">
            <button class="btn-ghost" id="confirm-cancel">Cancelar</button>
            <button class="btn-primary" id="confirm-ok">Continuar</button>
          </div>
        </div>`;
      document.body.appendChild(overlay);
      overlay.querySelector('#confirm-ok').onclick = () => { overlay.remove(); resolve(true); };
      overlay.querySelector('#confirm-cancel').onclick = () => { overlay.remove(); resolve(false); };
      overlay.onclick = e => { if (e.target === overlay) { overlay.remove(); resolve(false); } };
    });
  }

  // ── Toast ──
  function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      Object.assign(container.style, {
        position: 'fixed', bottom: '24px', right: '24px',
        zIndex: '10001', display: 'flex', flexDirection: 'column',
        gap: '8px', pointerEvents: 'none', maxWidth: '320px',
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
      background: c.bg, border: `1px solid ${c.border}`,
      backdropFilter: 'blur(12px)', color: 'var(--text)',
      padding: '10px 14px', borderRadius: '10px', fontSize: '13px',
      fontFamily: 'var(--ff-body)', pointerEvents: 'auto',
      boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
      opacity: '0', transform: 'translateX(20px)',
      transition: 'opacity 0.22s ease, transform 0.22s ease',
      display: 'flex', alignItems: 'center', gap: '8px',
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
    }, 3500);
  }

  function openAdvanced() {
    const step = document.querySelector(`.wizard-step[data-step="${_currentStep}"]`);
    if (step) {
      step.querySelectorAll('.advanced-section').forEach(s => s.classList.add('advanced-open'));
    }
  }

  function escHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
  }

  loadSources();
  loadDynamicSources();

})();
