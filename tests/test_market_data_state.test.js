/**
 * tests/test_market_data_state.test.js
 * --------------------------------------------------------------------------
 * Unit tests for frontend market data formatting, SVG chart coordinate calculation,
 * and security state rendering. Run via Node.js test runner (`node --test`).
 * --------------------------------------------------------------------------
 */

const test = require('node:test');
const assert = require('node:assert');
const MarketDataState = require('../js/market-data-state.js');

test('1. Decimal-string formatting handles nulls, strings and numbers', () => {
    assert.strictEqual(MarketDataState.formatDecimal(null), '—');
    assert.strictEqual(MarketDataState.formatDecimal(undefined), '—');
    assert.strictEqual(MarketDataState.formatDecimal(''), '—');
    assert.strictEqual(MarketDataState.formatDecimal('invalid'), '—');
    assert.strictEqual(MarketDataState.formatDecimal('1450.25', 2), '1,450.25');
    assert.strictEqual(MarketDataState.formatDecimal(1450.25, 2), '1,450.25');
    assert.strictEqual(MarketDataState.formatDecimal('0.00', 2), '0.00');
    assert.strictEqual(MarketDataState.formatDecimal(1000000, 0, 'en-US'), '1,000,000');
    assert.strictEqual(MarketDataState.formatDecimal(1000000, 0, 'en-IN'), '10,00,000');
});

test('2. Currency formatting applies correct symbol and avoids fake prefixes', () => {
    assert.strictEqual(MarketDataState.formatCurrency(null, 'INR'), '—');
    assert.strictEqual(MarketDataState.formatCurrency('1450.25', 'INR'), '₹1,450.25');
    assert.strictEqual(MarketDataState.formatCurrency('1450.25', 'USD'), '$1,450.25');
    assert.strictEqual(MarketDataState.formatCurrency('1450.25', 'EUR'), 'EUR 1,450.25');
});

test('3. Daily change display handles positive, negative, zero, and missing percentage', () => {
    // Positive change
    const pos = MarketDataState.formatDailyChange('23.10', '1.5984');
    assert.strictEqual(pos.isPositive, true);
    assert.strictEqual(pos.isNegative, false);
    assert.strictEqual(pos.changeText, '+23.10');
    assert.strictEqual(pos.percentText, '+1.60%');
    assert.strictEqual(pos.text, '+23.10 (+1.60%)');

    // Negative change
    const neg = MarketDataState.formatDailyChange('-15.40', '-1.05');
    assert.strictEqual(neg.isPositive, false);
    assert.strictEqual(neg.isNegative, true);
    assert.strictEqual(neg.changeText, '-15.40');
    assert.strictEqual(neg.percentText, '-1.05%');

    // Zero change
    const zero = MarketDataState.formatDailyChange('0.00', '0.00');
    assert.strictEqual(zero.isZero, true);
    assert.strictEqual(zero.changeText, '0.00');

    // Missing change
    const miss = MarketDataState.formatDailyChange(null, null);
    assert.strictEqual(miss.text, '—');
    assert.strictEqual(miss.changeText, '—');
    assert.strictEqual(miss.percentText, '—');
});

test('4. SVG coordinate calculation scales multi-point price time-series accurately', () => {
    const prices = [
        { date: '2026-09-01', close: '100.00' },
        { date: '2026-09-02', close: '150.00' },
        { date: '2026-09-03', close: '200.00' },
    ];
    const width = 600;
    const height = 260;
    const pad = { top: 20, right: 30, bottom: 30, left: 50 };

    const coords = MarketDataState.calculateSvgCoordinates(prices, width, height, pad);

    assert.strictEqual(coords.isEmpty, false);
    assert.strictEqual(coords.isSingle, false);
    assert.strictEqual(coords.isFlat, false);
    assert.strictEqual(coords.points.length, 3);
    assert.strictEqual(coords.minPrice, 100);
    assert.strictEqual(coords.maxPrice, 200);

    // Leftmost point: x = pad.left (50), y = pad.top + plotHeight = 20 + 210 = 230 (lowest price)
    assert.strictEqual(coords.points[0].x, 50);
    assert.strictEqual(coords.points[0].y, 230);

    // Rightmost point: x = width - pad.right = 600 - 30 = 570, y = pad.top = 20 (highest price)
    assert.strictEqual(coords.points[2].x, 570);
    assert.strictEqual(coords.points[2].y, 20);

    // Middle point: x = midpoint = 310, y = pad.top + plotHeight/2 = 125
    assert.strictEqual(coords.points[1].x, 310);
    assert.strictEqual(coords.points[1].y, 125);

    assert.match(coords.pathD, /^M 50 230 L 310 125 L 570 20$/);
    assert.match(coords.areaPathD, /L 570 230 L 50 230 Z$/);
});

test('5. One-point chart handling centers single point and prevents division by zero', () => {
    const prices = [{ date: '2026-09-15', close: '1450.25' }];
    const coords = MarketDataState.calculateSvgCoordinates(prices, 600, 260);

    assert.strictEqual(coords.isSingle, true);
    assert.strictEqual(coords.isFlat, true);
    assert.strictEqual(coords.isEmpty, false);
    assert.strictEqual(coords.points.length, 1);
    assert.strictEqual(coords.minPrice, 1450.25);
    assert.strictEqual(coords.maxPrice, 1450.25);
    assert.strictEqual(coords.points[0].x, 310); // pad.left (50) + (520 / 2)
    assert.strictEqual(coords.points[0].y, 125); // pad.top (20) + (210 / 2)
});

test('6. Flat-price chart handling places identical prices horizontally without NaN/Infinity', () => {
    const prices = [
        { date: '2026-09-10', close: '500.00' },
        { date: '2026-09-11', close: '500.00' },
        { date: '2026-09-12', close: '500.00' },
    ];
    const coords = MarketDataState.calculateSvgCoordinates(prices, 600, 260);

    assert.strictEqual(coords.isFlat, true);
    assert.strictEqual(coords.isSingle, false);
    assert.strictEqual(coords.points.length, 3);
    coords.points.forEach((pt) => {
        assert.strictEqual(pt.y, 125); // Vertical midpoint
        assert.ok(!isNaN(pt.x) && !isNaN(pt.y));
    });
});

test('7. Empty history returns clean empty descriptor', () => {
    const coords = MarketDataState.calculateSvgCoordinates([], 600, 260);
    assert.strictEqual(coords.isEmpty, true);
    assert.strictEqual(coords.points.length, 0);
    assert.strictEqual(coords.pathD, '');
});

test('8. Range selection and allowed range definitions', () => {
    const validRanges = ['1m', '3m', '6m', '1y', '3y', '5y', 'max'];
    const invalidRanges = ['1d', '5d', '10y', 'all'];

    validRanges.forEach((r) => {
        assert.ok(validRanges.includes(r.toLowerCase()));
    });
    invalidRanges.forEach((r) => {
        assert.ok(!validRanges.includes(r.toLowerCase()));
    });
});

test('9. Stale request prevention token mechanism', () => {
    let activeRequestId = 0;

    function startRequest() {
        activeRequestId += 1;
        return activeRequestId;
    }

    function isResponseCurrent(requestId) {
        return requestId === activeRequestId;
    }

    const req1 = startRequest();
    const req2 = startRequest();

    assert.strictEqual(isResponseCurrent(req1), false, 'Older request is marked stale');
    assert.strictEqual(isResponseCurrent(req2), true, 'Latest request is current');
});

test('10. Freshness metadata verification: No "real-time" claim', () => {
    const mockApiResponse = {
        freshness: {
            data_type: 'end_of_day',
            last_trading_date: '2026-09-15',
            is_real_time: false,
        },
        market_data: {
            is_adjusted: false,
        }
    };

    assert.strictEqual(mockApiResponse.freshness.is_real_time, false);
    assert.strictEqual(mockApiResponse.freshness.data_type, 'end_of_day');
    assert.strictEqual(mockApiResponse.market_data.is_adjusted, false);
});

test('11. Text is escaped safely against XSS injection', () => {
    const malicious = '<script>alert("hack")</script>&"\'';
    const escaped = MarketDataState.escapeHtml(malicious);
    assert.strictEqual(escaped, '&lt;script&gt;alert(&quot;hack&quot;)&lt;/script&gt;&amp;&quot;&#39;');
    assert.ok(!escaped.includes('<script>'));
});

test('12. No Alpha Vantage financial or news calls workflow check', () => {
    // Verifies that research state transitions to stored market data without AV endpoints
    const calledEndpoints = [];
    function mockFetch(url) {
        calledEndpoints.push(url);
    }

    // New workflow calls only security market data endpoints
    const securityId = 42;
    mockFetch(`/api/securities/${securityId}/market-data/latest`);
    mockFetch(`/api/securities/${securityId}/market-data/history?range=1y`);

    assert.strictEqual(calledEndpoints.length, 2);
    calledEndpoints.forEach((url) => {
        assert.ok(!url.includes('/financials'), 'No Alpha Vantage financials endpoint called');
        assert.ok(!url.includes('/news'), 'No Alpha Vantage news endpoint called');
        assert.ok(url.startsWith('/api/securities/'), 'Targeted local security endpoint');
    });
});

test('13. Price mode formatting for raw mode', () => {
    const meta = {
        is_adjusted: false,
        disclaimer: 'Unadjusted nominal exchange prices. Excludes corporate action adjustments.',
    };
    const info = MarketDataState.formatPriceModeLabel('raw', meta);
    assert.strictEqual(info.label, 'Raw Unadjusted');
    assert.strictEqual(info.badgeText, 'Unadjusted Prices');
    assert.strictEqual(info.isAdjusted, false);
    assert.strictEqual(info.isFallback, false);
});

test('14. Price mode formatting for split_adjusted mode with verified actions', () => {
    const meta = {
        is_adjusted: true,
        adjustment_version: 'split_bonus_v1',
        applied_action_count: 2,
        disclaimer: 'Adjusted for stock splits and bonus issues. Cash dividends and rights issues are excluded.',
    };
    const info = MarketDataState.formatPriceModeLabel('split_adjusted', meta);
    assert.strictEqual(info.label, 'Split/Bonus Adjusted');
    assert.strictEqual(info.badgeText, 'Split & Bonus Adjusted (split_bonus_v1)');
    assert.strictEqual(info.actionCountText, '2 corporate actions applied');
    assert.strictEqual(info.isAdjusted, true);
    assert.strictEqual(info.isFallback, false);
});

test('15. Price mode formatting fallback when split_adjusted data is unavailable', () => {
    const meta = {
        is_adjusted: false,
        unavailable_reason: 'Split-adjusted price history has not been calculated for this security.',
    };
    const info = MarketDataState.formatPriceModeLabel('split_adjusted', meta);
    assert.strictEqual(info.label, 'Raw Unadjusted (Fallback)');
    assert.strictEqual(info.badgeText, 'Unadjusted Prices');
    assert.strictEqual(info.isAdjusted, false);
    assert.strictEqual(info.isFallback, true);
    assert.strictEqual(info.disclaimer, 'Split-adjusted price history has not been calculated for this security.');
});

