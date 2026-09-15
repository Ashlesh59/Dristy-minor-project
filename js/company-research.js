/* ==========================================================================
   COMPANY-RESEARCH.JS
   --------------------------------------------------------------------------
   Behavior for company-research.html.
   - Company name search with debounced, sequenced autocomplete.
   - Requires selecting an autocomplete match or providing a valid ticker.
   - Validates ticker via backend before creating research records.
   - Distinct, clear error messages for all failure modes.
   ========================================================================== */

(function () {
  'use strict';

  var API_BASE_URL = window.INVESTIQ_API_BASE || 'http://127.0.0.1:5000';

  var form = document.getElementById('companySearchForm');
  if (!form) return;

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
  var autocompleteAbortController = null;
  var autocompleteSeq = 0;

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
    if (loadingEl) loadingEl.hidden = !show;
  }

  function showError(message) {
    if (errorEl) {
      errorEl.textContent = message;
      errorEl.hidden = false;
    }
  }

  function clearError() {
    if (errorEl) {
      errorEl.hidden = true;
      errorEl.textContent = '';
    }
    if (formError) {
      formError.hidden = true;
      formError.textContent = '';
    }
  }

  function renderOverview(record, financialData) {
    var initials = escapeHtml((record.company_name || '?').trim().slice(0, 2).toUpperCase());
    if (ovLogo) ovLogo.textContent = initials;
    if (ovName) ovName.textContent = record.company_name;
    if (ovTicker) ovTicker.textContent = record.ticker_symbol;

    if (financialData) {
      var curr = financialData.currency || 'USD';
      if (ovPrice) ovPrice.textContent = financialData.price ? formatPrice(financialData.price, curr) : 'N/A';
      if (ovChange) ovChange.textContent = financialData.change || 'N/A';
      if (ovChangePercent) ovChangePercent.textContent = financialData.change_percent || 'N/A';
      if (ovHigh) ovHigh.textContent = financialData.high ? formatPrice(financialData.high, curr) : 'N/A';
      if (ovLow) ovLow.textContent = financialData.low ? formatPrice(financialData.low, curr) : 'N/A';
      if (ovTradingDay) ovTradingDay.textContent = financialData.latest_trading_day || 'N/A';
    } else {
      [ovPrice, ovChange, ovChangePercent, ovHigh, ovLow, ovTradingDay].forEach(function (el) {
        if (el) el.textContent = 'N/A';
      });
    }
  }

  function renderFinancialCards(financialData) {
    if (!financialCards) return;
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
    if (!newsGrid) return;
    newsGrid.innerHTML = '';
    if (!articles || !articles.length) {
      if (newsEmpty) newsEmpty.hidden = false;
      return;
    }
    if (newsEmpty) newsEmpty.hidden = true;
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

  function search(companyName, ticker) {
    clearError();
    if (autocompleteDropdown) autocompleteDropdown.hidden = true;
    if (resultsEl) resultsEl.hidden = true;
    showLoading(true);
    if (submitBtn) submitBtn.disabled = true;

    fetchJson('/api/research', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ company_name: companyName, ticker_symbol: ticker })
    })
      .then(function (result) {
        showLoading(false);
        if (submitBtn) submitBtn.disabled = false;

        if (!result.ok) {
          var errorType = result.data ? result.data.error_type : null;
          var msg = result.data ? result.data.message : null;

          if (result.status === 503 || errorType === 'provider_unavailable') {
            showError('Financial data provider rate limit reached. Please try again in a minute.');
          } else if (result.status === 500 && (errorType === 'missing_api_key' || (msg && msg.indexOf('API key') !== -1))) {
            showError('Financial API key is not configured.');
          } else if (result.status === 400 && errorType === 'invalid_ticker') {
            showError('Invalid ticker symbol. No financial data found for this ticker.');
          } else {
            showError(msg || 'Could not retrieve financial data for this ticker.');
          }
          return null;
        }

        var research = result.data.research;
        var financialData = result.data.financial_data;
        currentResearchId = research.id;

        if (goToAnalysisBtn) {
          goToAnalysisBtn.href = 'ai-analysis.html?research_id=' + encodeURIComponent(currentResearchId);
        }

        renderOverview(research, financialData);
        renderFinancialCards(financialData);
        if (resultsEl) resultsEl.hidden = false;

        // Fetch news for this validated ticker
        return fetchJson('/api/research/' + encodeURIComponent(currentResearchId) + '/news', { method: 'GET' })
          .then(function (newsResult) {
            var news = newsResult.ok ? newsResult.data.news : [];
            renderNews(news);
          });
      })
      .catch(function () {
        showLoading(false);
        if (submitBtn) submitBtn.disabled = false;
        showError('Unable to connect to the server. Please check your backend connection.');
      });
  }

  /* ------------------------------------------------------------------
     TICKER / COMPANY AUTOCOMPLETE WITH SEQUENCE & ABORTCONTROLLER
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

      if (autocompleteAbortController) {
        autocompleteAbortController.abort();
      }
      if (window.AbortController) {
        autocompleteAbortController = new AbortController();
      }

      autocompleteSeq++;
      var thisSeq = autocompleteSeq;

      var fetchOptions = {
        method: 'GET',
        signal: autocompleteAbortController ? autocompleteAbortController.signal : undefined
      };

      fetchJson('/api/research/ticker-search?keywords=' + encodeURIComponent(query), fetchOptions)
        .then(function (result) {
          if (thisSeq !== autocompleteSeq) return;

          autocompleteDropdown.innerHTML = '';

          if (!result.ok || !result.data.matches || !result.data.matches.length) {
            var emptyItem = document.createElement('div');
            emptyItem.className = 'ticker-autocomplete-item ticker-autocomplete-item--empty';
            emptyItem.textContent = 'No matching companies found.';
            emptyItem.style.padding = '10px 14px';
            emptyItem.style.color = 'var(--color-text-secondary, #64748b)';
            emptyItem.style.fontSize = 'var(--fs-sm, 0.875rem)';
            autocompleteDropdown.appendChild(emptyItem);
            autocompleteDropdown.hidden = false;
            return;
          }

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
              clearError();
            });

            autocompleteDropdown.appendChild(item);
          });
          autocompleteDropdown.hidden = false;
        })
        .catch(function (err) {
          if (err && err.name === 'AbortError') return;
          if (thisSeq !== autocompleteSeq) return;
          autocompleteDropdown.hidden = true;
        });
    }

    nameInput.addEventListener('input', function () {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(doSearch, 250);
    });

    document.addEventListener('click', function (e) {
      if (!autocompleteDropdown.contains(e.target) && e.target !== nameInput) {
        autocompleteDropdown.hidden = true;
      }
    });
  }

  function handleFormSubmit(e) {
    if (e) e.preventDefault();
    clearError();

    var nameVal = (nameInput.value || '').trim();
    var tickerVal = (tickerInput.value || '').trim().toUpperCase();

    // 1. If user provided a specific ticker explicitly
    if (tickerVal) {
      var companyName = nameVal || tickerVal;
      search(companyName, tickerVal);
      return;
    }

    // 2. If user entered a single clean ticker in the name box (e.g., "AAPL", "MSFT", "TSLA", "RELIANCE.BSE")
    if (/^[A-Za-z0-9.]{1,6}$/.test(nameVal)) {
      tickerInput.value = nameVal.toUpperCase();
      search(nameVal.toUpperCase(), nameVal.toUpperCase());
      return;
    }

    // 3. User typed a general company name without selecting an autocomplete item
    if (nameVal) {
      if (formError) {
        formError.textContent = 'Please select a company from the search suggestions or enter a valid ticker symbol.';
        formError.hidden = false;
      }
      return;
    }

    // 4. Empty form
    if (formError) {
      formError.textContent = 'Please enter a company name or ticker symbol.';
      formError.hidden = false;
    }
  }

  form.addEventListener('submit', handleFormSubmit);

  document.querySelectorAll('.search-chip').forEach(function (chip) {
    chip.addEventListener('click', function () {
      var company = chip.getAttribute('data-company');
      var ticker = chip.getAttribute('data-ticker');
      if (nameInput) nameInput.value = company;
      if (tickerInput) tickerInput.value = ticker;
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

  // Support query parameters (e.g. ?q=AAPL)
  var urlParams = new URLSearchParams(window.location.search);
  var queryParam = urlParams.get('q') || urlParams.get('ticker') || urlParams.get('query') || urlParams.get('search');
  if (queryParam) {
    var q = queryParam.trim();
    if (/^[A-Za-z0-9.]{1,6}$/.test(q)) {
      if (nameInput) nameInput.value = q.toUpperCase();
      if (tickerInput) tickerInput.value = q.toUpperCase();
      search(q.toUpperCase(), q.toUpperCase());
    } else {
      if (nameInput) nameInput.value = q;
    }
  }
})();
