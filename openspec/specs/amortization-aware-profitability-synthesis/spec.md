# amortization-aware-profitability-synthesis Specification

## Purpose

Ensure rendered investment memos display cash and EBITDA margins alongside GAAP profitability metrics and instruct narrative synthesis to contextualize M&A intangible amortization gaps rather than misdiagnosing cash-generative businesses as operationally deteriorating, while maintaining strict zero-hallucination guarantees.

## Requirements

### Requirement: Profitability header ribbon includes EBITDA and FCF margins
The rendered Markdown memo's `Profitability & Cash Quality` header ribbon SHALL display `*EBITDA Margin:* XX.X% | *FCF Margin:* XX.X%` alongside Gross Margin, Operating Margin, ROIC, SBC-Adjusted FCF, OCF/NI, Accrual Ratio, and DSO/DIO, while keeping total rendered memo length within the 750-word one-page ceiling.

#### Scenario: Rendered Profitability ribbon shows EBITDA and FCF margins
- **WHEN** a memo is rendered for a snapshot with `ebitda_margin_ttm = 0.625` and `fcf_margin_ttm = 0.440`
- **THEN** the `Profitability & Cash Quality` header ribbon contains `*EBITDA Margin:* 62.5% | *FCF Margin:* 44.0%` and total rendered word count remains at or below 750 words

#### Scenario: Missing margin metrics render N/A cleanly
- **WHEN** a memo is rendered for a snapshot whose `ebitda_margin_ttm` or `fcf_margin_ttm` is `None`
- **THEN** the corresponding ribbon fields display `N/A` without failing rendering

### Requirement: Amortization-aware profitability synthesis rule
When `ebitda_margin_ttm` exceeds `operating_margin_ttm` by more than 15 percentage points (`> 0.15`), the synthesis prompt and deterministic offline synthesizer SHALL explicitly contextualize cash-flow margin durability (`ebitda_margin_ttm` and `fcf_margin_ttm`) and attribute the GAAP operating margin gap to non-cash amortization/D&A rather than framing GAAP operating margin alone as operational deterioration.

#### Scenario: Large EBITDA-to-Operating margin spread triggers amortization context
- **WHEN** a target equity has `ebitda_margin_ttm - operating_margin_ttm > 0.15`
- **THEN** the LLM synthesis instructions explicitly flag the amortization spread and the offline deterministic synthesizer highlights cash-flow durability via EBITDA and FCF margins rather than characterizing GAAP operating margin as operational collapse

#### Scenario: Grounding audit and anti-echoing guarantees remain enforced
- **WHEN** synthesized prose cites `ebitda_margin_ttm`, `fcf_margin_ttm`, or quarterly fiscal year labels present in the Audit Trail JSON
- **THEN** numeric grounding verification passes with zero unverified literals, opening-sentence ribbon echoing remains prohibited, and any invented numeric literal continues to fail validation
