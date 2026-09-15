# InvestIQ Data Dictionary

This document defines the schema, constraints, data types, and index justifications for all core entity and audit models in the InvestIQ Platform.

---

## 1. `companies` Table

Represents the legal corporate entity / issuer of securities.

| Column Name | Data Type | Nullable | Default | Description | Index Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `NO` | Autoincrement | Primary Key. Unique identifier for the company. | Primary Key index. |
| `legal_name` | `VARCHAR(255)` | `NO` | None | Full legal registered name of the corporate entity. | None. |
| `display_name` | `VARCHAR(255)` | `NO` | None | Clean, formatted commercial name used in UI presentation. | None. |
| `normalized_name` | `VARCHAR(255)` | `NO` | None | Lowercase, whitespace-collapsed name (spaces preserved) for exact lookup. | `ix_companies_normalized_name`: Accelerates company matching. |
| `country` | `VARCHAR(10)` | `NO` | `'IN'` | ISO 3166-1 alpha-2 country of domicile (e.g. `'IN'`). | `ix_companies_country`: Fast regional filtering. |
| `sector` | `VARCHAR(100)` | `YES` | `NULL` | Broad macroeconomic sector (e.g. Technology, Energy). | None. |
| `industry` | `VARCHAR(100)` | `YES` | `NULL` | Specific industry classification. | None. |
| `website` | `VARCHAR(255)` | `YES` | `NULL` | Official corporate web URL. | None. |
| `is_active` | `BOOLEAN` | `NO` | `TRUE` | Whether the company entity is currently operational. | `ix_companies_is_active`: Filters active issuers. |
| `created_at` | `DATETIME` | `NO` | UTC now | Timestamp of initial record creation. | None. |
| `updated_at` | `DATETIME` | `NO` | UTC now | Timestamp of last record modification. | None. |

---

## 2. `securities` Table

Represents a financial instrument listed and traded on a specific stock exchange.

| Column Name | Data Type | Nullable | Default | Description | Index Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `NO` | Autoincrement | Primary Key. Unique identifier for the security. | Primary Key index. |
| `company_id` | `INTEGER` | `NO` | None | Foreign Key referencing `companies.id`. | `ix_securities_company_id`: Fast joins to parent issuer. |
| `symbol` | `VARCHAR(50)` | `NO` | None | Exchange ticker symbol (normalized uppercase, e.g. `'TCS'`). | `ix_securities_symbol`: Instant ticker search. |
| `exchange` | `VARCHAR(20)` | `NO` | `'NSE'` | Market identifier (e.g. `'NSE'`, `'BSE'`). | `ix_securities_exchange`: Exchange filtering. |
| `series` | `VARCHAR(20)` | `NO` | `'EQ'` | Trading series category (e.g. `'EQ'`, `'BE'`, `'BZ'`). | `ix_securities_series`: Segment filtering. |
| `isin` | `VARCHAR(20)` | `YES` | `NULL` | 12-character International Securities Identification Number. | `ix_securities_isin`: Exact global ISIN lookup. |
| `currency` | `VARCHAR(10)` | `NO` | `'INR'` | ISO currency code in which the security trades. | None. |
| `asset_type` | `VARCHAR(50)` | `NO` | `'Equity'` | Asset class (e.g. `'Equity'`, `'ETF'`, `'Debt'`). | None. |
| `listing_date` | `DATE` | `YES` | `NULL` | Date on which the instrument was admitted to listing. | None. |
| `paid_up_value`| `NUMERIC(12,2)` | `YES`| `NULL` | Paid-up share capital value per share. | None. |
| `market_lot` | `INTEGER` | `YES` | `NULL` | Minimum trading lot size (typically 1 for equities). | None. |
| `face_value` | `NUMERIC(12,2)` | `YES`| `NULL` | Nominal face value per share. | None. |
| `is_active` | `BOOLEAN` | `NO` | `TRUE` | Whether the instrument is currently listed and tradeable. | `ix_securities_is_active`: Filters tradeable instruments. |
| `source` | `VARCHAR(100)` | `NO` | `'NSE'` | Provenance tag identifying dataset source. | None. |
| `source_updated_at`| `DATETIME` | `YES` | `NULL` | Timestamp when source feed last confirmed this row. | None. |
| `created_at` | `DATETIME` | `NO` | UTC now | Timestamp of record creation. | None. |
| `updated_at` | `DATETIME` | `NO` | UTC now | Timestamp of record update. | None. |

### Constraints & Composite Indexes:
- **`uq_security_exchange_symbol_series`**: `UNIQUE(exchange, symbol, series)`. Guarantees exact uniqueness for every listed instrument. Because `series` is non-null, SQL multi-NULL bypass issues are eliminated.
- **`ix_securities_exchange_symbol`**: Composite index on `(exchange, symbol)` for rapid ticker lookup within a target exchange.

---

## 3. `data_import_runs` Table

Audit log recording every execution of batch master data imports.

| Column Name | Data Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `NO` | Primary Key. Audit run ID. |
| `source` | `VARCHAR(100)` | `NO` | Source identifier (e.g. `'NSE'`). |
| `source_file` | `VARCHAR(255)` | `NO` | Privacy-safe relative file path (e.g. `'data/raw/nse/EQUITY_L.csv'`). |
| `file_sha256` | `VARCHAR(64)` | `NO` | Cryptographic SHA-256 hash of the ingested file. |
| `started_at` | `DATETIME` | `NO` | Timestamp when the import execution began. |
| `completed_at` | `DATETIME` | `YES` | Timestamp when execution finished. |
| `status` | `VARCHAR(50)` | `NO` | Execution status: `'completed'`, `'failed'`, `'dry_run'`. |
| `total_rows` | `INTEGER` | `NO` | Total raw rows parsed from the CSV file. |
| `inserted_companies` | `INTEGER` | `NO` | Number of newly created `Company` records. |
| `updated_companies` | `INTEGER` | `NO` | Number of updated `Company` records. |
| `inserted_securities`| `INTEGER` | `NO` | Number of newly created `Security` records. |
| `updated_securities` | `INTEGER` | `NO` | Number of updated `Security` records. |
| `unchanged_securities`|`INTEGER` | `NO` | Number of existing `Security` records confirmed identical. |
| `skipped_rows` | `INTEGER` | `NO` | Number of rows skipped due to non-fatal validation issues. |
| `failed_rows` | `INTEGER` | `NO` | Number of rows with fatal errors. |
| `deactivated_securities`|`INTEGER`| `NO` | Number of absent securities marked inactive in full-snapshot mode. |
| `error_summary` | `TEXT` | `YES` | Structured JSON summary of errors and warnings encountered. |

---

## 4. `daily_prices` Table (Phase 2A)

Stores verified End-of-Day (EOD) OHLCV, turnover, and delivery data for securities.

| Column Name | Data Type | Nullable | Default | Description | Index Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `NO` | Autoincrement | Primary Key. Unique price record identifier. | Primary Key index. |
| `security_id` | `INTEGER` | `NO` | None | Foreign Key referencing `securities.id` (`ON DELETE CASCADE`). | `ix_daily_prices_security_id`: Joins to parent security. |
| `trading_date` | `DATE` | `NO` | None | Date of market trading session on the exchange. | `ix_daily_prices_trading_date`: Time-slice queries. |
| `open_price` | `NUMERIC(14, 4)`| `NO` | None | Opening transaction price. Base-10 exact decimal. | None. |
| `high_price` | `NUMERIC(14, 4)`| `NO` | None | Session high price. Base-10 exact decimal. | None. |
| `low_price` | `NUMERIC(14, 4)`| `NO` | None | Session low price. Base-10 exact decimal. | None. |
| `close_price` | `NUMERIC(14, 4)`| `NO` | None | Official closing price. Base-10 exact decimal. | None. |
| `last_price` | `NUMERIC(14, 4)`| `YES` | `NULL` | Last traded price (LTP). | None. |
| `previous_close` | `NUMERIC(14, 4)`| `YES`| `NULL` | Previous session closing price. | None. |
| `vwap` | `NUMERIC(14, 4)`| `YES` | `NULL` | Volume Weighted Average Price. | None. |
| `volume` | `BIGINT` | `YES` | `NULL` | Total volume of shares transacted. | None. |
| `turnover` | `NUMERIC(20, 4)`| `YES`| `NULL` | Total traded value in INR. | None. |
| `trade_count` | `INTEGER` | `YES` | `NULL` | Total number of executed trades/transactions. | None. |
| `deliverable_quantity` | `BIGINT`| `YES` | `NULL` | Total delivery-settled share quantity. | None. |
| `deliverable_percentage`| `NUMERIC(6, 2)`| `YES`| `NULL` | Percentage of volume marked for delivery. | None. |
| `source` | `VARCHAR(50)` | `NO` | `'NSE_UDIFF'` | Provenance source format identifier. | `ix_daily_prices_source`: Source isolation. |
| `source_file_sha256` | `VARCHAR(64)` | `NO` | None | Cryptographic SHA-256 of the source archive. | None. |
| `source_row_number` | `INTEGER` | `YES` | `NULL` | Line index in raw source CSV. | None. |
| `is_adjusted` | `BOOLEAN` | `NO` | `FALSE` | Whether OHLC prices are corporate-action adjusted. | None. |
| `created_at` | `DATETIME` | `NO` | UTC now | Timestamp of initial ingestion. | None. |
| `updated_at` | `DATETIME` | `NO` | UTC now | Timestamp of last modification. | None. |

### Constraints & Composite Indexes:
- **`uq_daily_prices_security_date_source`**: `UNIQUE(security_id, trading_date, source)`. Prevents duplicate price records for any security on a given trading date.
- **`ix_daily_prices_security_trading_date`**: Composite index on `(security_id, trading_date)` for high-speed time series charting and range lookups.

---

## 5. `market_data_import_runs` Table (Phase 2A)

Audit log for End-of-Day market data batch ingestion runs.

| Column Name | Data Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `NO` | Primary Key. |
| `source` | `VARCHAR(50)` | `NO` | Source feed identifier (e.g. `'NSE_UDIFF'`). |
| `source_file` | `VARCHAR(255)` | `NO` | Sanitized basename of the ingested ZIP archive. |
| `file_sha256` | `VARCHAR(64)` | `NO` | Cryptographic SHA-256 hash of the archive. |
| `trading_date` | `DATE` | `YES` | Parsed trading session date. |
| `started_at` | `DATETIME` | `NO` | Run start timestamp. |
| `completed_at` | `DATETIME` | `YES` | Run completion timestamp. |
| `status` | `VARCHAR(20)` | `NO` | `'completed'`, `'failed'`, `'dry_run'`. |
| `total_rows` | `INTEGER` | `NO` | Total rows parsed from the archive. |
| `inserted_rows` | `INTEGER` | `NO` | Count of newly inserted daily price rows. |
| `updated_rows` | `INTEGER` | `NO` | Count of modified daily price rows. |
| `unchanged_rows`| `INTEGER` | `NO` | Count of confirmed identical daily price rows. |
| `skipped_rows` | `INTEGER` | `NO` | Count of skipped rows. |
| `unresolved_rows` | `INTEGER` | `NO` | Count of rows with unknown securities. |
| `failed_rows` | `INTEGER` | `NO` | Count of rows failing price validation rules. |
| `error_summary` | `TEXT` | `YES` | Summary of non-fatal and fatal error diagnostics. |

---

## 6. `corporate_actions` Table (Phase 2C)

Stores official exchange-announced corporate action events.

| Column Name | Data Type | Nullable | Default | Description | Index Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `NO` | Autoincrement | Primary Key. | Primary Key index. |
| `security_id` | `INTEGER` | `NO` | None | Foreign Key referencing `securities.id` (`ON DELETE CASCADE`). | `ix_corporate_actions_security_id`: Fast joins. |
| `action_type` | `VARCHAR(50)` | `NO` | None | Event category (`stock_split`, `bonus`, `cash_dividend`, etc.). | `ix_corporate_actions_action_type`: Type filtering. |
| `announcement_date` | `DATE` | `YES` | `NULL` | Board declaration date. | None. |
| `ex_date` | `DATE` | `NO` | None | Ex-entitlement trading date on exchange. | `ix_corporate_actions_ex_date`: Time boundary checks. |
| `record_date` | `DATE` | `YES` | `NULL` | Shareholder eligibility cutoff date. | None. |
| `action_description` | `TEXT` | `NO` | None | Raw official purpose description. | None. |
| `ratio_from` | `NUMERIC(14, 6)`| `YES` | `NULL` | Base ratio operand (e.g. old face value or existing shares). | None. |
| `ratio_to` | `NUMERIC(14, 6)`| `YES` | `NULL` | Target ratio operand (e.g. new face value or total new shares). | None. |
| `cash_amount` | `NUMERIC(14, 4)`| `YES` | `NULL` | Dividend payout per share in INR. | None. |
| `currency` | `VARCHAR(10)` | `YES` | `'INR'` | Currency of payout. | None. |
| `source` | `VARCHAR(50)` | `NO` | `'NSE_CA'` | Data feed identifier. | None. |
| `source_event_key` | `VARCHAR(128)` | `NO` | None | Deterministic cryptographic event hash. | Unique constraint operand. |
| `source_file_sha256` | `VARCHAR(64)` | `NO` | None | Source CSV file hash. | None. |
| `processing_status` | `VARCHAR(50)` | `NO` | `'pending'` | Lifecycle state: `pending`, `verified`, `applied`, `manual_review`, `rejected`. | `ix_corporate_actions_processing_status`. |
| `review_reason` | `VARCHAR(255)` | `YES` | `NULL` | Diagnostic explanation for manual review routing. | None. |
| `created_at`, `updated_at`| `DATETIME` | `NO` | UTC now | Audit timestamps. | None. |

### Constraints & Composite Indexes:
- **`uq_corporate_actions_source_event_key`**: `UNIQUE(source, source_event_key)`.
- **`ix_corporate_actions_security_ex_date`**: Composite index on `(security_id, ex_date)` for high-speed chronological multiplier calculation.

---

## 7. `corporate_action_import_runs` Table (Phase 2C)

Audit log for corporate action batch import executions.

| Column Name | Data Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `NO` | Primary Key. |
| `source` | `VARCHAR(50)` | `NO` | Source feed identifier (`'NSE_CA'`). |
| `source_file` | `VARCHAR(255)` | `NO` | Sanitized basename of CSV file. |
| `file_sha256` | `VARCHAR(64)` | `NO` | Cryptographic SHA-256 hash. |
| `started_at`, `completed_at` | `DATETIME` | Started `NO`, Completed `YES` | Execution timestamps. |
| `status` | `VARCHAR(20)` | `NO` | `'completed'`, `'failed'`, `'dry_run'`. |
| `total_rows`, `inserted_rows`, `updated_rows`, `unchanged_rows`, `skipped_rows`, `unresolved_rows`, `manual_review_rows`, `rejected_rows`, `failed_rows` | `INTEGER` | `NO` | Batch execution metrics. |
| `error_summary` | `TEXT` | `YES` | Diagnostic messages. |

---

## 8. `adjusted_daily_prices` Table (Phase 2C)

Stores derived split- and bonus-adjusted historical market data.

| Column Name | Data Type | Nullable | Default | Description | Index Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `NO` | Autoincrement | Primary Key. | Primary Key index. |
| `daily_price_id` | `INTEGER` | `NO` | None | Foreign Key referencing `daily_prices.id` (`ON DELETE CASCADE`). | `ix_adjusted_daily_prices_daily_price_id`. |
| `security_id` | `INTEGER` | `NO` | None | Foreign Key referencing `securities.id` (`ON DELETE CASCADE`). | `ix_adjusted_daily_prices_security_id`. |
| `trading_date` | `DATE` | `NO` | None | Trading session date. | Time-series filtering. |
| `adjusted_open` | `NUMERIC(14, 4)`| `NO` | None | Adjusted open price. | None. |
| `adjusted_high` | `NUMERIC(14, 4)`| `NO` | None | Adjusted high price. | None. |
| `adjusted_low` | `NUMERIC(14, 4)`| `NO` | None | Adjusted low price. | None. |
| `adjusted_close`| `NUMERIC(14, 4)`| `NO` | None | Adjusted closing price. | None. |
| `adjusted_volume`| `BIGINT` | `YES` | `NULL` | Proportional share volume. | None. |
| `cumulative_price_factor`| `NUMERIC(18, 10)`| `NO`| None | Product of all forward split/bonus factors. | None. |
| `cumulative_volume_factor`| `NUMERIC(18, 10)`| `NO`| None | Inverse of cumulative price factor. | None. |
| `adjustment_method` | `VARCHAR(50)` | `NO` | `'split_bonus_ratio'` | Calculation methodology identifier. | None. |
| `adjustment_version` | `VARCHAR(50)` | `NO` | `'split_bonus_v1'` | Version tag for reproducible backtests. | `ix_adjusted_daily_prices_adjustment_version`. |
| `calculated_at` | `DATETIME` | `NO` | UTC now | Rebuild timestamp. | None. |

### Constraints & Composite Indexes:
- **`uq_adjusted_daily_prices_daily_version`**: `UNIQUE(daily_price_id, adjustment_version)`.
- **`ix_adjusted_daily_prices_security_date_version`**: Composite index on `(security_id, trading_date, adjustment_version)`.

---

## 9. `adjustment_runs` Table (Phase 2C)

Audit log tracking execution of historical price adjustment recalculation runs.

| Column Name | Data Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `NO` | Primary Key. |
| `security_id` | `INTEGER` | `YES` | Null for full batch runs, or specific security ID. |
| `adjustment_version` | `VARCHAR(50)` | `NO` | Target calculation version (e.g. `'split_bonus_v1'`). |
| `started_at`, `completed_at` | `DATETIME` | Started `NO`, Completed `YES` | Timestamps. |
| `status` | `VARCHAR(20)` | `NO` | `'completed'`, `'failed'`, `'dry_run'`, `'partial_failure'`. |
| `securities_processed`, `prices_processed`, `actions_applied`, `manual_review_actions`, `failed_securities` | `INTEGER` | `NO` | Execution statistics. |
| `error_summary` | `TEXT` | `YES` | Error diagnostics. |


