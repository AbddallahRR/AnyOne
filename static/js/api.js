// static/js/api.js
(function () {
  'use strict';

  const headers = { 'Content-Type': 'application/json' };
  const inflight = new Map();

  async function handleError(res) {
    if (!res.ok) {
      let msg = `Error ${res.status}`;
      try { const body = await res.json(); msg = body.detail || body.error || msg; } catch {}
      throw new Error(msg);
    }
    return res.text().then(t => t ? JSON.parse(t) : null);
  }

  async function dedupedGet(path) {
    const pending = inflight.get(path);
    if (pending) return pending;
    const promise = fetch(path, { headers }).then(handleError);
    inflight.set(path, promise);
    promise.finally(() => { if (inflight.get(path) === promise) inflight.delete(path); });
    return promise;
  }

  window.api = {
    async get(path) {
      return dedupedGet(path);
    },
    async post(path, body) {
      const res = await fetch(path, { method: 'POST', headers, body: JSON.stringify(body) });
      return handleError(res);
    },
    async put(path, body) {
      const res = await fetch(path, { method: 'PUT', headers, body: JSON.stringify(body) });
      return handleError(res);
    },
    async del(path) {
      const res = await fetch(path, { method: 'DELETE', headers });
      return handleError(res);
    },
  };
})();
