/* ==========================================================================
   DASHBOARD.JS
   --------------------------------------------------------------------------
   Behavior for dashboard.html only. Five independent, small jobs -- each
   checks for its own elements and bails out quietly if they're not on
   the page, same pattern as auth.js.

   NOTE ON THE SIDEBAR TOGGLE:
   dashboard.css currently only defines a visual effect for the
   `sidebar-open` body class inside its mobile (max-width: 768px) media
   query -- on tablet the sidebar already auto-collapses to an icon rail
   via CSS alone (no JS needed), and on desktop it's always full width.
   So this toggle button's real job today is opening/closing the mobile
   drawer; at wider viewports, clicking it is harmless (the class is
   added but nothing in CSS reacts to it yet). A future phase can extend
   dashboard.css with a desktop rail-collapse state if that's wanted --
   this file is already structured so that's a CSS-only addition.
   ========================================================================== */

(function () {
  'use strict';

  /* ------------------------------------------------------------------
     0. AUTH GUARD (frontend-only, no backend yet)
     This file is loaded on every internal page (Dashboard, Company
     Research, AI Analysis, Investment Report, Saved Reports, Profile,
     Settings, Help) so this is the one place to gate all of them.
     If there's no session flag from js/auth.js's startSession(), bounce
     back to the login page immediately -- before the rest of the page
     has a chance to render -- rather than waiting for DOMContentLoaded.

     BACKEND HOOK: once Flask exists, replace the localStorage check
     with a real session/token validation call.
     ------------------------------------------------------------------ */
  var API_BASE_URL = window.INVESTIQ_API_BASE || 'http://127.0.0.1:5000';
  var SESSION_KEY = 'investiq_auth';
  var USER_KEY = 'investiq_user';

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  var cachedUser = null;
  try {
    cachedUser = JSON.parse(localStorage.getItem(USER_KEY));
  } catch (e) {}

  var isAuth = localStorage.getItem(SESSION_KEY) === 'true';

  if (!isAuth && !cachedUser) {
    window.location.href = 'login.html';
  } else {
    if (cachedUser) {
      populateUserInfo(cachedUser);
      loadDashboardData();
    }

    fetch(API_BASE_URL + '/api/auth/me', {
      method: 'GET',
      credentials: 'include'
    })
      .then(function (response) {
        if (!response.ok) {
          if (!cachedUser && !isAuth) {
            localStorage.removeItem(SESSION_KEY);
            localStorage.removeItem(USER_KEY);
            window.location.href = 'login.html';
          }
          return null;
        }
        return response.json();
      })
      .then(function (data) {
        if (data && data.success && data.user) {
          localStorage.setItem(USER_KEY, JSON.stringify(data.user));
          localStorage.setItem(SESSION_KEY, 'true');
          populateUserInfo(data.user);
          loadDashboardData();
        }
      })
      .catch(function () {
        // Allow session to continue with cached credentials
      });
  }

  /* ------------------------------------------------------------------
     REAL USER INFO IN THE TOPBAR
     This markup (user-trigger__name, user-avatar, user-menu__identity-*)
     is identical across every dashboard page, so this one function --
     called after /api/auth/me resolves above -- replaces the
     "Aditi Sharma" placeholder everywhere it appears without needing
     page-specific ids.
     ------------------------------------------------------------------ */
  function initials(name) {
    if (!name) return '?';
    var parts = name.trim().split(/\s+/);
    var first = parts[0] ? parts[0][0] : '';
    var last = parts.length > 1 ? parts[parts.length - 1][0] : '';
    return (first + last).toUpperCase();
  }

  function populateUserInfo(user) {
    var initialsText = initials(user.name);
    document.querySelectorAll('.user-avatar').forEach(function (el) {
      el.textContent = initialsText;
    });
    document.querySelectorAll('.user-trigger__name').forEach(function (el) {
      el.textContent = user.name;
    });
    document.querySelectorAll('.user-menu__identity-name').forEach(function (el) {
      el.textContent = user.name;
    });
    document.querySelectorAll('.user-menu__identity-email').forEach(function (el) {
      el.textContent = user.email;
    });

    var welcomeTitle = document.getElementById('dashboardWelcomeTitle');
    if (welcomeTitle) {
      var firstName = user.name ? user.name.trim().split(/\s+/)[0] : '';
      welcomeTitle.textContent = 'Welcome back' + (firstName ? ', ' + firstName : '') + ' 👋';
    }
  }

  /* ------------------------------------------------------------------
     REAL DASHBOARD DATA
     Only does anything on pages that actually have these elements
     (currently just dashboard.html) -- every other page's call to
     loadDashboardData() below is a harmless no-op.
     ------------------------------------------------------------------ */
  function fetchJson(url, options) {
    return fetch(API_BASE_URL + url, Object.assign({ credentials: 'include' }, options))
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, data: data };
        });
      });
  }

  function recommendationBadgeClass(rec) {
    if (rec === 'Buy') return 'badge--low';
    if (rec === 'Sell') return 'badge--high';
    return 'badge--medium';
  }

  function statusBadgeClass(status) {
    if (status === 'completed') return 'badge--completed';
    if (status === 'failed') return 'badge--high';
    return 'badge--medium';
  }

  function renderStats(records) {
    var companiesEl = document.getElementById('statCompaniesAnalysed');
    if (!companiesEl) return; // not on dashboard.html

    var distinctTickers = new Set(records.map(function (r) { return r.ticker_symbol; }));
    var completed = records.filter(function (r) { return r.status === 'completed'; });
    var scored = records.filter(function (r) { return typeof r.ai_score === 'number'; });
    var avgScore = scored.length
      ? Math.round(scored.reduce(function (sum, r) { return sum + r.ai_score; }, 0) / scored.length)
      : null;

    var now = new Date();
    var thisMonthCount = records.filter(function (r) {
      var created = new Date(r.created_at);
      return created.getFullYear() === now.getFullYear() && created.getMonth() === now.getMonth();
    }).length;

    companiesEl.textContent = distinctTickers.size;
    document.getElementById('statReportsGenerated').textContent = completed.length;
    document.getElementById('statAverageAiScore').textContent = (avgScore !== null) ? (avgScore + '/100') : '--';
    document.getElementById('statResearchThisMonth').textContent = thisMonthCount;
  }

  function renderScoreDistribution(records) {
    var container = document.getElementById('scoreDistribution');
    var emptyState = document.getElementById('chartsEmptyState');
    if (!container) return;

    var scored = records.filter(function (r) { return typeof r.ai_score === 'number'; });
    if (!scored.length) {
      emptyState.hidden = false;
      container.innerHTML = '';
      return;
    }
    emptyState.hidden = true;

    var buy = scored.filter(function (r) { return r.recommendation === 'Buy'; }).length;
    var hold = scored.filter(function (r) { return r.recommendation === 'Hold'; }).length;
    var sell = scored.filter(function (r) { return r.recommendation === 'Sell'; }).length;
    var avgScore = Math.round(scored.reduce(function (sum, r) { return sum + r.ai_score; }, 0) / scored.length);

    container.innerHTML =
      '<div class="stat-card"><div class="stat-card__value">' + avgScore + '/100</div><div class="stat-card__label">Average Score</div></div>' +
      '<div class="stat-card"><div class="stat-card__value">' + buy + '</div><div class="stat-card__label">Buy Recommendations</div></div>' +
      '<div class="stat-card"><div class="stat-card__value">' + hold + '</div><div class="stat-card__label">Hold Recommendations</div></div>' +
      '<div class="stat-card"><div class="stat-card__value">' + sell + '</div><div class="stat-card__label">Sell Recommendations</div></div>';
  }

  function renderRecentTable(records) {
    var body = document.getElementById('recentResearchBody');
    if (!body) return;

    var emptyEl = document.getElementById('recentResearchEmpty');
    var recent = records.slice(0, 8);

    if (!recent.length) {
      body.innerHTML = '';
      if (emptyEl) emptyEl.hidden = false;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;

    body.innerHTML = recent.map(function (r) {
      var score = (typeof r.ai_score === 'number') ? (r.ai_score + '/100') : 'N/A';
      var rec = r.recommendation
        ? '<span class="badge ' + recommendationBadgeClass(r.recommendation) + '">' + escapeHtml(r.recommendation) + '</span>'
        : '<span class="badge badge--medium">N/A</span>';
      var status = '<span class="badge ' + statusBadgeClass(r.status) + '">' + escapeHtml(r.status) + '</span>';
      var date = new Date(r.created_at).toLocaleDateString('en-US', { day: '2-digit', month: 'short', year: 'numeric' });
      var initialsText = escapeHtml((r.company_name || '?').trim().slice(0, 2).toUpperCase());
      var safeCompanyName = escapeHtml(r.company_name);
      var safeTicker = escapeHtml(r.ticker_symbol);
      var safeId = encodeURIComponent(r.id);

      return '<tr>' +
        '<td><span class="table-company"><span class="table-company__logo">' + initialsText + '</span>' + safeCompanyName + '</span></td>' +
        '<td>' + safeTicker + '</td>' +
        '<td>' + score + '</td>' +
        '<td>' + rec + '</td>' +
        '<td>' + status + '</td>' +
        '<td>' + date + '</td>' +
        '<td><a class="table-action-btn" href="' + (r.status === 'completed' ? 'investment-report.html' : 'ai-analysis.html') + '?research_id=' + safeId + '">View</a></td>' +
        '</tr>';
    }).join('');
  }

  function renderRecentChips(records) {
    var container = document.getElementById('recentSearchChips');
    if (!container) return;
    var emptyEl = document.getElementById('recentSearchEmpty');

    var recent = records.slice(0, 6);
    if (!recent.length) {
      container.innerHTML = '';
      if (emptyEl) emptyEl.hidden = false;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;

    container.innerHTML = recent.map(function (r) {
      var initialsText = escapeHtml((r.company_name || '?').trim().slice(0, 2).toUpperCase());
      var safeCompanyName = escapeHtml(r.company_name);
      var safeId = encodeURIComponent(r.id);
      return '<a href="ai-analysis.html?research_id=' + safeId + '" class="search-chip">' +
        '<span class="search-chip__logo">' + initialsText + '</span>' +
        '<span class="search-chip__name">' + safeCompanyName + '</span></a>';
    }).join('');
  }

  function loadDashboardData() {
    // Only relevant on dashboard.html, but harmless to call everywhere:
    // every render function above bails out immediately if its target
    // elements aren't on the current page.
    if (!document.getElementById('statCompaniesAnalysed')) return;

    fetchJson('/api/research', { method: 'GET' }).then(function (result) {
      if (!result.ok) return;
      var records = result.data.research || [];
      // Most-recent-first, same ordering the backend already returns,
      // but sorted explicitly here too since these render functions
      // are also usable independent of that assumption.
      records.sort(function (a, b) { return new Date(b.created_at) - new Date(a.created_at); });

      renderStats(records);
      renderScoreDistribution(records);
      renderRecentTable(records);
      renderRecentChips(records);
    });
  }

  /* ------------------------------------------------------------------
     LOGOUT
     Every internal page has a `.sidebar__link--logout` link that
     points at index.html -- call backend logout first so session
     cookie is invalidated, then clear localStorage and redirect.
     ------------------------------------------------------------------ */
  function initLogout() {
    document.querySelectorAll('.sidebar__link--logout, .dropdown-link--danger, [data-action="logout"]').forEach(function (link) {
      link.addEventListener('click', function (e) {
        e.preventDefault();
        fetch(API_BASE_URL + '/api/auth/logout', {
          method: 'POST',
          credentials: 'include'
        }).finally(function () {
          localStorage.removeItem(SESSION_KEY);
          localStorage.removeItem(USER_KEY);
          window.location.href = 'index.html';
        });
      });
    });
  }
  initLogout();

  /* ------------------------------------------------------------------
     REMOVE FAKE NOTIFICATIONS
     The notification bell's dropdown ships with hardcoded example
     items ("Risk score updated for NVIDIA Corp.", etc.) baked into
     every page's HTML. There's no real notifications backend, so
     these are fabricated activity claims -- this replaces them with
     an honest empty state instead of leaving them in place.
     ------------------------------------------------------------------ */
  function clearFakeNotifications() {
    document.querySelectorAll('.dropdown__header').forEach(function (header) {
      if (header.textContent.indexOf('Notifications') === -1) return;
      var panel = header.closest('.dropdown__panel');
      if (!panel) return;
      panel.querySelectorAll('.notification-item').forEach(function (item) {
        item.remove();
      });
      var empty = document.createElement('p');
      empty.style.padding = '12px 16px';
      empty.style.margin = '0';
      empty.style.fontSize = 'var(--fs-sm)';
      empty.style.color = 'var(--color-text-secondary)';
      empty.textContent = 'No notifications yet.';
      panel.appendChild(empty);
    });
    document.querySelectorAll('.topbar__badge').forEach(function (badge) {
      badge.remove();
    });
  }

  /* ------------------------------------------------------------------
     1. SIDEBAR MOBILE DRAWER
     ------------------------------------------------------------------ */
  function initSidebarToggle() {
    var toggleBtn = document.getElementById('sidebarToggle');
    var backdrop = document.getElementById('sidebarBackdrop');
    if (!toggleBtn) return;

    function closeSidebar() {
      document.body.classList.remove('sidebar-open');
      toggleBtn.setAttribute('aria-expanded', 'false');
    }

    toggleBtn.addEventListener('click', function () {
      var isOpen = document.body.classList.toggle('sidebar-open');
      toggleBtn.setAttribute('aria-expanded', String(isOpen));
    });

    if (backdrop) {
      backdrop.addEventListener('click', closeSidebar);
    }

    // If the window is resized past the mobile breakpoint while the
    // drawer is open, close it -- otherwise it could get "stuck" open
    // behind desktop layout styles that no longer expect it.
    window.addEventListener('resize', function () {
      if (window.innerWidth > 768) {
        closeSidebar();
      }
    });

    // Escape key closes the drawer, same as it closes dropdowns below.
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeSidebar();
    });
  }

  /* ------------------------------------------------------------------
     2. DROPDOWNS (notification bell + user menu)
     Both use the same markup contract: a wrapper with [data-dropdown],
     a trigger button with [data-dropdown-trigger], and a .dropdown__panel
     inside it. This lets one function drive any number of dropdowns
     without duplicating logic per-dropdown.
     ------------------------------------------------------------------ */
  function initDropdowns() {
    var dropdowns = document.querySelectorAll('[data-dropdown]');
    if (!dropdowns.length) return;

    function closeAllDropdowns() {
      document.querySelectorAll('.dropdown__panel.is-open').forEach(function (panel) {
        panel.classList.remove('is-open');
        var parent = panel.closest('[data-dropdown]');
        var trigger = parent ? parent.querySelector('[data-dropdown-trigger]') : null;
        if (trigger) trigger.setAttribute('aria-expanded', 'false');
      });
    }

    dropdowns.forEach(function (dropdown) {
      var trigger = dropdown.querySelector('[data-dropdown-trigger]');
      var panel = dropdown.querySelector('.dropdown__panel');
      if (!trigger || !panel) return;

      trigger.addEventListener('click', function (e) {
        // Stop this click from immediately re-closing the panel via
        // the document-level listener registered just below.
        e.stopPropagation();
        var wasOpen = panel.classList.contains('is-open');
        closeAllDropdowns();
        if (!wasOpen) {
          panel.classList.add('is-open');
          trigger.setAttribute('aria-expanded', 'true');
        }
      });
    });

    // Clicking anywhere outside an open dropdown closes it.
    document.addEventListener('click', closeAllDropdowns);

    // Escape closes any open dropdown too.
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeAllDropdowns();
    });
  }

  /* ------------------------------------------------------------------
     3. SKELETON LOADING SIMULATION
     Every element marked [data-skeleton] starts with the `.skeleton`
     class (shimmering placeholder, see dashboard.css) and loses it
     shortly after the page loads -- standing in for the moment real
     data arrives from the backend.
     ------------------------------------------------------------------ */
  function initSkeletonLoading() {
    var skeletonEls = document.querySelectorAll('[data-skeleton]');
    if (!skeletonEls.length) return;

    // BACKEND HOOK: once Flask endpoints exist, replace this fixed
    // timeout with removing `.skeleton` inside the `.then()` of the
    // real fetch() calls that populate each panel's data.
    setTimeout(function () {
      skeletonEls.forEach(function (el) {
        el.classList.remove('skeleton');
      });
    }, 900);
  }

  /* ------------------------------------------------------------------
     4. STAT CARD COUNT-UP
     Kept for any [data-target] element that might still exist on other
     pages (e.g. the landing page uses its own copy in statistics.js) --
     the real dashboard stat cards no longer use data-target, they're
     populated directly with real numbers by renderStats() above.
     ------------------------------------------------------------------ */
  function initStatCounters() {
    var values = document.querySelectorAll('.stat-card__value[data-target]');
    if (!values.length) return;

    var prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function animateValue(el) {
      var target = parseFloat(el.getAttribute('data-target'));
      var prefix = el.getAttribute('data-prefix') || '';
      var suffix = el.getAttribute('data-suffix') || '';
      var duration = 1200;

      if (prefersReducedMotion) {
        el.textContent = prefix + target.toLocaleString('en-IN') + suffix;
        return;
      }

      var startTime = null;
      function step(timestamp) {
        if (!startTime) startTime = timestamp;
        var progress = Math.min((timestamp - startTime) / duration, 1);
        var eased = 1 - Math.pow(1 - progress, 3);
        var current = Math.floor(eased * target);
        el.textContent = prefix + current.toLocaleString('en-IN') + suffix;
        if (progress < 1) {
          requestAnimationFrame(step);
        } else {
          el.textContent = prefix + target.toLocaleString('en-IN') + suffix;
        }
      }
      requestAnimationFrame(step);
    }

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            animateValue(entry.target);
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.4 }
    );

    values.forEach(function (el) {
      observer.observe(el);
    });
  }

  /* ------------------------------------------------------------------
     5. LIVE TOPBAR DATE
     Fills in today's date automatically, same "don't hardcode a value
     that goes stale" principle as the footer year in main.js.
     ------------------------------------------------------------------ */
  function initTopbarDate() {
    var dateEl = document.getElementById('topbarDate');
    if (!dateEl) return;
    var today = new Date();
    var options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    dateEl.textContent = today.toLocaleDateString('en-US', options);
  }

  /* ------------------------------------------------------------------
     6. QUICK ACTIONS, REPORT TABLE "VIEW", AND RECENT SEARCH CHIPS
     None of these had a destination before -- they're plain buttons
     with a data-action attribute and nowhere to go. Each one routes to
     the existing page that matches its intent; the two that involve a
     specific company (View Report row / recent-search chip) pass it
     along as a `?company=` query string, which company-research.js
     now reads on load (see initDeepLinkCompany there) to pre-load that
     company instead of the default.

     BACKEND HOOK: once real report IDs exist, "View" should link to
     /reports/:id instead of a query-string company name.
     ------------------------------------------------------------------ */
  function initQuickActions() {
    var routes = {
      'analyse': 'company-research.html',
      'generate-report': 'ai-analysis.html',
      'market-trends': 'company-research.html',
      'compare': 'company-research.html'
    };

    document.querySelectorAll('.quick-action[data-action]').forEach(function (btn) {
      var target = routes[btn.getAttribute('data-action')];
      if (!target) return;
      btn.addEventListener('click', function () {
        window.location.href = target;
      });
    });
  }

  /* ------------------------------------------------------------------
     INIT
     ------------------------------------------------------------------ */
  document.addEventListener('DOMContentLoaded', function () {
    initSidebarToggle();
    initDropdowns();
    initSkeletonLoading();
    initStatCounters();
    initTopbarDate();
    initQuickActions();
    clearFakeNotifications();
  });
})();