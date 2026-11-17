(function () {
  'use strict';

  window.showNotification = function (message, type = 'info', duration = 3500, cover = null) {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      Object.assign(container.style, {
        position: 'fixed',
        bottom: '24px',
        right: '24px',
        zIndex: '10001',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        pointerEvents: 'none',
        maxWidth: '320px',
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
      background: c.bg,
      border: `1px solid ${c.border}`,
      backdropFilter: 'blur(12px)',
      color: 'var(--text)',
      padding: '10px 14px',
      borderRadius: '10px',
      fontSize: '13px',
      fontFamily: 'var(--ff-body)',
      pointerEvents: 'auto',
      boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
      opacity: '0',
      transform: 'translateX(20px)',
      transition: 'opacity 0.22s ease, transform 0.22s ease',
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
    });
    const coverHtml = cover
      ? `<img src="${window.imageSrc ? window.imageSrc(cover) : cover}" alt="" style="width:32px;height:32px;border-radius:6px;flex-shrink:0;object-fit:cover;background:var(--surface);border:1px solid rgba(255,255,255,0.06)" loading="lazy">`
      : ''
    toast.innerHTML = `${coverHtml}<span style="flex-shrink:0;opacity:0.8;">${c.icon}</span><span>${message}</span>`;
    container.appendChild(toast);

    requestAnimationFrame(() => requestAnimationFrame(() => {
      toast.style.opacity = '1';
      toast.style.transform = 'translateX(0)';
    }));

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(20px)';
      setTimeout(() => toast.remove(), 250);
    }, duration);
  };
})();
