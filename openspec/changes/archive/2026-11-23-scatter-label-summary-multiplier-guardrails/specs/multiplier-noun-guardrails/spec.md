## Purpose

Prevent LLM synthesis from swapping the nouns attached to Reverse DCF Year-5 FCF multiples (`X.Xx current FCF` vs. `X.Xx current revenue`) through explicit prompt guidance and deterministic post-generation prose auditing.

## ADDED Requirements

### Requirement: Prompt distinguishes Year-5 FCF multiple from current-revenue ratio
The LLM synthesis system instructions SHALL explicitly require distinguishing `implied_y5_fcf_multiple` (`"X.Xx current FCF"`) from `implied_y5_fcf_vs_current_revenue` (`"X.Xx current revenue"`) and prohibit swapping their nouns.

#### Scenario: System prompt contains explicit multiplier noun qualification rule
- **WHEN** LLM synthesis instructions are prepared
- **THEN** the system prompt instructs the model to qualify `implied_y5_fcf_multiple` as a multiple of current FCF and `implied_y5_fcf_vs_current_revenue` as a multiple of current revenue without swapping nouns

### Requirement: Deterministic auditor catches swapped Reverse DCF multiplier nouns
When `implied_y5_fcf_multiple` and `implied_y5_fcf_vs_current_revenue` are distinct, the post-generation prose auditor SHALL flag a validation violation if a numeric literal matching `implied_y5_fcf_multiple` is immediately followed by `"x current revenue"`, `"× current revenue"`, `"x revenue"`, or `"× revenue"` (and symmetrically if `implied_y5_fcf_vs_current_revenue` is immediately followed by `"x current FCF"` or `"× current FCF"`).

#### Scenario: Swapped FCF multiple labeled as revenue fails audit
- **WHEN** a valuation has `implied_y5_fcf_multiple = 3.50` and `implied_y5_fcf_vs_current_revenue = 1.42`, and generated prose states `"requiring 3.5x current revenue in Year 5"`
- **THEN** the prose auditor reports a multiplier noun mismatch violation so the LLM synthesizer retries and corrects the phrasing

#### Scenario: Correctly qualified FCF multiple and revenue ratio pass audit
- **WHEN** generated prose states `"requiring 3.5x current FCF (1.42x current revenue)"`
- **THEN** the multiplier noun check reports zero violations
