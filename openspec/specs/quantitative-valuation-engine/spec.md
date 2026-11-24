# quantitative-valuation-engine Specification

## Purpose

Perform all fundamental valuation, comparable-company multiples, and earnings quality calculations deterministically in pure Python so that no financial math is delegated to a language model.

## Requirements

### Requirement: Five-year unlevered DCF valuation
The system SHALL compute a 5-year unlevered Discounted Cash Flow (DCF) intrinsic value per share using a conservative growth rate derived from 3-year historical revenue growth (clamped to a default floor of 2% and cap of 15%), a configurable WACC (default 9.5%), and a configurable Gordon Growth terminal growth rate (default 2.5%), bridging Enterprise Value to Equity Value via `EV + cash_and_equivalents - total_debt` and dividing by `shares_outstanding`.

#### Scenario: Standard positive FCF DCF calculation
- **WHEN** given a valid financial snapshot with positive TTM free cash flow, positive shares outstanding, and `wacc > terminal_growth_rate`
- **THEN** the system projects 5 annual unlevered free cash flows, discounts each cash flow and the Gordon Growth terminal value at WACC, bridges Enterprise Value to Equity Value, divides by shares outstanding to produce `dcf_intrinsic_value_per_share`, computes `dcf_upside_pct` relative to `current_price`, and records `wacc`, `terminal_growth_rate`, `projection_years`, and `fcf_cagr` in `dcf_assumptions`

#### Scenario: Growth rate clamping at bounds
- **WHEN** the target company's 3-year historical revenue growth exceeds 15% or falls below 2%
- **THEN** the projected FCF growth rate is capped at 15% or floored at 2% respectively, and the clamped rate is recorded as `fcf_cagr` in `dcf_assumptions`

#### Scenario: Invalid DCF parameters
- **WHEN** `wacc <= terminal_growth_rate`, `wacc <= 0`, or `shares_outstanding <= 0`
- **THEN** the system rejects the inputs with a descriptive validation error

#### Scenario: Non-positive base Free Cash Flow edge case
- **WHEN** the target company has zero or negative TTM free cash flow
- **THEN** the system handles the edge case deterministically without division-by-zero or unhandled exceptions, applying an explicit documented fallback or raising a structured domain error with clear diagnostic context

### Requirement: Comparable companies valuation analysis
The system SHALL compute peer group medians for `ev_to_ebitda` and `pe_ratio` while excluding `None` and non-positive outliers, and derive an implied share price from the available peer median multiples.

#### Scenario: Peer medians with missing and negative outliers
- **WHEN** peer comparables include a mix of valid positive multiples, `None` entries, and negative multiples
- **THEN** the system excludes all `None` and `<= 0` values before computing `peer_median_ev_ebitda` and `peer_median_pe`

#### Scenario: Implied share price from peer medians
- **WHEN** valid peer median multiples and positive corresponding target earnings/EBITDA metrics are available
- **THEN** the system computes `implied_value_by_comps` per share using the EV/EBITDA equity bridge (`(peer_median_ev_ebitda * ebitda_ttm + cash_and_equivalents - total_debt) / shares_outstanding`) and/or P/E implied share price (`peer_median_pe * (net_income_ttm / shares_outstanding)`), averaging available implied values when both are valid

#### Scenario: No valid peer multiples available
- **WHEN** every peer comparable has `None` or non-positive values for a multiple
- **THEN** the system sets the corresponding peer median to `None` and sets `implied_value_by_comps` to `None` if no valid implied price can be derived

### Requirement: Earnings quality diagnostics
The system SHALL compute the cash conversion ratio (`ocf_to_net_income_ratio`), the accrual ratio (`accrual_ratio`), and a categorical `earnings_quality_flag` (`"High"`, `"Moderate"`, or `"Low"`).

#### Scenario: Strong cash conversion and low accruals
- **WHEN** `ocf_to_net_income_ratio >= 1.0` and `accrual_ratio <= 0.05` (with positive net income)
- **THEN** the system classifies `earnings_quality_flag` as `"High"`

#### Scenario: Weak cash conversion flagged as concern
- **WHEN** `ocf_to_net_income_ratio < 0.8` or net income is non-positive alongside weak/negative cash conversion
- **THEN** the system flags an earnings quality concern (`"Low"` when `ocf_to_net_income_ratio < 0.8` or high accruals, and `"Moderate"` for intermediate bands)

#### Scenario: Accrual ratio denominator fallback
- **WHEN** total assets are unavailable in the financial snapshot
- **THEN** the system computes `accrual_ratio` as `(net_income_ttm - operating_cash_flow_ttm) / enterprise_value` (provided `enterprise_value > 0`)
