## Purpose

Enforce a strict opening-sentence negative constraint preventing metric-ribbon echoing across analytical prose sections, require Forward vs. Trailing multiple compression synthesis, and preserve deterministic numeric grounding across all new Audit Trail fields.

## ADDED Requirements

### Requirement: Strict opening-sentence anti-echoing constraint
The system SHALL require that the opening sentence of both `valuation_and_debate` and `profitability_and_cash_quality` starts with an analytical mechanism, business driver, or valuation tension rather than opening by naming or citing metrics already printed in that section's header table or KPI ribbon, and SHALL verify this constraint deterministically during synthesis audit.

#### Scenario: Opening sentence repeating header ribbon rejected
- **WHEN** `profitability_and_cash_quality` opens with a header metric recitation such as `"Gross margin is 75.5% and operating margin 29.3%..."` or `valuation_and_debate` opens by reciting raw DCF/WACC inputs
- **THEN** the deterministic synthesis audit flags an opening-sentence anti-echoing violation and triggers retry feedback (or fails validation if retries are exhausted)

#### Scenario: Mechanism-led opening sentence accepted
- **WHEN** `valuation_and_debate` and `profitability_and_cash_quality` open with a business driver, valuation tension, or analytical mechanism (for example `"Broadcom's custom AI accelerator and infrastructure software mix underpins..."`)
- **THEN** the opening-sentence anti-echoing check passes cleanly

### Requirement: Forward vs. Trailing multiple compression and consensus synthesis
The system SHALL instruct LLM synthesis—and construct offline mock synthesis—so that `valuation_and_debate` explicitly compares trailing `pe_ratio` against `forward_pe` and `analyst_target_mean`, assessing whether forward earnings growth materially compresses the trailing valuation premium, and SHALL include Forward P/E and Consensus Target rows in the rendered Markdown valuation table.

#### Scenario: Forward P/E and consensus target synthesized and grounded
- **WHEN** `forward_pe`, `pe_compression_pct`, `analyst_target_mean`, `implied_y5_fcf`, and `historical_trajectory` are present in the Audit Trail JSON
- **THEN** `valuation_and_debate` references forward vs. trailing multiple normalization alongside consensus target framing, and `verify_memo_grounding_and_repetition` passes with zero unverified numbers
