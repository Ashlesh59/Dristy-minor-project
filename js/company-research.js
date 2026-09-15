/* ==========================================================================
   COMPANY-RESEARCH.JS
   --------------------------------------------------------------------------
   Behavior for company-research.html. On submit: creates a research
   record (POST /api/research), then fetches real financials and news
   for it. Includes ticker-search autocomplete and XSS protection.
   ========================================================================== */

(function () {
  'use strict';

  var API_BASE_URL = window.INVESTIQ_API_BASE || 'http://127.0.0.1:5000';

  var form = document.getElementById('companySearchForm');
  if (!form) return; // not on this page

  var nameInput = document.getElementById('companyNameInput');
  var tickerInput = document.getElementById('companyTickerInput');
  var formError = document.getElementById('searchFormError');
  var submitBtn = form.querySelector('button[type="submit"]');
  var autocompleteDropdown = document.getElementById('tickerSearchResults');

  var loadingEl = document.getElementById('researchLoading');
  var errorEl = document.getElementById('researchError');
  var resultsEl = document.getElementById('researchResults');

  var ovLogo = document.getElementById('ovLogo');
  var ovName = document.getElementById('ovName');
  var ovTicker = document.getElementById('ovTicker');
  var ovPrice = document.getElementById('ovPrice');
  var ovChange = document.getElementById('ovChange');
  var ovChangePercent = document.getElementById('ovChangePercent');
  var ovHigh = document.getElementById('ovHigh');
  var ovLow = document.getElementById('ovLow');
  var ovTradingDay = document.getElementById('ovTradingDay');

  var financialCards = document.getElementById('financialCards');
  var newsGrid = document.getElementById('newsGrid');
  var newsEmpty = document.getElementById('newsEmpty');

  var goToAnalysisBtn = document.getElementById('goToAnalysisBtn');
  var generateReportActionBtn = document.getElementById('generateReportActionBtn');
  var exportPdfBtn = document.getElementById('exportPdfBtn');

  var currentResearchId = null;
  var debounceTimer = null;

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function getCurrencySymbol(currency) {
    if (!currency) return '$';
    var c = String(currency).toUpperCase();
    if (c === 'INR') return '₹';
    if (c === 'GBP') return '£';
    if (c === 'EUR') return '€';
    if (c === 'JPY') return '¥';
    if (c === 'CAD') return 'CA$';
    if (c === 'AUD') return 'AU$';
    return '$';
  }

  function formatPrice(val, currency) {
    if (val === null || val === undefined || val === '') return 'N/A';
    var sym = getCurrencySymbol(currency);
    return sym + val;
  }

  function fetchJson(url, options) {
    return fetch(API_BASE_URL + url, Object.assign({ credentials: 'include' }, options))
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, status: response.status, data: data };
        });
      });
  }

  function showLoading(show) {
    loadingEl.hidden = !show;
  }

  function showError(message) {
    errorEl.textContent = message;
    errorEl.hidden = false;
  }

  function clearError() {
    errorEl.hidden = true;
    errorEl.textContent = '';
  }

  function renderOverview(record, financialData) {
    var initials = escapeHtml((record.company_name || '?').trim().slice(0, 2).toUpperCase());
    ovLogo.textContent = initials;
    ovName.textContent = record.company_name;
    ovTicker.textContent = record.ticker_symbol;

    if (financialData) {
      var curr = financialData.currency || 'USD';
      ovPrice.textContent = financialData.price ? formatPrice(financialData.price, curr) : 'N/A';
      ovChange.textContent = financialData.change || 'N/A';
      ovChangePercent.textContent = financialData.change_percent || 'N/A';
      ovHigh.textContent = financialData.high ? formatPrice(financialData.high, curr) : 'N/A';
      ovLow.textContent = financialData.low ? formatPrice(financialData.low, curr) : 'N/A';
      ovTradingDay.textContent = financialData.latest_trading_day || 'N/A';
    } else {
      [ovPrice, ovChange, ovChangePercent, ovHigh, ovLow, ovTradingDay].forEach(function (el) {
        el.textContent = 'N/A';
      });
    }
  }

  function renderFinancialCards(financialData) {
    financialCards.innerHTML = '';
    if (!financialData) {
      financialCards.innerHTML = '<p class="field-hint">Financial data is temporarily unavailable for this ticker.</p>';
      return;
    }
    var curr = financialData.currency || 'USD';
    var cards = [
      { label: 'Last Close (EOD)', value: financialData.price ? formatPrice(financialData.price, curr) : null },
      { label: 'Change', value: financialData.change },
      { label: 'Change %', value: financialData.change_percent },
      { label: 'Day High', value: financialData.high ? formatPrice(financialData.high, curr) : null },
      { label: 'Day Low', value: financialData.low ? formatPrice(financialData.low, curr) : null },
      { label: 'Volume', value: financialData.volume ? Number(financialData.volume).toLocaleString('en-US') : null }
    ];
    cards.forEach(function (c) {
      if (!c.value) return;
      var card = document.createElement('div');
      card.className = 'stat-card';
      var valEl = document.createElement('div');
      valEl.className = 'stat-card__value';
      valEl.textContent = c.value;
      var lblEl = document.createElement('div');
      lblEl.className = 'stat-card__label';
      lblEl.textContent = c.label;
      card.appendChild(valEl);
      card.appendChild(lblEl);
      financialCards.appendChild(card);
    });
    if (!financialCards.children.length) {
      financialCards.innerHTML = '<p class="field-hint">No financial data available for this ticker.</p>';
    }
  }

  function renderNews(articles) {
    newsGrid.innerHTML = '';
    if (!articles || !articles.length) {
      newsEmpty.hidden = false;
      return;
    }
    newsEmpty.hidden = true;
    articles.slice(0, 6).forEach(function (article) {
      var card = document.createElement('a');
      card.className = 'news-card';
      card.href = article.url || '#';
      card.target = '_blank';
      card.rel = 'noopener noreferrer';

      var thumb = document.createElement('div');
      thumb.className = 'news-card__thumb';
      thumb.innerHTML = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 4h16v16H4V4Z" stroke="currentColor" stroke-width="1.6"/><path d="M8 9h8M8 13h8M8 17h4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';

      var body = document.createElement('div');
      body.className = 'news-card__body';

      var tag = document.createElement('span');
      tag.className = 'news-card__tag';
      tag.textContent = article.sentiment || 'News';

      var title = document.createElement('span');
      title.className = 'news-card__title';
      title.textContent = article.title || '';

      body.appendChild(tag);
      body.appendChild(title);
      card.appendChild(thumb);
      card.appendChild(body);
      newsGrid.appendChild(card);
    });
  }

  function loadFinancialsAndNews(researchId) {
    return Promise.all([
      fetchJson('/api/research/' + encodeURIComponent(researchId) + '/financials', { method: 'GET' }),
      fetchJson('/api/research/' + encodeURIComponent(researchId) + '/news', { method: 'GET' })
    ]).then(function (results) {
      var financialsResult = results[0];
      var newsResult = results[1];

      var financialData = financialsResult.ok ? financialsResult.data.financial_data : null;
      renderOverview({ company_name: nameInput.value.trim(), ticker_symbol: tickerInput.value.trim().toUpperCase() }, financialData);
      renderFinancialCards(financialData);

      if (!financialsResult.ok) {
        showError(financialsResult.data.message || 'Could not load financial data for this ticker.');
      }

      var news = newsResult.ok ? newsResult.data.news : [];
      renderNews(news);
      if (!newsResult.ok) {
        var msg = newsResult.data.message || 'Could not load news for this ticker.';
        if (errorEl.hidden) {
          showError(msg);
        } else {
          errorEl.textContent += ' ' + msg;
        }
      }
    });
  }

  function search(companyName, ticker) {
    clearError();
    if (autocompleteDropdown) autocompleteDropdown.hidden = true;
    resultsEl.hidden = true;
    showLoading(true);
    submitBtn.disabled = true;

    fetchJson('/api/research', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ company_name: companyName, ticker_symbol: ticker })
    })
      .then(function (result) {
        if (!result.ok) {
          showLoading(false);
          submitBtn.disabled = false;
          showError(result.data.message || 'Could not create a research request.');
          return null;
        }
        currentResearchId = result.data.research.id;
        goToAnalysisBtn.href = 'ai-analysis.html?research_id=' + encodeURIComponent(currentResearchId);
        resultsEl.hidden = false;
        return loadFinancialsAndNews(currentResearchId);
      })
      .then(function () {
        showLoading(false);
        submitBtn.disabled = false;
      })
      .catch(function () {
        showLoading(false);
        submitBtn.disabled = false;
        showError('Unable to connect to the server. Please make sure the backend is running.');
      });
  }

  /* ------------------------------------------------------------------
     TICKER / COMPANY AUTOCOMPLETE
     ------------------------------------------------------------------ */
  function initAutocomplete() {
    if (!nameInput || !autocompleteDropdown) return;

    function doSearch() {
      var query = nameInput.value.trim();
      if (query.length < 2) {
        autocompleteDropdown.hidden = true;
        autocompleteDropdown.innerHTML = '';
        return;
      }

      fetchJson('/api/research/ticker-search?keywords=' + encodeURIComponent(query), { method: 'GET' })
        .then(function (result) {
          if (!result.ok || !result.data.matches || !result.data.matches.length) {
            autocompleteDropdown.hidden = true;
            autocompleteDropdown.innerHTML = '';
            return;
          }

          autocompleteDropdown.innerHTML = '';
          result.data.matches.slice(0, 6).forEach(function (match) {
            var item = document.createElement('div');
            item.className = 'ticker-autocomplete-item';

            var info = document.createElement('div');
            info.className = 'ticker-autocomplete-item__info';

            var nameSpan = document.createElement('span');
            nameSpan.className = 'ticker-autocomplete-item__name';
            nameSpan.textContent = match.name || match.symbol;

            var regionSpan = document.createElement('span');
            regionSpan.className = 'ticker-autocomplete-item__region';
            regionSpan.textContent = (match.type || 'Equity') + ' • ' + (match.region || '') + (match.currency ? ' (' + match.currency + ')' : '');

            info.appendChild(nameSpan);
            info.appendChild(regionSpan);

            var symSpan = document.createElement('span');
            symSpan.className = 'ticker-autocomplete-item__symbol';
            symSpan.textContent = match.symbol;

            item.appendChild(info);
            item.appendChild(symSpan);

            item.addEventListener('click', function () {
              nameInput.value = match.name || match.symbol;
              tickerInput.value = match.symbol;
              autocompleteDropdown.hidden = true;
              autocompleteDropdown.innerHTML = '';
            });

            autocompleteDropdown.appendChild(item);
          });
          autocompleteDropdown.hidden = false;
        })
        .catch(function () {
          autocompleteDropdown.hidden = true;
        });
    }

    nameInput.addEventListener('input', function () {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(doSearch, 300);
    });

    document.addEventListener('click', function (e) {
      if (!autocompleteDropdown.contains(e.target) && e.target !== nameInput) {
        autocompleteDropdown.hidden = true;
      }
    });
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var companyName = nameInput.value.trim();
    var ticker = tickerInput.value.trim().toUpperCase();

    formError.hidden = true;
    if (!companyName || !ticker) {
      formError.textContent = 'Please enter both a company name and a ticker symbol.';
      formError.hidden = false;
      return;
    }

    search(companyName, ticker);
  });

  document.querySelectorAll('.search-chip').forEach(function (chip) {
    chip.addEventListener('click', function () {
      var company = chip.getAttribute('data-company');
      var ticker = chip.getAttribute('data-ticker');
      nameInput.value = company;
      tickerInput.value = ticker;
      search(company, ticker);
    });
  });

  if (generateReportActionBtn) {
    generateReportActionBtn.addEventListener('click', function () {
      if (!currentResearchId) return;
      window.location.href = 'ai-analysis.html?research_id=' + encodeURIComponent(currentResearchId);
    });
  }

  if (exportPdfBtn) {
    exportPdfBtn.addEventListener('click', function () {
      window.print();
    });
  }

  initAutocomplete();
})();
