// static/js/notifications.js
// Badges de novedades (biblioteca + campana) y popup de notificaciones.
// Compartido por index y detalle de serie.
(function () {
  'use strict';

  const tabLibrary = document.getElementById('tab-library');

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
          left: '26px',
          background: 'var(--accent)',
          color: '#fff',
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
          left: '26px',
          background: 'var(--accent)',
          color: '#fff',
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

    function _buildItemHtml(s) {
      const chs = Array.isArray(s.new_chapters) ? s.new_chapters : [];
      const chText = chs.length > 0
        ? (chs.length <= 3 ? chs.join(', ') : `${chs.slice(0, 2).join(', ')} y ${chs.length - 2} más`)
        : '';
      const link = (s.content_type && s.local_id)
        ? `/serie/${s.content_type}/local/${encodeURIComponent(s.local_id)}`
        : '';
      return `<div class="updates-popup-item" data-ref="${s.content_ref}">
        <div class="updates-popup-item-top">
          <span class="updates-popup-title">${s.title}</span>
          <button class="updates-popup-dismiss" data-ref="${s.content_ref}" title="Eliminar">&times;</button>
        </div>
        ${chText ? `<span class="updates-popup-chs">Cap. ${chText}</span>` : ''}
        ${link ? `<a class="updates-popup-view" href="${link}"><i class="fas fa-eye"></i> Ver serie</a>` : ''}
      </div>`;
    }

    const items = series.slice(0, 5).map(_buildItemHtml).join('');

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
        <div class="updates-popup-actions">
          <button class="btn-primary updates-popup-check"><i class="fas fa-sync-alt"></i> Buscar actualizaciones</button>
        </div>
        <div class="updates-popup-body">${bodyContent}</div>
        <div class="updates-popup-footer">${total > 0 ? '<button class="btn-secondary updates-popup-clear-all"><i class="fas fa-check"></i> Marcar todo leído</button>' : ''}</div>
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

    popup.addEventListener('click', async (e) => {
      const dismissBtn = e.target.closest('.updates-popup-dismiss');
      if (dismissBtn) {
        e.stopPropagation();
        const ref = dismissBtn.dataset.ref;
        const item = dismissBtn.closest('.updates-popup-item');
        await api.post('/api/library/acknowledge-updates', { content_ref: ref }).catch(() => {});
        item?.remove();
        await fetchUpdatesBadge();
        const body = popup.querySelector('.updates-popup-body');
        if (!body.querySelector('.updates-popup-item')) {
          body.innerHTML = '<div class="updates-popup-empty">No hay capítulos nuevos por ahora</div>';
          popup.querySelector('.updates-popup-clear-all')?.remove();
        }
        return;
      }
    });

    const clearAllBtn = popup.querySelector('.updates-popup-clear-all');
    if (clearAllBtn) {
      clearAllBtn.addEventListener('click', async () => {
        const refs = series.map(s => s.content_ref);
        await api.post('/api/library/acknowledge-updates', { content_refs: refs }).catch(() => {});
        const body = popup.querySelector('.updates-popup-body');
        body.innerHTML = '<div class="updates-popup-empty">No hay capítulos nuevos por ahora</div>';
        clearAllBtn.remove();
        await fetchUpdatesBadge();
      });
    }

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
          body.innerHTML = newSeries.slice(0, 5).map(_buildItemHtml).join('')
            + (newTotal > 5 ? `<div class="updates-popup-more">y ${newTotal - 5} serie${newTotal - 5 !== 1 ? 's' : ''} más…</div>` : '');
          if (!popup.querySelector('.updates-popup-clear-all')) {
            const footer = popup.querySelector('.updates-popup-footer');
            const clearBtn = document.createElement('button');
            clearBtn.className = 'btn-secondary updates-popup-clear-all';
            clearBtn.innerHTML = '<i class="fas fa-check"></i> Marcar todo leído';
            footer.appendChild(clearBtn);
            clearBtn.addEventListener('click', async () => {
              const allRefs = newSeries.map(s => s.content_ref);
              await api.post('/api/library/acknowledge-updates', { content_refs: allRefs }).catch(() => {});
              body.innerHTML = '<div class="updates-popup-empty">No hay capítulos nuevos por ahora</div>';
              clearBtn.remove();
              await fetchUpdatesBadge();
            });
          }
          const msg = totalQueued > 0
            ? `${newTotal} serie${newTotal !== 1 ? 's' : ''} con novedades — ${totalQueued} capítulo${totalQueued !== 1 ? 's' : ''} encolado${totalQueued !== 1 ? 's' : ''}`
            : `${newTotal} serie${newTotal !== 1 ? 's' : ''} con capítulos nuevos`;
          showNotification(msg, 'success');
        } else {
          body.innerHTML = '<div class="updates-popup-empty">No hay capítulos nuevos</div>';
          popup.querySelector('.updates-popup-clear-all')?.remove();
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

  // ── Bell button → open updates popup ──────────────────────────────────
  document.getElementById('nav-bell')?.addEventListener('click', _showUpdatesPopup);

  // Expuesto para que app.js refresque el badge al recargar la biblioteca.
  window.Notifications = { refresh: fetchUpdatesBadge, toggle: _showUpdatesPopup };

  fetchUpdatesBadge();
})();
