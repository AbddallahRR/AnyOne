// static/js/realtime.js
// SSE client for real-time updates (watched, notifications, downloads)
(function () {
  'use strict';

  let _es = null;
  let _handlers = new Map(); // event -> Set<callback>
  let _reconnectTimer = null;

  function connect() {
    if (_es) return; // Already connected

    _es = new EventSource('/api/realtime/updates');

    _es.onopen = () => {
      console.log('[SSE] Connected');
      if (_reconnectTimer) {
        clearTimeout(_reconnectTimer);
        _reconnectTimer = null;
      }
    };

    _es.onerror = (err) => {
      console.warn('[SSE] Error, will reconnect:', err);
      // EventSource auto-reconnects, but we can force a faster reconnect
      if (!_reconnectTimer) {
        _reconnectTimer = setTimeout(() => {
          if (_es && _es.readyState === EventSource.CLOSED) {
            _es.close();
            _es = null;
            connect();
          }
          _reconnectTimer = null;
        }, 3000);
      }
    };

    // Register event listeners
    _es.addEventListener('watched_changed', (e) => {
      try {
        const data = JSON.parse(e.data);
        _emit('watched_changed', data);
      } catch (err) {
        console.warn('[SSE] Failed to parse watched_changed:', err);
      }
    });

    _es.addEventListener('new_chapters', (e) => {
      try {
        const data = JSON.parse(e.data);
        _emit('new_chapters', data);
      } catch (err) {
        console.warn('[SSE] Failed to parse new_chapters:', err);
      }
    });
  }

  function _emit(event, data) {
    const handlers = _handlers.get(event);
    if (handlers) handlers.forEach(cb => cb(data));
  }

  function on(event, callback) {
    if (!_handlers.has(event)) _handlers.set(event, new Set());
    _handlers.get(event).add(callback);
    connect(); // Lazy connect on first subscription
    return () => _handlers.get(event)?.delete(callback);
  }

  function disconnect() {
    if (_es) {
      _es.close();
      _es = null;
    }
    if (_reconnectTimer) {
      clearTimeout(_reconnectTimer);
      _reconnectTimer = null;
    }
  }

  window.Realtime = { on, disconnect };
})();