## Why

Three final polish opportunities remain before closing out the Equity Fundamental Memo Generator: the `Peer Median` line label on the right edge of the Peer Valuation vs. Growth scatter chart can overlap high-growth peer bubbles such as `NVDA`; truncating `business_summary` to 2 sentences (or falling back to 1 sentence above 450 characters) omits segment-specific drivers (`Data Center`, `Client`, `Embedded`, `Services`); and LLMs can occasionally swap nouns when quoting Reverse DCF Year-5 FCF multiples (`X.Xx current FCF` vs. `X.Xx current revenue`). Addressing all three delivers crisp chart legibility, richer segment grounding, and airtight multiplier noun accuracy.

## What Changes

- **Peer Scatter Reference Label Positioning (`charts.py`)**:
  - Move the `Peer Median` horizontal reference line label (`fig.add_hline`) in `build_peer_valuation_scatter(...)` from `top right` to `top left` with `annotation_font_size=11`, placing it cleanly in the low-growth left margin away from high-growth peer bubbles.
- **Multi-Sentence Business Summary (`data_fetcher.py`, `schemas.py`, `fixtures/mock_market_data.json`, `fixtures/mock_watchlist_profiles.json`)**:
  - Expand `sanitize_business_summary(...)` defaults to `max_sentences=4` and `max_chars=700`, greedily retaining as many complete sentences as fit within 700 characters (typically 3–4 sentences) instead of falling back to only 1 sentence when the combined string exceeds the character ceiling.
  - Keep numeric grounding whitelisting active for every numeric token inside the expanded `business_summary`.
  - Expand bundled offline mock `business_summary` fields (`AVGO`, `NVDA`, `AMD`, `MRVL`, `QCOM`) to 3 sentences detailing concrete operating segments and end markets.
- **Reverse DCF Multiplier Noun Guardrail (`memo_synthesizer.py`)**:
  - Add an explicit system-prompt rule requiring clear noun qualification distinguishing `implied_y5_fcf_multiple` (`"X.Xx current FCF"`) from `implied_y5_fcf_vs_current_revenue` (`"X.Xx current revenue"`), never swapping nouns.
  - Add a deterministic check inside `verify_memo_grounding_and_repetition(...)` (plus a dedicated helper `check_multiplier_noun_alignment(...)`) that flags any violation when a number matching `implied_y5_fcf_multiple` (when distinct from `implied_y5_fcf_vs_current_revenue`) is immediately followed by `"x current revenue"` / `"× current revenue"` / `"x revenue"` / `"× revenue"` (and symmetrically when `implied_y5_fcf_vs_current_revenue` is paired with `"current FCF"` / `"TTM FCF"`).

## Capabilities

### New Capabilities

- `scatter-label-positioning`: Place the Peer Valuation vs. Growth horizontal `Peer Median` annotation at `top left` (`font_size=11`) so it never collides with high-growth peer bubbles on the right side of the plot.
- `richer-business-summary`: Retain the first 3–4 complete sentences (up to 700 characters) of `business_summary` with full numeric grounding whitelisting and 3-sentence segment-rich offline mock profiles.
- `multiplier-noun-guardrails`: Enforce explicit Reverse DCF Year-5 FCF vs. current-revenue noun qualification in both LLM synthesis prompts and deterministic post-generation prose auditing.

### Modified Capabilities

<!-- None in openspec/specs/ yet (previous changes remain unarchived in openspec/changes/). -->

## Impact

- **Modified Modules**: `fundamental_memo/src/fundamental_memo/{charts.py,data_fetcher.py,schemas.py,memo_synthesizer.py}`, `fundamental_memo/src/fundamental_memo/fixtures/{mock_market_data.json,mock_watchlist_profiles.json}`, and `fundamental_memo/tests/{test_charts.py,test_data_fetcher.py,test_synthesizer_and_renderer.py}`.
- **Dependencies**: Zero new dependencies.
- **Backward Compatibility**: Fully additive and backward-compatible across schemas, charts, and pipelines.
