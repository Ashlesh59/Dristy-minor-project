(function () {
  'use strict';

  var prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (prefersReducedMotion) return;

  var revenueEl = document.querySelector('[data-metric="revenue"]');
  var growthEl = document.querySelector('[data-metric="growth"]');

  if (!revenueEl || !growthEl) return;

  var baseRevenue = 482;
  var baseGrowth = 14.2;

  function tick() {
    var revenueDelta = (Math.random() * 4 - 2).toFixed(0);
    var growthDelta = (Math.random() * 0.6 - 0.3).toFixed(1);

    var newRevenue = baseRevenue + Number(revenueDelta);
    var newGrowth = (baseGrowth + Number(growthDelta)).toFixed(1);

    revenueEl.textContent = '$' + newRevenue + 'M';
    growthEl.textContent = (newGrowth >= 0 ? '+' : '') + newGrowth + '%';
  }

  setInterval(tick, 3500);
})();