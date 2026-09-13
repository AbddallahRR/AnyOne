// static/js/base.js
// Global utilities shared across all pages.

/* ── Body ready (fade-in) ── */
document.addEventListener('DOMContentLoaded', () => {
  requestAnimationFrame(() => document.body.classList.add('ready'));
});

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
