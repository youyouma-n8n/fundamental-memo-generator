# valuation-rigor-and-sensitivity-matrix Specification

## Purpose

Ensure accounting self-consistency for Enterprise Value, expose the Perpetuity DCF's implied exit EV/EBITDA multiple and a 5×5 WACC × FCF CAGR DCF sensitivity matrix, and ingest concise sanitized business descriptions for qualitative grounding across live and offline modes.

## Requirements

### Requirement: Self-consistent Enterprise Value calculation
The system SHALL deterministically compute `enterprise_value` as `market_cap + total_debt - cash_and_equivalents` rather than accepting external API `enterpriseValue` values, and SHALL compute `target_multiples.ev_to_ebitda` from that self-consistent `enterprise_value`.

#### Scenario: Mismatched upstream enterpriseValue overridden
- **WHEN** an upstream market data source returns an `enterpriseValue` that differs from `market_cap + total_debt - cash_and_equivalents`
- **THEN** the system discards the raw API `enterpriseValue`, sets `enterprise_value = market_cap + total_debt - cash_and_equivalents` to the exact dollar in the Audit Trail JSON, and computes `target_multiples.ev_to_ebitda` from the recomputed value

#### Scenario: Offline mock fixture preserves exact EV identity
- **WHEN** the pipeline runs in offline mock mode
- **THEN** `snapshot.enterprise_value` equals `snapshot.market_cap + snapshot.total_debt - snapshot.cash_and_equivalents` to the exact dollar

### Requirement: Perpetuity-implied exit EV/EBITDA multiple
The system SHALL compute `implied_exit_ev_ebitda` from the 5-year Perpetuity Growth DCF as `Terminal Value_{t=5} / EBITDA_{t=5}` (where `EBITDA_{t=5}` compounds from `ebitda_ttm` over 5 years at the base `fcf_cagr`) and expose it in `ValuationAnalysis`.

#### Scenario: Positive EBITDA yields implied exit multiple
- **WHEN** `ebitda_ttm > 0` and a valid 5-year Perpetuity DCF is computed
- **THEN** `ValuationAnalysis.implied_exit_ev_ebitda` equals `terminal_value_year_5 / (ebitda_ttm * (1 + base_fcf_cagr) ** 5)`

#### Scenario: Non-positive EBITDA handled gracefully
- **WHEN** `ebitda_ttm <= 0`
- **THEN** `ValuationAnalysis.implied_exit_ev_ebitda` is set to `None` without raising an error

### Requirement: Five-by-five DCF sensitivity matrix
The system SHALL generate a deterministic 5×5 `dcf_sensitivity_matrix` stored in `ValuationAnalysis` as `{ "wacc_values": [...], "cagr_values": [...], "grid": [[...]] }` spanning WACC columns `[base_wacc - 0.010, base_wacc - 0.005, base_wacc, base_wacc + 0.005, base_wacc + 0.010]` and 5Y FCF CAGR rows `[base_cagr - 0.05, base_cagr - 0.025, base_cagr, base_cagr + 0.025, base_cagr + 0.05]` clamped at `>= 0.0`.

#### Scenario: Center cell matches headline DCF intrinsic value
- **WHEN** `dcf_sensitivity_matrix` is computed for any valid DCF configuration with `base_cagr >= 0.0`
- **THEN** the matrix has 5 CAGR rows and 5 WACC columns, and the center cell `grid[2][2]` equals `dcf_intrinsic_value_per_share`

#### Scenario: Low base CAGR clamped at zero floor
- **WHEN** `base_cagr < 0.05`
- **THEN** any CAGR row offset that would fall below `0.0` is clamped to `0.0`, and cells where `wacc <= terminal_growth_rate` are recorded as `None` without failing

### Requirement: Sanitized business summary ingestion
The system SHALL ingest `longBusinessSummary` from upstream market metadata, truncate cleanly to at most the first 2 sentences and at most 450 characters as `financial_snapshot.business_summary`, and include a realistic 2-sentence `business_summary` in the offline mock fixture.

#### Scenario: Long business summary truncated cleanly
- **WHEN** upstream data provides a multi-paragraph `longBusinessSummary` exceeding 2 sentences or 450 characters
- **THEN** the system stores at most the first 2 sentences capped at 450 characters without mid-word truncation

#### Scenario: Missing business summary handled gracefully
- **WHEN** upstream data omits `longBusinessSummary`
- **THEN** `financial_snapshot.business_summary` is set to `None` without failing ingestion
