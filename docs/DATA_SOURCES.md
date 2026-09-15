# InvestIQ Data Sources & Provenance

This document records the origin, technical specifications, cryptographic signatures, update schedules, and licensing status of all external datasets ingested into InvestIQ.

---

## 1. National Stock Exchange of India (NSE) — Equity Master

- **Dataset Identifier**: `NSE_EQUITY_L`
- **Source Organization**: National Stock Exchange of India Ltd.
- **Official Source URL**: [https://www.nseindia.com/market-data/securities-available-for-trading](https://www.nseindia.com/market-data/securities-available-for-trading)
- **Direct Download Link**: `https://archives.nseindia.com/content/equities/EQUITY_L.csv`
- **File Name**: `data/raw/nse/EQUITY_L.csv`
- **File Size**: 182,540 bytes (~2,586 equity listings)
- **Ingestion Date / Snapshot**: 2026-09-15
- **SHA-256 Checksum**: `E85EB7F85F19541F6A58F062ADD488C7848EA8F843F84E25F38BCFF1C06A4890`
- **Expected Update Frequency**: Daily / Monthly (as new IPOs list or symbols are reclassified).

### Included Columns & Ingestion Mapping

| Source CSV Header | Domain Model Target | Type / Format | Transformation Notes |
| :--- | :--- | :--- | :--- |
| `SYMBOL` | `Security.symbol` | `VARCHAR(50)` | Uppercase, whitespace stripped. |
| `NAME OF COMPANY` | `Company.legal_name`, `Company.display_name`, `Company.normalized_name` | `VARCHAR(255)` | Whitespace-collapsed; normalized name lowercased with preserved word spaces. |
| ` SERIES` | `Security.series` | `VARCHAR(20)` | Header whitespace trimmed. Defaults to `'EQ'` if empty. |
| ` DATE OF LISTING` | `Security.listing_date` | `DATE` | Parsed from `DD-MMM-YYYY` (e.g. `06-OCT-2008`). |
| ` PAID UP VALUE` | `Security.paid_up_value` | `NUMERIC(12,2)` | Numeric conversion; invalid/missing set to `NULL`. |
| ` MARKET LOT` | `Security.market_lot` | `INTEGER` | Integer conversion (typically `1`). |
| ` ISIN NUMBER` | `Security.isin` | `VARCHAR(20)` | Validated against 12-char ISO 6166 and Luhn check digit. |
| ` FACE VALUE` | `Security.face_value` | `NUMERIC(12,2)` | Numeric conversion; invalid/missing set to `NULL`. |

### Known Data Limitations & Edge Cases
1. **Header Whitespace**: The official CSV includes leading spaces in headers like `' SERIES'` and `' ISIN NUMBER'`.
2. **Company Name Matching**: The raw feed identifies companies solely by their commercial string. Subtle corporate name variations across exchanges may require manual review when BSE datasets are introduced.
3. **No Market Sector/Industry**: `EQUITY_L.csv` does not provide GICS/macro sector tags; these are populated from complementary financial intelligence feeds.

### Usage & Licensing Status
- **Status**: **Licensing Review Required**.
- **Usage Scope**: Ingested locally for ticker validation, autocomplete normalization, and internal research reference. Raw CSV files are excluded from public source control via `.gitignore` (`data/raw/**`). InvestIQ does not claim redistribution rights over bulk exchange data.

---

## 2. National Stock Exchange of India (NSE) — CM-UDiFF Common Bhavcopy Final

- **Dataset Identifier**: `NSE_CM_UDIFF_BHAVCOPY`
- **Source Organization**: National Stock Exchange of India Ltd.
- **Specification / Standard**: SEBI / NSE Unified Data Interface Financial Format (UDiFF).
- **Direct Download Source**: Official NSE Daily EOD Archives (`https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_<YYYYMMDD>_F_0000.csv.zip`).
- **File Name Pattern**: `data/raw/nse/bhavcopy/BhavCopy_NSE_CM_0_0_0_<YYYYMMDD>_F_0000.csv.zip`
- **Expected Update Frequency**: Every trading day post-market close (~18:30 IST).

### Included Columns & Ingestion Mapping

| UDiFF Header | Canonical Field | Domain Model Target | Type / Format | Transformation Notes |
| :--- | :--- | :--- | :--- | :--- |
| `TradDt` | `trading_date` | `DailyPrice.trading_date` | `DATE` | Parsed from `YYYY-MM-DD` or `DD-MMM-YYYY`. |
| `TckrSymb` | `symbol` | Resolution Key | `VARCHAR(50)` | Uppercase ticker symbol. |
| `SctySrs` | `series` | Resolution Key | `VARCHAR(20)` | Uppercase series identifier (e.g. `'EQ'`, `'BE'`). |
| `ISIN` | `isin` | Diagnostic Lookup | `VARCHAR(20)` | Cross-validated against `Security.isin`. |
| `OpnPric` | `open` | `DailyPrice.open_price` | `NUMERIC(14, 4)` | Exact base-10 Decimal conversion. |
| `HghPric` | `high` | `DailyPrice.high_price` | `NUMERIC(14, 4)` | Exact base-10 Decimal conversion. |
| `LwPric` | `low` | `DailyPrice.low_price` | `NUMERIC(14, 4)` | Exact base-10 Decimal conversion. |
| `ClsPric` | `close` | `DailyPrice.close_price` | `NUMERIC(14, 4)` | Exact base-10 Decimal conversion. |
| `LastPric` | `last` | `DailyPrice.last_price` | `NUMERIC(14, 4)` | Nullable exact Decimal. |
| `PrvsClsgPric` | `prev_close` | `DailyPrice.previous_close` | `NUMERIC(14, 4)` | Nullable exact Decimal. |
| `Vwap` | `vwap` | `DailyPrice.vwap` | `NUMERIC(14, 4)` | If missing, computed as `turnover / volume`. |
| `TtlTradgVol` | `volume` | `DailyPrice.volume` | `BIGINT` | Total traded shares. |
| `TtlTrdVal` / `TtlTrfVal` | `turnover` | `DailyPrice.turnover` | `NUMERIC(20, 4)` | Total traded turnover value in INR. |
| `TtlNbOfTxsExctd` | `trade_count` | `DailyPrice.trade_count` | `INTEGER` | Total number of executed trades. |
| `DlvryQty` | `delivery_qty` | `DailyPrice.deliverable_quantity` | `BIGINT` | Total delivery-settled quantity. |
| `DlvryPrcnt` | `delivery_pct` | `DailyPrice.deliverable_percentage` | `NUMERIC(6, 2)` | Deliverable quantity percentage. |

### Known Limitations & Corporate Actions
1. **Unadjusted Prices**: EOD Bhavcopy values are nominal unadjusted prices as traded on that calendar date. Corporate action adjustments (splits, bonuses, rights issues) require dividend/split adjustment multipliers applied in analytics layers.
2. **Licensing**: Raw daily ZIP archives are proprietary to the exchange and strictly excluded from Git repositories (`data/raw/**`). Only synthetic fixtures are stored in source control.

---

## 3. National Stock Exchange of India (NSE) — Equities Corporate Actions

- **Dataset Identifier**: `NSE_EQUITIES_CORPORATE_ACTIONS`
- **Source Organization**: National Stock Exchange of India Ltd.
- **Official Source URL**: [https://www.nseindia.com/companies-listing/corporate-filings-actions](https://www.nseindia.com/companies-listing/corporate-filings-actions)
- **Direct Archive Link**: `https://archives.nseindia.com/content/equities/CA.csv`
- **File Name Pattern**: `data/raw/nse/CA.csv`
- **Expected Update Frequency**: Daily post-market or weekly snapshot.

### Included Columns & Ingestion Mapping

| Source CSV Header | Canonical Field | Domain Model Target | Type / Format | Transformation Notes |
| :--- | :--- | :--- | :--- | :--- |
| `SYMBOL` | `symbol` | Resolution Key | `VARCHAR(50)` | Uppercase, whitespace stripped. |
| `SERIES` | `series` | Resolution Key | `VARCHAR(20)` | Defaults to `'EQ'` if empty. |
| `SECURITY` / `COMPANY` | `security_name` | Audit Reference | `VARCHAR(255)` | Informational company string. |
| `RECORD_DATE` | `record_date` | `CorporateAction.record_date` | `DATE` | Parsed across multiple date formats. |
| `EX_DATE` | `ex_date` | `CorporateAction.ex_date` | `DATE` | Mandatory entitlement cutoff boundary. |
| `PURPOSE` / `SUBJECT` | `purpose` | `CorporateAction.action_description` | `TEXT` | Raw text parsed via regex for splits, bonuses, dividends. |
| `ISIN` | `isin` | Primary Resolution Key | `VARCHAR(20)` | Matched against `Security.isin`. |


