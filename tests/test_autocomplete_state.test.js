/**
 * tests/test_autocomplete_state.test.js
 * --------------------------------------------------------------------------
 * Unit tests for frontend autocomplete state logic using Node.js test runner.
 * Run with: node --test tests/test_autocomplete_state.test.js
 * --------------------------------------------------------------------------
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const state = require('../js/autocomplete-state.js');

test('normalizeSearchQuery trims whitespace safely', () => {
  assert.equal(state.normalizeSearchQuery('  Reliance Industries  '), 'Reliance Industries');
  assert.equal(state.normalizeSearchQuery(null), '');
  assert.equal(state.normalizeSearchQuery(undefined), '');
  assert.equal(state.normalizeSearchQuery('TCS'), 'TCS');
});

test('createSelection builds clean selection object with security_id', () => {
  const item = {
    security_id: 42,
    company_id: 10,
    symbol: 'RELIANCE',
    company_name: 'Reliance Industries Limited',
    exchange: 'NSE',
    series: 'EQ',
    isin: 'INE002A01018',
    currency: 'INR',
  };
  const selection = state.createSelection(item);
  assert.equal(selection.security_id, 42);
  assert.equal(selection.company_id, 10);
  assert.equal(selection.symbol, 'RELIANCE');
  assert.equal(selection.company_name, 'Reliance Industries Limited');

  // Invalid item returns null
  assert.equal(state.createSelection(null), null);
  assert.equal(state.createSelection({ symbol: 'BAD' }), null);
});

test('handleInputChange preserves selection when text matches, but clears when modified', () => {
  const current = {
    security_id: 42,
    symbol: 'RELIANCE',
    company_name: 'Reliance Industries Limited',
  };

  // Exact match on company name or symbol keeps selection
  assert.notEqual(state.handleInputChange(current, 'Reliance Industries Limited'), null);
  assert.notEqual(state.handleInputChange(current, 'RELIANCE'), null);
  assert.notEqual(state.handleInputChange(current, 'reliance'), null);

  // User edits or modifies text -> selection is cleared
  assert.equal(state.handleInputChange(current, 'Reliance Industries Ltd Changed'), null);
  assert.equal(state.handleInputChange(current, 'Tata Motors'), null);
  assert.equal(state.handleInputChange(current, ''), null);
  assert.equal(state.handleInputChange(null, 'Any Text'), null);
});

test('navigateActiveOption clamps active index strictly within list boundaries', () => {
  const total = 5;

  // Move down from initial (-1) -> 0
  assert.equal(state.navigateActiveOption(-1, total, 1), 0);

  // Move down from 0 -> 1 -> 2 -> 3 -> 4
  assert.equal(state.navigateActiveOption(0, total, 1), 1);
  assert.equal(state.navigateActiveOption(3, total, 1), 4);

  // Move down at bottom -> clamps at 4
  assert.equal(state.navigateActiveOption(4, total, 1), 4);

  // Move up from 4 -> 3 -> 2 -> 1 -> 0
  assert.equal(state.navigateActiveOption(4, total, -1), 3);
  assert.equal(state.navigateActiveOption(1, total, -1), 0);

  // Move up at top (0) -> -1 (unselected)
  assert.equal(state.navigateActiveOption(0, total, -1), -1);

  // Empty list returns -1
  assert.equal(state.navigateActiveOption(0, 0, 1), -1);
});

test('isStaleResponse detects race condition sequence divergence', () => {
  assert.equal(state.isStaleResponse(1, 2), true);   // Request #1 returned when current is #2 -> STALE
  assert.equal(state.isStaleResponse(2, 2), false);  // Matching latest sequence -> FRESH
});

test('validateSubmission strictly rejects unselected or invalid security_id', () => {
  assert.equal(state.validateSubmission(42), true);
  assert.equal(state.validateSubmission(1), true);

  assert.equal(state.validateSubmission(null), false);
  assert.equal(state.validateSubmission(undefined), false);
  assert.equal(state.validateSubmission(0), false);
  assert.equal(state.validateSubmission(-5), false);
  assert.equal(state.validateSubmission('42'), false); // string not allowed
});
