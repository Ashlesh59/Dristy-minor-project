# InvestIQ Developer Learning Log

A learning-first log to help the project owner understand every architectural concept, file modification, and function introduced into the codebase.

---

## Phase 0: Safe Development and Testing Foundation

### 1. Concepts Introduced
1. **The Application Factory Pattern (`create_app`)**: Dynamically configures the Flask application.
2. **Configuration Precedence & Engine Lifecycles**: Pre-factory test configuration prevents engine rebinding bugs.
3. **Test-Run Sentinels (`INVESTIQ_TEST_RUN`)**: Fails fast if testing is attempted against `investiq.db`.
4. **Cryptographic Integrity Verification (SHA-256)**: Mathematically guarantees zero dev database modification.

---

## Phase 1A: NSE Company Master Database and Importer

### 1. Concepts Introduced

1. **Separation of Issuer (`Company`) and Instrument (`Security`)**:
   - A **Company** (e.g. Reliance Industries Limited) is the legal corporation.
   - A **Security** (e.g. `RELIANCE-EQ` on NSE, `500325` on BSE) is a specific traded instrument.
   - Separating them allows a single company to have multiple listings across exchanges without duplicating corporate data.

2. **The Multi-NULL SQL Unique Constraint Problem**:
   - In SQL standard, `NULL != NULL`. If `series` were nullable, two rows with `(NSE, TCS, NULL)` would not collide, allowing duplicate rows.
   - Making `series` `NOT NULL` (defaulting to `"EQ"` or normalized from empty) ensures strict database-level unique enforcement.

3. **Space-Preserving Normalization**:
   - Storing `"tata motors limited"` rather than `"tatamotorslimited"` preserves word boundaries for readable and predictable search queries.

4. **ISO 6166 ISIN Validation & Luhn Algorithm**:
   - Every ISIN has a 2-letter country code, 9-character NSIN, and a Luhn check digit computed modulo 10.

5. **Outer Database Transactions vs. Independent Audit Transactions**:
   - The entire CSV import runs inside one outer transaction. If anything goes wrong, `db.session.rollback()` reverts all company and security inserts.
   - A separate, new transaction logs the failed `DataImportRun` record so the failure is preserved in the audit trail.

6. **Multi-Tier Snapshot Deactivation Safety**:
   - Preventing accidental mass-deactivations on truncated feeds by requiring `--confirm-deactivation`, a minimum row count, and a percentage threshold check ($\ge 80\%$).

---

### 2. Files Changed & Created in Phase 1A

| File | Action | Purpose |
| :--- | :--- | :--- |
| `backend/models/company.py` | Created | Company model representing the corporate issuer entity. |
| `backend/models/security.py` | Created | Security model representing exchange-listed instruments with unique constraints. |
| `backend/models/data_import_run.py` | Created | Audit log model tracking batch import execution metrics. |
| `backend/models/__init__.py` | Modified | Exports Company, Security, and DataImportRun models. |
| `backend/services/importer/csv_reader.py` | Created | Reads CSVs with UTF-8 BOM handling and calculates SHA-256 hashes. |
| `backend/services/importer/isin_validator.py` | Created | Validates ISO 6166 ISIN formats and Luhn check digits. |
| `backend/services/importer/normalizer.py` | Created | Space-preserving name normalizer, uppercase symbol sanitizer, date/numeric parser. |
| `backend/services/importer/nse_importer.py` | Created | Transactional importer with dry-run guarantee and snapshot safety checks. |
| `backend/cli/sync_companies.py` | Created | CLI command for synchronizing exchange master datasets. |
| `backend/tests/fixtures/synthetic_nse_equities.csv` | Created | Synthetic test fixture matching the real NSE CSV structure. |
| `backend/tests/test_importer.py` | Created | 13 automated unit and integration tests for Phase 1A. |
| `docs/DATA_DICTIONARY.md` | Created | Comprehensive field, type, constraint, and index dictionary. |
| `docs/DATA_SOURCES.md` | Created | Technical provenance, SHA-256, and licensing documentation for NSE data. |

---

### 3. Comprehension Questions for the Owner

Answer these questions to verify your understanding of Phase 1A:

#### Q1: Why did we separate the `Company` and `Security` models instead of storing everything in one table?
*Your understanding:*
```text
[ Write your answer here ]
```

#### Q2: How does making `series` `NOT NULL` prevent duplicate securities in SQLite and PostgreSQL?
*Your understanding:*
```text
[ Write your answer here ]
```

#### Q3: What happens to `Company` records if an import fails halfway through?
*Your understanding:*
```text
[ Write your answer here ]
```

#### Q4: Why does `--dry-run` make zero database writes?
*Your understanding:*
```text
[ Write your answer here ]
```

#### Q5: If a security disappears from an NSE snapshot, why is `Company.is_active` NOT marked false?
*Your understanding:*
```text
[ Write your answer here ]
```

---

## Phase 1B: Local Company Search API and Accessible Autocomplete

### 1. Concepts Introduced

1. **Deterministic Multi-Tier Search Ranking**:
   - Matches are categorized into 5 discrete tiers via SQL `CASE WHEN` constructs. Exact ticker and ISIN matches are promoted to Tier 1 and 2, ahead of partial and infix substring matches.
   - Secondary sorting ensures deterministic result ordering across identical scores: `Security.symbol ASC`, `Security.series ASC`.

2. **SQL LIKE Wildcard Sanitization**:
   - Characters `%`, `_`, and `\` have special meaning in SQL `LIKE` queries. Escaping them with `\\` and specifying `.like(..., escape='\\\\')` prevents accidental table-wide wildcard matching and query distortion.

3. **1-Character Query Optimization**:
   - Single-character searches perform an exact symbol equality check (`symbol = UPPER(q)`) instead of full-table wildcard scans (`%q%`), preventing excessive I/O while supporting single-letter symbols like `U` or `F`.

4. **Foreign Key Constraint Enforcement in SQLite**:
   - SQLite ignores foreign key constraints by default. Attaching `PRAGMA foreign_keys = ON;` to SQLAlchemy engine connect listeners ensures constraints are enforced on every database connection.

5. **Single Joined Query Execution**:
   - Joining `Company` and `Security` in a single SQL query avoids $N+1$ database query roundtrips during autocomplete lookups.

6. **Server-Controlled Creation Contract (`POST /api/research`)**:
   - The backend strictly accepts `security_id` (integer) and rejects missing or inactive IDs. `company_name` and `ticker_symbol` are retrieved directly from the verified database record, preventing client-side spoofing.

7. **WAI-ARIA 1.2 Accessible Combobox & Frontend Race Condition Protection**:
   - Fully compliant combobox (`aria-expanded`, `aria-autocomplete="list"`, `aria-activedescendant`).
   - Pure state helper (`js/autocomplete-state.js`) tested with Node.js test runner.
   - `AbortController` and monotonic sequence IDs ensure out-of-order network responses are safely discarded.

---

### 2. Files Changed & Created in Phase 1B

| File | Action | Purpose |
| :--- | :--- | :--- |
| `backend/database/db.py` | Modified | Enabled SQLite `PRAGMA foreign_keys = ON;` via connect listener. |
| `backend/models/research.py` | Modified | Added `company_id` and `security_id` foreign keys and relationships. |
| `backend/database/migrations.py` | Modified | Added idempotent schema migration for `research` foreign keys and indexes. |
| `backend/services/company_search_service.py` | Created | 5-tier deterministic search service with wildcard escaping. |
| `backend/routes/companies.py` | Created | `GET /api/companies/search` endpoint with query validation and session auth. |
| `backend/routes/research.py` | Modified | Refactored `POST /api/research` to require `security_id` and server-verify records. |
| `backend/app.py` | Modified | Registered `companies_bp`. |
| `backend/utils/limiter.py` | Modified | Added testing mode bypass. |
| `js/autocomplete-state.js` | Created | Pure frontend state machine for autocomplete navigation and race protection. |
| `tests/test_autocomplete_state.test.js` | Created | Native Node.js unit test suite for frontend state logic. |
| `company-research.html` | Modified | Accessible WAI-ARIA 1.2 combobox markup and feedback containers. |
| `js/company-research.js` | Modified | Debounced search, keyboard navigation, and honest research creation workflow. |
| `backend/tests/test_migration.py` | Created | Schema migration & SQLite foreign-key enforcement test suite. |
| `backend/tests/test_company_search.py` | Created | Automated test suite for search ranking, wildcard escaping, and creation contract. |
| `backend/tests/test_workflow.py` | Modified | Aligned workflow tests with Phase 1B contracts. |
| `docs/API_CONTRACTS.md` | Created | Formal specifications for Phase 1B endpoints. |

---

## Phase 2A: NSE End-of-Day Market Data Storage

### 1. Concepts Introduced

1. **OHLCV Market Representation**:
   - **Open, High, Low, Close, Volume** represent the complete discrete summary of daily trading activity.
   - Preserves historical price action needed for moving averages, RSI, MACD, and risk models.

2. **Base-10 Decimal Numeric Precision in Market Data**:
   - Financial prices must never use floating-point types (`float`), which introduce binary fractional approximation errors.
   - Python `decimal.Decimal` and SQL `NUMERIC(14, 4)` guarantee exact arithmetic across all price levels and turnover figures.

3. **NSE CM-UDiFF Common Bhavcopy Final Specification**:
   - Replaced legacy Bhavcopy with the standardized Unified Data Interface Financial Format (UDiFF).
   - Ingests prices, turnover, trade counts, settlement prices, and delivery percentages.

4. **Composite Key Security Resolution**:
   - Securities are resolved strictly via `exchange="NSE" + symbol + series`.
   - Matching never uses company names or fuzzy logic to prevent incorrect cross-security mapping.

5. **Idempotent Upsert & Reconciliation**:
   - Daily price records are unique on `(security_id, trading_date, source)`.
   - Re-running imports detects identical rows, skips redundant writes, and updates changed rows without duplicating volume or price history.

6. **Transactional Isolation & Failed Audit Logging**:
   - Price writes execute in a single atomic transaction.
   - If an error occurs, price inserts/updates are rolled back and a failure audit entry is committed in a new clean transaction.

---

### 2. Files Changed & Created in Phase 2A

| File | Action | Purpose |
| :--- | :--- | :--- |
| `backend/models/daily_price.py` | Created | DailyPrice model with Decimal numeric types, foreign keys, and unique constraint. |
| `backend/models/market_data_import_run.py` | Created | Audit log tracking market data batch ingestion runs. |
| `backend/models/__init__.py` | Modified | Exported DailyPrice and MarketDataImportRun. |
| `backend/database/migrations.py` | Modified | Added daily_prices indexes to schema migration runner. |
| `backend/services/importer/zip_reader.py` | Created | In-memory ZIP archive reader with path-traversal protection and SHA-256. |
| `backend/services/importer/price_parser.py` | Created | UDiFF parser with Decimal conversion, OHLC validation, and zero-volume handling. |
| `backend/services/importer/nse_market_importer.py` | Created | Transactional market data importer service. |
| `backend/cli/sync_market_data.py` | Created | CLI command for market data synchronization. |
| `backend/tests/fixtures/synthetic_nse_udiff_bhavcopy.zip` | Created | Synthetic UDiFF test fixture. |
| `backend/tests/test_daily_price.py` | Created | Model unit tests for DailyPrice and constraints. |
| `backend/tests/test_market_importer.py` | Created | Automated test suite for market data importer. |
| `docs/DATA_PIPELINE.md` | Created | Technical documentation of the market data ETL pipeline. |
| `docs/DATA_SOURCES.md` | Modified | Added NSE CM-UDiFF data source specifications. |
| `docs/DATA_DICTIONARY.md` | Modified | Added daily_prices and market_data_import_runs schemas. |

---

## Phase 2B: Stored Market Data API and Historical Price Charts

### 1. Concepts Introduced

1. **End-of-Day (EOD) vs. Real-Time Market Data**:
   - EOD Bhavcopy data reflects official settlement and closing transactions after market close. It does not fluctuate second-by-second.
   - Displaying EOD data honestly requires removing all "Live" or "Real-time" claims and showing the exact historical `trading_date`.

2. **Unadjusted vs. Corporate-Action Adjusted Prices**:
   - Bhavcopy prices represent historical unadjusted transaction values. They do not retroactively adjust for stock splits, bonus issues, or rights offerings.
   - Historical percentage performance and returns should never be calculated on unadjusted prices without explicit disclaimers.

3. **Chronological Ordering of Time Series Data**:
   - Stock chart rendering and technical analysis indicators require sequential time series data ($t_0, t_1, \dots, t_n$) ordered oldest to newest (`trading_date ASC`).
   - Querying with database-level limits (`ORDER BY trading_date DESC LIMIT N`) must be reversed before serialization to maintain chronological order.

4. **Division-by-Zero Protection in Daily Change**:
   - Percentage change formula: $\frac{\text{Close} - \text{Previous Close}}{\text{Previous Close}} \times 100$.
   - When $\text{Previous Close} \le 0$ or is missing, percentage calculation must safely yield `null` to avoid runtime crashes.

5. **Base-10 Decimal String Serialization**:
   - To prevent floating-point serialization bugs (e.g. `1450.2500000000002`), all prices are serialized as exact base-10 strings (`"1450.25"`).

6. **Native Accessible SVG Price Charting**:
   - Maps normalized data coordinates $(x_i, y_i)$ into SVG viewport space without heavy charting libraries.
   - Handles single data points, flat price lines, and non-trading days naturally.
   - Includes full WAI-ARIA labels, screen-reader data table alternatives, and unadjusted price disclaimers.

7. **Race Condition Prevention in Chart Range Selection**:
   - Uses `AbortController` and sequential monotonic request IDs to ensure that out-of-order network responses cannot overwrite newer user selections.

---

### 2. Files Changed & Created in Phase 2B

| File | Action | Purpose |
| :--- | :--- | :--- |
| `backend/services/market_data_service.py` | Created | Encapsulates market data queries, decimal serialization, change calculations, and freshness metadata. |
| `backend/routes/securities.py` | Created | Exposes `GET /api/securities/<id>/market-data/latest` and `history` endpoints. |
| `backend/app.py` | Modified | Registered `securities_bp`. |
| `backend/services/importer/nse_market_importer.py` | Modified | Added `import_bhavcopy_directory` with deterministic sorting and per-file transactions. |
| `backend/cli/sync_market_data.py` | Modified | Added `--directory` and `--force` arguments with mutual exclusivity checks. |
| `backend/routes/research.py` | Modified | Included `company_id` and `security_id` in Research serialization; marked Alpha Vantage routes deprecated. |
| `js/market-data-state.js` | Created | Pure formatting, SVG coordinate mapping, and escaping utilities (browser + Node.js). |
| `company-research.html` | Modified | Added EOD quote cards, range filter buttons (`1M`-`MAX`), native SVG chart container, and screen-reader table. |
| `css/company-research.css` | Modified | Styling for market data cards, SVG chart, range pill buttons, and accessibility tables. |
| `js/company-research.js` | Modified | Integrated EOD quote fetching, historical chart loading, range controls, and abort signal management. |
| `tests/test_market_data_state.test.js` | Created | Node.js unit tests for formatting, SVG math, and XSS safety. |
| `backend/tests/test_market_data_service.py` | Created | Unit tests for `MarketDataService`. |
| `backend/tests/test_market_data_routes.py` | Created | Integration tests for market data endpoints. |
| `backend/tests/test_directory_importer.py` | Created | Integration tests for directory import and per-file transactions. |
| `docs/API_CONTRACTS.md` | Modified | Documented Phase 2B endpoints and marked legacy Alpha Vantage routes. |
| `docs/ARCHITECTURE.md` | Modified | Documented market data service and chart architecture. |
| `docs/DATA_PIPELINE.md` | Modified | Documented directory ingestion pipeline. |

---

## Phase 2C: Corporate Actions and Split-Adjusted Historical Prices

### 1. Concepts Introduced

1. **Corporate Action Mechanics & Ex-Date Cutoffs**:
   - Stock splits change share face value without altering total equity value.
   - Bonus issues distribute free shares from reserves.
   - The **Ex-Date** is the mathematical boundary: only historical dates strictly before the ex-date ($t < \text{ex\_date}$) are multiplied by the action multiplier factor.

2. **Cumulative Adjustment Factor Multipliers**:
   - For multiple corporate actions $A_1, A_2, \dots, A_K$, the cumulative price factor $F(t) = \prod_{k: t < E_k} f_k$.
   - Volume scales inversely: $V_{\text{adj}} = V \times \frac{1}{F(t)}$.

3. **Ground Truth Preservation & Derived Storage**:
   - `DailyPrice` records represent official nominal exchange settlement ground truth and are **never** modified or overwritten.
   - Derived adjusted prices are stored in `AdjustedDailyPrice` with an explicit `adjustment_version` (`split_bonus_v1`).

4. **Transparent Price Mode Selection**:
   - Frontend and API provide explicit toggles (`price_mode=raw` vs `price_mode=split_adjusted`).
   - If adjusted data does not exist for a security, the API returns raw prices with an explicit honest `unavailable_reason`.
   - Clear disclaimers inform users that cash dividends and rights issues are excluded from automatic price adjustments.

---

### 2. Files Changed & Created in Phase 2C

| File | Action | Purpose |
| :--- | :--- | :--- |
| `backend/models/corporate_action.py` | Created | CorporateAction model with unique source event keys and decimal ratios. |
| `backend/models/corporate_action_import_run.py` | Created | Audit model tracking corporate action batch ingestion runs. |
| `backend/models/adjusted_daily_price.py` | Created | AdjustedDailyPrice model storing derived versioned prices. |
| `backend/models/adjustment_run.py` | Created | Audit model tracking adjustment rebuild executions. |
| `backend/models/__init__.py` | Modified | Exported Phase 2C models. |
| `backend/database/migrations.py` | Modified | Added Phase 2C indexes to schema migration runner. |
| `backend/services/importer/ca_parser.py` | Created | Regex-based parser for splits, bonuses, dividends, and manual review routing. |
| `backend/services/importer/corporate_action_importer.py` | Created | Transactional importer for exchange corporate action files. |
| `backend/services/adjustment_service.py` | Created | Cumulative adjustment engine with Decimal math and per-security transaction isolation. |
| `backend/cli/sync_corporate_actions.py` | Created | CLI tool for importing corporate actions CSVs. |
| `backend/cli/rebuild_adjusted_prices.py` | Created | CLI tool for recalculating adjusted prices. |
| `backend/services/market_data_service.py` | Modified | Added `price_mode` handling, versioned queries, and fallback metadata. |
| `backend/routes/securities.py` | Modified | Accepted `price_mode` query parameter on history route. |
| `js/market-data-state.js` | Modified | Added `formatPriceModeLabel` metadata formatter. |
| `company-research.html` | Modified | Added `[Raw]` and `[Split/Bonus Adjusted]` toggle buttons and disclaimer banner. |
| `css/company-research.css` | Modified | Styled price mode toggle buttons. |
| `js/company-research.js` | Modified | Integrated price mode switching, request cancellation, and dynamic disclaimer rendering. |
| `docs/CORPORATE_ACTIONS.md` | Created | Comprehensive mathematical and operational guide for corporate actions. |




