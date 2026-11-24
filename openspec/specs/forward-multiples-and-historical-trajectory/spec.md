# forward-multiples-and-historical-trajectory Specification

## Purpose

Ingest and deterministically compute Forward valuation multiples, Wall Street consensus target metrics, Reverse DCF Year-5 Free Cash Flow dollar magnitudes, and 3-year annual historical financial trajectories across both live market feeds and offline mock fixtures.

## Requirements

### Requirement: Forward multiples and Wall Street consensus target ingestion
The system SHALL ingest forward consensus fields (`forward_pe`, `forward_ev_ebitda` when derivable, `analyst_target_mean`, and `analyst_count`) with graceful `None` fallback, compute `pe_compression_pct = (forward_pe - pe_ratio) / pe_ratio` in `target_multiples` whenever both multiples are positive, ingest `forward_pe` per peer in `peer_comparables`, and compute `peer_median_forward_pe` in `ValuationAnalysis`.

#### Scenario: Forward P/E compression and peer median computed
- **WHEN** target trailing `pe_ratio`, target `forward_pe`, and positive peer `forward_pe` values are available
- **THEN** the system populates `target_multiples["forward_pe"]`, `target_multiples["pe_compression_pct"] = (forward_pe - pe_ratio) / pe_ratio`, `financial_snapshot.analyst_target_mean`, `financial_snapshot.analyst_count`, and `valuation_analysis.peer_median_forward_pe`

#### Scenario: Missing forward estimates handled gracefully
- **WHEN** upstream feeds omit `forwardPE`, `targetMeanPrice`, or `numberOfAnalystOpinions`
- **THEN** the system records `None` for the missing fields and sets `pe_compression_pct` to `None` without raising an error

### Requirement: Reverse DCF Year-5 FCF magnitude diagnostics
The system SHALL compute from `implied_fcf_cagr_5y` ($g_{\text{implied}}$):
- `implied_y5_fcf = free_cash_flow_ttm * (1 + g_implied) ** 5`
- `implied_y5_fcf_multiple = implied_y5_fcf / free_cash_flow_ttm`
- `implied_y5_fcf_vs_current_revenue = implied_y5_fcf / revenue_ttm` (when `revenue_ttm > 0`)

#### Scenario: Implied Year-5 FCF exact calculation
- **WHEN** `implied_fcf_cagr_5y` is solved for a company with positive TTM free cash flow and positive TTM revenue
- **THEN** `valuation_analysis.implied_y5_fcf` equals `free_cash_flow_ttm * (1 + implied_fcf_cagr_5y) ** 5` within `±$0.01B`, `implied_y5_fcf_multiple` equals `implied_y5_fcf / free_cash_flow_ttm`, and `implied_y5_fcf_vs_current_revenue` equals `implied_y5_fcf / revenue_ttm`

#### Scenario: Reverse DCF out of bounds sets Year-5 fields to None
- **WHEN** `implied_fcf_cagr_5y` is `None`
- **THEN** `implied_y5_fcf`, `implied_y5_fcf_multiple`, and `implied_y5_fcf_vs_current_revenue` are all set to `None`

### Requirement: Three-year annual historical trajectory extraction
The system SHALL extract up to the last 3 completed fiscal years ordered oldest to newest in `financial_snapshot.historical_trajectory`, where each entry contains `period`, `revenue`, `operating_margin` (optional if operating income unavailable), and `free_cash_flow` (optional if cash flow unavailable), and SHALL populate realistic 3-year historical sequences in the offline mock fixture.

#### Scenario: Three-year trajectory extracted in chronological order
- **WHEN** annual income statement and cash flow tables contain 3 or more completed fiscal years (or offline mock mode is enabled)
- **THEN** `financial_snapshot.historical_trajectory` contains 3 entries ordered oldest to newest with valid `period`, `revenue`, `operating_margin`, and `free_cash_flow` values

#### Scenario: Partial historical statements handled gracefully
- **WHEN** upstream annual statements contain fewer than 3 years or omit cash flow items for a historical year
- **THEN** the system returns the available chronological years with `None` for missing optional fields without failing ingestion
