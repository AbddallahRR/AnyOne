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

    // Catalog fields
    $('wiz-has-catalog').checked = data.has_catalog || false;
    toggleCatalogSection();
    setVal('wiz-catalog-url', data.catalog_url_template || '');
    setVal('wiz-catalog-item', data.catalog_item_selector || '');
    setVal('wiz-catalog-title', data.catalog_title_selector || '');
    setVal('wiz-catalog-title-attr', data.catalog_title_attr || 'text');
    setVal('wiz-catalog-url-sel', data.catalog_url_selector || '');
    setVal('wiz-catalog-url-attr', data.catalog_url_attr || 'href');
    setVal('wiz-catalog-cover', data.catalog_cover_selector || '');
    setVal('wiz-catalog-cover-attr', data.catalog_cover_attr || 'src');
    setVal('wiz-catalog-max-pages', data.catalog_max_pages || 100);
    setVal('wiz-catalog-ttl', data.catalog_cache_ttl || 259200);

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
    $('wiz-has-catalog').checked = false;
    toggleCatalogSection();
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

  // ── Catalog toggle ──
  $('wiz-has-catalog').addEventListener('change', toggleCatalogSection);
  function toggleCatalogSection() {
    const isCatalog = $('wiz-has-catalog').checked;
    $('wiz-search-section').classList.toggle('hidden', isCatalog);
    $('wiz-catalog-section').classList.toggle('hidden', !isCatalog);
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
        _wizardData.has_catalog = $('wiz-has-catalog').checked;
        if (_wizardData.has_catalog) {
          _wizardData.catalog_url_template = getVal('wiz-catalog-url');
          _wizardData.catalog_item_selector = getVal('wiz-catalog-item');
          _wizardData.catalog_title_selector = getVal('wiz-catalog-title');
          _wizardData.catalog_title_attr = getVal('wiz-catalog-title-attr');
          _wizardData.catalog_url_selector = getVal('wiz-catalog-url-sel');
          _wizardData.catalog_url_attr = getVal('wiz-catalog-url-attr');
          _wizardData.catalog_cover_selector = getVal('wiz-catalog-cover');
          _wizardData.catalog_cover_attr = getVal('wiz-catalog-cover-attr');
          _wizardData.catalog_max_pages = parseInt(getVal('wiz-catalog-max-pages')) || 100;
          _wizardData.catalog_cache_ttl = parseInt(getVal('wiz-catalog-ttl')) || 259200;
        } else {
          _wizardData.search_url_template = getVal('wiz-search-url');
          _wizardData.search_result_selector = getVal('wiz-search-result');
          _wizardData.search_title_selector = getVal('wiz-search-title');
          _wizardData.search_title_attr = getVal('wiz-search-title-attr');
          _wizardData.search_url_selector = getVal('wiz-search-url-sel');
          _wizardData.search_url_attr = getVal('wiz-search-url-attr');
          _wizardData.search_cover_selector = getVal('wiz-search-cover');
          _wizardData.search_cover_attr = getVal('wiz-search-cover-attr');
        }
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

  // ── Helper: fill URL templates ──
  function fillUrl(template, vars) {
    let url = template;
    for (const [k, v] of Object.entries(vars)) {
      url = url.replace(`{${k}}`, v);
    }
    return url;
  }

  // ── Text-based detect helpers ──
  async function detectByText(url, stage, text, baseUrl, resultsEl) {
    if (!url || !text) {
      showToast('Completa la URL y el texto de muestra', 'error');
      return;
    }
    resultsEl.innerHTML = '<div class="loading-spinner"></div>';
    try {
      const res = await fetch('/api/scraper-configs/detect-selectors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, stage, text, base_url: baseUrl }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'HTTP error');
      const data = await res.json();
      if (!data.detected || !Object.keys(data.detected).length) {
        resultsEl.innerHTML = `<p style="color:var(--warning);">${escHtml(data.warning || 'No se pudieron detectar selectores con ese texto.')}</p>`;
        return;
      }
      const d = data.detected;
      let html = '<div class="detect-success"><strong>Selectores detectados:</strong><div class="detect-grid">';
      for (const [key, val] of Object.entries(d)) {
        if (key === 'confidence' || key === 'matched_text') continue;
        html += `<span>${key.replace(/_/g,' ')}:</span><code>${escHtml(String(val))}</code>`;
      }
      if (d.confidence !== undefined) {
        html += `<span>Confianza:</span><code>${d.confidence}</code>`;
      }
      if (d.matched_text) {
        html += `<span>Texto encontrado:</span><code>${escHtml(d.matched_text)}</code>`;
      }
      html += '</div></div>';
      resultsEl.innerHTML = html;
      return d;
    } catch (err) {
      resultsEl.innerHTML = `<p style="color:var(--danger);">Error: ${err.message}</p>`;
      return null;
    }
  }

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

  // ── Detect by text: Search (step 2) ──
  $('wiz-search-detect-text-btn').addEventListener('click', async () => {
    const sampleText = getVal('wiz-search-sample-text');
    const baseUrl = getVal('wiz-base-url');
    const urlTemplate = getVal('wiz-search-url');
    const query = getVal('wiz-search-test-query');
    if (!baseUrl || !urlTemplate || !query) {
      showToast('Completa URL base, URL de búsqueda y query de prueba', 'error');
      return;
    }
    const url = fillUrl(urlTemplate, { base: baseUrl, query: encodeURIComponent(query) });
    const resultsEl = $('wiz-search-test-results');
    const d = await detectByText(url, 'search', sampleText, baseUrl, resultsEl);
    if (d) {
      if (d.result_selector) setVal('wiz-search-result', d.result_selector);
      if (d.title_selector) setVal('wiz-search-title', d.title_selector);
      if (d.title_attr) setVal('wiz-search-title-attr', d.title_attr);
      if (d.url_selector) setVal('wiz-search-url-sel', d.url_selector);
      if (d.url_attr) setVal('wiz-search-url-attr', d.url_attr);
      if (d.cover_selector) setVal('wiz-search-cover', d.cover_selector);
      if (d.cover_attr) setVal('wiz-search-cover-attr', d.cover_attr);
      openAdvanced();
    }
  });

  // ── Detect by text: Details (step 3) ──
  $('wiz-details-detect-text-btn').addEventListener('click', async () => {
    const sampleText = getVal('wiz-details-sample-text');
    const baseUrl = getVal('wiz-base-url');
    const urlTemplate = getVal('wiz-details-url');
    const contentId = getVal('wiz-details-test-id');
    if (!baseUrl || !urlTemplate || !contentId) {
      showToast('Completa URL base, URL de detalles y content ID', 'error');
      return;
    }
    const url = fillUrl(urlTemplate, { base: baseUrl, content_id: encodeURIComponent(contentId) });
    const resultsEl = $('wiz-details-test-results');
    const d = await detectByText(url, 'details', sampleText, baseUrl, resultsEl);
    if (d) {
      if (d.selector) setVal('wiz-details-title', d.selector);
      if (d.attr) setVal('wiz-details-title-attr', d.attr);
      openAdvanced();
    }
  });

  // ── Detect by text: Chapters (step 4) ──
  $('wiz-chapters-detect-text-btn').addEventListener('click', async () => {
    const sampleText = getVal('wiz-chapters-sample-text');
    const baseUrl = getVal('wiz-base-url');
    const urlTemplate = getVal('wiz-chapters-url');
    const contentId = getVal('wiz-chapters-test-id');
    if (!baseUrl || !urlTemplate || !contentId) {
      showToast('Completa URL base, URL de capítulos y content ID', 'error');
      return;
    }
    const url = fillUrl(urlTemplate, { base: baseUrl, content_id: encodeURIComponent(contentId) });
    const resultsEl = $('wiz-chapters-test-results');
    const d = await detectByText(url, 'chapters', sampleText, baseUrl, resultsEl);
    if (d) {
      if (d.item_selector) setVal('wiz-chapters-item', d.item_selector);
      if (d.num_selector) setVal('wiz-chapters-num', d.num_selector);
      if (d.num_attr) setVal('wiz-chapters-num-attr', d.num_attr);
      if (d.url_selector) setVal('wiz-chapters-url-sel', d.url_selector);
      if (d.url_attr) setVal('wiz-chapters-url-attr', d.url_attr);
      openAdvanced();
    }
  });

  // ── Detect by text: Content (step 5) ──
  $('wiz-content-detect-text-btn').addEventListener('click', async () => {
    const sampleText = getVal('wiz-content-sample-text');
    const baseUrl = getVal('wiz-base-url');
    const urlTemplate = getVal('wiz-content-url');
    const contentId = getVal('wiz-details-test-id') || getVal('wiz-chapters-test-id') || '';
    const chapterId = getVal('wiz-content-test-chapter');
    if (!baseUrl || !urlTemplate || !contentId || !chapterId) {
      showToast('Completa URL base, URL de contenido, content ID y chapter ID', 'error');
      return;
    }
    const url = fillUrl(urlTemplate, {
      base: baseUrl,
      content_id: encodeURIComponent(contentId),
      chapter_id: encodeURIComponent(chapterId),
    });
    const resultsEl = $('wiz-content-test-results');
    const d = await detectByText(url, 'content', sampleText, baseUrl, resultsEl);
    if (d) {
      if (d.selector) setVal('wiz-content-img', d.selector);
      if (d.attr) setVal('wiz-content-img-attr', d.attr);
      openAdvanced();
    }
  });

  // ── Detect by text: Catalog (in step 2 catalog section) ──
  $('wiz-catalog-detect-text-btn').addEventListener('click', async () => {
    const sampleText = getVal('wiz-catalog-sample-text');
    const baseUrl = getVal('wiz-base-url');
    const urlTemplate = getVal('wiz-catalog-url');
    if (!baseUrl || !urlTemplate) {
      showToast('Completa URL base y URL del catálogo', 'error');
      return;
    }
    const url = fillUrl(urlTemplate, { base: baseUrl, page: '1' });
    const resultsEl = $('wiz-search-test-results');
    const d = await detectByText(url, 'search', sampleText, baseUrl, resultsEl);
    if (d) {
      if (d.result_selector) setVal('wiz-catalog-item', d.result_selector);
      if (d.title_selector) setVal('wiz-catalog-title', d.title_selector);
      if (d.title_attr) setVal('wiz-catalog-title-attr', d.title_attr);
      if (d.url_selector) setVal('wiz-catalog-url-sel', d.url_selector);
      if (d.url_attr) setVal('wiz-catalog-url-attr', d.url_attr);
      if (d.cover_selector) setVal('wiz-catalog-cover', d.cover_selector);
      if (d.cover_attr) setVal('wiz-catalog-cover-attr', d.cover_attr);
      openAdvanced();
    }
  });

  function getCatalogConfig() {
    return {
      has_catalog: $('wiz-has-catalog').checked,
      catalog_url_template: getVal('wiz-catalog-url'),
      catalog_item_selector: getVal('wiz-catalog-item'),
      catalog_title_selector: getVal('wiz-catalog-title'),
      catalog_title_attr: getVal('wiz-catalog-title-attr'),
      catalog_url_selector: getVal('wiz-catalog-url-sel'),
      catalog_url_attr: getVal('wiz-catalog-url-attr'),
      catalog_cover_selector: getVal('wiz-catalog-cover'),
      catalog_cover_attr: getVal('wiz-catalog-cover-attr'),
      catalog_max_pages: parseInt(getVal('wiz-catalog-max-pages')) || 100,
      catalog_cache_ttl: parseInt(getVal('wiz-catalog-ttl')) || 259200,
    };
  }

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
      ...getCatalogConfig(),
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

    const isCatalog = $('wiz-has-catalog').checked;
    const items = [
      ['Nombre interno', name || '—'],
      ['Tipo', type],
      ['Etiqueta', label || '—'],
      ['URL base', baseUrl || '—'],
      [isCatalog ? 'URL catálogo' : 'URL busqueda', isCatalog ? (getVal('wiz-catalog-url') || '—') : (getVal('wiz-search-url') || '—')],
      [isCatalog ? 'Catálogo cacheado' : '', isCatalog ? 'Sí' : ''],
      ['URL detalles', getVal('wiz-details-url') || '—'],
      ['URL capitulos', getVal('wiz-chapters-url') || '—'],
      ['Tipo contenido', getVal('wiz-content-type') === 'video' ? 'Video' : 'Imagenes'],
      ['URL contenido', getVal('wiz-content-url') || '—'],
    ].filter(row => row[1] !== '');

    $('wiz-summary').innerHTML = items.map(([label, value]) =>
      `<div class="summary-row"><span class="summary-label">${label}</span><span class="summary-value">${value}</span></div>`
    ).join('');
  }

  // ── Confirm Dialog ──
  function showConfirm(title, message) {
    return window.showConfirm(title, message);
  }

  var showToast = window.showNotification;

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
