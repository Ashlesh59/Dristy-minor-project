/**
 * tests/test_market_data_errors.test.js
 * --------------------------------------------------------------------------
 * Unit tests verifying frontend error handling logic for market data requests.
 * --------------------------------------------------------------------------
 */

const test = require('node:test');
const assert = require('node:assert');

// Simulate the logic in js/company-research.js
function handleLatestMarketDataResponse(result, state) {
    if (result.status === 401) {
        state.error = 'Your session has expired. Please log in again.';
        return;
    }
    
    if (!result.ok || !result.data || !result.data.success) {
        state.error = (result.data && result.data.message) || 'Could not load latest market data.';
        return;
    }
    
    // Success path (even if market_data is null, because success is true)
    state.data = result.data;
}

test('Successful empty data (200 OK, market_data: null)', () => {
    const state = {};
    const result = {
        status: 200,
        ok: true,
        data: {
            success: true,
            market_data: null,
            message: "No price data available for this security."
        }
    };
    
    handleLatestMarketDataResponse(result, state);
    
    // Should NOT have an error. Should pass the data through to renderLatestMarketData
    assert.strictEqual(state.error, undefined);
    assert.deepStrictEqual(state.data, result.data);
});

test('401 Session Expired', () => {
    const state = {};
    const result = {
        status: 401,
        ok: false,
        data: { message: "Token expired" }
    };
    
    handleLatestMarketDataResponse(result, state);
    
    // Must trigger session expired message
    assert.strictEqual(state.error, 'Your session has expired. Please log in again.');
    assert.strictEqual(state.data, undefined);
});

test('500 Internal Server Error (Backend failure)', () => {
    const state = {};
    const result = {
        status: 500,
        ok: false,
        data: { success: false, message: "Database connection failed" }
    };
    
    handleLatestMarketDataResponse(result, state);
    
    // Must display the actual error message, not disguise it as missing market data
    assert.strictEqual(state.error, 'Database connection failed');
    assert.strictEqual(state.data, undefined);
});

test('404 Not Found (Invalid security ID)', () => {
    const state = {};
    const result = {
        status: 404,
        ok: false,
        data: { success: false, message: "Security not found" }
    };
    
    handleLatestMarketDataResponse(result, state);
    
    // Must display actual error message
    assert.strictEqual(state.error, 'Security not found');
    assert.strictEqual(state.data, undefined);
});
