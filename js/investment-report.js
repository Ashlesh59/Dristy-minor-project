/* ==========================================================================
   INVESTMENT-REPORT.JS
   --------------------------------------------------------------------------
   Behavior for investment-report.html.
   - Loads research record & authoritative Security from Neon Postgres.
   - Enforces strict zero-credit verified market data display:
     * OHLC, Prev Close, VWAP, Volume, 30-Day Avg Volume, SMA20, SMA50,
       Annualized Volatility, 52-Week Range, Period Returns (1M, 3M, 6M, 1Y).
   - Renders interactive historical SVG price chart with exclusive states:
     * setChartState("idle" | "loading" | "data" | "empty" | "error")
     * Dynamic theme (green for gains, red for losses, neutral for flat).
     * Interactive tooltip with OHLCV data.
   - Renders structured AI Investment Decision Summary:
     * Research View, Suggested Action, Confidence Level, "Why This View?",
       Key Risks, Change Drivers, and Checklist.
   - Generates AI analysis ONLY on explicit user click, and reuses saved DB
     records with zero external API calls on subsequent views or prints.
   ========================================================================== */

(function () {
  'use strict';

  var marketHelper = window.MarketDataState || {
    escapeHtml: function (s) { return String(s || ''); },
    formatDecimal: function (v, d) {
      if (v === null || v === undefined || v === '') return '—';
      var num = typeof v === 'number' ? v : parseFloat(String(v));
      return isNaN(num) ? '—' : num.toLocaleString('en-IN', { minimumFractionDigits: d !== undefined ? d : 2, maximumFractionDigits: d !== undefined ? d : 2 });
    },
    formatCurrency: function (v, c) {
      var curr = (c || 'INR').toUpperCase();
      var sym = curr === 'INR' ? '₹' : (curr === 'USD' ? '$' : curr + ' ');
      if (v === null || v === undefined || v === '') return '—';
      var num = typeof v === 'number' ? v : parseFloat(String(v));
      if (isNaN(num)) return '—';
      return sym + num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    },
    formatDailyChange: function (c, cp) {
      if (c === null || c === undefined || c === '') {
        return { text: '—', isPositive: false, isNegative: false, isZero: true };
      }
      var num = typeof c === 'number' ? c : parseFloat(String(c));
      if (isNaN(num)) return { text: '—', isPositive: false, isNegative: false, isZero: true };
      var isPos = num > 0;
      var isNeg = num < 0;
      var sign = isPos ? '+' : (isNeg ? '-' : '');
      var absFormatted = Math.abs(num).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      var pctFormatted = cp ? (' (' + (isPos ? '+' : (isNeg ? '-' : '')) + Math.abs(parseFloat(String(cp))).toFixed(2) + '%)') : '';
      return {
        text: sign + '₹' + absFormatted + pctFormatted,
        isPositive: isPos,
        isNegative: isNeg,
        isZero: num === 0
      };
    },
    calculateSvgCoordinates: function (prices, w, h, pad) {
      if (!prices || !prices.length) return { isEmpty: true, points: [] };
      return window.MarketDataState.calculateSvgCoordinates(prices, w, h, pad);
    },
    formatPriceModeLabel: function (mode, meta) {
      if (mode === 'split_adjusted' && meta && meta.is_adjusted) {
        return { label: 'Split/Bonus Adjusted', badgeText: 'Split & Bonus Adjusted', disclaimer: 'Adjusted for splits and bonus issues.' };
      }
      return { label: 'Raw Unadjusted', badgeText: 'Official NSE Closing Prices', disclaimer: 'Unadjusted nominal exchange closing prices.' };
    },
    format52WeekRange: function (l, h, c) {
      if (!l || !h) return '—';
      return (c === 'INR' ? '₹' : '') + l + ' – ' + (c === 'INR' ? '₹' : '') + h;
    },
    formatReturn: function (ret) {
      if (ret === null || ret === undefined || ret === '') return { text: '—', isPositive: false, isNegative: false, isZero: true };
      var num = typeof ret === 'number' ? ret : parseFloat(String(ret));
      if (isNaN(num)) return { text: '—', isPositive: false, isNegative: false, isZero: true };
      var isPos = num > 0;
      var isNeg = num < 0;
      var sign = isPos ? '+' : (isNeg ? '-' : '');
      return {
        text: sign + Math.abs(num).toFixed(2) + '%',
        isPositive: isPos,
        isNegative: isNeg,
        isZero: num === 0,
        raw: num
      };
    }
  };

  var API_BASE_URL = window.INVESTIQ_API_BASE || '';
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
    companyExchange: document.getElementById('reportCompanyExchange'),
    companySeries: document.getElementById('reportCompanySeries'),
    companyIsin: document.getElementById('reportCompanyIsin'),
    aiStatusBadge: document.getElementById('reportAiStatusBadge'),
    tradingDate: document.getElementById('reportTradingDate'),
    marketSession: document.getElementById('reportMarketSession'),
    historicalCoverage: document.getElementById('reportHistoricalCoverage'),
    timestamp: document.getElementById('reportTimestamp'),
    recommendationBadge: document.getElementById('reportRecommendationBadge'),
    content: document.getElementById('reportContent'),

    // Numerical Market Metrics
    marketPerformancePanel: document.getElementById('reportMarketPerformance'),
    marketDataAvailable: document.getElementById('reportMarketDataAvailable'),
    marketDataEmptyNotice: document.getElementById('reportMarketDataEmptyNotice'),
    badgeSource: document.getElementById('reportBadgeSource'),
    badgeImported: document.getElementById('reportBadgeImported'),
    latestClose: document.getElementById('reportLatestClose'),
    dayChange: document.getElementById('reportDayChange'),
    prevClose: document.getElementById('reportPrevClose'),
    dayRange: document.getElementById('reportDayRange'),
    currency: document.getElementById('reportCurrency'),
    dayOpen: document.getElementById('reportDayOpen'),
    dayHigh: document.getElementById('reportDayHigh'),
    dayLow: document.getElementById('reportDayLow'),
    vwap: document.getElementById('reportVwap'),
    volume: document.getElementById('reportVolume'),
    avgVolume30: document.getElementById('reportAvgVolume30'),
    sma20: document.getElementById('reportSma20'),
    sma50: document.getElementById('reportSma50'),
    volatility: document.getElementById('reportVolatility'),
    week52Range: document.getElementById('report52WeekRange'),
    return1M: document.getElementById('reportReturn1M'),
    return3M: document.getElementById('reportReturn3M'),
    return6M: document.getElementById('reportReturn6M'),
    return1Y: document.getElementById('reportReturn1Y'),

    // AI Executive Summary
    companyOverview: document.getElementById('reportCompanyOverview'),
    investmentSummary: document.getElementById('reportInvestmentSummary'),
    aiScore: document.getElementById('reportAiScore'),
    aiRecommendation: document.getElementById('reportAiRecommendation'),
    coverageQuality: document.getElementById('reportCoverageQuality'),

    // Signals & News
    financialAssessment: document.getElementById('reportFinancialAssessment'),
    positiveSignalsList: document.getElementById('reportPositiveSignalsList'),
    newsSection: document.getElementById('reportNewsSection'),
    newsSentiment: document.getElementById('reportNewsSentiment'),
    keyRisks: document.getElementById('reportKeyRisks'),
    keyOpportunities: document.getElementById('reportKeyOpportunities'),

    // Investment Decision Summary (Section 17)
    decisionSummaryCard: document.getElementById('reportDecisionSummaryCard'),
    researchViewBadge: document.getElementById('reportResearchViewBadge'),
    confidenceBadge: document.getElementById('reportConfidenceBadge'),
    suggestedAction: document.getElementById('reportSuggestedAction'),
    whyThisViewList: document.getElementById('reportWhyThisViewList'),
    keyRisksList: document.getElementById('reportKeyRisksList'),
    whatCouldChange: document.getElementById('reportWhatCouldChange'),
    checkNextList: document.getElementById('reportCheckNextList'),

    // SVG Historical Price Chart (Section 8 & 9)
    chartContainer: document.getElementById('reportChartContainer'),
    chartLoading: document.getElementById('reportChartLoading'),
    chartEmpty: document.getElementById('reportChartEmpty'),
    chartEmptyMessage: document.getElementById('reportChartEmptyMessage'),
    chartError: document.getElementById('reportChartError'),
    chartErrorMessage: document.getElementById('reportChartErrorMessage'),
    chartRetryBtn: document.getElementById('reportChartRetryBtn'),
    priceHistorySvg: document.getElementById('reportPriceHistorySvg'),
    svgGridlines: document.getElementById('reportSvgGridlines'),
    svgAxes: document.getElementById('reportSvgAxes'),
    svgAreaPath: document.getElementById('reportSvgAreaPath'),
    svgLinePath: document.getElementById('reportSvgLinePath'),
    svgCrosshair: document.getElementById('reportSvgCrosshair'),
    svgPoints: document.getElementById('reportSvgPoints'),
    chartTooltip: document.getElementById('reportChartTooltip'),
    chartAccessibleSummary: document.getElementById('reportChartAccessibleSummary'),
    chartSubtitle: document.getElementById('reportChartSubtitle'),
    chartDisclaimerText: document.getElementById('reportChartDisclaimerText'),
    chartPeriodReturn: document.getElementById('reportChartPeriodReturn'),
    chartPeriodLow: document.getElementById('reportChartPeriodLow'),
    chartPeriodHigh: document.getElementById('reportChartPeriodHigh'),
    chartPlottedCount: document.getElementById('reportChartPlottedCount'),
    rangeButtons: document.querySelectorAll('.range-btn'),
    priceModeButtons: document.querySelectorAll('.mode-btn'),

    // Actions
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
  var cachedHistoryPrices = [];

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function formatIST(isoStr) {
    if (!isoStr) return '—';
    try {
      var d = new Date(isoStr);
      if (isNaN(d.getTime())) return isoStr;
      return d.toLocaleString('en-IN', {
        timeZone: 'Asia/Kolkata',
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: true
      }) + ' IST';
    } catch (e) {
      return isoStr;
    }
  }

  function formatDateOnly(isoDateStr) {
    if (!isoDateStr) return '—';
    try {
      var parts = isoDateStr.split('T')[0].split('-');
      if (parts.length === 3) {
        var d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
        return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
      }
      return isoDateStr;
    } catch (e) {
      return isoDateStr;
    }
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

  // =========================================================================
  // 1. EXCLUSIVE CHART STATES (Section 9)
  // setChartState("idle" | "loading" | "data" | "empty" | "error")
  // Exactly ONE state is visible at any time.
  // =========================================================================
  function setChartState(state, message) {
    // Hide all states first
    if (els.chartLoading) els.chartLoading.hidden = true;
    if (els.chartEmpty) els.chartEmpty.hidden = true;
    if (els.chartError) els.chartError.hidden = true;
    if (els.chartContainer) els.chartContainer.hidden = true;

    if (state === 'loading') {
      if (els.chartLoading) els.chartLoading.hidden = false;
    } else if (state === 'data') {
      if (els.chartContainer) els.chartContainer.hidden = false;
    } else if (state === 'empty') {
      if (els.chartEmpty) {
        els.chartEmpty.hidden = false;
        if (els.chartEmptyMessage && message) {
          els.chartEmptyMessage.textContent = message;
        }
      }
    } else if (state === 'error') {
      if (els.chartError) {
        els.chartError.hidden = false;
        if (els.chartErrorMessage && message) {
          els.chartErrorMessage.textContent = message;
        }
      }
    }
    // "idle" leaves all states hidden
  }

  // =========================================================================
  // 2. CORE NUMERICAL MARKET PERFORMANCE (Section 6)
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

    // Freshness & Identity
    if (els.tradingDate) {
      els.tradingDate.textContent = formatDateOnly(md.trading_date);
    }
    if (els.marketSession) {
      els.marketSession.textContent = 'NSE End-of-Day';
    }

    var cov = md.coverage || {};
    if (els.historicalCoverage) {
      if (cov.start_date && cov.end_date) {
        els.historicalCoverage.textContent = formatDateOnly(cov.start_date) + ' to ' + formatDateOnly(cov.end_date) +
          ' (' + (cov.total_sessions || 0) + ' sessions)';
      } else {
        els.historicalCoverage.textContent = 'Verified EOD Dataset';
      }
    }

    if (els.badgeSource) {
      els.badgeSource.textContent = 'Source: ' + (md.source || 'NSE CM-UDiFF');
    }

    // Latest Price & Day Movement
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

    if (els.prevClose) els.prevClose.textContent = md.previous_close ? marketHelper.formatCurrency(md.previous_close, currency) : '—';
    if (els.dayRange) {
      if (md.low && md.high) {
        els.dayRange.textContent = marketHelper.formatCurrency(md.low, currency) + ' – ' + marketHelper.formatCurrency(md.high, currency);
      } else {
        els.dayRange.textContent = '—';
      }
    }
    if (els.currency) els.currency.textContent = currency + ' (' + (currency === 'INR' ? '₹' : currency) + ')';

    // Numerical Metrics
    if (els.dayOpen) els.dayOpen.textContent = md.open ? marketHelper.formatCurrency(md.open, currency) : '—';
    if (els.dayHigh) els.dayHigh.textContent = md.high ? marketHelper.formatCurrency(md.high, currency) : '—';
    if (els.dayLow) els.dayLow.textContent = md.low ? marketHelper.formatCurrency(md.low, currency) : '—';
    if (els.vwap) els.vwap.textContent = md.vwap ? marketHelper.formatCurrency(md.vwap, currency) : '—';
    if (els.volume) els.volume.textContent = md.volume !== null && md.volume !== undefined ? Number(md.volume).toLocaleString('en-IN') : '—';
    if (els.avgVolume30) els.avgVolume30.textContent = md.average_volume_30 ? Number(md.average_volume_30).toLocaleString('en-IN') : '—';
    if (els.sma20) els.sma20.textContent = md.sma_20 ? marketHelper.formatCurrency(md.sma_20, currency) : '—';
    if (els.sma50) els.sma50.textContent = md.sma_50 ? marketHelper.formatCurrency(md.sma_50, currency) : '—';
    if (els.volatility) els.volatility.textContent = md.volatility || '—';
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

  // =========================================================================
  // 3. ACCURATE SVG CHART & TOOLTIP (Section 8)
  // =========================================================================
  function renderSvgChart(historyData) {
    if (!els.priceHistorySvg) return;

    var prices = (historyData && historyData.prices) || [];
    cachedHistoryPrices = prices;
    var currency = (currentSecurityMeta && currentSecurityMeta.currency) || 'INR';

    // Clear previous SVG paths and text
    if (els.svgGridlines) els.svgGridlines.innerHTML = '';
    if (els.svgAxes) els.svgAxes.innerHTML = '';
    if (els.svgPoints) els.svgPoints.innerHTML = '';
    if (els.svgCrosshair) els.svgCrosshair.innerHTML = '';
    if (els.svgAreaPath) els.svgAreaPath.setAttribute('d', '');
    if (els.svgLinePath) els.svgLinePath.setAttribute('d', '');

    if (prices.length === 0) {
      setChartState('empty', 'No verified NSE price records found for range ' + activeRange.toUpperCase() + '.');
      if (els.chartAccessibleSummary) {
        els.chartAccessibleSummary.textContent = 'No historical data points available.';
      }
      return;
    }

    setChartState('data');

    var width = 640;
    var height = 280;
    var pad = { top: 25, right: 35, bottom: 35, left: 65 };

    var coords = marketHelper.calculateSvgCoordinates(prices, width, height, pad);

    // Period Return & Color Theme
    var firstPrice = prices[0].close;
    var lastPrice = prices[prices.length - 1].close;
    var numFirst = typeof firstPrice === 'number' ? firstPrice : parseFloat(String(firstPrice || 0));
    var numLast = typeof lastPrice === 'number' ? lastPrice : parseFloat(String(lastPrice || 0));
    var periodReturnPct = (numFirst > 0) ? ((numLast - numFirst) / numFirst * 100) : 0;
    var isPositive = periodReturnPct > 0;
    var isNegative = periodReturnPct < 0;

    if (els.chartPeriodReturn) {
      var retSign = isPositive ? '+' : (isNegative ? '-' : '');
      els.chartPeriodReturn.textContent = retSign + Math.abs(periodReturnPct).toFixed(2) + '%';
      els.chartPeriodReturn.className = isPositive ? 'return-item__value--pos' : (isNegative ? 'return-item__value--neg' : 'return-item__value--neutral');
    }

    // Apply color theme to paths
    var strokeColor = isPositive ? '#16a34a' : (isNegative ? '#dc2626' : '#2563eb');
    var gradientId = isPositive ? '#reportChartGradientPos' : (isNegative ? '#reportChartGradientNeg' : '#reportChartGradient');

    if (els.svgLinePath) {
      els.svgLinePath.setAttribute('d', coords.pathD);
      els.svgLinePath.style.stroke = strokeColor;
    }
    if (els.svgAreaPath) {
      els.svgAreaPath.setAttribute('d', coords.areaPathD);
      els.svgAreaPath.setAttribute('fill', 'url(' + gradientId + ')');
    }

    // Gridlines and Y-axis
    var plotHeight = height - pad.top - pad.bottom;
    var yLevels = [
      { y: pad.top, price: coords.maxPrice },
      { y: pad.top + plotHeight * 0.25, price: coords.minPrice + (coords.maxPrice - coords.minPrice) * 0.75 },
      { y: pad.top + plotHeight * 0.5, price: coords.minPrice + (coords.maxPrice - coords.minPrice) * 0.5 },
      { y: pad.top + plotHeight * 0.75, price: coords.minPrice + (coords.maxPrice - coords.minPrice) * 0.25 },
      { y: pad.top + plotHeight, price: coords.minPrice }
    ];

    var gridHtml = '';
    var axesHtml = '';

    yLevels.forEach(function (lvl) {
      gridHtml += '<line class="chart-gridline" x1="' + pad.left + '" y1="' + lvl.y.toFixed(2) + '" x2="' + (width - pad.right) + '" y2="' + lvl.y.toFixed(2) + '" />';
      axesHtml += '<text class="chart-axis-text" x="' + (pad.left - 8) + '" y="' + (lvl.y + 4).toFixed(2) + '" text-anchor="end">' +
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

    // Interactive Hover & Data Points
    var pointsHtml = '';
    var renderAllDots = coords.points.length <= 40 || coords.isSingle;

    coords.points.forEach(function (pt, pIdx) {
      var isEdge = pIdx === 0 || pIdx === coords.points.length - 1;
      if (renderAllDots || isEdge) {
        pointsHtml += '<circle class="chart-dot" data-idx="' + pIdx + '" cx="' + pt.x + '" cy="' + pt.y + '" r="' + (coords.isSingle ? '6' : '3.5') + '" style="stroke:' + strokeColor + ';" />';
      }
    });
    if (els.svgPoints) els.svgPoints.innerHTML = pointsHtml;

    // Markers & Metadata
    if (els.chartPeriodLow) els.chartPeriodLow.textContent = marketHelper.formatCurrency(coords.minPrice, currency);
    if (els.chartPeriodHigh) els.chartPeriodHigh.textContent = marketHelper.formatCurrency(coords.maxPrice, currency);
    if (els.chartPlottedCount) els.chartPlottedCount.textContent = prices.length + ' sessions';

    var modeInfo = marketHelper.formatPriceModeLabel(activePriceMode, historyData.metadata);
    if (els.chartSubtitle) {
      els.chartSubtitle.textContent = modeInfo.badgeText;
    }
    if (els.chartDisclaimerText) {
      els.chartDisclaimerText.innerHTML = '<strong>' + marketHelper.escapeHtml(modeInfo.badgeText) + ':</strong> ' +
        marketHelper.escapeHtml(modeInfo.disclaimer);
    }

    if (els.chartAccessibleSummary) {
      var sym = currentSecurityMeta ? currentSecurityMeta.symbol : 'equity';
      els.chartAccessibleSummary.textContent = 'Price history for ' + sym + ' (' + activeRange.toUpperCase() + '): ' +
        prices.length + ' sessions plotted. Period low ₹' + coords.minPrice.toFixed(2) + ', period high ₹' + coords.maxPrice.toFixed(2) +
        ', net change ' + periodReturnPct.toFixed(2) + '%.';
    }

    // Attach Tooltip Hover Interaction
    setupChartTooltip(coords.points, currency);
  }

  function setupChartTooltip(points, currency) {
    if (!els.priceHistorySvg || !els.chartTooltip) return;

    var svgRect = null;

    function handleMouseMove(e) {
      if (!points || !points.length) return;
      svgRect = els.priceHistorySvg.getBoundingClientRect();
      var mouseX = e.clientX - svgRect.left;
      var svgX = (mouseX / svgRect.width) * 640;

      // Find closest point by X coordinate
      var closest = points[0];
      var minDiff = Math.abs(svgX - closest.x);
      for (var i = 1; i < points.length; i++) {
        var diff = Math.abs(svgX - points[i].x);
        if (diff < minDiff) {
          minDiff = diff;
          closest = points[i];
        }
      }

      if (closest && closest.raw) {
        var r = closest.raw;
        var tooltipHtml = '<strong>' + escapeHtml(r.date) + ' (NSE EOD)</strong><br/>' +
          'Close: ' + marketHelper.formatCurrency(r.close, currency) + '<br/>' +
          'Open: ' + marketHelper.formatCurrency(r.open, currency) + '<br/>' +
          'High: ' + marketHelper.formatCurrency(r.high, currency) + ' | Low: ' + marketHelper.formatCurrency(r.low, currency) + '<br/>' +
          'Volume: ' + (r.volume ? Number(r.volume).toLocaleString('en-IN') : '—');

        els.chartTooltip.innerHTML = tooltipHtml;
        els.chartTooltip.style.display = 'block';
        var pointScreenX = (closest.x / 640) * svgRect.width;
        var pointScreenY = (closest.y / 280) * svgRect.height;
        els.chartTooltip.style.left = pointScreenX + 'px';
        els.chartTooltip.style.top = pointScreenY + 'px';
      }
    }

    function handleMouseLeave() {
      if (els.chartTooltip) els.chartTooltip.style.display = 'none';
    }

    els.priceHistorySvg.onmousemove = handleMouseMove;
    els.priceHistorySvg.onmouseleave = handleMouseLeave;
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

    setChartState('loading');

    var modeParam = priceMode || activePriceMode || 'raw';
    var url = '/api/securities/' + encodeURIComponent(securityId) +
      '/market-data/history?range=' + encodeURIComponent(rangeKey) +
      '&price_mode=' + encodeURIComponent(modeParam);

    fetchJson(url, {
      method: 'GET',
      signal: historyAbortController ? historyAbortController.signal : undefined
    })
      .then(function (result) {
        if (thisSeq !== historyRequestSeq) return; // Discard stale responses

        if (!result.ok || !result.data || !result.data.success) {
          setChartState('empty', 'No verified NSE price records found for range ' + rangeKey.toUpperCase() + '.');
          return;
        }

        renderSvgChart(result.data);
      })
      .catch(function (err) {
        if (err && err.name === 'AbortError') return;
        if (thisSeq !== historyRequestSeq) return;
        setChartState('error', 'Unable to retrieve historical market records.');
      });
  }

  function loadMarketPerformance(securityId) {
    if (!securityId) {
      if (els.marketDataAvailable) els.marketDataAvailable.hidden = true;
      if (els.marketDataEmptyNotice) els.marketDataEmptyNotice.hidden = false;
      return;
    }

    currentSecurityId = securityId;

    // Fetch Latest Market Summary
    fetchJson('/api/securities/' + encodeURIComponent(securityId) + '/market-data/summary', { method: 'GET' })
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

    // Fetch Historical Time-Series
    loadPriceHistory(securityId, activeRange, activePriceMode);
  }

  // =========================================================================
  // 4. INVESTMENT DECISION SUMMARY & REPORT RENDERING (Section 17)
  // =========================================================================
  function renderDecisionSummary(reportObj, record) {
    var dec = (reportObj && reportObj.decision_summary) || {};
    var rView = dec.research_view || (reportObj.recommendation === 'Buy' ? 'Positive' : (reportObj.recommendation === 'Sell' ? 'Cautious' : 'Neutral'));
    var sAction = dec.suggested_action || (rView === 'Positive' ? 'Consider for further research' : 'Add to watchlist');
    var cLevel = dec.confidence_level || 'Medium';

    // View Badge
    if (els.researchViewBadge) {
      els.researchViewBadge.textContent = rView;
      var vClass = 'decision-view-badge--' + (
        rView === 'Positive' ? 'positive' :
        (rView === 'Cautious' ? 'cautious' :
         (rView === 'Insufficient Data' ? 'insufficient' : 'neutral'))
      );
      els.researchViewBadge.className = 'decision-view-badge ' + vClass;
    }

    // Confidence Badge
    if (els.confidenceBadge) {
      els.confidenceBadge.textContent = cLevel + ' Confidence';
      var cClass = 'confidence-badge--' + (cLevel === 'High' ? 'high' : (cLevel === 'Low' ? 'low' : 'medium'));
      els.confidenceBadge.className = 'confidence-badge ' + cClass;
    }

    // Suggested Action
    if (els.suggestedAction) {
      els.suggestedAction.textContent = sAction;
    }

    // "Why This View?" Reasons
    if (els.whyThisViewList) {
      els.whyThisViewList.innerHTML = '';
      var reasons = dec.why_this_view || [];
      if (!reasons.length) {
        reasons = [
          'Evaluated from official NSE EOD closing series.',
          'Assigned ' + (reportObj.recommendation || 'Neutral') + ' research posture.'
        ];
      }
      reasons.forEach(function (r) {
        var li = document.createElement('li');
        li.textContent = r;
        els.whyThisViewList.appendChild(li);
      });
    }

    // Key Risks List
    if (els.keyRisksList) {
      els.keyRisksList.innerHTML = '';
      var risks = dec.key_risks_list || reportObj.key_risks_list || [];
      if (!risks.length) {
        risks = [
          'Market-wide volatility and macroeconomic headwinds.',
          'Verified fundamental balance sheet figures pending quarterly import.'
        ];
      }
      risks.forEach(function (r) {
        var li = document.createElement('li');
        li.textContent = r;
        els.keyRisksList.appendChild(li);
      });
    }

    // What Could Change
    if (els.whatCouldChange) {
      els.whatCouldChange.textContent = dec.what_could_change_view ||
        'A sustained breakout above 50-session moving averages on elevated volume or release of audited quarterly earnings statements would update this assessment.';
    }

    // Checklist
    if (els.checkNextList) {
      els.checkNextList.innerHTML = '';
      var checklist = dec.check_next_checklist || [
        'Review upcoming quarterly audited financial statements',
        'Verify trading volume relative to 30-session average',
        'Compare performance with sector peers',
        'Check corporate action updates on NSE'
      ];
      checklist.forEach(function (item) {
        var li = document.createElement('li');
        li.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> ' +
          escapeHtml(item);
        els.checkNextList.appendChild(li);
      });
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
    if (els.companyName) els.companyName.textContent = record.company_name;
    if (els.companyTicker) els.companyTicker.textContent = record.ticker_symbol;
    if (els.companyExchange) els.companyExchange.textContent = 'NSE';
    if (els.companySeries) els.companySeries.textContent = 'Series: EQ';

    if (els.timestamp) {
      els.timestamp.textContent = formatIST(reportObj.generated_at || record.created_at);
    }

    var rec = reportObj.recommendation || record.recommendation || 'Hold';
    if (els.recommendationBadge) {
      els.recommendationBadge.textContent = rec;
      els.recommendationBadge.className = 'badge report-header__recommendation ' +
        (rec === 'Buy' ? 'badge--low' : (rec === 'Sell' ? 'badge--high' : 'badge--medium'));
    }

    if (els.companyOverview) els.companyOverview.textContent = reportObj.company_overview || '';
    if (els.investmentSummary) els.investmentSummary.textContent = reportObj.investment_summary || '';
    if (els.aiScore) {
      var scoreVal = (typeof reportObj.ai_score === 'number') ? reportObj.ai_score : record.ai_score;
      els.aiScore.textContent = (typeof scoreVal === 'number') ? (scoreVal + ' / 100') : '—';
    }
    if (els.aiRecommendation) els.aiRecommendation.textContent = rec;

    if (els.financialAssessment) els.financialAssessment.textContent = reportObj.financial_assessment || '';

    // Positive Signals List
    if (els.positiveSignalsList) {
      els.positiveSignalsList.innerHTML = '';
      var posSignals = reportObj.positive_signals || [];
      if (!posSignals.length) {
        posSignals = [
          'Listed on NSE equity segment with verified daily market activity.',
          'Official EOD price series archived and validated in database.'
        ];
      }
      posSignals.forEach(function (s) {
        var li = document.createElement('li');
        li.textContent = s;
        els.positiveSignalsList.appendChild(li);
      });
    }

    // News Sentiment
    if (els.newsSentiment) {
      els.newsSentiment.textContent = reportObj.news_sentiment || 'Verified news sentiment neutral/pending live feed.';
    }

    // Key Risks & Opportunities
    if (els.keyRisks) els.keyRisks.textContent = reportObj.key_risks || 'Market volatility and unverified fundamental earnings data.';
    if (els.keyOpportunities) els.keyOpportunities.textContent = reportObj.key_opportunities || 'Domestic sector expansion and sustained market liquidity.';

    // Decision Summary Section
    renderDecisionSummary(reportObj, record);

    // Load Core Market Performance & Chart
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
        showError('Unable to connect to the server. Please check your network connection.');
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
        showError('Unable to connect to the server. Please check your network connection.');
      });
  }

  function bindActions() {
    if (els.generateBtn) {
      els.generateBtn.addEventListener('click', generateReport);
    }
    if (els.chartRetryBtn) {
      els.chartRetryBtn.addEventListener('click', function () {
        if (currentSecurityId) {
          loadPriceHistory(currentSecurityId, activeRange, activePriceMode);
        }
      });
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

    // Chart Range Selector Buttons (Zero External Calls)
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

    // Chart Price Mode Buttons (Zero External Calls)
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
