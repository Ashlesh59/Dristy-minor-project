/* ==========================================================================
   INVESTMENT-REPORT.JS
   --------------------------------------------------------------------------
   Behavior for investment-report.html. Reads `research_id` from the URL,
   loads the research record, and either renders its already-persisted
   report (no repeat Gemini call) or offers to generate one via POST
   /api/research/:id/report.
   ========================================================================== */

(function () {
  'use strict';

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

  function renderFinancialCards(financialData) {
    if (!els.financialCards) return;
    els.financialCards.innerHTML = '';
    if (!financialData) {
      els.financialCards.innerHTML = '<p class="field-hint">No financial data was available for this research.</p>';
      return;
    }

    var fin = financialData;
    if (typeof fin === 'string') {
      try { fin = JSON.parse(fin); } catch (e) { fin = null; }
    }
    if (!fin) {
      els.financialCards.innerHTML = '<p class="field-hint">No financial data was available for this research.</p>';
      return;
    }

    var curr = fin.currency || 'USD';
    var cards = [
      { label: 'Last Close (EOD)', value: fin.price ? formatPrice(fin.price, curr) : null },
      { label: 'Change', value: fin.change },
      { label: 'Change %', value: fin.change_percent },
      { label: 'Day High', value: fin.high ? formatPrice(fin.high, curr) : null },
      { label: 'Day Low', value: fin.low ? formatPrice(fin.low, curr) : null },
      { label: 'Volume', value: fin.volume ? Number(fin.volume).toLocaleString('en-US') : null }
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
      els.financialCards.innerHTML = '<p class="field-hint">No financial data was available for this research.</p>';
    }
  }

  function recommendationBadgeClass(rec) {
    if (rec === 'Buy') return 'badge--low';
    if (rec === 'Sell') return 'badge--high';
    return 'badge--medium';
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
