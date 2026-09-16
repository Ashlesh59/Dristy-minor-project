/* ==========================================================================
   COMPANY-RESEARCH.JS
   --------------------------------------------------------------------------
   Behavior for company-research.html (Phase 2B).
   - Local database-backed company & security search (zero external API calls).
   - WAI-ARIA 1.2 Combobox accessible autocomplete with full keyboard support.
   - End-of-Day Market Data retrieval and freshness metadata.
   - Responsive native SVG closing-price time series chart.
   - Time-range selector (1M, 3M, 6M, 1Y, 3Y, 5Y, MAX) with cancellation.
   - Honest empty, single-point, and unadjusted-price disclaimer states.
   ========================================================================== */

(function () {
  'use strict';

  var autoHelper = window.InvestIQAutocompleteState || {
    normalizeSearchQuery: function (s) { return (s || '').trim(); },
    createSelection: function (item) { return item; },
    clearSelection: function () { return null; },
    handleInputChange: function () { return null; },
    navigateActiveOption: function (idx, count, dir) { return dir > 0 ? 0 : -1; },
    isStaleResponse: function (seq, latest) { return seq !== latest; },
    validateSubmission: function (id) { return typeof id === 'number' && id > 0; }
  };

  var marketHelper = window.MarketDataState || {
    escapeHtml: function (s) { return String(s || ''); },
    formatDecimal: function (v) { return v !== null && v !== undefined ? String(v) : '—'; },
    formatCurrency: function (v, c) { return (c || 'INR') + ' ' + (v || '—'); },
    formatDailyChange: function (c, cp) { return { text: '—', isPositive: false, isNegative: false, isZero: true }; },
    calculateSvgCoordinates: function () { return { isEmpty: true, points: [] }; }
  };

  var API_BASE_URL = window.INVESTIQ_API_BASE || 'http://127.0.0.1:5000';

  // DOM Elements
  var form = document.getElementById('companySearchForm');
  if (!form) return;

  var nameInput = document.getElementById('companyNameInput');
  var formError = document.getElementById('searchFormError');
  var submitBtn = document.getElementById('companySearchSubmitBtn') || form.querySelector('button[type="submit"]');
  var autocompleteDropdown = document.getElementById('companySearchResults');

  var loadingEl = document.getElementById('researchLoading');
  var errorEl = document.getElementById('researchError');
  var resultsEl = document.getElementById('researchResults');

  // Overview elements
  var ovLogo = document.getElementById('ovLogo');
  var ovName = document.getElementById('ovName');
  var ovTicker = document.getElementById('ovTicker');
  var ovPrice = document.getElementById('ovPrice');
  var ovChange = document.getElementById('ovChange');
  var ovTradingDay = document.getElementById('ovTradingDay');
  var ovPrevClose = document.getElementById('ovPrevClose');
  var ovOpen = document.getElementById('ovOpen');
  var ovHigh = document.getElementById('ovHigh');
  var ovLow = document.getElementById('ovLow');
  var ovVolume = document.getElementById('ovVolume');
  var ovTurnover = document.getElementById('ovTurnover');
  var ovExchangeSeries = document.getElementById('ovExchangeSeries');
  var marketDataNotice = document.getElementById('marketDataNotice');
  var marketDataNoticeText = document.getElementById('marketDataNoticeText');
  var badgeSource = document.getElementById('badgeSource');

  // Chart elements
  var chartContainer = document.getElementById('chartContainer');
  var chartLoading = document.getElementById('chartLoading');
  var chartEmpty = document.getElementById('chartEmpty');
  var chartEmptyMessage = document.getElementById('chartEmptyMessage');
  var priceHistorySvg = document.getElementById('priceHistorySvg');
  var svgGridlines = document.getElementById('svgGridlines');
  var svgAxes = document.getElementById('svgAxes');
  var svgAreaPath = document.getElementById('svgAreaPath');
  var svgLinePath = document.getElementById('svgLinePath');
  var svgPoints = document.getElementById('svgPoints');
  var chartAccessibleSummary = document.getElementById('chartAccessibleSummary');
  var chartTableBody = document.getElementById('chartTableBody');
  var rangeButtons = document.querySelectorAll('.range-btn');
  var priceModeButtons = document.querySelectorAll('.mode-btn');
  var chartAdjustmentDisclaimer = document.getElementById('chartAdjustmentDisclaimer');
  var chartDisclaimerText = document.getElementById('chartDisclaimerText');
  var chartSubtitle = document.getElementById('chartSubtitle');

  // State variables
  var currentSelection = null;
  var currentSecurityId = null;
  var currentSecurityMeta = null;
  var activeRange = '1y';
  var activePriceMode = 'raw';
  var currentResults = [];
  var activeOptionIndex = -1;
  var debounceTimer = null;
  var autocompleteAbortController = null;
  var autocompleteSeq = 0;
  var historyAbortController = null;
  var historyRequestSeq = 0;


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
      errorEl.textContent = '';
      errorEl.hidden = true;
    }
    if (formError) {
      formError.textContent = '';
      formError.hidden = true;
    }
  }

  function showFormError(message) {
    if (formError) {
      formError.textContent = message;
      formError.hidden = false;
    }
  }

  function updateAriaAttributes(expanded, activeId) {
    if (!nameInput) return;
    nameInput.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    if (activeId) {
      nameInput.setAttribute('aria-activedescendant', activeId);
    } else {
      nameInput.removeAttribute('aria-activedescendant');
    }
  }

  function hideDropdown() {
    if (autocompleteDropdown) {
      autocompleteDropdown.hidden = true;
      autocompleteDropdown.innerHTML = '';
    }
    activeOptionIndex = -1;
    currentResults = [];
    updateAriaAttributes(false, null);
  }

  function selectItem(item) {
    if (!item) return;
    currentSelection = autoHelper.createSelection(item);
    if (nameInput) {
      nameInput.value = (item.company_name || item.symbol) + ' (' + item.symbol + ')';
    }
    hideDropdown();
    clearError();
  }

  function renderDropdown(items) {
    if (!autocompleteDropdown) return;
    autocompleteDropdown.innerHTML = '';
    currentResults = items || [];
    activeOptionIndex = -1;

    if (!items || !items.length) {
      var emptyEl = document.createElement('div');
      emptyEl.className = 'ticker-autocomplete-item ticker-autocomplete-item--empty';
      emptyEl.textContent = 'No matching companies found in local database.';
      emptyEl.style.padding = '10px 14px';
      emptyEl.style.color = 'var(--color-text-secondary, #64748b)';
      emptyEl.style.fontSize = 'var(--fs-sm, 0.875rem)';
      autocompleteDropdown.appendChild(emptyEl);
      autocompleteDropdown.hidden = false;
      updateAriaAttributes(true, null);
      return;
    }

    items.forEach(function (item, idx) {
      var opt = document.createElement('div');
      opt.className = 'ticker-autocomplete-item';
      opt.setAttribute('role', 'option');
      opt.setAttribute('id', 'comp-opt-' + item.security_id);
      opt.setAttribute('aria-selected', 'false');

      var info = document.createElement('div');
      info.className = 'ticker-autocomplete-item__info';

      var nameSpan = document.createElement('span');
      nameSpan.className = 'ticker-autocomplete-item__name';
      nameSpan.textContent = item.company_name;

      var metaSpan = document.createElement('span');
      metaSpan.className = 'ticker-autocomplete-item__region';
      metaSpan.textContent = (item.exchange || 'NSE') + ' • ' + (item.series || 'EQ') + (item.isin ? ' • ' + item.isin : '') + ' • ' + (item.currency || 'INR');

      info.appendChild(nameSpan);
      info.appendChild(metaSpan);

      var symSpan = document.createElement('span');
      symSpan.className = 'ticker-autocomplete-item__symbol';
      symSpan.textContent = item.symbol;

      opt.appendChild(info);
      opt.appendChild(symSpan);

      opt.addEventListener('click', function () {
        selectItem(item);
      });

      opt.addEventListener('mouseenter', function () {
        setActiveOption(idx);
      });

      autocompleteDropdown.appendChild(opt);
    });

    autocompleteDropdown.hidden = false;
    updateAriaAttributes(true, null);
  }

  function setActiveOption(index) {
    if (!autocompleteDropdown || !currentResults.length) return;
    var options = autocompleteDropdown.querySelectorAll('[role="option"]');
    options.forEach(function (el, i) {
      if (i === index) {
        el.classList.add('is-active');
        el.setAttribute('aria-selected', 'true');
        el.scrollIntoView({ block: 'nearest' });
        updateAriaAttributes(true, el.id);
      } else {
        el.classList.remove('is-active');
        el.setAttribute('aria-selected', 'false');
      }
    });
    activeOptionIndex = index;
  }

  function initAutocomplete() {
    if (!nameInput || !autocompleteDropdown) return;

    function doSearch() {
      var query = autoHelper.normalizeSearchQuery(nameInput.value);
      if (query.length < 2 && !(query.length === 1 && /^[a-zA-Z0-9]$/.test(query))) {
        hideDropdown();
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

      fetchJson('/api/companies/search?q=' + encodeURIComponent(query), {
        method: 'GET',
        signal: autocompleteAbortController ? autocompleteAbortController.signal : undefined
      })
        .then(function (result) {
          if (autoHelper.isStaleResponse(thisSeq, autocompleteSeq)) return;

          if (result.status === 401) {
            showFormError('Please log in to search the company database.');
            hideDropdown();
            return;
          }

          if (!result.ok || !result.data || !result.data.success) {
            renderDropdown([]);
            return;
          }

          renderDropdown(result.data.results || []);
        })
        .catch(function (err) {
          if (err && err.name === 'AbortError') return;
          if (autoHelper.isStaleResponse(thisSeq, autocompleteSeq)) return;
          showFormError('Backend service unavailable. Please ensure the server is running.');
          hideDropdown();
        });
    }

    nameInput.addEventListener('input', function () {
      clearError();
      currentSelection = autoHelper.handleInputChange(currentSelection, nameInput.value);
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(doSearch, 250);
    });

    nameInput.addEventListener('keydown', function (e) {
      if (autocompleteDropdown.hidden || !currentResults.length) {
        if (e.key === 'ArrowDown' && nameInput.value.trim().length >= 2) {
          doSearch();
        }
        return;
      }

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        var nextIdx = autoHelper.navigateActiveOption(activeOptionIndex, currentResults.length, 1);
        setActiveOption(nextIdx);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        var prevIdx = autoHelper.navigateActiveOption(activeOptionIndex, currentResults.length, -1);
        setActiveOption(prevIdx);
      } else if (e.key === 'Enter') {
        if (activeOptionIndex >= 0 && activeOptionIndex < currentResults.length) {
          e.preventDefault();
          selectItem(currentResults[activeOptionIndex]);
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        hideDropdown();
      } else if (e.key === 'Tab') {
        hideDropdown();
      }
    });

    document.addEventListener('click', function (e) {
      if (!autocompleteDropdown.contains(e.target) && e.target !== nameInput) {
        hideDropdown();
      }
    });
  }

  // =========================================================================
  // MARKET DATA & CHART RENDERING
  // =========================================================================

  function renderLatestMarketData(data) {
    var sec = data.security || {};
    var md = data.market_data;
    var freshness = data.freshness || {};
    var currency = sec.currency || 'INR';

    currentSecurityMeta = sec;

    // Header identity
    if (ovName) ovName.textContent = sec.company_name || '';
    if (ovTicker) ovTicker.textContent = (sec.symbol || '') + ' • ' + (sec.exchange || 'NSE') + ' (' + (sec.series || 'EQ') + ')';
    if (ovLogo) {
      var nameStr = sec.company_name || sec.symbol || 'IQ';
      ovLogo.textContent = nameStr.slice(0, 2).toUpperCase();
    }
    if (ovExchangeSeries) {
      ovExchangeSeries.textContent = (sec.exchange || 'NSE') + ' / ' + (sec.series || 'EQ') + ' (' + currency + ')';
    }

    if (badgeSource && md && md.source) {
      badgeSource.textContent = md.source;
    }

    if (!md) {
      // Empty Market Data State
      if (ovPrice) ovPrice.textContent = 'No price data';
      if (ovChange) {
        ovChange.textContent = '—';
        ovChange.className = 'price-highlight__change price-highlight__change--neutral';
      }
      if (ovTradingDay) ovTradingDay.textContent = '—';
      if (ovPrevClose) ovPrevClose.textContent = '—';
      if (ovOpen) ovOpen.textContent = '—';
      if (ovHigh) ovHigh.textContent = '—';
      if (ovLow) ovLow.textContent = '—';
      if (ovVolume) ovVolume.textContent = '—';
      if (ovTurnover) ovTurnover.textContent = '—';

      if (marketDataNotice && marketDataNoticeText) {
        marketDataNoticeText.textContent = data.message || 'No imported market data records exist for this security.';
        marketDataNotice.hidden = false;
      }
      return;
    }

    // Populate Price Metrics
    if (ovPrice) {
      ovPrice.textContent = marketHelper.formatCurrency(md.close, currency);
    }

    var changeObj = marketHelper.formatDailyChange(md.change, md.change_percent);
    if (ovChange) {
      ovChange.textContent = changeObj.text;
      ovChange.className = 'price-highlight__change ' +
        (changeObj.isPositive ? 'price-highlight__change--pos' : (changeObj.isNegative ? 'price-highlight__change--neg' : 'price-highlight__change--neutral'));
    }

    if (ovTradingDay) ovTradingDay.textContent = md.trading_date || '—';
    if (ovPrevClose) ovPrevClose.textContent = md.previous_close ? marketHelper.formatCurrency(md.previous_close, currency) : '—';
    if (ovOpen) ovOpen.textContent = md.open ? marketHelper.formatCurrency(md.open, currency) : '—';
    if (ovHigh) ovHigh.textContent = md.high ? marketHelper.formatCurrency(md.high, currency) : '—';
    if (ovLow) ovLow.textContent = md.low ? marketHelper.formatCurrency(md.low, currency) : '—';
    if (ovVolume) ovVolume.textContent = md.volume !== null && md.volume !== undefined ? marketHelper.formatDecimal(md.volume, 0) : '—';
    if (ovTurnover) ovTurnover.textContent = md.turnover ? marketHelper.formatCurrency(md.turnover, currency) : '—';

    if (marketDataNotice) {
      marketDataNotice.hidden = false;
    }
  }

  function renderSvgChart(historyData) {
    if (!priceHistorySvg) return;

    var prices = historyData.prices || [];
    var currency = (currentSecurityMeta && currentSecurityMeta.currency) || 'INR';

    // Clear previous SVG contents
    if (svgGridlines) svgGridlines.innerHTML = '';
    if (svgAxes) svgAxes.innerHTML = '';
    if (svgPoints) svgPoints.innerHTML = '';
    if (svgAreaPath) svgAreaPath.setAttribute('d', '');
    if (svgLinePath) svgLinePath.setAttribute('d', '');
    if (chartTableBody) chartTableBody.innerHTML = '';

    if (prices.length === 0) {
      if (chartContainer) chartContainer.hidden = true;
      if (chartEmpty) {
        chartEmpty.hidden = false;
        if (chartEmptyMessage) chartEmptyMessage.textContent = 'No price history available for range ' + activeRange.toUpperCase() + '.';
      }
      if (chartAccessibleSummary) chartAccessibleSummary.textContent = 'No historical data points available.';
      return;
    }

    if (chartEmpty) chartEmpty.hidden = true;
    if (chartContainer) chartContainer.hidden = false;

    var width = 600;
    var height = 260;
    var pad = { top: 25, right: 35, bottom: 35, left: 60 };

    var coords = marketHelper.calculateSvgCoordinates(prices, width, height, pad);

    // Build gridlines and price labels on Y-axis
    var plotHeight = height - pad.top - pad.bottom;
    var plotWidth = width - pad.left - pad.right;

    var yLevels = [
      { y: pad.top, price: coords.maxPrice },
      { y: pad.top + plotHeight / 2, price: (coords.minPrice + coords.maxPrice) / 2 },
      { y: pad.top + plotHeight, price: coords.minPrice }
    ];

    var gridHtml = '';
    var axesHtml = '';

    yLevels.forEach(function (lvl) {
      gridHtml += '<line class="chart-gridline" x1="' + pad.left + '" y1="' + lvl.y + '" x2="' + (width - pad.right) + '" y2="' + lvl.y + '" />';
      axesHtml += '<text class="chart-axis-text" x="' + (pad.left - 8) + '" y="' + (lvl.y + 4) + '" text-anchor="end">' +
        marketHelper.escapeHtml(marketHelper.formatDecimal(lvl.price, 2)) + '</text>';
    });

    // Date labels on X-axis (Start date and End date)
    if (coords.minDate && coords.maxDate) {
      axesHtml += '<text class="chart-axis-text" x="' + pad.left + '" y="' + (height - 10) + '" text-anchor="start">' +
        marketHelper.escapeHtml(coords.minDate) + '</text>';
      if (coords.minDate !== coords.maxDate) {
        axesHtml += '<text class="chart-axis-text" x="' + (width - pad.right) + '" y="' + (height - 10) + '" text-anchor="end">' +
          marketHelper.escapeHtml(coords.maxDate) + '</text>';
      }
    }

    if (svgGridlines) svgGridlines.innerHTML = gridHtml;
    if (svgAxes) svgAxes.innerHTML = axesHtml;

    // Line and Area Paths
    if (svgLinePath) svgLinePath.setAttribute('d', coords.pathD);
    if (svgAreaPath) svgAreaPath.setAttribute('d', coords.areaPathD);

    // Render interactive data dots
    var pointsHtml = '';
    // If dense dataset (>60 points), only render dots on single, start, end, or min/max
    var renderAllDots = coords.points.length <= 40 || coords.isSingle;
    coords.points.forEach(function (pt, pIdx) {
      var isEdge = pIdx === 0 || pIdx === coords.points.length - 1;
      if (renderAllDots || isEdge) {
        var dotTitle = pt.date + ': ' + marketHelper.formatCurrency(pt.close, currency);
        pointsHtml += '<circle class="chart-dot" cx="' + pt.x + '" cy="' + pt.y + '" r="' + (coords.isSingle ? '6' : '3.5') + '">' +
          '<title>' + marketHelper.escapeHtml(dotTitle) + '</title>' +
          '</circle>';
      }
    });
    if (svgPoints) svgPoints.innerHTML = pointsHtml;

    // Accessible Text Summary & Disclaimer Update
    var modeInfo = marketHelper.formatPriceModeLabel(activePriceMode, historyData.metadata);
    if (chartSubtitle) {
      chartSubtitle.textContent = modeInfo.badgeText;
    }
    if (chartDisclaimerText) {
      if (modeInfo.isAdjusted) {
        chartDisclaimerText.innerHTML = '<strong>' + marketHelper.escapeHtml(modeInfo.badgeText) + ':</strong> ' +
          marketHelper.escapeHtml(modeInfo.disclaimer) + ' <em>(' + marketHelper.escapeHtml(modeInfo.actionCountText) + ')</em>';
      } else {
        chartDisclaimerText.innerHTML = '<strong>' + marketHelper.escapeHtml(modeInfo.badgeText) + ':</strong> ' +
          marketHelper.escapeHtml(modeInfo.disclaimer);
      }
    }

    if (chartAccessibleSummary) {
      var summaryText = 'Price history for ' + (currentSecurityMeta ? currentSecurityMeta.symbol : 'security') +
        ' (' + activeRange.toUpperCase() + ' - ' + modeInfo.label + '): ' + prices.length + ' trading days plotted. ' +
        'Low: ' + marketHelper.formatCurrency(coords.minPrice, currency) + ', High: ' + marketHelper.formatCurrency(coords.maxPrice, currency) +
        (historyData.range && historyData.range.truncated ? ' [Data truncated to maximum limit]' : '');
      chartAccessibleSummary.textContent = summaryText;
    }

    // Populate Data Table
    if (chartTableBody) {
      var tableHtml = '';
      prices.forEach(function (p) {
        tableHtml += '<tr>' +
          '<td>' + marketHelper.escapeHtml(p.date) + '</td>' +
          '<td>' + marketHelper.escapeHtml(marketHelper.formatDecimal(p.open, 2)) + '</td>' +
          '<td>' + marketHelper.escapeHtml(marketHelper.formatDecimal(p.high, 2)) + '</td>' +
          '<td>' + marketHelper.escapeHtml(marketHelper.formatDecimal(p.low, 2)) + '</td>' +
          '<td><strong>' + marketHelper.escapeHtml(marketHelper.formatDecimal(p.close, 2)) + '</strong></td>' +
          '<td>' + marketHelper.escapeHtml(marketHelper.formatDecimal(p.volume, 0)) + '</td>' +
          '</tr>';
      });
      chartTableBody.innerHTML = tableHtml;
    }
  }

  function loadSecurityMarketData(securityId) {
    currentSecurityId = securityId;
    if (resultsEl) resultsEl.hidden = false;

    // 1. Fetch Latest Market Data
    fetchJson('/api/securities/' + encodeURIComponent(securityId) + '/market-data/latest', {
      method: 'GET'
    })
      .then(function (result) {
        if (result.status === 401) {
          showError('Your session has expired. Please log in again.');
          return;
        }
        if (!result.ok || !result.data || !result.data.success) {
          var msg = (result.data && result.data.message) || 'Could not load latest market data.';
          showError(msg);
          return;
        }
        renderLatestMarketData(result.data);
      })
      .catch(function () {
        showError('Network error loading latest market data.');
      });

    // 2. Fetch Historical Price Data
    loadPriceHistory(securityId, activeRange, activePriceMode);
  }

  function loadPriceHistory(securityId, rangeKey, priceMode) {
    if (!securityId) return;

    if (historyAbortController) {
      historyAbortController.abort();
    }
    if (window.AbortController) {
      historyAbortController = new AbortController();
    }

    historyRequestSeq++;
    var thisReqSeq = historyRequestSeq;

    if (chartLoading) chartLoading.hidden = false;
    if (chartEmpty) chartEmpty.hidden = true;

    var modeParam = priceMode || activePriceMode || 'raw';
    var url = '/api/securities/' + encodeURIComponent(securityId) +
      '/market-data/history?range=' + encodeURIComponent(rangeKey) +
      '&price_mode=' + encodeURIComponent(modeParam);

    fetchJson(url, {
      method: 'GET',
      signal: historyAbortController ? historyAbortController.signal : undefined
    })
      .then(function (result) {
        if (thisReqSeq !== historyRequestSeq) return; // Ignore stale responses
        if (chartLoading) chartLoading.hidden = true;

        if (result.status === 401) {
          showError('Your session has expired. Please log in again.');
          return;
        }

        if (!result.ok || !result.data || !result.data.success) {
          if (chartEmpty) {
            chartEmpty.hidden = false;
            if (chartEmptyMessage) chartEmptyMessage.textContent = (result.data && result.data.message) || 'Failed to load price history.';
          }
          return;
        }

        renderSvgChart(result.data);
      })
      .catch(function (err) {
        if (err && err.name === 'AbortError') return;
        if (thisReqSeq !== historyRequestSeq) return;
        if (chartLoading) chartLoading.hidden = true;
        if (chartEmpty) {
          chartEmpty.hidden = false;
          if (chartEmptyMessage) chartEmptyMessage.textContent = 'Backend service unavailable while fetching price history.';
        }
      });
  }

  function initRangeControls() {
    rangeButtons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var range = btn.getAttribute('data-range');
        if (!range || range === activeRange) return;

        activeRange = range;
        rangeButtons.forEach(function (b) {
          var isCurrent = b === btn;
          b.classList.toggle('is-active', isCurrent);
          b.setAttribute('aria-pressed', isCurrent ? 'true' : 'false');
        });

        if (currentSecurityId) {
          loadPriceHistory(currentSecurityId, activeRange, activePriceMode);
        }
      });
    });
  }

  function initPriceModeControls() {
    priceModeButtons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var mode = btn.getAttribute('data-mode');
        if (!mode || mode === activePriceMode) return;

        activePriceMode = mode;
        priceModeButtons.forEach(function (b) {
          var isCurrent = b === btn;
          b.classList.toggle('is-active', isCurrent);
          b.setAttribute('aria-pressed', isCurrent ? 'true' : 'false');
        });

        if (currentSecurityId) {
          loadPriceHistory(currentSecurityId, activeRange, activePriceMode);
        }
      });
    });
  }

  function handleFormSubmit(e) {
    e.preventDefault();
    clearError();

    if (!currentSelection || !autoHelper.validateSubmission(currentSelection.security_id)) {
      showFormError('Please select a verified company from the suggestions list.');
      return;
    }

    showLoading(true);
    if (submitBtn) submitBtn.disabled = true;
    hideDropdown();

    fetchJson('/api/research', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        security_id: currentSelection.security_id,
        research_type: 'general'
      })
    })
      .then(function (result) {
        showLoading(false);
        if (submitBtn) submitBtn.disabled = false;

        if (result.status === 401) {
          showError('Your session has expired. Please log in again.');
          return;
        }

        if (!result.ok || !result.data || !result.data.success) {
          var msg = (result.data && result.data.message) || 'Failed to create research record.';
          showError(msg);
          return;
        }

        var research = result.data.research || {};
        var secId = research.security_id || currentSelection.security_id;

        // Load stored market data using the verified security_id
        loadSecurityMarketData(secId);
      })
      .catch(function () {
        showLoading(false);
        if (submitBtn) submitBtn.disabled = false;
        showError('Backend unavailable. Please ensure the backend server is running.');
      });
  }

  function initPopularChips() {
    var chips = document.querySelectorAll('.search-chip');
    chips.forEach(function (chip) {
      chip.addEventListener('click', function (e) {
        e.preventDefault();
        var ticker = chip.getAttribute('data-ticker') || chip.getAttribute('data-company');
        if (!ticker) return;

        if (nameInput) {
          nameInput.value = ticker;
          nameInput.focus();
        }

        clearError();
        showLoading(true);

        fetchJson('/api/companies/search?q=' + encodeURIComponent(ticker), { method: 'GET' })
          .then(function (result) {
            showLoading(false);
            if (result.ok && result.data && result.data.results && result.data.results.length > 0) {
              var topMatch = result.data.results[0];
              selectItem(topMatch);
              // Trigger research creation
              handleFormSubmit(new Event('submit'));
            } else {
              showError('Could not find verified security for ' + ticker + '.');
            }
          })
          .catch(function () {
            showLoading(false);
            showError('Unable to connect to search service.');
          });
      });
    });
  }

  form.addEventListener('submit', handleFormSubmit);
  initAutocomplete();
  initRangeControls();
  initPriceModeControls();
  initPopularChips();

  // URL query parameter deep-linking support
  var urlParams = new URLSearchParams(window.location.search);
  var qParam = urlParams.get('q');
  if (qParam && nameInput) {
    nameInput.value = qParam;
    nameInput.focus();
  }
})();

