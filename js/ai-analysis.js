/* ==========================================================================
   AI-ANALYSIS.JS
   --------------------------------------------------------------------------
   Behavior for ai-analysis.html. Reads `research_id` from the URL query
   string, loads that research record (GET /api/research/:id), and either
   shows its already-persisted analysis or lets the user run one (POST
   /api/research/:id/analyze).
   ========================================================================== */

(function () {
  'use strict';

  var API_BASE_URL = window.INVESTIQ_API_BASE || 'http://127.0.0.1:5000';

  var params = new URLSearchParams(window.location.search);
  var researchId = params.get('research_id');

  var els = {
    noResearchNotice: document.getElementById('aiNoResearchNotice'),
    errorNotice: document.getElementById('aiErrorNotice'),
    headerPanel: document.getElementById('aiHeaderPanel'),
    companyLogo: document.getElementById('aiCompanyLogo'),
    companyName: document.getElementById('aiCompanyName'),
    companyTicker: document.getElementById('aiCompanyTicker'),
    statusBadge: document.getElementById('aiStatusBadge'),
    headerScore: document.getElementById('aiHeaderScore'),
    runBtn: document.getElementById('runAnalysisBtn'),
    scoreSection: document.getElementById('aiScoreSection'),
    scoreArc: document.getElementById('aiScoreArc'),
    scoreNumber: document.getElementById('aiScoreNumber'),
    summaryText: document.getElementById('aiSummaryText'),
    financialSection: document.getElementById('aiFinancialSection'),
    financialCards: document.getElementById('aiFinancialCards'),
    financialAssessment: document.getElementById('aiFinancialAssessment'),
    recommendationSection: document.getElementById('aiRecommendationSection'),
    recommendationBadge: document.getElementById('aiRecommendationBadge'),
    recommendationConfidence: document.getElementById('aiRecommendationConfidence'),
    outlookText: document.getElementById('aiOutlookText'),
    risksSection: document.getElementById('aiRisksSection'),
    keyRisks: document.getElementById('aiKeyRisks'),
    keyOpportunities: document.getElementById('aiKeyOpportunities'),
    newsSentimentSection: document.getElementById('aiNewsSentimentSection'),
    newsSentimentText: document.getElementById('aiNewsSentimentText'),
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

  function renderRecord(record) {
    var initials = escapeHtml((record.company_name || '?').trim().slice(0, 2).toUpperCase());
    els.companyLogo.textContent = initials;
    els.companyName.textContent = record.company_name;
    els.companyTicker.textContent = record.ticker_symbol;

    if (record.status === 'completed' || record.analysis_data) {
      els.statusBadge.textContent = 'Complete';
      els.statusBadge.className = 'badge badge--completed';
    } else {
      els.statusBadge.textContent = 'Not analyzed yet';
      els.statusBadge.className = 'badge badge--medium';
    }

    els.headerScore.textContent = (record.ai_score !== null && record.ai_score !== undefined)
      ? record.ai_score + '/100'
      : '--';

    if (record.analysis_data) {
      renderAnalysis(record.analysis_data, record.financial_data);
    }

    // Always ensure financial cards are rendered
    if (record.financial_data) {
      renderFinancialCards(record.financial_data);
    } else if (record.id) {
      fetchJson('/api/research/' + encodeURIComponent(record.id) + '/financials', { method: 'GET' })
        .then(function (result) {
          if (result.ok && result.data && result.data.financial_data) {
            record.financial_data = result.data.financial_data;
            renderFinancialCards(record.financial_data);
          }
        })
        .catch(function () {});
    }
  }

  function renderFinancialCards(financialData) {
    els.financialCards.innerHTML = '';
    if (!financialData || !financialData.price) {
      els.financialCards.innerHTML = '<p class="field-hint">Loading financial data...</p>';
      return;
    }
    var curr = financialData.currency || 'INR';

    var chgVal = financialData.change;
    var chgPct = financialData.change_percent;
    var chgFormatted = null;
    if (chgVal !== null && chgVal !== undefined && chgVal !== '') {
      var numChg = parseFloat(chgVal);
      var sign = numChg > 0 ? '+' : '';
      chgFormatted = sign + formatPrice(chgVal, curr);
    }

    var chgPctFormatted = null;
    if (chgPct !== null && chgPct !== undefined && chgPct !== '') {
      var strPct = String(chgPct).replace('%', '').trim();
      var numPct = parseFloat(strPct);
      var pSign = numPct > 0 ? '+' : '';
      chgPctFormatted = isNaN(numPct) ? chgPct : (pSign + numPct.toFixed(2) + '%');
    }

    var volFormatted = null;
    if (financialData.volume !== null && financialData.volume !== undefined && financialData.volume !== '') {
      var numVol = Number(financialData.volume);
      volFormatted = !isNaN(numVol) ? numVol.toLocaleString('en-US') : String(financialData.volume);
    }

    var cards = [
      { label: 'Last Close (EOD)', value: financialData.price ? formatPrice(financialData.price, curr) : null },
      { label: 'Daily Change', value: chgFormatted },
      { label: 'Change %', value: chgPctFormatted },
      { label: 'Day High', value: financialData.high ? formatPrice(financialData.high, curr) : null },
      { label: 'Day Low', value: financialData.low ? formatPrice(financialData.low, curr) : null },
      { label: 'Day Open', value: financialData.open ? formatPrice(financialData.open, curr) : null },
      { label: 'Volume', value: volFormatted },
      { label: '52-Week High', value: financialData.week_52_high ? formatPrice(financialData.week_52_high, curr) : null },
      { label: '52-Week Low', value: financialData.week_52_low ? formatPrice(financialData.week_52_low, curr) : null }
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
      els.financialCards.innerHTML = '<p class="field-hint">No financial data available for this research yet.</p>';
    }
  }

  function renderAnalysis(analysis, financialData) {
    els.scoreSection.hidden = false;
    els.financialSection.hidden = false;
    els.recommendationSection.hidden = false;
    els.risksSection.hidden = false;
    els.newsSentimentSection.hidden = false;
    els.actionsSection.hidden = false;

    var score = analysis.ai_score;
    if (typeof score === 'number') {
      els.scoreNumber.textContent = score;
      var offset = 314 - (314 * score / 100);
      els.scoreArc.style.setProperty('--gauge-offset', offset);
    } else {
      els.scoreNumber.textContent = 'N/A';
    }
    els.summaryText.textContent = analysis.summary || '';

    renderFinancialCards(financialData);
    els.financialAssessment.textContent = analysis.financial_assessment || 'Not available.';

    if (analysis.recommendation) {
      els.recommendationBadge.textContent = analysis.recommendation;
      var badgeClass = analysis.recommendation === 'Buy' ? 'badge--low'
        : analysis.recommendation === 'Sell' ? 'badge--high'
        : 'badge--medium';
      els.recommendationBadge.className = 'ai-recommendation__verdict-label badge ' + badgeClass;
    } else {
      els.recommendationBadge.textContent = 'Not available';
      els.recommendationBadge.className = 'ai-recommendation__verdict-label badge badge--medium';
    }
    els.recommendationConfidence.textContent = typeof score === 'number'
      ? ('AI score: ' + score + '/100 — not a certainty')
      : '';
    els.outlookText.textContent = analysis.overall_outlook || '';

    els.keyRisks.textContent = analysis.key_risks || 'Not available.';
    els.keyOpportunities.textContent = analysis.key_opportunities || 'Not available.';
    els.newsSentimentText.textContent = analysis.news_sentiment || 'Not available.';
  }

  function runAnalysis() {
    if (!researchId) return;
    els.runBtn.disabled = true;
    els.runBtn.querySelector('.btn-label').textContent = 'Analyzing...';
    clearError();

    fetchJson('/api/research/' + encodeURIComponent(researchId) + '/analyze', { method: 'POST' })
      .then(function (result) {
        els.runBtn.disabled = false;
        els.runBtn.querySelector('.btn-label').textContent = 'Run AI Analysis';

        if (!result.ok) {
          showError(result.data.message || 'Could not run AI analysis for this research.');
          return;
        }

        // Re-fetch the record so financial_data is rendered alongside the fresh analysis
        loadRecord();
      })
      .catch(function () {
        els.runBtn.disabled = false;
        els.runBtn.querySelector('.btn-label').textContent = 'Run AI Analysis';
        showError('Unable to connect to the server. Please make sure the backend is running.');
      });
  }

  function loadRecord() {
    fetchJson('/api/research/' + encodeURIComponent(researchId), { method: 'GET' })
      .then(function (result) {
        if (!result.ok) {
          showError(result.data.message || 'Could not load this research record.');
          return;
        }
        renderRecord(result.data.research);
      })
      .catch(function () {
        showError('Unable to connect to the server. Please make sure the backend is running.');
      });
  }

  function bindActions() {
    if (els.runBtn) els.runBtn.addEventListener('click', runAnalysis);
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

    // If no research_id query param was given, fetch the user's latest research record
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
