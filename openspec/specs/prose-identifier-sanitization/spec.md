# prose-identifier-sanitization Specification

## Purpose

Guarantee that rendered investment memo prose in both Markdown and standalone HTML exports reads in clean institutional financial English and never exposes raw Audit Trail JSON `snake_case` field identifiers.

## Requirements

### Requirement: LLM synthesis prompt prohibits raw JSON field identifiers
The LLM synthesis instructions SHALL explicitly forbid emitting raw `snake_case` JSON variable names (such as `pe_compression_pct`, `analyst_target_mean`, `ocf_to_net_income_ratio`, or `implied_fcf_cagr_5y`) in any memo prose section and SHALL instruct the model to translate them into natural institutional financial English.

#### Scenario: Synthesis system instructions include explicit identifier ban
- **WHEN** the LLM synthesis prompt is constructed for any equity analysis
- **THEN** the prompt explicitly instructs the model never to output raw `snake_case` JSON keys and provides natural English phrasing examples

### Requirement: Deterministic post-check sanitizer eliminates leaked snake_case JSON keys
Before final grounding verification and Markdown/HTML rendering, a deterministic prose sanitizer SHALL scan all generated narrative sections for `snake_case` Audit Trail JSON identifiers matching `\b[a-z]+(?:_[a-z0-9]+){1,}\b` and replace any matched identifier via a human-readable institutional alias map (while preserving normal English words, tickers, and numeric literals unchanged).

#### Scenario: Leaked Audit Trail identifiers are replaced with natural financial English
- **WHEN** generated prose contains raw JSON keys such as `pe_compression_pct`, `analyst_target_mean`, `implied_fcf_cagr_5y`, or `ocf_to_net_income_ratio`
- **THEN** the deterministic sanitizer replaces every leaked key with its natural institutional phrase (e.g., `forward P/E compression`, `consensus target price`, `market-implied 5-year FCF CAGR`, `OCF-to-Net-Income ratio`) so zero raw `snake_case` Audit Trail keys remain in the rendered Markdown memo or standalone HTML report

#### Scenario: Non-identifier prose and grounding verification remain intact
- **WHEN** the sanitizer processes a memo containing valid institutional prose, tickers, percentages, and dollar figures
- **THEN** no numeric values are altered, `Grounding Audit: Passed` remains enforced, and the rendered memo stays within the 750-word ceiling
