/* ==========================================================================
   AI-ANALYSIS.JS
   --------------------------------------------------------------------------
   Behavior for ai-analysis.html.
   Loads verified research snapshot (GET /api/research/:id) and renders:
   1. Verified Market Data Card (with EOD stats & source badge)
   2. Verified Financial Statements Card (or clear unavailable notice)
   3. Verified News Articles Card (actual headlines with links/timestamps)
   4. AI Assessment & Decision Summary (strictly grounded in verified data)
   ========================================================================== */

window.INVESTIQ_BUILD_ID = 'VERIFIED_SNAPSHOT_V2';

(function () {
  'use strict';

  var API_BASE_URL = window.INVESTIQ_API_BASE || 'http://127.0.0.1:5000';

  var params = new URLSearchParams(window.location.search);
  var researchId = params.get('research_id');

  var els = {
    noResearchNotice: document.getElementById('aiNoResearchNotice'),
    errorNotice: document.getElementById('aiErrorNotice'),
    legacyWarning: document.getElementById('aiLegacyWarning'),
    regenerateBtn: document.getElementById('regenerateAnalysisBtn'),
    headerPanel: document.getElementById('aiHeaderPanel'),
    companyLogo: document.getElementById('aiCompanyLogo'),
    companyName: document.getElementById('aiCompanyName'),
    companyTicker: document.getElementById('aiCompanyTicker'),
    statusBadge: document.getElementById('aiStatusBadge'),
    headerScore: document.getElementById('aiHeaderScore'),
    runBtn: document.getElementById('runAnalysisBtn'),

    // Card 1: Market Data
    marketSection: document.getElementById('aiMarketSection'),
    marketSourceBadge: document.getElementById('aiMarketSourceBadge'),
    marketDate: document.getElementById('aiMarketDate'),
    financialCards: document.getElementById('aiFinancialCards'),
    marketAssessmentText: document.getElementById('aiMarketAssessmentText'),

    // Card 2: Financial Statements
    statementsSection: document.getElementById('aiStatementsSection'),
    statementsSourceBadge: document.getElementById('aiStatementsSourceBadge'),
    statementsPeriod: document.getElementById('aiStatementsPeriod'),
    statementsContainer: document.getElementById('aiStatementsContainer'),
    fundamentalAssessmentText: document.getElementById('aiFundamentalAssessmentText'),

    // Card 3: News
    newsSection: document.getElementById('aiNewsSection'),
    newsSourceBadge: document.getElementById('aiNewsSourceBadge'),
    newsCountBadge: document.getElementById('aiNewsCountBadge'),
    newsHeadlinesList: document.getElementById('aiNewsHeadlinesList'),
    newsSentimentText: document.getElementById('aiNewsSentimentText'),

    // Card 4: AI Decision Summary
    scoreSection: document.getElementById('aiScoreSection'),
    scoreArc: document.getElementById('aiScoreArc'),
    scoreNumber: document.getElementById('aiScoreNumber'),
    summaryText: document.getElementById('aiSummaryText'),
    recommendationBadge: document.getElementById('aiRecommendationBadge'),
    confidenceBadge: document.getElementById('aiConfidenceBadge'),
    actionBadge: document.getElementById('aiActionBadge'),

    missingInfoSection: document.getElementById('aiMissingInfoSection'),
    missingInfoList: document.getElementById('aiMissingInfoList'),
    risksSection: document.getElementById('aiRisksSection'),
    keyRisks: document.getElementById('aiKeyRisks'),
    keyRisksList: document.getElementById('aiKeyRisksList'),
    keyOpportunities: document.getElementById('aiKeyOpportunities'),
    positiveSignalsList: document.getElementById('aiPositiveSignalsList'),
    outlookSection: document.getElementById('aiOutlookSection'),
    outlookText: document.getElementById('aiOutlookText'),

    actionsSection: document.getElementById('aiActionsSection'),
    goToReportBtn: document.getElementById('goToReportBtn'),
    exportBtn: document.getElementById('exportAnalysisBtn')
  };

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
    if (val === null || val === undefined || val === '') return 'N/A';
    var num = parseFloat(String(val).replace(/,/g, ''));
    if (isNaN(num)) return String(val);
    var sym = getCurrencySymbol(currency);
    return sym + num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function showError(message) {
    if (!els.errorNotice) return;
    els.errorNotice.textContent = message;
    els.errorNotice.hidden = false;
  }

  function clearError() {
    if (!els.errorNotice) return;
    els.errorNotice.hidden = true;
    els.errorNotice.textContent = '';
  }

  function fetchJson(url, options) {
    return fetch(API_BASE_URL + url, Object.assign({ credentials: 'include' }, options))
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, status: response.status, data: data };
        });
      });
  }

  function renderMarketData(mkt, comp) {
    if (!els.marketSection) return;
    els.marketSection.hidden = false;

    var curr = (comp && comp.currency) || (mkt && mkt.currency) || 'INR';

    if (els.marketSourceBadge) {
      els.marketSourceBadge.textContent = (mkt && mkt.source) || 'NSE Bhavcopy';
    }
    if (els.marketDate) {
      els.marketDate.textContent = mkt && mkt.trading_date ? 'As of ' + mkt.trading_date : 'Exchange Archive';
    }

    if (!els.financialCards) return;
    els.financialCards.innerHTML = '';

    if (!mkt || mkt.close === null || mkt.close === undefined) {
      els.financialCards.innerHTML = '<p class="field-hint">No verified market price data found for this security.</p>';
      return;
    }

    var chgVal = mkt.change;
    var chgPct = mkt.change_percent;
    var chgFormatted = null;
    if (chgVal !== null && chgVal !== undefined) {
      var numChg = parseFloat(chgVal);
      var sign = numChg > 0 ? '+' : '';
      chgFormatted = sign + formatPrice(numChg, curr);
    }

    var chgPctFormatted = null;
    if (chgPct !== null && chgPct !== undefined) {
      var numPct = parseFloat(String(chgPct).replace('%', ''));
      var pSign = numPct > 0 ? '+' : '';
      chgPctFormatted = isNaN(numPct) ? String(chgPct) : (pSign + numPct.toFixed(2) + '%');
    }

    var volFormatted = null;
    if (mkt.volume !== null && mkt.volume !== undefined) {
      var numVol = Number(mkt.volume);
      volFormatted = !isNaN(numVol) ? numVol.toLocaleString('en-IN') : String(mkt.volume);
    }

    var vwapFormatted = mkt.vwap ? formatPrice(mkt.vwap, curr) : null;

    var cards = [
      { label: 'Last Close (EOD)', value: formatPrice(mkt.close, curr) },
      { label: 'Daily Change', value: chgFormatted },
      { label: 'Change %', value: chgPctFormatted },
      { label: 'VWAP', value: vwapFormatted },
      { label: 'Day High', value: mkt.high ? formatPrice(mkt.high, curr) : null },
      { label: 'Day Low', value: mkt.low ? formatPrice(mkt.low, curr) : null },
      { label: 'Day Open', value: mkt.open ? formatPrice(mkt.open, curr) : null },
      { label: 'Volume (Shares)', value: volFormatted },
      { label: '52-Week High', value: mkt.week_52_high ? formatPrice(mkt.week_52_high, curr) : null },
      { label: '52-Week Low', value: mkt.week_52_low ? formatPrice(mkt.week_52_low, curr) : null }
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
  }

  function renderFinancialStatements(stmts, ratios) {
    if (!els.statementsSection) return;
    els.statementsSection.hidden = false;

    if (els.statementsSourceBadge) {
      els.statementsSourceBadge.textContent = (stmts && stmts.source) || 'Exchange Filings';
    }
    if (els.statementsPeriod) {
      els.statementsPeriod.textContent = (stmts && stmts.reporting_period) ? 'Period: ' + stmts.reporting_period : 'Awaiting Filings';
    }

    if (!els.statementsContainer) return;
    els.statementsContainer.innerHTML = '';

    if (!stmts || !stmts.is_available) {
      els.statementsContainer.innerHTML =
        '<div style="background: rgba(30, 41, 59, 0.4); border: 1px solid var(--color-border); border-radius: 8px; padding: 14px 18px; color: var(--color-text-muted); display: flex; align-items: center; gap: 10px;">' +
        '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>' +
        '<span>Verified financial statements are not available for this company yet.</span>' +
        '</div>';
      return;
    }

    var table = document.createElement('table');
    table.className = 'table table--statements';
    table.style.width = '100%';
    table.innerHTML =
      '<thead><tr><th>Metric</th><th>Value</th><th>Reporting Period</th><th>Source</th></tr></thead>' +
      '<tbody>' +
      '<tr><td>Total Revenue</td><td><strong>' + escapeHtml(stmts.revenue || 'N/A') + '</strong></td><td>' + escapeHtml(stmts.reporting_period || '--') + '</td><td>' + escapeHtml(stmts.source || 'Filings') + '</td></tr>' +
      '<tr><td>Net Profit</td><td><strong>' + escapeHtml(stmts.net_profit || 'N/A') + '</strong></td><td>' + escapeHtml(stmts.reporting_period || '--') + '</td><td>' + escapeHtml(stmts.source || 'Filings') + '</td></tr>' +
      '<tr><td>Earnings Per Share (EPS)</td><td><strong>' + escapeHtml(stmts.eps || 'N/A') + '</strong></td><td>' + escapeHtml(stmts.reporting_period || '--') + '</td><td>' + escapeHtml(stmts.source || 'Filings') + '</td></tr>' +
      '<tr><td>Operating Cash Flow</td><td><strong>' + escapeHtml(stmts.operating_cash_flow || 'N/A') + '</strong></td><td>' + escapeHtml(stmts.reporting_period || '--') + '</td><td>' + escapeHtml(stmts.source || 'Filings') + '</td></tr>' +
      '</tbody>';
    els.statementsContainer.appendChild(table);
  }

  function renderNewsArticles(articles) {
    if (!els.newsSection) return;
    els.newsSection.hidden = false;

    if (els.newsCountBadge) {
      els.newsCountBadge.textContent = (articles && articles.length > 0) ? (articles.length + ' Verified Articles') : '0 Articles';
    }

    if (!els.newsHeadlinesList) return;
    els.newsHeadlinesList.innerHTML = '';

    if (!articles || articles.length === 0) {
      els.newsHeadlinesList.innerHTML =
        '<div style="background: rgba(30, 41, 59, 0.4); border: 1px solid var(--color-border); border-radius: 8px; padding: 14px 18px; color: var(--color-text-muted); display: flex; align-items: center; gap: 10px;">' +
        '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>' +
        '<span>No verified recent news was found. News sentiment was not calculated.</span>' +
        '</div>';
      return;
    }

    articles.forEach(function (a) {
      var item = document.createElement('div');
      item.style.background = 'rgba(15, 23, 42, 0.6)';
      item.style.border = '1px solid var(--color-border)';
      item.style.borderRadius = '8px';
      item.style.padding = '12px 16px';
      item.style.display = 'flex';
      item.style.justifyContent = 'space-between';
      item.style.alignItems = 'flex-start';
      item.style.gap = '12px';

      var mainCol = document.createElement('div');
      mainCol.style.flex = '1';

      var link = document.createElement('a');
      link.href = a.url || '#';
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = a.headline || a.title || 'Market Update';
      link.style.color = 'var(--color-primary-light, #818cf8)';
      link.style.fontWeight = '600';
      link.style.fontSize = '0.95rem';
      link.style.textDecoration = 'none';

      var meta = document.createElement('div');
      meta.style.fontSize = '0.8rem';
      meta.style.color = 'var(--color-text-muted)';
      meta.style.marginTop = '4px';
      meta.textContent = (a.source || 'Media') + (a.published_at ? ' • ' + a.published_at : '');

      mainCol.appendChild(link);
      mainCol.appendChild(meta);

      var sentBadge = document.createElement('span');
      var sent = a.sentiment || 'Neutral';
      sentBadge.className = 'badge ' + (sent.indexOf('Bull') >= 0 ? 'badge--low' : (sent.indexOf('Bear') >= 0 ? 'badge--high' : 'badge--medium'));
      sentBadge.textContent = sent;
      sentBadge.style.fontSize = '0.75rem';

      item.appendChild(mainCol);
      item.appendChild(sentBadge);
      els.newsHeadlinesList.appendChild(item);
    });
  }

  function renderAnalysis(analysis, snapshot) {
    if (!analysis) return;

    if (els.scoreSection) els.scoreSection.hidden = false;
    if (els.risksSection) els.risksSection.hidden = false;
    if (els.outlookSection) els.outlookSection.hidden = false;
    if (els.actionsSection) els.actionsSection.hidden = false;

    // AI Assessment texts on cards
    if (els.marketAssessmentText) {
      els.marketAssessmentText.textContent = analysis.market_assessment || analysis.summary || 'Market trajectory verified from exchange price records.';
    }
    if (els.fundamentalAssessmentText) {
      els.fundamentalAssessmentText.textContent = analysis.fundamental_assessment || analysis.financial_assessment || 'Verified financial statements are not available for this company yet.';
    }
    if (els.newsSentimentText) {
      els.newsSentimentText.textContent = analysis.news_sentiment || 'No verified recent news was found. News sentiment was not calculated.';
    }

    // Overall Score
    var score = analysis.ai_score;
    if (typeof score === 'number' && score !== null) {
      els.scoreNumber.textContent = score;
      if (els.headerScore) els.headerScore.textContent = score + '/100';
      var offset = 314 - (314 * score / 100);
      if (els.scoreArc) els.scoreArc.style.setProperty('--gauge-offset', offset);
    } else {
      els.scoreNumber.textContent = '--';
      if (els.headerScore) els.headerScore.textContent = '--';
    }

    if (els.summaryText) {
      els.summaryText.textContent = analysis.summary || '';
    }

    // Recommendation & Decision Summary
    var dec = analysis.decision_summary || {};
    var view = dec.research_view || 'Neutral';
    var rec = analysis.recommendation || 'Hold';
    var conf = dec.confidence_level || 'Medium';
    var act = dec.suggested_action || 'Consider for further research';

    if (els.recommendationBadge) {
      els.recommendationBadge.textContent = 'Recommendation: ' + rec;
      var rClass = rec === 'Buy' ? 'badge--low' : (rec === 'Sell' ? 'badge--high' : 'badge--medium');
      els.recommendationBadge.className = 'badge ' + rClass;
    }
    if (els.confidenceBadge) {
      els.confidenceBadge.textContent = 'Confidence: ' + conf;
      var cClass = conf === 'High' ? 'badge--completed' : (conf === 'Low' ? 'badge--high' : 'badge--medium');
      els.confidenceBadge.className = 'badge ' + cClass;
    }
    if (els.actionBadge) {
      els.actionBadge.textContent = 'Action: ' + act;
    }

    // Missing information list
    if (els.missingInfoSection && els.missingInfoList) {
      var missing = analysis.missing_information || (snapshot && snapshot.missing_sections) || [];
      if (missing && missing.length > 0) {
        els.missingInfoSection.hidden = false;
        els.missingInfoList.innerHTML = '';
        missing.forEach(function (m) {
          var li = document.createElement('li');
          li.textContent = m;
          els.missingInfoList.appendChild(li);
        });
      } else {
        els.missingInfoSection.hidden = true;
      }
    }

    // Key Risks & Opportunities
    if (els.keyRisks) els.keyRisks.textContent = analysis.key_risks || 'Market volatility and valuation considerations.';
    if (els.keyRisksList) {
      els.keyRisksList.innerHTML = '';
      (analysis.key_risks_list || []).forEach(function (r) {
        var li = document.createElement('li');
        li.textContent = r;
        els.keyRisksList.appendChild(li);
      });
    }

    if (els.keyOpportunities) els.keyOpportunities.textContent = analysis.key_opportunities || 'Domestic expansion and sectoral demand.';
    if (els.positiveSignalsList) {
      els.positiveSignalsList.innerHTML = '';
      (analysis.positive_signals || []).forEach(function (p) {
        var li = document.createElement('li');
        li.textContent = p;
        els.positiveSignalsList.appendChild(li);
      });
    }

    // Synthesized Outlook
    if (els.outlookText) {
      els.outlookText.textContent = analysis.overall_outlook || '';
    }
  }

  function renderRecord(record, snapshot) {
    var comp = (snapshot && snapshot.company) || {};
    var name = comp.name || record.company_name || 'Company';
    var symbol = comp.symbol || record.ticker_symbol || '--';
    var initials = escapeHtml(name.trim().slice(0, 2).toUpperCase());

    if (els.companyLogo) els.companyLogo.textContent = initials;
    if (els.companyName) els.companyName.textContent = name;
    if (els.companyTicker) {
      var isinText = comp.isin ? ' • ' + comp.isin : '';
      els.companyTicker.textContent = symbol + ' (' + (comp.exchange || 'NSE') + ':' + (comp.series || 'EQ') + isinText + ')';
    }

    var quality = (snapshot && snapshot.quality_status) || 'partial';
    if (els.statusBadge) {
      if (quality === 'complete') {
        els.statusBadge.textContent = 'Complete Verified Data';
        els.statusBadge.className = 'badge badge--completed';
      } else if (quality === 'insufficient') {
        els.statusBadge.textContent = 'Insufficient Data';
        els.statusBadge.className = 'badge badge--high';
      } else {
        els.statusBadge.textContent = 'Partial Verified Snapshot';
        els.statusBadge.className = 'badge badge--medium';
      }
    }

    // Check legacy analysis warning
    if (els.legacyWarning) {
      if (record.is_legacy_analysis) {
        els.legacyWarning.style.display = 'block';
      } else {
        els.legacyWarning.style.display = 'none';
      }
    }

    // Render cards from snapshot
    if (snapshot) {
      renderMarketData(snapshot.market_data, snapshot.company);
      renderFinancialStatements(snapshot.financial_statements, snapshot.financial_ratios);
      renderNewsArticles(snapshot.news_articles);
    }

    if (record.analysis_data) {
      renderAnalysis(record.analysis_data, snapshot);
    }
  }

  function runAnalysis() {
    if (!researchId) return;
    if (els.runBtn) {
      els.runBtn.disabled = true;
      els.runBtn.querySelector('.btn-label').textContent = 'Analyzing...';
    }
    clearError();

    fetchJson('/api/research/' + encodeURIComponent(researchId) + '/analyze', { method: 'POST' })
      .then(function (result) {
        if (els.runBtn) {
          els.runBtn.disabled = false;
          els.runBtn.querySelector('.btn-label').textContent = 'Run AI Analysis';
        }

        if (!result.ok) {
          showError(result.data.message || 'Could not run AI analysis for this research.');
          return;
        }

        loadRecord();
      })
      .catch(function () {
        if (els.runBtn) {
          els.runBtn.disabled = false;
          els.runBtn.querySelector('.btn-label').textContent = 'Run AI Analysis';
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
        var record = result.data.research || {};
        var snapshot = result.data.snapshot || record.snapshot || {};
        renderRecord(record, snapshot);
      })
      .catch(function () {
        showError('Unable to connect to the server. Please make sure the backend is running.');
      });
  }

  function bindActions() {
    if (els.runBtn) els.runBtn.addEventListener('click', runAnalysis);
    if (els.regenerateBtn) els.regenerateBtn.addEventListener('click', runAnalysis);
    if (els.goToReportBtn) {
      els.goToReportBtn.addEventListener('click', function () {
        if (researchId) {
          window.location.href = 'investment-report.html?research_id=' + encodeURIComponent(researchId);
        }
      });
    }
    if (els.exportBtn) {
      els.exportBtn.addEventListener('click', function () {
        window.print();
      });
    }
  }

  function init() {
    bindActions();

    if (researchId) {
      loadRecord();
      return;
    }

    // Auto-fetch latest research if no research_id query param
    fetchJson('/api/research', { method: 'GET' })
      .then(function (result) {
        if (result.ok && result.data.research && result.data.research.length > 0) {
          researchId = result.data.research[0].id;
          if (history.replaceState) {
            history.replaceState(null, '', 'ai-analysis.html?research_id=' + encodeURIComponent(researchId));
          }
          if (els.noResearchNotice) els.noResearchNotice.hidden = true;
          if (els.headerPanel) els.headerPanel.hidden = false;
          loadRecord();
        } else {
          if (els.noResearchNotice) els.noResearchNotice.hidden = false;
          if (els.headerPanel) els.headerPanel.hidden = true;
        }
      })
      .catch(function () {
        if (els.noResearchNotice) els.noResearchNotice.hidden = false;
        if (els.headerPanel) els.headerPanel.hidden = true;
      });
  }

  document.addEventListener('DOMContentLoaded', init);
})();
