/* ==========================================================================
   NAVBAR.JS
   --------------------------------------------------------------------------
   Two small, independent jobs, each explained below. We keep this file
   scoped ONLY to navbar behavior -- hero animations live in hero.js, and
   anything page-wide lives in main.js. This separation is what "modular
   JavaScript" means in practice: each file has one clear responsibility,
   so when the Dashboard page needs a navbar later, we can reuse this
   exact file with zero changes.
   ========================================================================== */

(function () {
  'use strict';

  var navbar = document.getElementById('navbar');
  var toggleBtn = document.getElementById('navbarToggle');
  var links = document.getElementById('navbarLinks');

  /* ------------------------------------------------------------------
     JOB 1: Toggle `.is-scrolled` on the navbar once the page has
     scrolled past a small threshold (40px). We read `window.scrollY`
     inside a scroll listener, but wrap the actual DOM write in
     requestAnimationFrame so we never fight the browser's own paint
     cycle -- this keeps scrolling smooth even on low-end devices.
     ------------------------------------------------------------------ */
  var SCROLL_THRESHOLD = 40;
  var ticking = false;

  function updateNavbarState() {
    if (window.scrollY > SCROLL_THRESHOLD) {
      navbar.classList.add('is-scrolled');
    } else {
      navbar.classList.remove('is-scrolled');
    }
    ticking = false;
  }

  window.addEventListener('scroll', function () {
    if (!ticking) {
      window.requestAnimationFrame(updateNavbarState);
      ticking = true;
    }
  });

  // Run once on load in case the page is refreshed mid-scroll.
  updateNavbarState();

  /* ------------------------------------------------------------------
     JOB 2: Mobile menu toggle. Clicking the hamburger adds `.is-open`
     to both the button (so the CSS can morph it into an "X") and the
     link list (so CSS can slide/fade it into view). We also update
     `aria-expanded` for screen reader users, and close the menu
     automatically when a link is clicked -- a small but important UX
     detail so the menu doesn't stay open after navigation.
     ------------------------------------------------------------------ */
  if (toggleBtn && links) {
    toggleBtn.addEventListener('click', function () {
      var isOpen = links.classList.toggle('is-open');
      toggleBtn.classList.toggle('is-open', isOpen);
      toggleBtn.setAttribute('aria-expanded', String(isOpen));
    });

    links.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        links.classList.remove('is-open');
        toggleBtn.classList.remove('is-open');
        toggleBtn.setAttribute('aria-expanded', 'false');
      });
    });
  }
})();