/* ==========================================================================
   SAVED-REPORTS.JS
   --------------------------------------------------------------------------
   Behavior for saved-reports.html. Loads the signed-in user's real
   research records (GET /api/research), renders only the ones that are
   actually "completed" as report cards, and supports search/filter/sort
   over that real data plus a real delete (DELETE /api/research/:id).
   ========================================================================== */

(function () {
  'use strict';

  var API_BASE_URL = window.INVESTIQ_API_BASE || 'http://127.0.0.1:5000';

  var searchInput = document.getElementById('savedReportsSearch');
  var filterChips = document.querySelectorAll('.filter-chip');
  var sortSelect = document.getElementById('savedReportsSort');
  var grid = document.getElementById('savedReportsGrid');
  var emptyState = document.getElementById('savedReportsEmpty');

  if (!grid) return;

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  var records = []; // completed research records from the backend
  var state = { search: '', filter: 'all', sort: 'recent' };

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

  function buildCard(record) {
    var card = document.createElement('article');
    card.className = 'panel report-card';
    card.setAttribute('data-recommendation', (record.recommendation || '').toLowerCase());
    card.setAttribute('data-id', record.id);

    var initials = escapeHtml((record.company_name || '?').trim().slice(0, 2).toUpperCase());
    var rec = record.recommendation ? escapeHtml(record.recommendation) : 'Not available';
    var score = (typeof record.ai_score === 'number') ? (record.ai_score + ' / 100') : 'N/A';
    var savedDate = record.updated_at ? new Date(record.updated_at).toLocaleDateString('en-US', { day: '2-digit', month: 'short', year: 'numeric' }) : '';
    var safeCompanyName = escapeHtml(record.company_name);
    var safeTicker = escapeHtml(record.ticker_symbol);
    var safeId = encodeURIComponent(record.id);

    card.innerHTML =
      '<div class="report-card__top">' +
        '<div class="ai-header__identity">' +
          '<div class="company-overview__logo">' + initials + '</div>' +
          '<div>' +
            '<h2 class="report-card__name">' + safeCompanyName + '</h2>' +
            '<span class="company-overview__ticker">' + safeTicker + '</span>' +
          '</div>' +
        '</div>' +
        '<button type="button" class="report-card__delete" data-action="delete-report" aria-label="Delete saved report for ' + safeCompanyName + '">' +
          '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3m-8 0 1 13a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2l1-13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
        '</button>' +
      '</div>' +
      '<div class="report-card__meta">' +
        '<span class="badge ' + recommendationBadgeClass(record.recommendation) + '">' + rec + '</span>' +
        '<span class="report-card__date">Saved ' + savedDate + '</span>' +
      '</div>' +
      '<div class="report-card__score">' +
        '<span class="company-overview__label">AI Score</span>' +
        '<span class="report-card__score-value">' + score + '</span>' +
      '</div>' +
      '<a href="investment-report.html?research_id=' + safeId + '" class="btn btn-primary btn-block report-card__open">' +
        '<span class="btn-label">Open Report</span>' +
      '</a>';

    return card;
  }

  function cardMatches(record) {
    var matchesFilter = state.filter === 'all' || (record.recommendation || '').toLowerCase() === state.filter;
    var matchesSearch = !state.search ||
      record.company_name.toLowerCase().indexOf(state.search) !== -1 ||
      record.ticker_symbol.toLowerCase().indexOf(state.search) !== -1;
    return matchesFilter && matchesSearch;
  }

  function sortRecords(list) {
    var sorted = list.slice();
    switch (state.sort) {
      case 'oldest':
        sorted.sort(function (a, b) { return new Date(a.updated_at) - new Date(b.updated_at); });
        break;
      case 'score-high':
        sorted.sort(function (a, b) { return (b.ai_score || 0) - (a.ai_score || 0); });
        break;
      case 'score-low':
        sorted.sort(function (a, b) { return (a.ai_score || 0) - (b.ai_score || 0); });
        break;
      case 'name':
        sorted.sort(function (a, b) { return a.company_name.localeCompare(b.company_name); });
        break;
      case 'recent':
      default:
        sorted.sort(function (a, b) { return new Date(b.updated_at) - new Date(a.updated_at); });
        break;
    }
    return sorted;
  }

  function render() {
    grid.innerHTML = '';
    var visible = sortRecords(records.filter(cardMatches));

    if (!visible.length) {
      grid.setAttribute('hidden', '');
      if (emptyState) emptyState.removeAttribute('hidden');
      return;
    }

    grid.removeAttribute('hidden');
    if (emptyState) emptyState.setAttribute('hidden', '');

    visible.forEach(function (record) {
      grid.appendChild(buildCard(record));
    });
  }

  function initSearch() {
    if (!searchInput) return;
    searchInput.addEventListener('input', function () {
      state.search = searchInput.value.trim().toLowerCase();
      render();
    });
  }

  function initFilterChips() {
    if (!filterChips.length) return;
    filterChips.forEach(function (chip) {
      chip.addEventListener('click', function () {
        filterChips.forEach(function (c) { c.classList.remove('is-active'); });
        chip.classList.add('is-active');
        state.filter = chip.getAttribute('data-filter') || 'all';
        render();
      });
    });
  }

  function initSort() {
    if (!sortSelect) return;
    sortSelect.addEventListener('change', function () {
      state.sort = sortSelect.value;
      render();
    });
  }

  function initDeleteButtons() {
    grid.addEventListener('click', function (e) {
      var deleteBtn = e.target.closest('[data-action="delete-report"]');
      if (!deleteBtn) return;

      var card = deleteBtn.closest('.report-card');
      if (!card) return;
      var id = card.getAttribute('data-id');
      var record = records.find(function (r) { return String(r.id) === id; });
      var companyName = (record && record.company_name) || 'this company';

      var confirmed = window.confirm('Delete the saved report for ' + companyName + '? This cannot be undone.');
      if (!confirmed) return;

      deleteBtn.disabled = true;

      fetchJson('/api/research/' + id, { method: 'DELETE' })
        .then(function (result) {
          if (!result.ok) {
            deleteBtn.disabled = false;
            window.alert(result.data.message || 'Could not delete this report. Please try again.');
            return;
          }
          // Only remove from the real list (and re-render) after the
          // backend confirms the record is actually gone -- never
          // optimistically delete client-side first.
          records = records.filter(function (r) { return String(r.id) !== id; });
          render();
        })
        .catch(function () {
          deleteBtn.disabled = false;
          window.alert('Unable to connect to the server. Please make sure the backend is running.');
        });
    });
  }

  function loadRecords() {
    fetchJson('/api/research', { method: 'GET' })
      .then(function (result) {
        if (!result.ok) {
          return;
        }
        // Only completed research records are "saved reports" -- see
        // section 12 of the implementation plan.
        records = (result.data.research || []).filter(function (r) {
          return r.status === 'completed';
        });
        render();
      });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initSearch();
    initFilterChips();
    initSort();
    initDeleteButtons();
    loadRecords();
  });
})();
