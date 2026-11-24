## Context

See [proposal.md](proposal.md) for motivation and scope. All three changes are surgical refinements to existing modules:
1. `charts.py:build_peer_valuation_scatter` currently calls `fig.add_hline(..., annotation_position="top right")`.
2. `data_fetcher.py:sanitize_business_summary` currently defaults to `max_sentences=2, max_chars=450` and falls straight back to `sentences[0]` if `sentences[:2]` exceeds `max_chars`.
3. `memo_synthesizer.py:verify_memo_grounding_and_repetition` already validates numeric grounding, Single-Mention, and opening-sentence anti-echoing, and is the single chokepoint called during LLM retry loops and `render_investment_memo`.

## Goals / Non-Goals

**Goals:**
- Prevent the Peer Median label from colliding with high-growth bubbles on the right side of the scatter chart.
- Greedily retain up to 4 complete sentences (within 700 characters) in `business_summary` across live and offline profiles, preserving grounding whitelisting.
- Catch swapped Reverse DCF multiplier nouns (`implied_y5_fcf_multiple` paired with `"revenue"`, or `implied_y5_fcf_vs_current_revenue` paired with `"current FCF"`) deterministically during synthesis and rendering.

**Non-Goals:**
- Changing chart dimensions, color palettes, or DCF formulas.
- Modifying the 750-word memo ceiling or Pydantic schema contracts.

## Decisions

### 1. Peer Scatter `top left` annotation (`charts.py`)
- **Decision**: Change `annotation_position="top right"` to `annotation_position="top left"` and pass `annotation_font_size=11` in `build_peer_valuation_scatter(...)`.
- **Rationale**: In `Peer Valuation vs. Growth`, high-growth mega-cap peers (`NVDA`) occupy the right side of the X-axis while the left margin near `x=0` has ample whitespace above the median line.

### 2. Greedy Multi-Sentence Business Summary (`data_fetcher.py`, `schemas.py`, fixtures)
- **Decision**: Change `sanitize_business_summary` signature defaults to `max_sentences: int = 4, max_chars: int = 700`, and iterate over `sentences[:max_sentences]` appending each complete sentence while `len(candidate) <= max_chars` (falling back to ellipsis word-boundary truncation only when even `sentences[0]` exceeds `max_chars`). Update `FinancialSnapshot.business_summary` field docstring in `schemas.py` and expand the bundled mock summaries in `mock_market_data.json` and `mock_watchlist_profiles.json` to 3 concise sentences covering core operating segments.
- **Rationale**: Greedy accumulation ensures that a 3-sentence description of 620 chars is preserved in full even if a 4th sentence would push the length to 780 chars, fixing the previous 1-sentence collapse bug.

### 3. Deterministic Multiplier Noun Guardrail (`memo_synthesizer.py`)
- **Decision**:
  - Append to `SYSTEM_PROMPT`: `"When citing Reverse DCF Year-5 FCF multiples, always distinguish implied_y5_fcf_multiple ('X.Xx current FCF') from implied_y5_fcf_vs_current_revenue ('X.Xx current revenue') — never swap their nouns."`
  - Implement helper `check_multiplier_noun_alignment(section_texts: Mapping[str, str], valuation: ValuationAnalysis) -> list[str]` invoked inside `verify_memo_grounding_and_repetition(...)`:
    - Skip when `implied_y5_fcf_multiple is None`.
    - Check whether `implied_y5_fcf_multiple` is distinct from `implied_y5_fcf_vs_current_revenue` (`rev_ratio is None or abs(fcf_mult - rev_ratio) > 0.05`).
    - Match formatted 1- or 2-decimal variants (`f"{val:.2f}"`, `f"{val:.1f}"`, and integer if exact) followed by `[x×]\s*(?:current\s+|ttm\s+|annual\s+)?revenue\b` (case-insensitive) and emit a clear violation instructing the model to qualify it as `current FCF` instead of `current revenue`.
    - Symmetrically, when `implied_y5_fcf_vs_current_revenue` is distinct and non-null, flag if its value is immediately followed by `[x×]\s*(?:current\s+|ttm\s+)?(?:fcf|free\s+cash\s+flow)\b`.
- **Rationale**: Wiring this check directly into `verify_memo_grounding_and_repetition(...)` means local LLMs automatically self-correct on retry if they swap nouns, while `render_investment_memo(...)` enforces it deterministically as a final gate.

## Risks / Trade-offs

- **[Risk] False positive when `implied_y5_fcf_multiple` happens to equal `implied_y5_fcf_vs_current_revenue` (e.g., 100% FCF margin)** → **Mitigation**: Guard the check with `abs(fcf_mult - rev_ratio) > 0.05` so identical ratios never trigger false positives.
- **[Risk] Slightly longer `business_summary` in the LLM prompt (+250 chars)** → **Mitigation**: Negligible (~60 tokens) relative to context windows of all local models while substantially improving segment specificity in Bull/Bear cases.
