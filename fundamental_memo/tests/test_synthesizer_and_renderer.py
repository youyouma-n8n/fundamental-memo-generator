"""Unit tests for LLM retry, numeric grounding audit, Single-Mention rule, and renderer."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from openai import AuthenticationError, RateLimitError

from fundamental_memo.data_fetcher import load_mock_market_data
from fundamental_memo.deterministic_memo import GROQ_BASE_URL
from fundamental_memo.html_exporter import build_html_report
from fundamental_memo.memo_synthesizer import (
    SYSTEM_PROMPT,
    _count_formatted_value_mentions,
    build_synthesis_user_prompt,
    check_multiplier_noun_alignment,
    find_leaked_snake_case_identifiers,
    has_amortization_margin_gap,
    sanitize_memo_prose,
    synthesize_memo_with_llm,
    synthesize_mock_memo,
    verify_memo_grounding_and_repetition,
)
from fundamental_memo.renderer import render_investment_memo
from fundamental_memo.schemas import (
    GroundingAuditError,
    MemoWordLimitError,
    SynthesisError,
    count_words,
)
from fundamental_memo.valuation_engine import compute_dcf_sensitivity, run_valuation_analysis


class _FakeCompletions:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []
        self.kwargs_log: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.kwargs_log.append(dict(kwargs))
        messages = kwargs.get("messages")
        if isinstance(messages, list):
            self.calls.append(list(messages))
        content = self._responses.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


class _FakeOpenAIClient:
    def __init__(self, responses: list[str]) -> None:
        self.completions = _FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=self.completions)


def test_offline_mock_memo_passes_grounding_and_single_mention_audit() -> None:
    """Offline mock memo uses business drivers and passes grounding + anti-repetition audits."""
    bundle = load_mock_market_data()
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    memo = synthesize_mock_memo(bundle.snapshot, valuation, bundle.peers)
    violations = verify_memo_grounding_and_repetition(
        memo, bundle.snapshot, valuation, bundle.peers
    )
    assert violations == []
    # Business-grounded bull/bear cases cite segment drivers from business_summary
    assert any("custom AI accelerators" in bullet for bullet in memo.bull_case)
    assert any("custom AI accelerators" in bullet for bullet in memo.bear_case)
    assert "forward P/E" in memo.valuation_and_debate
    assert "$196.50" in memo.valuation_and_debate
    # Mock AVGO has 54.0% EBITDA margin vs 36.3% operating margin (>15pp spread)
    assert has_amortization_margin_gap(bundle.snapshot) is True
    assert "EBITDA margin" in memo.profitability_and_cash_quality
    assert "FCF margin" in memo.profitability_and_cash_quality
    assert "amortization" in memo.profitability_and_cash_quality.lower()

    prompt_text = build_synthesis_user_prompt(bundle.snapshot, valuation, bundle.peers)
    assert "CRITICAL AMORTIZATION NOTE" in prompt_text
    assert "ebitda_margin_ttm" in prompt_text
    assert "fcf_margin_ttm" in prompt_text


def test_anti_echoing_auditor_rejects_metric_first_opening_sentences() -> None:
    """Opening valuation_and_debate or profitability_and_cash_quality with header metrics fails."""
    bundle = load_mock_market_data()
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    valid_memo = synthesize_mock_memo(bundle.snapshot, valuation, bundle.peers)

    echo_profitability = valid_memo.model_copy(
        update={
            "profitability_and_cash_quality": (
                "Gross margin is 64.2% and operating margin is 36.3%, supporting High quality."
            )
        }
    )
    violations_prof = verify_memo_grounding_and_repetition(
        echo_profitability, bundle.snapshot, valuation, bundle.peers
    )
    assert any("Anti-echoing violation" in msg for msg in violations_prof)

    echo_valuation = valid_memo.model_copy(
        update={
            "valuation_and_debate": (
                "Base DCF yields $97.25 while peers imply $160.18."
            )
        }
    )
    violations_val = verify_memo_grounding_and_repetition(
        echo_valuation, bundle.snapshot, valuation, bundle.peers
    )
    assert any("Anti-echoing violation" in msg for msg in violations_val)


def test_grounding_auditor_whitelists_business_summary_qualitative_numbers() -> None:
    """Qualitative numeric terms in business_summary pass grounding without false positives."""
    bundle = load_mock_market_data()
    enriched_snapshot = bundle.snapshot.model_copy(
        update={
            "business_summary": (
                "Broadcom supplies 800G Ethernet switches and 3nm custom AI accelerators. "
                "It also delivers enterprise infrastructure software globally."
            )
        }
    )
    valuation = run_valuation_analysis(enriched_snapshot, bundle.peers)
    base_memo = synthesize_mock_memo(enriched_snapshot, valuation, bundle.peers)
    memo_with_spec = base_memo.model_copy(
        update={
            "bull_case": [
                "Leadership in 800G Ethernet switches and 3nm custom AI accelerators drives ROIC.",
                base_memo.bull_case[1],
                base_memo.bull_case[2],
            ]
        }
    )
    violations = verify_memo_grounding_and_repetition(
        memo_with_spec, enriched_snapshot, valuation, bundle.peers
    )
    assert violations == []


def test_grounding_verifier_flags_unverified_number_and_repetition() -> None:
    """Verifier catches fabricated numbers and repeated DCF share price in bull_case."""
    bundle = load_mock_market_data()
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    valid_memo = synthesize_mock_memo(bundle.snapshot, valuation, bundle.peers)

    hallucinated = valid_memo.model_copy(
        update={
            "executive_thesis": (
                "Broadcom trades at $170.00 versus fabricated target $249.99 with 77.7% margin."
            )
        }
    )
    hallucination_violations = verify_memo_grounding_and_repetition(
        hallucinated, bundle.snapshot, valuation, bundle.peers
    )
    assert any("Unverified numeric literals" in msg for msg in hallucination_violations)

    repeated_in_bull = valid_memo.model_copy(
        update={
            "bull_case": [
                f"Upside exceeds base DCF of ${valuation.dcf_intrinsic_value_per_share:,.2f}.",
                valid_memo.bull_case[1],
                valid_memo.bull_case[2],
            ]
        }
    )
    repetition_violations = verify_memo_grounding_and_repetition(
        repeated_in_bull, bundle.snapshot, valuation, bundle.peers
    )
    assert any("bull_case must not repeat" in msg for msg in repetition_violations)
    assert any(
        "Single-Mention violation" in msg and "bull_case: 1" in msg
        for msg in repetition_violations
    )


def test_single_mention_counter_distinguishes_multiples_from_percentages() -> None:
    """Forward P/E 28.2x never collides with 28.4% CAGR, and '100 bps' never collides with $100."""
    text = "Forward P/E is 28.2x (peers 28.25x), while Reverse DCF implies 28.4% CAGR."
    assert _count_formatted_value_mentions(text, 0.284, is_percentage=True) == 1
    assert _count_formatted_value_mentions("Target $97.25 vs 97.2% margin.", 97.25) == 1
    assert _count_formatted_value_mentions("A 100 bps WACC shift vs $100.28 comps.", 100.28) == 1


def test_llm_synthesizer_retries_on_grounding_failure_and_recovers() -> None:
    """Synthesizer retries after an unverified numeric literal and succeeds on attempt 2."""
    bundle = load_mock_market_data()
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    valid_output = synthesize_mock_memo(bundle.snapshot, valuation, bundle.peers)
    valid_json_fenced = f"```json\n{valid_output.model_dump_json()}\n```"

    bad_payload = valid_output.model_dump()
    bad_payload["executive_thesis"] = "Broadcom could surge to $333.33 on 88.8% margin expansion."

    fake_client = _FakeOpenAIClient([json.dumps(bad_payload), valid_json_fenced])
    result = synthesize_memo_with_llm(
        bundle.snapshot,
        valuation,
        bundle.peers,
        max_retries=2,
        client=fake_client,
    )

    assert result == valid_output
    assert len(fake_client.completions.calls) == 2
    assert fake_client.completions.kwargs_log[0]["reasoning_effort"] == "none"
    assert "Unverified numeric literals" in fake_client.completions.calls[1][-1]["content"]


def test_llm_synthesizer_uses_surgical_retry_on_word_limit_overflow() -> None:
    """Word-count overflow triggers a focused surgical trim instruction and recovers."""
    bundle = load_mock_market_data()
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    valid_output = synthesize_mock_memo(bundle.snapshot, valuation, bundle.peers)
    long_payload = valid_output.model_dump()
    long_payload["executive_thesis"] = " ".join(["thesis"] * 61)

    fake_client = _FakeOpenAIClient([json.dumps(long_payload), valid_output.model_dump_json()])
    result = synthesize_memo_with_llm(
        bundle.snapshot,
        valuation,
        bundle.peers,
        max_retries=2,
        client=fake_client,
    )
    assert result == valid_output
    assert len(fake_client.completions.calls) == 2
    retry_prompt = fake_client.completions.calls[1][-1]["content"]
    assert "word-count ceiling" in retry_prompt
    assert "at least 20 words shorter" in retry_prompt
    assert "currently 61 words" in retry_prompt


def test_llm_synthesizer_condenses_slight_bullet_word_overflow_losslessly() -> None:
    """A 91-word bear_case with verbose phrases condenses cleanly under 90 without a retry."""
    bundle = load_mock_market_data()
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    valid_output = synthesize_mock_memo(bundle.snapshot, valuation, bundle.peers)

    slightly_over_bear = [
        (
            "Demand risk across custom AI accelerators and Ethernet switches could slow "
            "trailing twelve-month free cash flow conversion compared to elevated market "
            "expectations and compress return on invested capital materially across cycles."
        ),
        (
            "Rising stock-based compensation and capital expenditures could weigh on "
            "operating cash flow compared with peers if hyperscale orders pause across "
            "enterprise networking and broadband carrier customers globally."
        ),
        (
            "Multiple compression risk persists because enterprise value to EBITDA sits at "
            "a premium versus peers while net cash remains deeply negative due to the fact that "
            "total debt stays elevated relative to liquid cash reserves."
        ),
    ]
    assert sum(len(b.split()) for b in slightly_over_bear) > 90
    over_payload = valid_output.model_dump()
    over_payload["bear_case"] = slightly_over_bear

    fake_client = _FakeOpenAIClient([json.dumps(over_payload)])
    result = synthesize_memo_with_llm(
        bundle.snapshot,
        valuation,
        bundle.peers,
        max_retries=2,
        client=fake_client,
    )
    assert len(fake_client.completions.calls) == 1
    assert sum(len(b.split()) for b in result.bear_case) <= 90
    assert any("FCF" in b for b in result.bear_case)
    assert any("SBC" in b for b in result.bear_case)


def test_llm_synthesizer_raises_grounding_error_when_retries_exhausted() -> None:
    """Exhausting retries on hallucinated numbers raises GroundingAuditError."""
    bundle = load_mock_market_data()
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    valid_output = synthesize_mock_memo(bundle.snapshot, valuation, bundle.peers)
    bad_payload = valid_output.model_dump()
    bad_payload["executive_thesis"] = "Target price $999.99 with 88.8% EBITDA margin."
    bad_json = json.dumps(bad_payload)

    fake_client = _FakeOpenAIClient([bad_json, bad_json, bad_json])
    with pytest.raises(GroundingAuditError, match="failed validation after 3 attempts"):
        synthesize_memo_with_llm(
            bundle.snapshot,
            valuation,
            bundle.peers,
            max_retries=2,
            client=fake_client,
        )


def test_llm_synthesizer_raises_synthesis_error_on_malformed_json() -> None:
    """Exhausting retries on malformed JSON raises SynthesisError."""
    bundle = load_mock_market_data()
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    fake_client = _FakeOpenAIClient(["not json", "still not json", "{}"])
    with pytest.raises(SynthesisError, match="failed validation after 3 attempts"):
        synthesize_memo_with_llm(
            bundle.snapshot,
            valuation,
            bundle.peers,
            max_retries=2,
            client=fake_client,
        )


def test_renderer_outputs_all_upgraded_sections_and_enforces_word_limit() -> None:
    """Verify rendered memo includes all upgraded sections and enforces word limit."""
    bundle = load_mock_market_data()
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    memo_output = synthesize_mock_memo(bundle.snapshot, valuation, bundle.peers)

    markdown = render_investment_memo(bundle.snapshot, valuation, bundle.peers, memo_output)
    words = count_words(markdown)
    assert 400 <= words <= 750
    for expected_heading in (
        "# Investment Memo: Broadcom Inc. (AVGO)",
        "## Executive Thesis",
        "## Valuation & The Debate (Variant Perception)",
        "## Profitability & Cash Quality",
        "*EBITDA Margin:* 54.0% | *FCF Margin:* 40.5%",
        "## Bull Case vs. Bear Case",
        "## Key Downside Risks",
    ):
        assert expected_heading in markdown

    # Missing margins fall back cleanly to N/A in the Profitability ribbon
    missing_margin_snap = bundle.snapshot.model_copy(
        update={"ebitda_margin_ttm": None, "fcf_margin_ttm": None}
    )
    rendered_na = render_investment_memo(
        missing_margin_snap, valuation, bundle.peers, memo_output, enforce_grounding=False
    )
    assert "*EBITDA Margin:* N/A | *FCF Margin:* N/A" in rendered_na

    with pytest.raises(MemoWordLimitError):
        render_investment_memo(
            bundle.snapshot,
            valuation,
            bundle.peers,
            memo_output,
            max_words=100,
        )


def test_prose_sanitizer_eliminates_leaked_snake_case_keys_in_md_and_html() -> None:
    """System prompt bans snake_case keys and sanitizer strips leaks before MD/HTML output."""
    assert "NEVER output raw JSON snake_case variable names" in SYSTEM_PROMPT

    bundle = load_mock_market_data()
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    sensitivity = compute_dcf_sensitivity(bundle.snapshot)
    valid_memo = synthesize_mock_memo(bundle.snapshot, valuation, bundle.peers)

    leaked_memo = valid_memo.model_copy(
        update={
            "valuation_and_debate": (
                "The valuation debate hinges on `pe_compression_pct` normalization and "
                "analyst_target_mean of $196.50 against implied_fcf_cagr_5y of 28.4% "
                "and base DCF of $97.25."
            ),
            "profitability_and_cash_quality": (
                "Broadcom's custom silicon mix drives strong ocf_to_net_income_ratio of 1.51x "
                "and resilient fcf_margin_ttm of 40.5% despite amortization."
            ),
        }
    )

    sanitized = sanitize_memo_prose(leaked_memo)
    assert "pe_compression_pct" not in sanitized.valuation_and_debate
    assert "forward P/E compression" in sanitized.valuation_and_debate
    assert "consensus target price" in sanitized.valuation_and_debate
    assert "market-implied 5-year FCF CAGR" in sanitized.valuation_and_debate
    assert "OCF-to-Net-Income ratio" in sanitized.profitability_and_cash_quality
    assert "TTM FCF margin" in sanitized.profitability_and_cash_quality

    rendered_md = render_investment_memo(
        bundle.snapshot, valuation, bundle.peers, leaked_memo, sensitivity=sensitivity
    )
    assert find_leaked_snake_case_identifiers(rendered_md) == []
    assert count_words(rendered_md) <= 750

    html_doc = build_html_report(
        bundle.snapshot, valuation, bundle.peers, sensitivity, rendered_md
    )
    assert find_leaked_snake_case_identifiers(html_doc) == []


def test_multiplier_noun_guardrail_catches_swapped_fcf_and_revenue_nouns() -> None:
    """Prompt enforces multiplier noun qualification and auditor flags swapped FCF/revenue nouns."""
    assert "never swap their nouns" in SYSTEM_PROMPT

    bundle = load_mock_market_data()
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    assert valuation.implied_y5_fcf_multiple is not None
    assert valuation.implied_y5_fcf_vs_current_revenue is not None

    fcf_mult = valuation.implied_y5_fcf_multiple
    rev_ratio = valuation.implied_y5_fcf_vs_current_revenue

    # Swapping implied_y5_fcf_multiple onto "current revenue" fails validation
    swapped_fcf_text = {
        "valuation_and_debate": (
            f"The debate hinges on Reverse DCF requiring {fcf_mult:.2f}x current revenue in Year 5."
        )
    }
    violations_swapped = check_multiplier_noun_alignment(swapped_fcf_text, valuation)
    assert len(violations_swapped) == 1
    assert "Multiplier noun mismatch" in violations_swapped[0]

    # Swapping implied_y5_fcf_vs_current_revenue onto "current FCF" also fails validation
    swapped_rev_text = {
        "valuation_and_debate": (
            f"The debate hinges on Year-5 FCF reaching {rev_ratio:.2f}x current FCF."
        )
    }
    violations_rev = check_multiplier_noun_alignment(swapped_rev_text, valuation)
    assert len(violations_rev) == 1
    assert "Multiplier noun mismatch" in violations_rev[0]

    # Properly qualified nouns pass cleanly
    proper_text = {
        "valuation_and_debate": (
            f"The debate centers on Year-5 FCF expanding {fcf_mult:.2f}x current FCF "
            f"({rev_ratio:.2f}x current revenue)."
        )
    }
    assert check_multiplier_noun_alignment(proper_text, valuation) == []

    # Identical ratios (100% FCF margin edge case) do not produce false positives
    equal_val = valuation.model_copy(
        update={
            "implied_y5_fcf_multiple": 2.50,
            "implied_y5_fcf_vs_current_revenue": 2.50,
        }
    )
    assert (
        check_multiplier_noun_alignment(
            {"valuation_and_debate": "Year-5 FCF hits 2.50x current revenue."}, equal_val
        )
        == []
    )


def test_groq_llama_skips_reasoning_effort_and_passes_grounding() -> None:
    """Non-reasoning Groq Llama models omit reasoning_effort to preserve free-tier RPM."""
    bundle = load_mock_market_data()
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    valid_output = synthesize_mock_memo(bundle.snapshot, valuation, bundle.peers)

    fake_client = _FakeOpenAIClient([valid_output.model_dump_json()])
    result = synthesize_memo_with_llm(
        bundle.snapshot,
        valuation,
        bundle.peers,
        model="llama-3.3-70b-versatile",
        base_url=GROQ_BASE_URL,
        api_key="gsk_test",
        client=fake_client,
    )
    assert result == valid_output
    assert "reasoning_effort" not in fake_client.completions.kwargs_log[0]

    # Groq qwen3 reasoning model keeps reasoning_effort="none"
    qwen_client = _FakeOpenAIClient([valid_output.model_dump_json()])
    synthesize_memo_with_llm(
        bundle.snapshot,
        valuation,
        bundle.peers,
        model="qwen/qwen3-32b",
        base_url=GROQ_BASE_URL,
        api_key="gsk_test",
        client=qwen_client,
    )
    assert qwen_client.completions.kwargs_log[0]["reasoning_effort"] == "none"


def test_llm_synthesizer_surfaces_explicit_401_and_429_synthesis_errors() -> None:
    """AuthenticationError (401) and RateLimitError (429) raise explicit SynthesisError."""
    bundle = load_mock_market_data()
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    fake_req = SimpleNamespace(url=f"{GROQ_BASE_URL}/chat/completions")

    class _ErrClient:
        def __init__(self, exc: Exception) -> None:
            self._exc = exc
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs: object) -> object:
            raise self._exc

    auth_err = AuthenticationError(
        "Invalid API Key",
        response=SimpleNamespace(status_code=401, headers={}, request=fake_req),  # type: ignore[arg-type]
        body={"error": {"message": "Invalid API Key"}},
    )
    with pytest.raises(SynthesisError, match="401 Unauthorized"):
        synthesize_memo_with_llm(
            bundle.snapshot,
            valuation,
            bundle.peers,
            model="llama-3.3-70b-versatile",
            base_url=GROQ_BASE_URL,
            api_key="gsk_bad",
            client=_ErrClient(auth_err),
        )

    rate_err = RateLimitError(
        "Rate limit exceeded",
        response=SimpleNamespace(status_code=429, headers={}, request=fake_req),  # type: ignore[arg-type]
        body={"error": {"message": "Rate limit reached"}},
    )
    with pytest.raises(SynthesisError, match="429 Too Many Requests"):
        synthesize_memo_with_llm(
            bundle.snapshot,
            valuation,
            bundle.peers,
            model="llama-3.3-70b-versatile",
            base_url=GROQ_BASE_URL,
            api_key="gsk_valid",
            client=_ErrClient(rate_err),
        )
