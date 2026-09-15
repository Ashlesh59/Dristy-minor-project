(function () {
  'use strict';

  var yearEl = document.getElementById('footerYear');
  if (yearEl) {
    var year = new Date().getFullYear();
    yearEl.textContent = '\u00A9 ' + year + ' InvestIQ. All rights reserved.';
  }
})();