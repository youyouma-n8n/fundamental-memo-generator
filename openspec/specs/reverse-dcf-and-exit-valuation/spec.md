# reverse-dcf-and-exit-valuation Specification

## Purpose

Extend the deterministic quantitative valuation engine with a Reverse DCF solver for market-implied growth expectations, configurable FCF CAGR and Exit EV/EBITDA Multiple cross-checks, peer growth metrics, and peer valuation percentile ranges.

## Requirements

### Requirement: Reverse DCF market-implied growth solver
The system SHALL solve deterministically for the 5-year FCF CAGR `implied_fcf_cagr_5y` over the search domain `[-0.20, 1.00]` such that evaluating the forward 5-year unlevered DCF model at `(implied_fcf_cagr_5y, wacc, terminal_growth_rate)` reproduces `current_price` within `±$0.01`, and SHALL compute `cagr_spread_vs_base` as `implied_fcf_cagr_5y - base_fcf_cagr`.

#### Scenario: Reverse DCF round-trip accuracy
- **WHEN** a target snapshot has positive TTM free cash flow and a `current_price` bracketed by the DCF valuations at `-20%` and `+100%` 5-year FCF CAGR
- **THEN** plugging `implied_fcf_cagr_5y` back into the forward DCF calculation produces an intrinsic value per share within `±$0.01` of `current_price`, and `cagr_spread_vs_base` equals `implied_fcf_cagr_5y - base_fcf_cagr`

#### Scenario: Market price outside solver bracket
- **WHEN** the target's `current_price` lies below the DCF value at `-20%` CAGR or above the DCF value at `+100%` CAGR
- **THEN** the system sets `implied_fcf_cagr_5y` and `cagr_spread_vs_base` to `None` rather than raising an unhandled root-finding error or extrapolating outside bounds

### Requirement: Configurable base FCF CAGR and Terminal Exit EV/EBITDA Multiple DCF
The system SHALL accept an optional explicit `base_fcf_cagr` override (falling back to historical 3-year revenue growth clamped to `[0.02, 0.15]` when omitted) and a configurable `target_exit_ev_ebitda` multiple (default `15.0`), and SHALL compute `exit_multiple_dcf_value` by projecting 5-year cash flows and Terminal Year EBITDA, discounting the explicit FCFs and `Terminal Year EBITDA * target_exit_ev_ebitda` back at `wacc`, adding `net_cash` (`cash_and_equivalents - total_debt`), and dividing by `shares_outstanding`.

#### Scenario: Explicit FCF CAGR and exit multiple cross-check
- **WHEN** a caller supplies `base_fcf_cagr` and `target_exit_ev_ebitda > 0` for a company with positive `ebitda_ttm`
- **THEN** the forward perpetuity DCF uses the supplied `base_fcf_cagr`, records `fcf_cagr` and `target_exit_ev_ebitda` in `dcf_assumptions`, and computes a deterministic `exit_multiple_dcf_value` per share

#### Scenario: Non-positive EBITDA disables exit multiple valuation
- **WHEN** `ebitda_ttm <= 0` or `target_exit_ev_ebitda <= 0`
- **THEN** the system sets `exit_multiple_dcf_value` to `None` without failing the rest of the valuation analysis

### Requirement: Peer growth metrics and comps percentile valuation range
The system SHALL enrich each peer comparable with `revenue_growth_3y` (or YoY growth fallback), `market_cap`, and `fcf_yield`, and SHALL compute the 25th and 75th percentile peer-implied share price range (`peer_comps_p25_value`, `peer_comps_p75_value`) from valid positive peer multiples to support the Valuation Football Field.

#### Scenario: Peer comps 25th to 75th percentile range calculation
- **WHEN** two or more peers have valid positive EV/EBITDA or P/E multiples
- **THEN** the system computes per-peer implied target share prices and records `peer_comps_p25_value <= peer_comps_p75_value` in `ValuationAnalysis`

#### Scenario: Insufficient valid peer multiples for range
- **WHEN** fewer than one valid positive peer multiple exists
- **THEN** the system sets `peer_comps_p25_value` and `peer_comps_p75_value` to `None`
