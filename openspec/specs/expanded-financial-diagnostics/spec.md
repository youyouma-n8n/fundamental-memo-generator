# expanded-financial-diagnostics Specification

## Purpose

Expand deterministic financial statement ingestion and Audit Trail JSON metrics with institutional profitability margins, return on invested capital (ROIC), stock-based compensation adjusted free cash flow, net cash ratios, 52-week trading range, and working capital diagnostics across both live and offline fixture modes.

## Requirements

### Requirement: Profitability margins and ROIC diagnostics
The system SHALL deterministically compute and include `gross_margin_ttm` (`gross_profit_ttm / revenue_ttm`), `operating_margin_ttm` (`operating_income_ttm / revenue_ttm`), and `roic_ttm` (`nopat_ttm / invested_capital`, where `nopat_ttm = operating_income_ttm * (1 - effective_tax_rate)` using a `0.21` fallback tax rate when unavailable and `invested_capital = total_debt + total_equity - cash_and_equivalents`) in the financial snapshot and Audit Trail JSON.

#### Scenario: Complete financial inputs produce valid margins and ROIC
- **WHEN** positive revenue, gross profit, operating income, total debt, total equity, and cash are available
- **THEN** the system computes `gross_margin_ttm`, `operating_margin_ttm`, and `roic_ttm` deterministically in pure Python and includes them in the validated financial snapshot

#### Scenario: Missing or non-positive denominator handled gracefully
- **WHEN** `revenue_ttm <= 0`, `invested_capital <= 0`, or upstream inputs such as `gross_profit_ttm` or `total_equity` are unavailable
- **THEN** the system sets the affected ratio (`gross_margin_ttm`, `operating_margin_ttm`, or `roic_ttm`) to `None` without raising a division-by-zero error

#### Scenario: Missing effective tax rate uses fallback
- **WHEN** upstream financial statements omit an effective tax rate
- **THEN** the system uses `0.21` as the effective tax rate when computing `nopat_ttm` for `roic_ttm`

### Requirement: SBC-adjusted FCF, net cash, and 52-week range metrics
The system SHALL ingest and compute `sbc_ttm` (TTM stock-based compensation), `sbc_adjusted_fcf_ttm` (`free_cash_flow_ttm - sbc_ttm`), `net_cash` (`cash_and_equivalents - total_debt`), `net_cash_to_market_cap` (`net_cash / market_cap`), and the 52-week trading range (`52w_low`, `52w_high`).

#### Scenario: SBC-adjusted FCF and net cash calculation
- **WHEN** `free_cash_flow_ttm`, `sbc_ttm`, `cash_and_equivalents`, `total_debt`, and `market_cap` are present
- **THEN** the system computes `sbc_adjusted_fcf_ttm = free_cash_flow_ttm - sbc_ttm`, `net_cash = cash_and_equivalents - total_debt`, and `net_cash_to_market_cap = net_cash / market_cap`

#### Scenario: Missing stock-based compensation
- **WHEN** upstream data omits `sbc_ttm`
- **THEN** the system records `sbc_ttm` and `sbc_adjusted_fcf_ttm` as `None` rather than substituting an arbitrary estimate

### Requirement: Working capital decomposition and OCF-to-Net-Income gap driver
The system SHALL compute a `working_capital_metrics` structure containing `dso_days` (`(accounts_receivable / revenue_ttm) * 365`), `dio_days` (`(inventory / cost_of_revenue_ttm) * 365`), and a deterministic `ocf_net_income_gap_driver` classification comparing `capex_ttm`, `sbc_ttm`, and `change_in_working_capital` to explain why `ocf_to_net_income_ratio` deviates from `1.0x`.

#### Scenario: Working capital days computed from balance sheet and income items
- **WHEN** accounts receivable, inventory, revenue, and cost of revenue are available and denominators are positive
- **THEN** the system computes `dso_days` and `dio_days` deterministically and emits a non-empty `ocf_net_income_gap_driver` explanation

#### Scenario: Service or software company without inventory
- **WHEN** `inventory` is `None` or `cost_of_revenue_ttm <= 0`
- **THEN** the system sets `dio_days` to `None` while still computing `dso_days` and `ocf_net_income_gap_driver`

### Requirement: Offline mock fixture parity for expanded diagnostics
The system SHALL populate the bundled offline mock fixture with realistic, internally consistent values for all expanded financial diagnostics (including gross profit, operating income, total equity, effective tax rate, `sbc_ttm`, accounts receivable, inventory, cost of revenue, change in working capital, `52w_low`, and `52w_high`) so offline mode operates cleanly without network access.

#### Scenario: Offline mock mode returns populated expanded metrics
- **WHEN** the pipeline runs with offline mock mode enabled
- **THEN** the validated financial snapshot contains populated values for `gross_margin_ttm`, `operating_margin_ttm`, `roic_ttm`, `sbc_ttm`, `sbc_adjusted_fcf_ttm`, `net_cash`, `net_cash_to_market_cap`, `52w_low`, `52w_high`, and `working_capital_metrics` with zero external network calls
