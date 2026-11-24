# structured-debate-memo-synthesis Specification

## Purpose

Upgrade LLM memo synthesis and Markdown rendering to enforce a 6-section institutional structure featuring "The Debate / Variant Perception", strict anti-repetition rules, and an automated post-generation regex numeric grounding audit against the Audit Trail JSON.

## Requirements

### Requirement: Six-section InvestmentMemoSchema contract
The system SHALL enforce structured synthesis output matching `InvestmentMemoSchema` with strict word budgets targeting 550–700 words total:
1. `executive_thesis` (max 60 words): core stance, price vs. DCF/Comps spread, and primary catalyst/risk.
2. `valuation_and_debate` (max 150 words): compare Base DCF, Reverse DCF (`implied_fcf_cagr_5y`), and Peer Comps, explicitly explaining why the market prices the stock at a discount or premium.
3. `profitability_and_cash_quality` (max 120 words): analyze Gross/Operating Margins, ROIC, SBC-adjusted FCF, and explain the driver behind `ocf_to_net_income_ratio` and `accrual_ratio` using `ocf_net_income_gap_driver`.
4. `bull_case` (exact 3 bullets, max 90 words total): fundamental/operational upside drivers and margin/ROIC durability.
5. `bear_case` (exact 3 bullets, max 90 words total): multiple compression, growth deceleration vs. Reverse DCF expectations, and peer dispersion risks.
6. `key_downside_risks` (3 to 4 bullets, max 90 words total): actionable monitoring triggers.

#### Scenario: Valid six-section output passes validation
- **WHEN** a synthesized JSON payload satisfies all six field schemas, bullet counts, and per-section word budgets
- **THEN** validation succeeds and returns an `InvestmentMemoSchema` instance

#### Scenario: Oversized section or invalid bullet count rejected
- **WHEN** any narrative field exceeds its word budget (`60`, `150`, `120`, or `90` total words per bullet list) or fails bullet count constraints
- **THEN** schema validation rejects the payload with field-specific error details

### Requirement: Anti-repetition and Single-Mention Rule
The system SHALL enforce that headline valuation figures (`dcf_intrinsic_value_per_share`, `implied_value_by_comps`, and `implied_fcf_cagr_5y`) appear at most twice across the entire synthesized memo narrative (at most once in `executive_thesis` and once in `valuation_and_debate`), and SHALL forbid repeating exact DCF or Comps share price figures inside `bull_case` or `bear_case`.

#### Scenario: Headline valuation figure repeated in bull or bear case
- **WHEN** an LLM draft repeats the exact DCF intrinsic value or Comps implied share price inside `bull_case` or `bear_case`, or cites a headline valuation figure more than twice across the memo
- **THEN** validation rejects the draft with an explicit anti-repetition error message

### Requirement: Post-generation deterministic regex numeric grounding audit
The system SHALL run a deterministic regex numeric verifier over the generated narrative before rendering or displaying the memo, confirming that every numeric literal matches a value (or exact rounded/scaled representation) present in the Audit Trail JSON or approved model structural constants (such as projection horizon `5`, historical CAGR window `3`, or sensitivity step `100 bps`).

#### Scenario: Unverified number in LLM output rejected and retried
- **WHEN** an LLM response contains a numeric figure not traceable to the Audit Trail JSON
- **THEN** the verifier flags the unverified number(s), triggers the automatic retry loop with concrete corrective feedback (up to 2 retries), and raises a synthesis error if retries are exhausted

#### Scenario: Grounded offline mock memo passes grounding and anti-repetition audits
- **WHEN** offline mock synthesis generates a memo for a validated Audit Trail JSON
- **THEN** the output passes schema validation, the Single-Mention Rule, and the deterministic numeric grounding audit with zero violations

### Requirement: Updated one-page Markdown memo rendering and export
The system SHALL render the upgraded multi-section Markdown memo (Header Block, Executive Thesis, Valuation & The Debate with comps table and DCF/Exit Multiple/Reverse DCF summary, Profitability & Cash Quality, Bull Case vs. Bear Case, and Key Downside Risks), enforce a post-render word ceiling (`<= 750` words to accommodate the 550–700 word narrative target plus structured tables), and export cleanly as `memo_<TICKER>.md`.

#### Scenario: Upgraded memo renders cleanly under ceiling
- **WHEN** valid Audit Trail data and a grounded `InvestmentMemoSchema` are rendered
- **THEN** the rendered Markdown contains all required sections, passes the post-render word ceiling check, and exports cleanly via CLI `--output` and Streamlit download
