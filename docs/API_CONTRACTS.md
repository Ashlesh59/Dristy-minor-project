# InvestIQ API Contracts Specification

**Current Phase:** 1B — Local Company Search API & Accessible Autocomplete  
**Last Updated:** September 2026

---

## 1. Company Discovery

### `GET /api/companies/search`

Searches local `Company` and `Security` records with deterministic 5-tier ranking. Performs **zero** external network calls.

#### Request

- **Method:** `GET`
- **Path:** `/api/companies/search`
- **Authentication:** Required (Valid session cookie)
- **Rate Limit:** 60 requests per minute per IP

##### Query Parameters

| Parameter | Type | Required | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- |
| `q` | `string` | **Yes** | Min 2 chars (or 1 alphanumeric for exact ticker lookup). Escapes SQL wildcards `%`, `_`. | Search keyword |
| `country` | `string` | No | Max 30 chars, alphanumeric/dash/space. Case-insensitive (e.g., `IN`, `US`). | Filter by company country |
| `exchange` | `string` | No | Max 30 chars, alphanumeric/dash/space. Case-insensitive (e.g., `NSE`, `BSE`). | Filter by security exchange |
| `asset_type` | `string` | No | Max 30 chars, alphanumeric/dash/space. Case-insensitive (e.g., `Equity`). | Filter by security asset type |
| `limit` | `integer`| No | Min `1`, Max `20`, Default `10`. | Maximum items returned |

#### Ranking Priority (SQL Multi-Tier)

1. **Tier 1 (Exact Ticker):** `Security.symbol == UPPER(q)`
2. **Tier 2 (Exact ISIN):** `Security.isin == UPPER(q)`
3. **Tier 3 (Exact Legal Name):** `Company.normalized_name == clean_q.lower()`
4. **Tier 4 (Company Name Prefix):** `Company.legal_name LIKE '{clean_q}%'`
5. **Tier 5 (Partial Match):** `Company.legal_name LIKE '%{clean_q}%'` OR `Security.symbol LIKE '%{clean_q}%'`
- **Tie-Breaker:** Alphabetical by `Security.symbol ASC`, then `Security.series ASC`.

#### Success Response (`200 OK`)

```json
{
  "success": true,
  "query": "TATA",
  "count": 2,
  "results": [
    {
      "security_id": 14,
      "company_id": 8,
      "symbol": "TATAMOTORS",
      "company_name": "Tata Motors Limited",
      "exchange": "NSE",
      "series": "EQ",
      "isin": "INE155A01022",
      "country": "IN",
      "asset_type": "Equity",
      "currency": "INR"
    },
    {
      "security_id": 15,
      "company_id": 9,
      "symbol": "TCS",
      "company_name": "Tata Consultancy Services Limited",
      "exchange": "NSE",
      "series": "EQ",
      "isin": "INE467B01029",
      "country": "IN",
      "asset_type": "Equity",
      "currency": "INR"
    }
  ]
}
```

#### Error Responses

- **`400 Bad Request`** (Missing or invalid query):
  ```json
  {
    "success": false,
    "message": "Query parameter 'q' is required."
  }
  ```
- **`401 Unauthorized`** (Not logged in):
  ```json
  {
    "success": false,
    "message": "You must be logged in to do that."
  }
  ```
- **`429 Too Many Requests`** (Rate limit exceeded):
  ```json
  {
    "success": false,
    "message": "Too many requests. Please wait 60 requests per 60s limit. Try again in 45s."
  }
  ```

---

## 2. Research Management

### `POST /api/research`

Creates a new investment research request. Strictly requires a valid, active `security_id`.

#### Request

- **Method:** `POST`
- **Path:** `/api/research`
- **Authentication:** Required (Valid session cookie)
- **Content-Type:** `application/json`

##### Body Parameters

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `security_id` | `integer` | **Yes** | Primary key of the selected `Security` record. |
| `research_type` | `string` | No | Default `"general"`. Type of research request. |

> **Security Note:** Client-submitted `company_name` or `ticker_symbol` fields are strictly ignored. Authoritative values are populated by the server from the database.

#### Success Response (`201 Created`)

```json
{
  "success": true,
  "message": "Research request created successfully.",
  "research": {
    "id": 42,
    "user_id": 1,
    "company_id": 8,
    "security_id": 14,
    "company_name": "Tata Motors Limited",
    "ticker_symbol": "TATAMOTORS",
    "research_type": "general",
    "status": "pending",
    "created_at": "2026-09-15T19:30:00.000000",
    "updated_at": "2026-09-15T19:30:00.000000"
  }
}
```

#### Error Responses

- **`400 Bad Request`** (Missing/invalid `security_id`):
  ```json
  {
    "success": false,
    "message": "security_id (integer) is required for new research requests."
  }
  ```
- **`404 Not Found`** (Security not found or inactive):
  ```json
  {
    "success": false,
    "message": "Security not found or is no longer active."
  }
  ```
- **`401 Unauthorized`** (Not logged in):
  ```json
  {
    "success": false,
    "message": "You must be logged in to do that."
  }
  ```

---

### `GET /api/research/stats`

Returns research statistics and total searches for the authenticated user.

#### Success Response (`200 OK`)

```json
{
  "success": true,
  "stats": {
    "total_searches": 12,
    "completed_reports": 5,
    "distinct_companies": 8,
    "average_score": 78
  }
}
```

---

## 3. Stored Market Data (Phase 2B)

### `GET /api/securities/<security_id>/market-data/latest`

Retrieves the latest verified exchange End-of-Day (EOD) market data record for a specified security. Calculates absolute change and percentage change safely without converting through binary floating-point numbers.

#### Request

- **Method:** `GET`
- **Path:** `/api/securities/<security_id>/market-data/latest`
- **Authentication:** Required (Valid session cookie)
- **Rate Limit:** 60 requests per minute per IP

#### Success Response (`200 OK`) — When Price Data Exists

```json
{
  "success": true,
  "security": {
    "security_id": 1,
    "company_id": 1,
    "company_name": "Reliance Industries Limited",
    "symbol": "RELIANCE",
    "exchange": "NSE",
    "series": "EQ",
    "currency": "INR"
  },
  "market_data": {
    "trading_date": "2026-09-15",
    "open": "1450.25",
    "high": "1472.50",
    "low": "1441.10",
    "close": "1468.30",
    "last_price": "1465.00",
    "previous_close": "1445.20",
    "change": "23.10",
    "change_percent": "1.5984",
    "volume": 1234567,
    "turnover": "1800000000.00",
    "vwap": "1462.50",
    "trade_count": 45600,
    "deliverable_quantity": 650000,
    "deliverable_percentage": "52.65",
    "source": "NSE_UDIFF",
    "is_adjusted": false
  },
  "freshness": {
    "data_type": "end_of_day",
    "last_trading_date": "2026-09-15",
    "is_real_time": false
  }
}
```

#### Success Response (`200 OK`) — When Security Has No Ingested Prices

```json
{
  "success": true,
  "security": {
    "security_id": 99,
    "company_id": 50,
    "company_name": "New Listed Entity Limited",
    "symbol": "NEWLIST",
    "exchange": "NSE",
    "series": "EQ",
    "currency": "INR"
  },
  "market_data": null,
  "freshness": {
    "data_type": "end_of_day",
    "last_trading_date": null,
    "is_real_time": false,
    "message": "No price data has been imported for this security yet."
  }
}
```

---

### `GET /api/securities/<security_id>/market-data/history`

Retrieves historical closing prices and volume in chronological order (oldest to newest).

#### Request

- **Method:** `GET`
- **Path:** `/api/securities/<security_id>/market-data/history`
- **Authentication:** Required (Valid session cookie)
- **Rate Limit:** 60 requests per minute per IP

##### Query Parameters

| Parameter | Type | Required | Allowed Values | Description |
| :--- | :--- | :--- | :--- | :--- |
| `range` | `string` | No | `1m`, `3m`, `6m`, `1y`, `3y`, `5y`, `max` (Default `1y` if neither start nor end is given) | Predefined time period |
| `start` | `string` | No | ISO Date `YYYY-MM-DD` | Custom start date boundary |
| `end` | `string` | No | ISO Date `YYYY-MM-DD` | Custom end date boundary |
| `limit` | `integer`| No | Min `1`, Max `5000`, Default `2000` | Max rows to return from database |
| `price_mode` | `string` | No | `raw`, `split_adjusted` (Default: `raw`) | Whether to return raw exchange prices or split/bonus adjusted series |
| `version` | `string` | No | `split_bonus_v1` (Default: `split_bonus_v1`) | Calculation version identifier |

> **Validation Rule:** Specifying `range` alongside `start` or `end` is rejected with `400 Bad Request` to avoid ambiguity. `start` later than `end` is rejected.

#### Success Response (`200 OK`) — Raw Mode (`price_mode=raw`)

```json
{
  "success": true,
  "security": {
    "security_id": 1,
    "company_id": 1,
    "company_name": "Reliance Industries Limited",
    "symbol": "RELIANCE",
    "exchange": "NSE",
    "series": "EQ",
    "isin": "INE002A01018",
    "currency": "INR"
  },
  "range": {
    "requested": "1y",
    "start": "2025-09-15",
    "end": "2026-09-15",
    "count": 248,
    "truncated": false
  },
  "prices": [
    {
      "date": "2025-09-16",
      "open": "1420.00",
      "high": "1435.50",
      "low": "1412.00",
      "close": "1430.10",
      "volume": 980000,
      "turnover": "1401500000.00",
      "vwap": "1425.40"
    }
  ],
  "metadata": {
    "data_type": "end_of_day",
    "source": "NSE_UDIFF",
    "is_adjusted": false,
    "requested_price_mode": "raw",
    "returned_price_mode": "raw",
    "adjustment_version": null,
    "applied_action_count": 0,
    "adjustment_scope": "none",
    "disclaimer": "Unadjusted nominal exchange prices. Excludes corporate action adjustments."
  }
}
```

#### Success Response (`200 OK`) — Split Adjusted Mode (`price_mode=split_adjusted`)

```json
{
  "success": true,
  "security": {
    "security_id": 1,
    "company_id": 1,
    "company_name": "Reliance Industries Limited",
    "symbol": "RELIANCE",
    "exchange": "NSE",
    "series": "EQ",
    "isin": "INE002A01018",
    "currency": "INR"
  },
  "range": {
    "requested": "1y",
    "start": "2025-09-15",
    "end": "2026-09-15",
    "count": 248,
    "truncated": false
  },
  "prices": [
    {
      "date": "2025-09-16",
      "open": "284.00",
      "high": "287.10",
      "low": "282.40",
      "close": "286.02",
      "volume": 4900000,
      "cumulative_price_factor": "0.200000"
    }
  ],
  "metadata": {
    "data_type": "end_of_day",
    "source": "NSE_UDIFF",
    "is_adjusted": true,
    "requested_price_mode": "split_adjusted",
    "returned_price_mode": "split_adjusted",
    "adjustment_version": "split_bonus_v1",
    "applied_action_count": 1,
    "adjustment_scope": "split_bonus_only",
    "disclaimer": "Adjusted for stock splits and bonus issues. Cash dividends and rights issues are excluded."
  }
}
```


---

## 4. Legacy Endpoints (Deprecated)

| Endpoint | Method | Status | Notes |
| :--- | :--- | :--- | :--- |
| `/api/research/<id>/financials` | `GET` | **Legacy / Deprecated** | Original Alpha Vantage live quote endpoint. Maintained for backward compatibility; replaced in UI by `/api/securities/<id>/market-data/latest`. |
| `/api/research/<id>/news` | `GET` | **Legacy / Deprecated** | Original Alpha Vantage news endpoint. Retained for historical record playback; UI no longer invokes this in Company Research. |

