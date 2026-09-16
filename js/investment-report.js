/* ==========================================================================
   INVESTMENT-REPORT.JS
   --------------------------------------------------------------------------
   Behavior for investment-report.html.
   - Reads `research_id` from the URL, loads the research record.
   - Renders verified End-of-Day Market Performance panel and SVG price chart
     from stored DailyPrice records in Neon Postgres.
   - Renders persisted AI investment report or offers one-click report generation.
   - Isolates chart range/mode switches from Gemini report generation.
   ========================================================================== */

(function () {
  'use strict';

  var marketHelper = window.MarketDataState || {
    escapeHtml: function (s) { return String(s || ''); },
    formatDecimal: function (v) { return v !== null && v !== undefined ? String(v) : '—'; },
    formatCurrency: function (v, c) { return (c || 'INR') + ' ' + (v || '—'); },
    formatDailyChange: function (c, cp) { return { text: '—', isPositive: false, isNegative: false, isZero: true }; },
    calculateSvgCoordinates: function () { return { isEmpty: true, points: [] }; },
    formatPriceModeLabel: function () { return { label: 'Raw Unadjusted', badgeText: 'Unadjusted Prices', disclaimer: '' }; },
    format52WeekRange: function () { return '—'; },
    formatReturn: function () { return { text: '—', isPositive: false, isNegative: false, isZero: true }; }
  };

  var API_BASE_URL = window.INVESTIQ_API_BASE || 'http://127.0.0.1:5000';
  var params = new URLSearchParams(window.location.search);
  var researchId = params.get('research_id');

  var els = {
    noResearchNotice: document.getElementById('reportNoResearchNotice'),
    generateNotice: document.getElementById('reportGenerateNotice'),
    generateBtn: document.getElementById('generateReportBtn'),
    errorNotice: document.getElementById('reportErrorNotice'),
    headerPanel: document.getElementById('reportHeaderPanel'),
    companyLogo: document.getElementById('reportCompanyLogo'),
    companyName: document.getElementById('reportCompanyName'),
    companyTicker: document.getElementById('reportCompanyTicker'),
    timestamp: document.getElementById('reportTimestamp'),
    recommendationBadge: document.getElementById('reportRecommendationBadge'),
    content: document.getElementById('reportContent'),

    // Market Performance Elements
    marketPerformancePanel: document.getElementById('reportMarketPerformance'),
    marketDataAvailable: document.getElementById('reportMarketDataAvailable'),
    marketDataEmptyNotice: document.getElementById('reportMarketDataEmptyNotice'),
    badgeEod: document.getElementById('reportBadgeEod'),
    badgeDate: document.getElementById('reportBadgeDate'),
    badgeSource: document.getElementById('reportBadgeSource'),
    latestClose: document.getElementById('reportLatestClose'),
    dayChange: document.getElementById('reportDayChange'),
    dayHigh: document.getElementById('reportDayHigh'),
    dayLow: document.getElementById('reportDayLow'),
    prevClose: document.getElementById('reportPrevClose'),
    volume: document.getElementById('reportVolume'),
    vwap: document.getElementById('reportVwap'),
    week52Range: document.getElementById('report52WeekRange'),
    return1M: document.getElementById('reportReturn1M'),
    return3M: document.getElementById('reportReturn3M'),
    return6M: document.getElementById('reportReturn6M'),
    return1Y: document.getElementById('reportReturn1Y'),

    // SVG Chart Elements
    chartContainer: document.getElementById('reportChartContainer'),
    chartLoading: document.getElementById('reportChartLoading'),
    chartEmpty: document.getElementById('reportChartEmpty'),
    chartEmptyMessage: document.getElementById('reportChartEmptyMessage'),
    priceHistorySvg: document.getElementById('reportPriceHistorySvg'),
    svgGridlines: document.getElementById('reportSvgGridlines'),
    svgAxes: document.getElementById('reportSvgAxes'),
    svgAreaPath: document.getElementById('reportSvgAreaPath'),
    svgLinePath: document.getElementById('reportSvgLinePath'),
    svgPoints: document.getElementById('reportSvgPoints'),
    chartAccessibleSummary: document.getElementById('reportChartAccessibleSummary'),
    chartSubtitle: document.getElementById('reportChartSubtitle'),
    chartDisclaimerText: document.getElementById('reportChartDisclaimerText'),
    rangeButtons: document.querySelectorAll('#reportMarketPerformance .range-btn'),
    priceModeButtons: document.querySelectorAll('#reportMarketPerformance .mode-btn'),

    // Report body elements
    companyOverview: document.getElementById('reportCompanyOverview'),
    investmentSummary: document.getElementById('reportInvestmentSummary'),
    aiScore: document.getElementById('reportAiScore'),
    aiRecommendation: document.getElementById('reportAiRecommendation'),
    financialCards: document.getElementById('reportFinancialCards'),
    financialAssessment: document.getElementById('reportFinancialAssessment'),
    newsSentiment: document.getElementById('reportNewsSentiment'),
    keyRisks: document.getElementById('reportKeyRisks'),
    keyOpportunities: document.getElementById('reportKeyOpportunities'),
    outlook: document.getElementById('reportOutlook'),
    conclusion: document.getElementById('reportConclusion'),
    printBtn: document.getElementById('printReportBtn'),
    shareBtn: document.getElementById('shareReportBtn')
  };

  var currentRecord = null;
  var currentSecurityId = null;
  var currentSecurityMeta = null;
  var activeRange = '1y';
  var activePriceMode = 'raw';
  var historyAbortController = null;
  var historyRequestSeq = 0;

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
    if (!currency) return '₹';
    var c = String(currency).toUpperCase();
    if (c === 'INR') return '₹';
    if (c === 'USD') return '$';
    if (c === 'GBP') return '£';
    if (c === 'EUR') return '€';
    return c + ' ';
  }

  function formatPrice(val, currency) {
    if (val === null || val === undefined || val === '') return '—';
    return marketHelper.formatCurrency(val, currency);
  }

  function showError(message) {
    if (!els.errorNotice) return;
    els.errorNotice.textContent = message;
    els.errorNotice.hidden = false;
  }

  function clearError() {
    if (!els.errorNotice) return;
    els.errorNotice.textContent = '';
    els.errorNotice.hidden = true;
  }

  function fetchJson(url, options) {
    return fetch(API_BASE_URL + url, Object.assign({ credentials: 'include' }, options))
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, status: response.status, data: data };
        });
      });
  }

  function recommendationBadgeClass(rec) {
    if (rec === 'Buy') return 'badge--low';
    if (rec === 'Sell') return 'badge--high';
    return 'badge--medium';
  }

  // =========================================================================
  // MARKET PERFORMANCE & CHART RENDERING
  // =========================================================================

  function renderMarketSummary(summaryData, securityMeta) {
    currentSecurityMeta = securityMeta || (summaryData && summaryData.security) || null;
    var md = (summaryData && (summaryData.summary || summaryData.market_data)) || null;
    var currency = (currentSecurityMeta && currentSecurityMeta.currency) || 'INR';

    if (!md || !md.close) {
      if (els.marketDataAvailable) els.marketDataAvailable.hidden = true;
      if (els.marketDataEmptyNotice) els.marketDataEmptyNotice.hidden = false;
      return;
    }

    if (els.marketDataEmptyNotice) els.marketDataEmptyNotice.hidden = true;
    if (els.marketDataAvailable) els.marketDataAvailable.hidden = false;

    // Badges
    if (els.badgeDate) {
      els.badgeDate.textContent = 'Trading Date: ' + (md.trading_date || '—');
    }
    if (els.badgeSource) {
      els.badgeSource.textContent = md.source || 'NSE CM-UDiFF';
    }

    // Latest Close & Change
    if (els.latestClose) {
      els.latestClose.textContent = marketHelper.formatCurrency(md.close, currency);
    }
    if (els.dayChange) {
      var changeObj = marketHelper.formatDailyChange(md.change, md.change_percent);
      els.dayChange.textContent = changeObj.text;
      els.dayChange.className = 'price-highlight__change ' +
        (changeObj.isPositive ? 'price-highlight__change--pos' :
         changeObj.isNegative ? 'price-highlight__change--neg' : 'price-highlight__change--neutral');
    }

    // Metric Cards
    if (els.dayHigh) els.dayHigh.textContent = md.high ? marketHelper.formatCurrency(md.high, currency) : '—';
    if (els.dayLow) els.dayLow.textContent = md.low ? marketHelper.formatCurrency(md.low, currency) : '—';
    if (els.prevClose) els.prevClose.textContent = md.previous_close ? marketHelper.formatCurrency(md.previous_close, currency) : '—';
    if (els.volume) els.volume.textContent = md.volume !== null && md.volume !== undefined ? marketHelper.formatDecimal(md.volume, 0) : '—';
    if (els.vwap) els.vwap.textContent = md.vwap ? marketHelper.formatCurrency(md.vwap, currency) : '—';
    if (els.week52Range) els.week52Range.textContent = marketHelper.format52WeekRange(md.week_52_low, md.week_52_high, currency);

    // Period Returns
    var returns = md.returns || {};
    var r1m = marketHelper.formatReturn(returns.return_1m);
    var r3m = marketHelper.formatReturn(returns.return_3m);
    var r6m = marketHelper.formatReturn(returns.return_6m);
    var r1y = marketHelper.formatReturn(returns.return_1y);

    function applyReturnStyle(el, retObj) {
      if (!el) return;
      el.textContent = retObj.text;
      el.className = 'return-item__value ' +
        (retObj.isPositive ? 'return-item__value--pos' :
         retObj.isNegative ? 'return-item__value--neg' : 'return-item__value--neutral');
    }

    applyReturnStyle(els.return1M, r1m);
    applyReturnStyle(els.return3M, r3m);
    applyReturnStyle(els.return6M, r6m);
    applyReturnStyle(els.return1Y, r1y);
  }

  function renderSvgChart(historyData) {
    if (!els.priceHistorySvg) return;

    var prices = (historyData && historyData.prices) || [];
    var currency = (currentSecurityMeta && currentSecurityMeta.currency) || 'INR';

    // Clear previous SVG contents
    if (els.svgGridlines) els.svgGridlines.innerHTML = '';
    if (els.svgAxes) els.svgAxes.innerHTML = '';
    if (els.svgPoints) els.svgPoints.innerHTML = '';
    if (els.svgAreaPath) els.svgAreaPath.setAttribute('d', '');
    if (els.svgLinePath) els.svgLinePath.setAttribute('d', '');

    if (prices.length === 0) {
      if (els.chartContainer) els.chartContainer.hidden = true;
      if (els.chartEmpty) {
        els.chartEmpty.hidden = false;
        if (els.chartEmptyMessage) {
          els.chartEmptyMessage.textContent = 'No verified NSE price records found for range ' + activeRange.toUpperCase() + '.';
        }
      }
      if (els.chartAccessibleSummary) {
        els.chartAccessibleSummary.textContent = 'No historical data points available.';
      }
      return;
    }

    if (els.chartEmpty) els.chartEmpty.hidden = true;
    if (els.chartContainer) els.chartContainer.hidden = false;

    var width = 600;
    var height = 260;
    var pad = { top: 25, right: 35, bottom: 35, left: 60 };

    var coords = marketHelper.calculateSvgCoordinates(prices, width, height, pad);

    // Gridlines and Y-axis
    var plotHeight = height - pad.top - pad.bottom;
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

    // Date labels on X-axis
    if (coords.minDate && coords.maxDate) {
      axesHtml += '<text class="chart-axis-text" x="' + pad.left + '" y="' + (height - 10) + '" text-anchor="start">' +
        marketHelper.escapeHtml(coords.minDate) + '</text>';
      if (coords.minDate !== coords.maxDate) {
        axesHtml += '<text class="chart-axis-text" x="' + (width - pad.right) + '" y="' + (height - 10) + '" text-anchor="end">' +
          marketHelper.escapeHtml(coords.maxDate) + '</text>';
      }
    }

    if (els.svgGridlines) els.svgGridlines.innerHTML = gridHtml;
    if (els.svgAxes) els.svgAxes.innerHTML = axesHtml;

    // Line & Area Paths
    if (els.svgLinePath) els.svgLinePath.setAttribute('d', coords.pathD);
    if (els.svgAreaPath) els.svgAreaPath.setAttribute('d', coords.areaPathD);

    // Data dots
    var pointsHtml = '';
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
    if (els.svgPoints) els.svgPoints.innerHTML = pointsHtml;

    // Subtitle & Disclaimer
    var modeInfo = marketHelper.formatPriceModeLabel(activePriceMode, historyData.metadata);
    if (els.chartSubtitle) {
      els.chartSubtitle.textContent = modeInfo.badgeText;
    }
    if (els.chartDisclaimerText) {
      if (modeInfo.isAdjusted) {
        els.chartDisclaimerText.innerHTML = '<strong>' + marketHelper.escapeHtml(modeInfo.badgeText) + ':</strong> ' +
          marketHelper.escapeHtml(modeInfo.disclaimer) + ' <em>(' + marketHelper.escapeHtml(modeInfo.actionCountText) + ')</em>';
      } else {
        els.chartDisclaimerText.innerHTML = '<strong>' + marketHelper.escapeHtml(modeInfo.badgeText) + ':</strong> ' +
          marketHelper.escapeHtml(modeInfo.disclaimer);
      }
    }

    // Accessible text summary
    if (els.chartAccessibleSummary) {
      var summaryText = 'Price history for ' + (currentSecurityMeta ? currentSecurityMeta.symbol : 'security') +
        ' (' + activeRange.toUpperCase() + ' - ' + modeInfo.label + '): ' + prices.length + ' trading days plotted. ' +
        'Low: ' + marketHelper.formatCurrency(coords.minPrice, currency) + ', High: ' + marketHelper.formatCurrency(coords.maxPrice, currency);
      els.chartAccessibleSummary.textContent = summaryText;
    }
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
    var thisSeq = historyRequestSeq;

    if (els.chartLoading) els.chartLoading.hidden = false;
    if (els.chartEmpty) els.chartEmpty.hidden = true;

    var modeParam = priceMode || activePriceMode || 'raw';
    var url = '/api/securities/' + encodeURIComponent(securityId) +
      '/market-data/history?range=' + encodeURIComponent(rangeKey) +
      '&price_mode=' + encodeURIComponent(modeParam);

    fetchJson(url, {
      method: 'GET',
      signal: historyAbortController ? historyAbortController.signal : undefined
    })
      .then(function (result) {
        if (thisSeq !== historyRequestSeq) return; // Stale request prevention
        if (els.chartLoading) els.chartLoading.hidden = true;

        if (!result.ok || !result.data || !result.data.success) {
          if (els.chartEmpty) {
            els.chartEmpty.hidden = false;
            if (els.chartEmptyMessage) {
              els.chartEmptyMessage.textContent = 'No verified NSE price records found for range ' + rangeKey.toUpperCase() + '.';
            }
          }
          if (els.chartContainer) els.chartContainer.hidden = true;
          return;
        }

        renderSvgChart(result.data);
      })
      .catch(function (err) {
        if (err && err.name === 'AbortError') return;
        if (thisSeq !== historyRequestSeq) return;
        if (els.chartLoading) els.chartLoading.hidden = true;
        if (els.chartEmpty) {
          els.chartEmpty.hidden = false;
          if (els.chartEmptyMessage) {
            els.chartEmptyMessage.textContent = 'Unable to load price history.';
          }
        }
      });
  }

  function loadMarketPerformance(securityId) {
    if (!securityId) {
      if (els.marketDataAvailable) els.marketDataAvailable.hidden = true;
      if (els.marketDataEmptyNotice) els.marketDataEmptyNotice.hidden = false;
      return;
    }

    currentSecurityId = securityId;

    // 1. Fetch Latest Market Summary
    fetchJson('/api/securities/' + encodeURIComponent(securityId) + '/market-data/summary', {
      method: 'GET'
    })
      .then(function (result) {
        if (result.ok && result.data && result.data.success) {
          renderMarketSummary(result.data, result.data.security);
        } else {
          if (els.marketDataAvailable) els.marketDataAvailable.hidden = true;
          if (els.marketDataEmptyNotice) els.marketDataEmptyNotice.hidden = false;
        }
      })
      .catch(function () {
        if (els.marketDataAvailable) els.marketDataAvailable.hidden = true;
        if (els.marketDataEmptyNotice) els.marketDataEmptyNotice.hidden = false;
      });

    // 2. Fetch Historical Time-Series for Chart
    loadPriceHistory(securityId, activeRange, activePriceMode);
  }

  // =========================================================================
  // REPORT RENDERING & AI INTERACTION
  // =========================================================================

  function renderFinancialCards(financialData) {
    if (!els.financialCards) return;
    els.financialCards.innerHTML = '';
    if (!financialData) {
      els.financialCards.innerHTML = '<p class="field-hint">No financial highlights were available for this research.</p>';
      return;
    }

    var fin = financialData;
    if (typeof fin === 'string') {
      try { fin = JSON.parse(fin); } catch (e) { fin = null; }
    }
    if (!fin) {
      els.financialCards.innerHTML = '<p class="field-hint">No financial highlights were available for this research.</p>';
      return;
    }

    var curr = fin.currency || 'INR';
    var cards = [
      { label: 'Last Close (EOD)', value: fin.price ? formatPrice(fin.price, curr) : null },
      { label: 'Day Change', value: fin.change },
      { label: 'Day Change %', value: fin.change_percent },
      { label: 'Day High', value: fin.high ? formatPrice(fin.high, curr) : null },
      { label: 'Day Low', value: fin.low ? formatPrice(fin.low, curr) : null },
      { label: 'Volume', value: fin.volume ? Number(fin.volume).toLocaleString('en-IN') : null }
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
      els.financialCards.appendChild(card);
    });
    if (!els.financialCards.children.length) {
      els.financialCards.innerHTML = '<p class="field-hint">No financial highlights were available for this research.</p>';
    }
  }

  function renderReport(record, report) {
    if (!report) return;

    var reportObj = report;
    if (typeof reportObj === 'string') {
      try { reportObj = JSON.parse(reportObj); } catch (e) { reportObj = {}; }
    }

    if (els.generateNotice) els.generateNotice.hidden = true;
    if (els.errorNotice) els.errorNotice.hidden = true;
    if (els.noResearchNotice) els.noResearchNotice.hidden = true;
    if (els.headerPanel) els.headerPanel.hidden = false;
    if (els.content) els.content.hidden = false;

    var initials = escapeHtml((record.company_name || '?').trim().slice(0, 2).toUpperCase());
    if (els.companyLogo) els.companyLogo.textContent = initials;
    if (els.companyName) els.companyName.textContent = record.company_name + ' — Investment Report';
    if (els.companyTicker) els.companyTicker.textContent = record.ticker_symbol;

    if (els.timestamp) {
      els.timestamp.textContent = reportObj.generated_at
        ? new Date(reportObj.generated_at).toLocaleString()
        : new Date().toLocaleString();
    }

    var rec = reportObj.recommendation || record.recommendation || 'Not available';
    if (els.recommendationBadge) {
      els.recommendationBadge.textContent = rec;
      els.recommendationBadge.className = 'badge report-header__recommendation ' + recommendationBadgeClass(rec);
    }

    if (els.companyOverview) els.companyOverview.textContent = reportObj.company_overview || '';
    if (els.investmentSummary) els.investmentSummary.textContent = reportObj.investment_summary || '';
    if (els.aiScore) {
      var scoreVal = (typeof reportObj.ai_score === 'number') ? reportObj.ai_score : record.ai_score;
      els.aiScore.textContent = (typeof scoreVal === 'number') ? (scoreVal + ' / 100') : 'Not available';
    }
    if (els.aiRecommendation) els.aiRecommendation.textContent = rec;

    renderFinancialCards(record.financial_data);
    if (els.financialAssessment) els.financialAssessment.textContent = reportObj.financial_assessment || '';
    if (els.newsSentiment) els.newsSentiment.textContent = reportObj.news_sentiment || '';
    if (els.keyRisks) els.keyRisks.textContent = reportObj.key_risks || '';
    if (els.keyOpportunities) els.keyOpportunities.textContent = reportObj.key_opportunities || '';
    if (els.outlook) els.outlook.textContent = reportObj.overall_outlook || '';
    if (els.conclusion) els.conclusion.textContent = reportObj.conclusion || '';

    // Load Market Performance & Chart
    var secId = record.security_id || (record.security && record.security.id);
    loadMarketPerformance(secId);
  }

  function generateReport() {
    if (!researchId) return;
    clearError();
    if (els.generateBtn) {
      els.generateBtn.disabled = true;
      var lbl = els.generateBtn.querySelector('.btn-label');
      if (lbl) lbl.textContent = 'Generating Investment Report...';
    }

    fetchJson('/api/research/' + encodeURIComponent(researchId) + '/report', { method: 'POST' })
      .then(function (result) {
        if (els.generateBtn) {
          els.generateBtn.disabled = false;
          var lbl = els.generateBtn.querySelector('.btn-label');
          if (lbl) lbl.textContent = 'Generate Investment Report';
        }

        if (!result.ok) {
          showError(result.data.message || 'Could not generate a report for this research.');
          return;
        }

        if (els.generateNotice) els.generateNotice.hidden = true;

        if (result.data && result.data.report && currentRecord) {
          renderReport(currentRecord, result.data.report);
        } else {
          loadRecord();
        }
      })
      .catch(function () {
        if (els.generateBtn) {
          els.generateBtn.disabled = false;
          var lbl = els.generateBtn.querySelector('.btn-label');
          if (lbl) lbl.textContent = 'Generate Investment Report';
        }
        showError('Unable to connect to the server. Please make sure the backend is running.');
      });
  }

  function loadRecord() {
    clearError();
    fetchJson('/api/research/' + encodeURIComponent(researchId), { method: 'GET' })
      .then(function (result) {
        if (!result.ok) {
          showError(result.data.message || 'Could not load this research record.');
          return;
        }

        currentRecord = result.data.research;

        if (currentRecord.report_data) {
          renderReport(currentRecord, currentRecord.report_data);
        } else {
          if (els.headerPanel) els.headerPanel.hidden = true;
          if (els.content) els.content.hidden = true;
          if (els.generateNotice) els.generateNotice.hidden = false;
        }
      })
      .catch(function () {
        showError('Unable to connect to the server. Please make sure the backend is running.');
      });
  }

  function bindActions() {
    if (els.generateBtn) {
      els.generateBtn.addEventListener('click', generateReport);
    }
    if (els.printBtn) {
      els.printBtn.addEventListener('click', function () {
        window.print();
      });
    }
    if (els.shareBtn) {
      els.shareBtn.addEventListener('click', function () {
        var url = window.location.href;
        if (navigator.share) {
          navigator.share({ title: 'InvestIQ Investment Report', url: url }).catch(function () {});
        } else if (navigator.clipboard) {
          navigator.clipboard.writeText(url).then(function () {
            var label = els.shareBtn.querySelector('.btn-label');
            var original = label.textContent;
            label.textContent = 'Link Copied';
            setTimeout(function () { label.textContent = original; }, 1500);
          });
        }
      });
    }

    // Chart Range Selector Buttons (Independent of Gemini)
    if (els.rangeButtons) {
      els.rangeButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
          var selectedRange = btn.getAttribute('data-range');
          if (!selectedRange || selectedRange === activeRange) return;

          els.rangeButtons.forEach(function (b) {
            b.classList.remove('is-active');
            b.setAttribute('aria-pressed', 'false');
          });
          btn.classList.add('is-active');
          btn.setAttribute('aria-pressed', 'true');
          activeRange = selectedRange;

          if (currentSecurityId) {
            loadPriceHistory(currentSecurityId, activeRange, activePriceMode);
          }
        });
      });
    }

    // Chart Price Mode Buttons (Independent of Gemini)
    if (els.priceModeButtons) {
      els.priceModeButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
          var selectedMode = btn.getAttribute('data-mode');
          if (!selectedMode || selectedMode === activePriceMode) return;

          els.priceModeButtons.forEach(function (b) {
            b.classList.remove('is-active');
            b.setAttribute('aria-pressed', 'false');
          });
          btn.classList.add('is-active');
          btn.setAttribute('aria-pressed', 'true');
          activePriceMode = selectedMode;

          if (currentSecurityId) {
            loadPriceHistory(currentSecurityId, activeRange, activePriceMode);
          }
        });
      });
    }
  }

  function init() {
    bindActions();

    if (researchId) {
      loadRecord();
      return;
    }

    // If no research_id query param was given, fetch the user's latest research record
    fetchJson('/api/research', { method: 'GET' })
      .then(function (result) {
        if (result.ok && result.data.research && result.data.research.length > 0) {
          researchId = result.data.research[0].id;
          if (history.replaceState) {
            history.replaceState(null, '', 'investment-report.html?research_id=' + encodeURIComponent(researchId));
          }
          if (els.noResearchNotice) els.noResearchNotice.hidden = true;
          loadRecord();
        } else {
          if (els.noResearchNotice) els.noResearchNotice.hidden = false;
        }
      })
      .catch(function () {
        if (els.noResearchNotice) els.noResearchNotice.hidden = false;
      });
  }

  document.addEventListener('DOMContentLoaded', init);
})();
