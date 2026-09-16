/* ==========================================================================
   CONFIG.JS
   --------------------------------------------------------------------------
   Single source of truth for the backend API base URL.
   Dynamically aligns with the current host (localhost vs 127.0.0.1) so
   session cookies work seamlessly across ports in development.
   Override at deployment time by setting window.INVESTIQ_API_BASE.
   ========================================================================== */

(function () {
  var host = (typeof window !== 'undefined' && window.location && window.location.hostname) ? window.location.hostname : '127.0.0.1';
  var proto = (typeof window !== 'undefined' && window.location && window.location.protocol && window.location.protocol.indexOf('http') === 0) ? window.location.protocol : 'http:';

  var isLocal = (host === 'localhost' || host === '127.0.0.1');
  var defaultBase = isLocal ? (proto + '//' + host + ':5000') : (proto + '//' + host);

  window.INVESTIQ_API_BASE = window.INVESTIQ_API_BASE || defaultBase;
})();

var INVESTIQ_API_BASE = window.INVESTIQ_API_BASE;
