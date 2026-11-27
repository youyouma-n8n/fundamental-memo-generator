"""Unit tests for the pure-Python Deterministic Rule-Based Memo Engine and hybrid fallback."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from openai import APIConnectionError, AuthenticationError, RateLimitError

from fundamental_memo.cli import run_memo_pipeline
from fundamental_memo.data_fetcher import load_mock_market_data
from fundamental_memo.deterministic_memo import (
    DETERMINISTIC_MODE_LABEL,
    GROQ_BASE_URL,
    PROVIDER_CUSTOM,
    PROVIDER_GROQ,
    PROVIDER_OLLAMA,
    build_deterministic_memo,
    build_deterministic_memo_schema,
    generate_memo,
    is_localhost_url,
    probe_local_llm_endpoint,
    resolve_provider_api_key,
)
from fundamental_memo.memo_synthesizer import (
    build_audit_trail_payload,
    find_leaked_snake_case_identifiers,
    verify_memo_grounding_and_repetition,
)
from fundamental_memo.schemas import GroundingAuditError, count_words
from fundamental_memo.valuation_engine import compute_dcf_sensitivity, run_valuation_analysis


class _FailingConnectionClient:
    """Fake OpenAI client that raises APIConnectionError to simulate offline Ollama."""

    def __init__(self) -> None:
        self.called = False
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    def _create(self, **kwargs: object) -> object:
        self.called = True
        raise APIConnectionError(request=SimpleNamespace(url="http://localhost:11434/v1"))  # type: ignore[arg-type]


def test_build_deterministic_memo_from_audit_trail_passes_grounding_and_word_cap() -> None:
    """build_deterministic_memo produces a grounded <=750w 6-section Markdown memo in <0.5s."""
    t0 = time.perf_counter()
    bundle = load_mock_market_data("AVGO", ["NVDA", "AMD", "MRVL", "QCOM"])
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    sensitivity = compute_dcf_sensitivity(bundle.snapshot)
    audit_trail = build_audit_trail_payload(
        bundle.snapshot, valuation, bundle.peers, sensitivity=sensitivity
    )

    markdown = build_deterministic_memo(audit_trail)
    elapsed = time.perf_counter() - t0

    assert elapsed < 2.0
    assert count_words(markdown) <= 750
    assert find_leaked_snake_case_identifiers(markdown) == []
    for section in (
        "## Executive Thesis",
        "## Valuation & The Debate (Variant Perception)",
        "## Profitability & Cash Quality",
        "## Bull Case vs. Bear Case",
        "## Key Downside Risks",
    ):
        assert section in markdown


def test_deterministic_threshold_rules_adapt_to_high_roic_and_pe_compression() -> None:
    """High ROIC (>15%), Forward P/E compression (>20%), and high implied CAGR trigger rules."""
    bundle = load_mock_market_data("NVDA", ["AMD", "MRVL", "QCOM", "AVGO"])
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    memo = build_deterministic_memo_schema(bundle.snapshot, valuation, bundle.peers)

    assert verify_memo_grounding_and_repetition(
        memo, bundle.snapshot, valuation, bundle.peers
    ) == []
    assert any("Elite capital efficiency" in bullet for bullet in memo.bull_case)
    assert any("forward P/E compression" in bullet for bullet in memo.bull_case)


def test_generate_memo_bypasses_llm_when_disabled_or_missing_cloud_key() -> None:
    """AI disabled or cloud URL without API key bypasses OpenAI client instantaneously."""
    bundle = load_mock_market_data("AVGO")
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    sensitivity = compute_dcf_sensitivity(bundle.snapshot)

    failing_client = _FailingConnectionClient()
    outcome_disabled = generate_memo(
        bundle.snapshot,
        valuation,
        bundle.peers,
        sensitivity=sensitivity,
        use_ai_synthesis=False,
        client=failing_client,
    )
    assert failing_client.called is False
    assert outcome_disabled.used_deterministic is True
    assert outcome_disabled.mode_label == DETERMINISTIC_MODE_LABEL
    assert outcome_disabled.fallback_notice is None

    outcome_cloud_no_key = generate_memo(
        bundle.snapshot,
        valuation,
        bundle.peers,
        sensitivity=sensitivity,
        use_ai_synthesis=True,
        base_url="https://api.groq.com/openai/v1",
        api_key="",
    )
    assert outcome_cloud_no_key.used_deterministic is True
    assert outcome_cloud_no_key.fallback_notice is not None
    assert "Cloud API key" in outcome_cloud_no_key.fallback_notice


def test_generate_memo_falls_back_gracefully_when_local_llm_unreachable() -> None:
    """Unreachable local Ollama switches cleanly to Deterministic Rule Engine with notice."""
    bundle = load_mock_market_data("AVGO")
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    sensitivity = compute_dcf_sensitivity(bundle.snapshot)
    failing_client = _FailingConnectionClient()

    outcome = generate_memo(
        bundle.snapshot,
        valuation,
        bundle.peers,
        sensitivity=sensitivity,
        use_ai_synthesis=True,
        base_url="http://localhost:11434/v1",
        api_key="",
        allow_fallback=True,
        client=failing_client,
    )
    assert failing_client.called is True
    assert outcome.used_deterministic is True
    assert outcome.mode_label == DETERMINISTIC_MODE_LABEL
    assert outcome.fallback_notice == (
        "Local LLM unreachable — switched to Deterministic Rule Engine"
    )


def test_probe_local_llm_endpoint_and_is_localhost_url() -> None:
    """Localhost URL detection and fast <0.3s probe return False on closed/remote ports."""
    assert is_localhost_url("http://localhost:11434/v1") is True
    assert is_localhost_url("http://127.0.0.1:8080/v1") is True
    assert is_localhost_url("https://api.groq.com/openai/v1") is False

    t0 = time.perf_counter()
    assert probe_local_llm_endpoint("https://api.groq.com/openai/v1", timeout=0.2) is False
    # Unbound local high port should fail immediately in well under 0.3s
    assert probe_local_llm_endpoint("http://127.0.0.1:59999/v1", timeout=0.2) is False
    assert (time.perf_counter() - t0) < 0.5


def test_run_memo_pipeline_zero_llm_mode_returns_deterministic_mode_label() -> None:
    """Pipeline with use_ai_synthesis=False produces Deterministic Rule Engine result cleanly."""
    res = run_memo_pipeline(
        ticker="AVGO",
        peers=["NVDA", "AMD", "MRVL", "QCOM"],
        mock_data=True,
        use_ai_synthesis=False,
    )
    assert res.synthesis_mode == DETERMINISTIC_MODE_LABEL
    assert res.used_mock_llm is True
    assert res.fallback_notice is None
    assert res.word_count <= 750
    assert pytest.approx(res.snapshot.current_price) == 170.0


class _RaisingStatusClient:
    """Fake OpenAI client that raises a caller-supplied exception on completions.create."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    def _create(self, **kwargs: object) -> object:
        raise self._exc


def test_resolve_provider_api_key_priority_and_ollama_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify sidebar > st.secrets['GROQ_API_KEY'] > env > LLM_API_KEY and Ollama defaults."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    # Explicit user input always wins over secrets/env
    secrets = {"GROQ_API_KEY": "gsk_from_secret", "LLM_API_KEY": "llm_from_secret"}
    key, from_sec = resolve_provider_api_key(
        PROVIDER_GROQ, "gsk_manual", secrets_lookup=secrets.get
    )
    assert key == "gsk_manual"
    assert from_sec is False

    # Blank user input resolves st.secrets["GROQ_API_KEY"] first
    monkeypatch.setenv("GROQ_API_KEY", "gsk_from_env")
    key, from_sec = resolve_provider_api_key(PROVIDER_GROQ, "", secrets_lookup=secrets.get)
    assert key == "gsk_from_secret"
    assert from_sec is True

    # Without secret, falls back to os.getenv("GROQ_API_KEY")
    key, from_sec = resolve_provider_api_key(PROVIDER_GROQ, "", secrets_lookup=lambda _: None)
    assert key == "gsk_from_env"
    assert from_sec is True

    # Without GROQ_API_KEY, falls back to LLM_API_KEY secret then env
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "llm_env")
    key, from_sec = resolve_provider_api_key(
        PROVIDER_GROQ, "", secrets_lookup=lambda k: "llm_sec" if k == "LLM_API_KEY" else None
    )
    assert key == "llm_sec"
    assert from_sec is True

    key, from_sec = resolve_provider_api_key(
        PROVIDER_GROQ, "", secrets_lookup=lambda _: (_ for _ in ()).throw(RuntimeError("no file"))
    )
    assert key == "llm_env"
    assert from_sec is True

    # Custom provider reads LLM_API_KEY; Ollama returns empty key (caller uses "ollama")
    key_custom, from_sec_custom = resolve_provider_api_key(
        PROVIDER_CUSTOM, "", secrets_lookup=lambda _: None
    )
    assert key_custom == "llm_env"
    assert from_sec_custom is True

    key_ollama, from_sec_ollama = resolve_provider_api_key(
        PROVIDER_OLLAMA, "", secrets_lookup=secrets.get
    )
    assert key_ollama == ""
    assert from_sec_ollama is False


def test_generate_memo_handles_groq_401_and_429_with_warning_fallback() -> None:
    """Groq 401 Unauthorized and 429 Too Many Requests fall back cleanly with warning banners."""
    bundle = load_mock_market_data("AVGO")
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    sensitivity = compute_dcf_sensitivity(bundle.snapshot)

    fake_req = SimpleNamespace(url=f"{GROQ_BASE_URL}/chat/completions")
    auth_exc = AuthenticationError(
        "Invalid API key",
        response=SimpleNamespace(status_code=401, headers={}, request=fake_req),  # type: ignore[arg-type]
        body={"error": {"message": "Invalid API Key"}},
    )
    outcome_401 = generate_memo(
        bundle.snapshot,
        valuation,
        bundle.peers,
        sensitivity=sensitivity,
        use_ai_synthesis=True,
        model="llama-3.3-70b-versatile",
        base_url=GROQ_BASE_URL,
        api_key="gsk_bad",
        allow_fallback=True,
        client=_RaisingStatusClient(auth_exc),
    )
    assert outcome_401.used_deterministic is True
    assert outcome_401.mode_label == DETERMINISTIC_MODE_LABEL
    assert outcome_401.fallback_severity == "warning"
    assert outcome_401.fallback_notice is not None
    assert "401 Unauthorized" in outcome_401.fallback_notice
    assert verify_memo_grounding_and_repetition(
        outcome_401.memo_output, bundle.snapshot, valuation, bundle.peers
    ) == []

    rate_exc = RateLimitError(
        "Rate limit exceeded",
        response=SimpleNamespace(status_code=429, headers={}, request=fake_req),  # type: ignore[arg-type]
        body={"error": {"message": "Rate limit reached"}},
    )
    outcome_429 = generate_memo(
        bundle.snapshot,
        valuation,
        bundle.peers,
        sensitivity=sensitivity,
        use_ai_synthesis=True,
        model="llama-3.3-70b-versatile",
        base_url=GROQ_BASE_URL,
        api_key="gsk_valid",
        allow_fallback=True,
        client=_RaisingStatusClient(rate_exc),
    )
    assert outcome_429.used_deterministic is True
    assert outcome_429.fallback_severity == "warning"
    assert outcome_429.fallback_notice is not None
    assert "429 Too Many Requests" in outcome_429.fallback_notice


def test_generate_memo_does_not_swallow_grounding_audit_error() -> None:
    """Strict GroundingAuditError propagates rather than silently falling back."""
    bundle = load_mock_market_data("AVGO")
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    sensitivity = compute_dcf_sensitivity(bundle.snapshot)

    bad_payload = build_deterministic_memo_schema(bundle.snapshot, valuation, bundle.peers)
    hallucinated = bad_payload.model_dump()
    hallucinated["executive_thesis"] = "Target price $999.99 with 88.8% EBITDA margin."
    import json

    raw_json = json.dumps(hallucinated)

    class _HallucinatingClient:
        def __init__(self) -> None:
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs: object) -> object:
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=raw_json))]
            )

    with pytest.raises(GroundingAuditError):
        generate_memo(
            bundle.snapshot,
            valuation,
            bundle.peers,
            sensitivity=sensitivity,
            use_ai_synthesis=True,
            model="llama-3.3-70b-versatile",
            base_url=GROQ_BASE_URL,
            api_key="gsk_valid",
            max_retries=0,
            allow_fallback=True,
            client=_HallucinatingClient(),
        )
