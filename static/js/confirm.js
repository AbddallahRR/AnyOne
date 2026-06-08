(function () {
  'use strict';

  window.showConfirm = function (title, message, okLabel, okClass) {
    return new Promise(function (resolve) {
      var overlay = document.createElement('div');
      overlay.className = 'confirm-overlay';
      overlay.innerHTML =
        '<div class="confirm-dialog">' +
          '<h3>' + title + '</h3>' +
          '<p>' + message + '</p>' +
          '<div class="confirm-actions">' +
            '<button class="btn-ghost" id="confirm-cancel">Cancelar</button>' +
            '<button class="btn-primary' + (okClass ? ' ' + okClass : '') + '" id="confirm-ok">' + (okLabel || 'Continuar') + '</button>' +
          '</div>' +
        '</div>';
      document.body.appendChild(overlay);

      var resolveAndClose = function (value) {
        overlay.remove();
        resolve(value);
      };

      overlay.querySelector('#confirm-ok').onclick = function () { resolveAndClose(true); };
      overlay.querySelector('#confirm-cancel').onclick = function () { resolveAndClose(false); };
      overlay.onclick = function (e) { if (e.target === overlay) { resolveAndClose(false); } };
    });
  };
})();
