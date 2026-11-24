## Purpose

Ensure trailing twelve-month (TTM) financial flow totals and every downstream profitability, capital-efficiency, and valuation metric reconcile mathematically with the exact sum of the last 4 completed fiscal quarters whenever 4 quarters are available, eliminating stale external API summary mismatches.

## ADDED Requirements

### Requirement: Four-quarter sum TTM reconciliation
When the 4 most recent completed fiscal quarters are available in `quarterly_trajectory`, the quantitative ingestion engine SHALL compute TTM flow totals directly from the exact sum of those 4 quarters—including `revenue_ttm`, `operating_income_ttm`, `ebitda_ttm` (falling back to summary `.info` EBITDA only if quarterly EBITDA is unavailable across any of the 4 quarters), `operating_cash_flow_ttm`, `capex_ttm` (sum of absolute quarterly CapEx), and `free_cash_flow_ttm` (`operating_cash_flow_ttm - capex_ttm`)—and SHALL derive all downstream TTM ratios (`gross_margin_ttm`, `operating_margin_ttm`, `ebitda_margin_ttm`, `fcf_margin_ttm`, `roic_ttm`, `ocf_to_net_income_ratio`, `implied_fcf_cagr_5y`, and `dcf_intrinsic_value_per_share`) from those reconciled TTM totals.

#### Scenario: Four complete quarters override mismatched API summary fields
- **WHEN** a ticker has 4 completed quarterly periods summing to `$303.0B` revenue, `$197.0B` operating income, `$105.0B` operating cash flow, and `$5.0B` CapEx while the provider `.info` summary reports stale or mismatched values (`$361.8B` revenue and 36.0% operating margin)
- **THEN** `revenue_ttm` equals exactly `$303.0B`, `operating_margin_ttm` equals `$197.0B / $303.0B` (~65.0%), `capex_ttm` equals `$5.0B`, `free_cash_flow_ttm` equals `$100.0B`, and `fcf_margin_ttm` equals `$100.0B / $303.0B`

#### Scenario: Missing quarterly EBITDA falls back cleanly to summary EBITDA
- **WHEN** 4 completed quarters provide revenue, operating income, operating cash flow, and CapEx, but quarterly EBITDA is unavailable for one or more quarters
- **THEN** revenue, operating margin, OCF, CapEx, and FCF are still reconciled from the 4-quarter sum while `ebitda_ttm` falls back cleanly to the provider summary EBITDA and `ebitda_margin_ttm` is computed against the reconciled `revenue_ttm`

#### Scenario: Fewer than 4 quarters falls back to provider summary fields
- **WHEN** a ticker has fewer than 4 completed quarters in `quarterly_trajectory` (such as a newly listed equity or missing quarterly statements)
- **THEN** TTM headline flow totals fall back to the provider `.info` / annual statement values without raising an error
