// static/js/base.js
// Global utilities shared across all pages.

/* ── Body ready (fade-in) ── */
document.addEventListener('DOMContentLoaded', () => {
  requestAnimationFrame(() => document.body.classList.add('ready'));
});

/* ── Transición al navegar entre páginas del menú (View Transitions, nativo) ──
   Las tabs del menú principal son en-page salvo "Horario"/"Volver", que son
   enlaces: sin esto el salto entre secciones se ve como un corte seco.
   El cross-fade por defecto del navegador se afina en base.css. Si el
   navegador no soporta la API, el enlace navega normal (no hay fallback que
   mantener). */
if (document.startViewTransition && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
  document.addEventListener('click', (e) => {
    const a = e.target.closest('a[href]');
    if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;
    if (a.target || a.hasAttribute('download')) return;
    const href = a.getAttribute('href');
    if (!href || href.startsWith('#') || new URL(a.href).origin !== location.origin) return;
    e.preventDefault();
    document.startViewTransition(() => { location.href = a.href; });
  });
}

/* ── Modal helpers (globales) ── */
window.openModal = function() {
  const m = document.getElementById('modal');
  if (!m) return;
  m.classList.remove('hidden');
  requestAnimationFrame(() => requestAnimationFrame(() => m.classList.add('open')));
};
window.closeModal = function() {
  const m = document.getElementById('modal');
  if (!m) return;
  m.classList.remove('open');
  setTimeout(() => m.classList.add('hidden'), 250);
};

/* ── Animate cards with IntersectionObserver (reuses/disconnects per container) ── */
window.animateCards = function(containerSelector, itemSelector) {
  const container = document.querySelector(containerSelector);
  if (!container) return;
  if (container._cardsObserver) container._cardsObserver.disconnect();
  const items = container.querySelectorAll(itemSelector || '.media-card-wrapper, .chapter-pill');
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.04 });
  items.forEach((el, i) => {
    el.style.transitionDelay = `${Math.min(i * 30, 380)}ms`;
    observer.observe(el);
  });
  container._cardsObserver = observer;
};
