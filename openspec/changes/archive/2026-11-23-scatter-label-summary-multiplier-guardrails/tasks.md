## 1. Peer Scatter Reference Label Polish

- [x] 1.1 Update `build_peer_valuation_scatter(...)` in `fundamental_memo/src/fundamental_memo/charts.py` to set `annotation_position="top left"` and `annotation_font_size=11` on the `Peer Median` horizontal line; verify via unit tests in `tests/test_charts.py` asserting left-aligned paper anchor (`xanchor == "left"`, `x == 0`) and font size `11`.

## 2. Richer Multi-Sentence Business Summary

- [x] 2.1 Update `sanitize_business_summary(...)` in `fundamental_memo/src/fundamental_memo/data_fetcher.py` (and docstring in `schemas.py`) to default to `max_sentences=4, max_chars=700` with greedy complete-sentence accumulation, expand bundled mock summaries in `fixtures/mock_market_data.json` and `fixtures/mock_watchlist_profiles.json` to 3 segment-rich sentences, and verify via unit tests in `tests/test_data_fetcher.py` covering 4-sentence retention, 3-sentence greedy fit when 4 exceed 700 chars, ellipsis fallback when sentence 1 exceeds 700 chars, and 3-sentence mock profiles.

## 3. Reverse DCF Multiplier Noun Guardrail

- [x] 3.1 Update `fundamental_memo/src/fundamental_memo/memo_synthesizer.py` to add the explicit multiplier noun qualification rule to `SYSTEM_PROMPT` and implement `check_multiplier_noun_alignment(...)` inside `verify_memo_grounding_and_repetition(...)` flagging swapped `implied_y5_fcf_multiple` (`x revenue`) or `implied_y5_fcf_vs_current_revenue` (`x current FCF`) nouns when the two ratios differ; verify via unit tests in `tests/test_synthesizer_and_renderer.py` covering swapped-noun detection, properly qualified acceptance, and identical-ratio immunity.

## 4. Verification

- [x] 4.1 Run full quality gates (`ruff check src tests`, `mypy src tests`, `pytest -v`) inside `fundamental_memo/.venv` and confirm all unit and E2E tests pass cleanly.
