## Purpose

Provide deterministic trailing EBITDA margin, trailing Free Cash Flow margin, and a 4-quarter recent operational trajectory on the financial snapshot across both live market data and offline mock runs so analysts can distinguish cash-flow durability from non-cash accounting amortization and monitor recent sequential momentum.

## ADDED Requirements

### Requirement: Deterministic EBITDA and FCF margin computation
The financial snapshot SHALL expose `ebitda_margin_ttm` (`ebitda_ttm / revenue_ttm`) and `fcf_margin_ttm` (`free_cash_flow_ttm / revenue_ttm`) whenever trailing twelve-month revenue is strictly positive, and SHALL fall back cleanly to `None` when trailing revenue is zero or negative.

#### Scenario: Positive trailing revenue computes both margins deterministically
- **WHEN** a financial snapshot is constructed with `revenue_ttm = 50_000_000_000`, `ebitda_ttm = 30_000_000_000`, and `free_cash_flow_ttm = 20_000_000_000`
- **THEN** `ebitda_margin_ttm` equals `0.60` and `fcf_margin_ttm` equals `0.40`

#### Scenario: Non-positive trailing revenue falls back safely
- **WHEN** a financial snapshot is constructed with `revenue_ttm <= 0`
- **THEN** both `ebitda_margin_ttm` and `fcf_margin_ttm` are `None` without raising a division error

### Requirement: Recent 4-quarter operational trajectory extraction
The data ingestion layer SHALL extract up to the 4 most recent completed fiscal quarters ordered chronologically from oldest to newest into `quarterly_trajectory`, recording for each quarter its period label (e.g., `"2025-Q3"`), revenue, gross margin, operating margin, and free cash flow, with graceful `None` fallbacks for missing optional quarterly fields.

#### Scenario: Live quarterly financial statements populate 4 chronological quarters
- **WHEN** live quarterly income statement and cash flow tables contain 4 or more completed fiscal quarters with revenue, gross profit, operating income, and free cash flow (or operating cash flow and CapEx)
- **THEN** `quarterly_trajectory` contains exactly 4 entries ordered oldest to newest, each populated with a `YYYY-Q#` period label, positive revenue, computed gross margin and operating margin ratios, and free cash flow

#### Scenario: Missing quarterly Free Cash Flow falls back to OCF minus CapEx
- **WHEN** a quarterly cash flow statement omits a dedicated Free Cash Flow line item but provides Operating Cash Flow and Capital Expenditure
- **THEN** quarterly `free_cash_flow` is deterministically computed as `operating_cash_flow - abs(capex)`

#### Scenario: Unavailable quarterly statements degrade gracefully
- **WHEN** quarterly income or cash flow statements are empty or unavailable for a ticker
- **THEN** `quarterly_trajectory` defaults to an empty list without failing the analysis pipeline

### Requirement: Offline mock fixtures include realistic 4-quarter sequences
The bundled offline mock market dataset SHALL include realistic 4-quarter `quarterly_trajectory` sequences alongside full TTM metrics so `Use Offline Mock Data` runs deterministically end-to-end without network calls.

#### Scenario: Offline mock mode returns populated margins and 4-quarter history
- **WHEN** an analysis is executed with `Use Offline Mock Data` enabled for a supported mock ticker
- **THEN** the returned snapshot contains non-null `ebitda_margin_ttm`, `fcf_margin_ttm`, and 4 chronological entries in `quarterly_trajectory`
