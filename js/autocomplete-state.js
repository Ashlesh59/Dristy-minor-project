/* ==========================================================================
   AUTOCOMPLETE-STATE.JS
   --------------------------------------------------------------------------
   Pure, testable state machine and validation functions for company search
   and accessible autocomplete.
   Runs in both browser (window.InvestIQAutocompleteState) and Node.js.
   ========================================================================== */

(function (root, factory) {
  if (typeof exports === 'object' && typeof module === 'object') {
    module.exports = factory();
  } else if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else {
    root.InvestIQAutocompleteState = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  function normalizeSearchQuery(raw) {
    if (raw === null || raw === undefined) return '';
    return String(raw).trim();
  }

  function createSelection(item) {
    if (!item || typeof item.security_id !== 'number') {
      return null;
    }
    return {
      security_id: item.security_id,
      company_id: item.company_id,
      symbol: item.symbol || '',
      company_name: item.company_name || '',
      exchange: item.exchange || 'NSE',
      series: item.series || 'EQ',
      isin: item.isin || '',
      currency: item.currency || 'INR',
    };
  }

  function clearSelection() {
    return null;
  }

  function handleInputChange(currentSelection, newText) {
    if (!currentSelection) return null;
    var clean = (newText || '').trim();
    if (!clean) return null;

    // If user modified the input so it matches neither the selected company name nor ticker, clear
    var matchesName = currentSelection.company_name && currentSelection.company_name.toLowerCase() === clean.toLowerCase();
    var matchesSymbol = currentSelection.symbol && currentSelection.symbol.toLowerCase() === clean.toLowerCase();

    if (!matchesName && !matchesSymbol) {
      return null;
    }
    return currentSelection;
  }

  function navigateActiveOption(currentIndex, totalCount, direction) {
    if (totalCount <= 0) return -1;
    if (direction > 0) {
      // Move Down
      if (currentIndex < 0) return 0;
      if (currentIndex >= totalCount - 1) return totalCount - 1;
      return currentIndex + 1;
    } else if (direction < 0) {
      // Move Up
      if (currentIndex <= 0) return -1;
      return currentIndex - 1;
    }
    return currentIndex;
  }

  function isStaleResponse(requestSeq, latestSeq) {
    return requestSeq !== latestSeq;
  }

  function validateSubmission(selectedSecurityId) {
    return (
      selectedSecurityId !== null &&
      selectedSecurityId !== undefined &&
      typeof selectedSecurityId === 'number' &&
      selectedSecurityId > 0
    );
  }

  return {
    normalizeSearchQuery: normalizeSearchQuery,
    createSelection: createSelection,
    clearSelection: clearSelection,
    handleInputChange: handleInputChange,
    navigateActiveOption: navigateActiveOption,
    isStaleResponse: isStaleResponse,
    validateSubmission: validateSubmission,
  };
});
