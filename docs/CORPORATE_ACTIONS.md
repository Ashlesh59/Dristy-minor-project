# InvestIQ Corporate Actions & Split-Adjustment Specification (Phase 2C)

This document details the corporate action domain models, ingestion pipeline, ratio parsing logic, cumulative price/volume adjustment algorithms, versioning methodology, and manual review processes in InvestIQ.

---

## 1. Supported Corporate Action Types & Conventions

| Action Type | Code | Automatic Adjustment | Multiplier Formula | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Stock Split** | `stock_split` | **Yes** | $f = \frac{\text{New Face Value}}{\text{Old Face Value}}$ | Sub-divides share face value (e.g. 10 to 2 $\implies f = 0.2$). |
| **Bonus Issue** | `bonus` | **Yes** | $f = \frac{\text{Existing Shares}}{\text{Existing} + \text{Bonus}}$ | Issues free shares (e.g. 1:1 $\implies f = 1/2 = 0.5$). |
| **Cash Dividend** | `cash_dividend` | **No** (Stored only) | N/A | Excluded from price adjustments to preserve discrete capital gains. |
| **Rights Issue** | `rights_issue` | **No** (Manual review) | N/A | Requires Theoretical Ex-Rights Price (TERP) calculation. |
| **Buyback** | `buyback` | **No** (Manual review) | N/A | Capital reduction requiring tender price verification. |
| **Merger / Demerger**| `merger` / `demerger` | **No** (Manual review) | N/A | Structural spin-offs requiring asset carve-out allocation. |
| **Symbol Change** | `symbol_change` | **No** (Manual review) | N/A | Exchange instrument linkage review. |
| **Other / Ambiguous**| `other` | **No** (Manual review) | N/A | Ambiguous wording routed to human operator review. |

---

## 2. Ex-Date Boundary Rule

The **Ex-Date (`ex_date`)** is the exact calendar date on which a security begins trading on the exchange without the benefit of the announced corporate action:
- **Historical Trading Dates $t < \text{ex\_date}$:** Adjusted by the event multiplier ($P_{\text{adj}} = P_{\text{raw}} \times f$, $V_{\text{adj}} = V_{\text{raw}} \times \frac{1}{f}$).
- **Trading Dates $t \ge \text{ex\_date}$:** Not adjusted by this event ($f = 1.0$).

---

## 3. Cumulative Adjustment Factor Algorithm

When a security undergoes $K$ corporate actions with ex-dates $E_1 < E_2 < \dots < E_K$ and factors $f_1, f_2, \dots, f_K$:

For any historical trading date $D$:
$$\text{Cumulative Price Factor } F_{\text{price}}(D) = \prod_{k: D < E_k} f_k$$
$$\text{Cumulative Volume Factor } F_{\text{volume}}(D) = \frac{1}{F_{\text{price}}(D)} = \prod_{k: D < E_k} \frac{1}{f_k}$$

### Adjusted Price & Volume Formulas:
- $\text{Adjusted Open} = (\text{Raw Open} \times F_{\text{price}}(D)).\text{quantize}(\text{0.0001}, \text{ROUND\_HALF\_UP})$
- $\text{Adjusted High} = (\text{Raw High} \times F_{\text{price}}(D)).\text{quantize}(\text{0.0001}, \text{ROUND\_HALF\_UP})$
- $\text{Adjusted Low} = (\text{Raw Low} \times F_{\text{price}}(D)).\text{quantize}(\text{0.0001}, \text{ROUND\_HALF\_UP})$
- $\text{Adjusted Close} = (\text{Raw Close} \times F_{\text{price}}(D)).\text{quantize}(\text{0.0001}, \text{ROUND\_HALF\_UP})$
- $\text{Adjusted Volume} = \text{round}(\text{Raw Volume} \times F_{\text{volume}}(D))$

---

## 4. Hand-Calculated Examples

### Example 1: 5-for-1 Stock Split
- **Event:** Face value split from Rs 10 to Rs 2 on `2026-09-01`.
- **Multiplier:** $f = 2 / 10 = 0.20$.
- **Pre-Split Date (`2026-08-31`):** Raw Close = Rs 1,000.00, Raw Volume = 1,000 shares.
  - $\text{Adjusted Close} = 1000.00 \times 0.2 = \mathbf{200.0000}$
  - $\text{Adjusted Volume} = 1000 \times 5 = \mathbf{5000}$
- **Post-Split Date (`2026-09-01`):** Raw Close = Rs 204.00, Raw Volume = 5,200 shares.
  - $\text{Adjusted Close} = 204.00 \times 1.0 = \mathbf{204.0000}$
  - $\text{Adjusted Volume} = 5200 \times 1.0 = \mathbf{5200}$

### Example 2: Multi-Action Sequence (Bonus + Split)
- **Action 1:** Bonus 1:1 on `2026-08-01` ($f_1 = 0.5$).
- **Action 2:** Split 5:1 on `2026-09-01` ($f_2 = 0.2$).
- **Timeline Evaluation:**
  - $D < \text{Aug 01}$: $F(D) = 0.5 \times 0.2 = \mathbf{0.10}$ (e.g. Rs 2,000 raw $\implies$ Rs 200 adjusted).
  - $\text{Aug 01} \le D < \text{Sep 01}$: $F(D) = \mathbf{0.20}$ (e.g. Rs 1,000 raw $\implies$ Rs 200 adjusted).
  - $D \ge \text{Sep 01}$: $F(D) = \mathbf{1.00}$ (e.g. Rs 200 raw $\implies$ Rs 200 adjusted).

---

## 5. Storage & Adjustment Versioning

1. **Raw Database Invariance:** `daily_prices` table is ground truth and is **never** modified or overwritten.
2. **Derived Storage:** Adjusted prices are stored in `adjusted_daily_prices` referencing `daily_price_id` and `adjustment_version`.
3. **Deterministic Rebuild:** Running `rebuild_adjusted_prices` for version `split_bonus_v1` cleanly replaces existing derived records for that version without destroying raw data or other calculation versions.

---

## 6. CLI Management Commands

```bash
# Dry-run corporate actions import
python -m backend.cli.sync_corporate_actions --source nse --file data/raw/nse/CA.csv --dry-run

# Live corporate actions import
python -m backend.cli.sync_corporate_actions --source nse --file data/raw/nse/CA.csv

# Rebuild adjusted prices for a single security
python -m backend.cli.rebuild_adjusted_prices --security-id 1 --version split_bonus_v1

# Rebuild adjusted prices for all active securities
python -m backend.cli.rebuild_adjusted_prices --all --version split_bonus_v1
```
