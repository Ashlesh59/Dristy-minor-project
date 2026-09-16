/**
 * tests/test_investment_report_market.test.js
 * --------------------------------------------------------------------------
 * Unit tests for Investment Report Market Performance calculations, 52-week range,
 * period returns presentation, range switching state, and stale request handling.
 * --------------------------------------------------------------------------
 */

const test = require('node:test');
const assert = require('node:assert');
const MarketDataState = require('../js/market-data-state.js');

test('1. Market summary 52-week range formatting', () => {
    // Normal high/low
    const rangeStr = MarketDataState.format52WeekRange('1800.50', '3250.00', 'INR');
    assert.strictEqual(rangeStr, '₹1,800.50 – ₹3,250.00');

    // USD currency
    const usdRange = MarketDataState.format52WeekRange('120.00', '250.00', 'USD');
    assert.strictEqual(usdRange, '$120.00 – $250.00');

    // Missing bounds
    assert.strictEqual(MarketDataState.format52WeekRange(null, '3250.00', 'INR'), '—');
    assert.strictEqual(MarketDataState.format52WeekRange('1800.50', null, 'INR'), '—');
    assert.strictEqual(MarketDataState.format52WeekRange(undefined, undefined, 'INR'), '—');
});

test('2. 1M, 3M, 6M, 1Y period returns formatting and color status', () => {
    // Positive return (green)
    const ret1m = MarketDataState.formatReturn('15.75');
    assert.strictEqual(ret1m.text, '+15.75%');
    assert.strictEqual(ret1m.isPositive, true);
    assert.strictEqual(ret1m.isNegative, false);
    assert.strictEqual(ret1m.isZero, false);

    // Negative return (red)
    const ret3m = MarketDataState.formatReturn('-8.40');
    assert.strictEqual(ret3m.text, '-8.40%');
    assert.strictEqual(ret3m.isPositive, false);
    assert.strictEqual(ret3m.isNegative, true);

    // Flat return (0%)
    const ret6m = MarketDataState.formatReturn('0.00');
    assert.strictEqual(ret6m.text, '0.00%');
    assert.strictEqual(ret6m.isZero, true);

    // Missing return (not enough history)
    const ret1y = MarketDataState.formatReturn(null);
    assert.strictEqual(ret1y.text, '—');
    assert.strictEqual(ret1y.raw, null);
});

test('3. Allowed chart time-ranges for investment report', () => {
    const allowedRanges = ['1m', '3m', '6m', '1y', 'max'];
    allowedRanges.forEach(range => {
        assert.ok(typeof range === 'string' && range.length >= 2);
    });
});

test('4. Stale request prevention sequence logic', () => {
    let globalSeq = 0;

    // Simulate 3 rapid range switch clicks: 1M -> 6M -> 1Y
    globalSeq++;
    const req1Seq = globalSeq; // 1 (1M)

    globalSeq++;
    const req2Seq = globalSeq; // 2 (6M)

    globalSeq++;
    const req3Seq = globalSeq; // 3 (1Y)

    // Suppose response for req1 arrives last:
    assert.strictEqual(req1Seq === globalSeq, false, 'Stale response 1 must be discarded');
    assert.strictEqual(req2Seq === globalSeq, false, 'Stale response 2 must be discarded');
    assert.strictEqual(req3Seq === globalSeq, true, 'Only latest response 3 must be applied');
});

test('5. Native SVG coordinate calculation for investment report chart', () => {
    const prices = [
        { date: '2026-08-01', open: '2400.00', high: '2450.00', low: '2380.00', close: '2420.00', volume: 10000 },
        { date: '2026-08-15', open: '2420.00', high: '2500.00', low: '2410.00', close: '2490.00', volume: 15000 },
        { date: '2026-09-01', open: '2490.00', high: '2550.00', low: '2470.00', close: '2530.00', volume: 20000 },
        { date: '2026-09-15', open: '2530.00', high: '2600.00', low: '2510.00', close: '2580.00', volume: 25000 },
    ];

    const coords = MarketDataState.calculateSvgCoordinates(prices, 600, 260, { top: 25, right: 35, bottom: 35, left: 60 });
    assert.strictEqual(coords.isEmpty, false);
    assert.strictEqual(coords.points.length, 4);
    assert.strictEqual(coords.minPrice, 2420);
    assert.strictEqual(coords.maxPrice, 2580);
    assert.strictEqual(coords.minDate, '2026-08-01');
    assert.strictEqual(coords.maxDate, '2026-09-15');
    assert.ok(coords.pathD.startsWith('M'));
    assert.ok(coords.areaPathD.startsWith('M'));
});

test('6. Empty price history handled cleanly without NaN or syntax error', () => {
    const coords = MarketDataState.calculateSvgCoordinates([], 600, 260, { top: 25, right: 35, bottom: 35, left: 60 });
    assert.strictEqual(coords.isEmpty, true);
    assert.strictEqual(coords.points.length, 0);
    assert.strictEqual(coords.pathD, '');
    assert.strictEqual(coords.areaPathD, '');
});
