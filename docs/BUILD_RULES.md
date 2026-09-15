# InvestIQ Engineering & Build Rules

This document governs the engineering standards, safety practices, and operational rules for developing the InvestIQ platform. Every developer and AI assistant working on this codebase must strictly adhere to these rules.

---

## 1. One Phase at a Time
- Work strictly within the defined scope of the current phase.
- Do not anticipate or jump ahead to future phases until the current phase is fully built, tested, and verified.

## 2. No Invented Financial Information
- Financial tickers, stock quotes, and corporate metadata must originate from real financial providers or verified fallbacks.
- Never synthesize or truncate company names into fake ticker symbols (e.g. "Reliance Industries" must never be converted into "RELIA").
- Failed ticker validations must reject cleanly without generating bogus database records.

## 3. No Secrets in Git
- API keys, session secrets, and sensitive credentials must never be committed to source control or logged in console outputs.
- All secrets must be loaded via environment variables (`backend/.env` in development, platform config in production).
- Production deployments must fail fast if using default or insecure keys.

## 4. Complete Test Isolation
- Automated test suites must **never** connect to, read from, or modify the live development database (`backend/database/investiq.db`).
- Test executions must use an isolated temporary SQLite database or `:memory:` created outside the workspace repository.
- Tests must clean up their temporary files completely upon completion.

## 5. Mockable External Services
- Automated test suites must never make live external HTTP calls to Alpha Vantage, Google Gemini, or third-party APIs.
- All network dependencies must be mocked with clean domain exceptions and predictable test payloads.

## 6. Mandatory Dual Verification (Automated + Manual)
- Every new feature, bug fix, or refactor requires both:
  1. Isolated automated unit/integration tests with 100% pass status.
  2. Documented manual testing procedures in browser DevTools.

## 7. No Automatic Git Commits
- Changes should not be committed automatically unless explicitly requested by the user.
- Every commit must represent a verified, tested state.

## 8. Honest Test Reporting
- Never claim completion or mask test failures.
- If a test fails, report the exact error, root cause, and remediation steps transparently.

## 9. Zero External Market Data Calls on Stored Research
- The Company Research workflow must only query stored local database records via `/api/securities/<id>/market-data/*`.
- Never call Alpha Vantage, Twelve Data, Gemini, or external financial APIs during company research or price charting.

## 10. Honest End-of-Day Data Representation
- Never label End-of-Day (EOD) Bhavcopy data as "Live" or "Real-time".
- Always display the verified exchange trading date associated with the price record.
- Unadjusted prices must always feature clear disclaimers to prevent misleading total-return interpretations.

## 11. Base-10 Decimal Numeric Integrity
- All price and percentage calculations must use `Decimal` types and be serialized as base-10 strings to prevent binary floating-point representation drift.

## 12. Invariance of Raw Market Data Records
- Raw `daily_prices` records are immutable ground truth and must **never** be modified or overwritten during corporate action adjustments.
- Adjusted prices must always be calculated into separate derived data structures (`adjusted_daily_prices`) with explicit versioning.

## 13. Strict Scope of Automatic Corporate Action Adjustments
- Only verified stock splits (`stock_split`) and bonus issues (`bonus`) may be automatically applied to adjusted OHLC price series.
- Cash dividends (`cash_dividend`), rights issues, buybacks, and restructurings must never be silently or automatically subtracted from OHLC prices without explicit Total Return Index (TRI) models.
- Ambiguous corporate actions must always be routed to `manual_review`.


