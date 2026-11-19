// static/js/custom-select.js
// Drop-in custom select component — replaces native <select> styling
// Keeps native select in DOM for API compatibility (.value, change event, form submit)

(function () {
  'use strict';

  const SELECTOR = 'select.input-field:not([data-custom-select])';
  const OPEN_CLASS = 'cs-open';
  const HIDDEN_CLASS = 'cs-hidden';

  // ─── Create custom select markup ───
  function enhance(select) {
    if (select.dataset.customSelect) return; // already enhanced
    select.dataset.customSelect = 'true';

    // Hide native select visually but keep it accessible
    select.classList.add(HIDDEN_CLASS);
    select.style.position = 'absolute';
    select.style.opacity = '0';
    select.style.pointerEvents = 'none';
    select.style.width = '100%';
    select.style.height = '100%';
    select.style.zIndex = '1';

    // Wrapper
    const wrapper = document.createElement('div');
    wrapper.className = 'custom-select-wrapper';
    wrapper.style.cssText = `
      position: relative;
      display: inline-flex;
      flex-direction: column;
      width: 100%;
      font-family: inherit;
    `;

    // Trigger button (what user sees)
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'custom-select-trigger';
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.style.cssText = `
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      width: 100%;
      padding: 10px 14px;
      background: rgba(255,255,255,0.05);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text);
      font-family: inherit;
      font-size: 14px;
      text-align: left;
      cursor: pointer;
      transition: border-color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
    `;

    // Selected value display
    const valueEl = document.createElement('span');
    valueEl.className = 'custom-select-value';
    valueEl.style.cssText = 'flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;';
    trigger.appendChild(valueEl);

    // Chevron icon
    const chevron = document.createElement('span');
    chevron.className = 'custom-select-chevron';
    chevron.innerHTML = '<svg width="12" height="8" fill="none"><path d="M1 1l5 5 5-5" stroke="var(--muted)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    chevron.style.cssText = 'flex-shrink: 0; transition: transform 0.15s ease; color: var(--muted);';
    trigger.appendChild(chevron);

    // Dropdown panel
    const panel = document.createElement('div');
    panel.className = 'custom-select-panel';
    panel.setAttribute('role', 'listbox');
    panel.setAttribute('aria-label', select.getAttribute('aria-label') || '');
    panel.style.cssText = `
      position: absolute;
      top: calc(100% + 4px);
      left: 0; right: 0;
      background: var(--raised);
      border: 1px solid var(--border);
      border-radius: 8px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.4);
      max-height: 240px;
      overflow-y: auto;
      z-index: 100;
      display: none;
      padding: 4px;
    `;

    wrapper.append(trigger, panel);
    select.parentNode.insertBefore(wrapper, select.nextSibling);

    // Sync options from native select
    function syncOptions() {
      panel.innerHTML = '';
      let selectedIndex = -1;
      [...select.options].forEach((opt, i) => {
        const item = document.createElement('div');
        item.className = 'custom-select-option';
        item.setAttribute('role', 'option');
        item.setAttribute('data-value', opt.value);
        item.textContent = opt.textContent;
        item.style.cssText = `
          padding: 8px 12px;
          border-radius: 6px;
          cursor: pointer;
          font-size: 14px;
          color: var(--text);
          transition: background 0.1s ease;
        `;
        if (opt.selected) {
          item.style.background = 'rgba(124,92,252,0.15)';
          item.style.color = 'var(--accent-lt)';
          selectedIndex = i;
        }
        item.addEventListener('mousedown', (e) => {
          e.preventDefault(); // keep focus on trigger
          select.value = opt.value;
          select.dispatchEvent(new Event('change', { bubbles: true }));
          close();
        });
        panel.appendChild(item);
      });
      updateTrigger(selectedIndex);
    }

    function updateTrigger(idx) {
      const opt = select.options[idx >= 0 ? idx : select.selectedIndex];
      valueEl.textContent = opt ? opt.textContent : '';
      valueEl.style.color = opt && opt.value ? 'var(--text)' : 'var(--muted)';
    }

    function open() {
      if (panel.style.display === 'block') return;
      panel.style.display = 'block';
      trigger.setAttribute('aria-expanded', 'true');
      chevron.style.transform = 'rotate(180deg)';
      trigger.style.borderColor = 'var(--accent)';
      trigger.style.boxShadow = '0 0 0 3px rgba(124,92,252,0.1)';
      // Focus management
      const selectedItem = panel.querySelector('[style*="rgba(124,92,252,0.15)"]');
      selectedItem?.scrollIntoView({ block: 'nearest' });
      document.addEventListener('click', outsideClick);
      document.addEventListener('keydown', onKeyDown);
    }

    function close() {
      panel.style.display = 'none';
      trigger.setAttribute('aria-expanded', 'false');
      chevron.style.transform = 'rotate(0deg)';
      trigger.style.borderColor = 'var(--border)';
      trigger.style.boxShadow = 'none';
      document.removeEventListener('click', outsideClick);
      document.removeEventListener('keydown', onKeyDown);
    }

    function outsideClick(e) {
      if (!wrapper.contains(e.target)) close();
    }

    function onKeyDown(e) {
      const items = [...panel.querySelectorAll('.custom-select-option')];
      if (!items.length) return;
      const focused = panel.querySelector('.custom-select-option:focus') || items[0];
      const idx = items.indexOf(focused);
      let nextIdx = idx;
      if (e.key === 'ArrowDown') { e.preventDefault(); nextIdx = Math.min(idx + 1, items.length - 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); nextIdx = Math.max(idx - 1, 0); }
      else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); focused.click(); return; }
      else if (e.key === 'Escape') { e.preventDefault(); close(); return; }
      else return;
      items[nextIdx].focus();
      items[nextIdx].scrollIntoView({ block: 'nearest' });
    }

    // Events
    trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      panel.style.display === 'block' ? close() : open();
    });

    // Keep native select in sync (for form submit, .value access, etc.)
    // 'input' catches programmatic value changes; 'change' catches user interaction
    select.addEventListener('input', () => updateTrigger(select.selectedIndex));
    select.addEventListener('change', () => updateTrigger(select.selectedIndex));

    // Auto-refresh when options are added/removed programmatically (e.g., innerHTML = '')
    new MutationObserver(syncOptions).observe(select, { childList: true });

    // Initial sync
    syncOptions();

    // Expose API for dynamic option updates
    wrapper.refresh = syncOptions;
    wrapper.destroy = () => {
      document.removeEventListener('click', outsideClick);
      document.removeEventListener('keydown', onKeyDown);
      select.classList.remove(HIDDEN_CLASS);
      select.style.cssText = '';
      delete select.dataset.customSelect;
      wrapper.remove();
    };

    return wrapper;
  }

  // ─── Auto-enhance all matching selects ───
  function init() {
    document.querySelectorAll(SELECTOR).forEach(enhance);
  }

  // Re-run when new selects are added dynamically
  const observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      m.addedNodes.forEach(node => {
        if (node.nodeType === 1) {
          if (node.matches && node.matches(SELECTOR)) enhance(node);
          node.querySelectorAll?.(SELECTOR).forEach(enhance);
        }
      });
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Public API
  window.CustomSelect = { enhance, init };
})();