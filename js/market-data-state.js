/**
 * js/market-data-state.js
 * --------------------------------------------------------------------------
 * Pure state and presentation utilities for End-of-Day market data and SVG charts.
 * Independent of DOM manipulation for reliable unit testing.
 * --------------------------------------------------------------------------
 */

(function (root, factory) {
    if (typeof module === "object" && module.exports) {
        // Node / CommonJS test environment
        module.exports = factory();
    } else {
        // Browser environment
        root.MarketDataState = factory();
    }
})(typeof self !== "undefined" ? self : this, function () {
    "use strict";

    /**
     * Escapes unsafe characters for HTML rendering.
     */
    function escapeHtml(str) {
        if (str === null || str === undefined) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    /**
     * Formats a numeric value or decimal string with standard fraction digits.
     */
    function formatDecimal(value, fractionDigits, locale) {
        if (fractionDigits === undefined) fractionDigits = 2;
        if (value === null || value === undefined || value === "") {
            return "—";
        }
        var num = typeof value === "number" ? value : parseFloat(String(value));
        if (isNaN(num)) {
            return "—";
        }
        return num.toLocaleString(locale || "en-IN", {
            minimumFractionDigits: fractionDigits,
            maximumFractionDigits: fractionDigits,
        });
    }

    /**
     * Formats currency amounts with honest currency prefix/symbol.
     */
    function formatCurrency(value, currency) {
        var curr = (currency || "INR").toUpperCase();
        var formatted = formatDecimal(value, 2);
        if (formatted === "—") return "—";

        if (curr === "INR") {
            return "₹" + formatted;
        } else if (curr === "USD") {
            return "$" + formatted;
        }
        return curr + " " + formatted;
    }

    /**
     * Computes daily change presentation object with color flags and safe formatting.
     */
    function formatDailyChange(change, changePercent) {
        if (change === null || change === undefined || change === "") {
            return {
                text: "—",
                changeText: "—",
                percentText: "—",
                isPositive: false,
                isNegative: false,
                isZero: true,
                rawChange: 0,
            };
        }

        var numChange = typeof change === "number" ? change : parseFloat(String(change));
        if (isNaN(numChange)) {
            return {
                text: "—",
                changeText: "—",
                percentText: "—",
                isPositive: false,
                isNegative: false,
                isZero: true,
                rawChange: 0,
            };
        }

        var numPct = (changePercent !== null && changePercent !== undefined && changePercent !== "")
            ? (typeof changePercent === "number" ? changePercent : parseFloat(String(changePercent)))
            : null;

        var isPositive = numChange > 0;
        var isNegative = numChange < 0;
        var isZero = numChange === 0;

        var sign = isPositive ? "+" : (isNegative ? "-" : "");
        var absChangeFormatted = formatDecimal(Math.abs(numChange), 2);
        var changeText = sign + absChangeFormatted;

        var percentText = "—";
        if (numPct !== null && !isNaN(numPct)) {
            var absPctFormatted = formatDecimal(Math.abs(numPct), 2);
            percentText = sign + absPctFormatted + "%";
        }

        var combinedText = percentText !== "—"
            ? changeText + " (" + percentText + ")"
            : changeText;

        return {
            text: combinedText,
            changeText: changeText,
            percentText: percentText,
            isPositive: isPositive,
            isNegative: isNegative,
            isZero: isZero,
            rawChange: numChange,
        };
    }

    /**
     * Calculates SVG coordinates and path definitions for price time-series.
     * Prevents division by zero for single points or flat horizontal lines.
     */
    function calculateSvgCoordinates(prices, width, height, padding) {
        var w = width || 600;
        var h = height || 260;
        var pad = padding || { top: 20, right: 30, bottom: 30, left: 50 };

        var plotWidth = w - pad.left - pad.right;
        var plotHeight = h - pad.top - pad.bottom;

        if (!prices || !Array.isArray(prices) || prices.length === 0) {
            return {
                points: [],
                pathD: "",
                areaPathD: "",
                minPrice: 0,
                maxPrice: 0,
                minDate: null,
                maxDate: null,
                isFlat: false,
                isSingle: false,
                isEmpty: true,
            };
        }

        // Single data point handling
        if (prices.length === 1) {
            var p0 = prices[0];
            var closeVal = typeof p0.close === "number" ? p0.close : parseFloat(String(p0.close || 0));
            var singleX = pad.left + plotWidth / 2;
            var singleY = pad.top + plotHeight / 2;

            return {
                points: [{
                    x: singleX,
                    y: singleY,
                    date: p0.date,
                    close: closeVal,
                    raw: p0,
                }],
                pathD: "M " + singleX.toFixed(2) + " " + singleY.toFixed(2),
                areaPathD: "",
                minPrice: closeVal,
                maxPrice: closeVal,
                minDate: p0.date,
                maxDate: p0.date,
                isFlat: true,
                isSingle: true,
                isEmpty: false,
            };
        }

        // Multiple points: find min/max close
        var numericPrices = prices.map(function (p) {
            return {
                date: p.date,
                close: typeof p.close === "number" ? p.close : parseFloat(String(p.close || 0)),
                raw: p,
            };
        });

        var minPrice = numericPrices[0].close;
        var maxPrice = numericPrices[0].close;

        for (var i = 1; i < numericPrices.length; i++) {
            if (numericPrices[i].close < minPrice) minPrice = numericPrices[i].close;
            if (numericPrices[i].close > maxPrice) maxPrice = numericPrices[i].close;
        }

        var isFlat = (minPrice === maxPrice);
        var priceRange = maxPrice - minPrice;

        var points = [];
        var n = numericPrices.length;

        for (var idx = 0; idx < n; idx++) {
            var item = numericPrices[idx];
            // X coordinate: evenly distributed along time series
            var x = pad.left + (idx / (n - 1)) * plotWidth;

            // Y coordinate: high price at top (pad.top), low price at bottom (pad.top + plotHeight)
            var y;
            if (isFlat) {
                y = pad.top + plotHeight / 2;
            } else {
                y = pad.top + ((maxPrice - item.close) / priceRange) * plotHeight;
            }

            points.push({
                x: Number(x.toFixed(2)),
                y: Number(y.toFixed(2)),
                date: item.date,
                close: item.close,
                raw: item.raw,
            });
        }

        // Construct SVG path data
        var pathD = "";
        for (var pIdx = 0; pIdx < points.length; pIdx++) {
            var pt = points[pIdx];
            if (pIdx === 0) {
                pathD += "M " + pt.x + " " + pt.y;
            } else {
                pathD += " L " + pt.x + " " + pt.y;
            }
        }

        // Construct area fill path data
        var bottomY = pad.top + plotHeight;
        var firstPt = points[0];
        var lastPt = points[points.length - 1];
        var areaPathD = pathD + " L " + lastPt.x + " " + bottomY + " L " + firstPt.x + " " + bottomY + " Z";

        return {
            points: points,
            pathD: pathD,
            areaPathD: areaPathD,
            minPrice: minPrice,
            maxPrice: maxPrice,
            minDate: numericPrices[0].date,
            maxDate: numericPrices[numericPrices.length - 1].date,
            isFlat: isFlat,
            isSingle: false,
            isEmpty: false,
        };
    }

    /**
     * Formats metadata and badge presentation for price mode (raw vs split-adjusted).
     */
    function formatPriceModeLabel(priceMode, metadata) {
        var mode = (priceMode || "raw").toLowerCase();
        var meta = metadata || {};
        var isAdjusted = meta.is_adjusted === true;

        if (mode === "split_adjusted") {
            if (isAdjusted) {
                var count = meta.applied_action_count || 0;
                var ver = meta.adjustment_version || "v1";
                return {
                    label: "Split/Bonus Adjusted",
                    badgeText: "Split & Bonus Adjusted (" + ver + ")",
                    disclaimer: meta.disclaimer || "Adjusted for stock splits and bonus issues. Cash dividends and rights issues are excluded.",
                    actionCountText: count + " corporate action" + (count === 1 ? "" : "s") + " applied",
                    isAdjusted: true,
                    isFallback: false,
                };
            } else {
                return {
                    label: "Raw Unadjusted (Fallback)",
                    badgeText: "Unadjusted Prices",
                    disclaimer: meta.unavailable_reason || "Split-adjusted price history has not been calculated for this security.",
                    actionCountText: "0 corporate actions applied",
                    isAdjusted: false,
                    isFallback: true,
                };
            }
        }

        return {
            label: "Raw Unadjusted",
            badgeText: "Unadjusted Prices",
            disclaimer: meta.disclaimer || "Unadjusted nominal exchange prices. Excludes corporate action adjustments.",
            actionCountText: "0 corporate actions applied",
            isAdjusted: false,
            isFallback: false,
        };
    }

    /**
     * Formats 52-week price range: "Low – High" or "—".
     */
    function format52WeekRange(low, high, currency) {
        if (low === null || low === undefined || high === null || high === undefined || low === "" || high === "") {
            return "—";
        }
        var formattedLow = formatCurrency(low, currency);
        var formattedHigh = formatCurrency(high, currency);
        if (formattedLow === "—" || formattedHigh === "—") return "—";
        return formattedLow + " – " + formattedHigh;
    }

    /**
     * Formats a percentage return value with sign and color indicator flags.
     */
    function formatReturn(returnVal) {
        if (returnVal === null || returnVal === undefined || returnVal === "") {
            return {
                text: "—",
                isPositive: false,
                isNegative: false,
                isZero: true,
                raw: null,
            };
        }
        var num = typeof returnVal === "number" ? returnVal : parseFloat(String(returnVal));
        if (isNaN(num)) {
            return {
                text: "—",
                isPositive: false,
                isNegative: false,
                isZero: true,
                raw: null,
            };
        }
        var isPos = num > 0;
        var isNeg = num < 0;
        var isZero = num === 0;
        var sign = isPos ? "+" : (isNeg ? "-" : "");
        var absFormatted = formatDecimal(Math.abs(num), 2);
        return {
            text: sign + absFormatted + "%",
            isPositive: isPos,
            isNegative: isNeg,
            isZero: isZero,
            raw: num,
        };
    }

    return {
        escapeHtml: escapeHtml,
        formatDecimal: formatDecimal,
        formatCurrency: formatCurrency,
        formatDailyChange: formatDailyChange,
        calculateSvgCoordinates: calculateSvgCoordinates,
        formatPriceModeLabel: formatPriceModeLabel,
        format52WeekRange: format52WeekRange,
        formatReturn: formatReturn,
    };
});

