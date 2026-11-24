"""Deterministic equity fundamental analysis and one-page investment memo generator."""

from fundamental_memo.html_exporter import build_html_report
from fundamental_memo.memo_synthesizer import DEFAULT_BASE_URL, DEFAULT_MODEL, SUPPORTED_MODELS
from fundamental_memo.schemas import (
    DataFetchError,
    DcfSensitivity,
    DcfSensitivityMatrix,
    FinancialSnapshot,
    FundamentalMemoError,
    GroundingAuditError,
    HistoricalYearPoint,
    InvestmentMemoOutput,
    InvestmentMemoSchema,
    MarketDataBundle,
    MemoWordLimitError,
    NegativeFreeCashFlowError,
    PeerComparable,
    QuarterlyPoint,
    SynthesisError,
    ValuationAnalysis,
    ValuationError,
    WorkingCapitalMetrics,
)
from fundamental_memo.screener import run_watchlist_scan

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "SUPPORTED_MODELS",
    "DataFetchError",
    "DcfSensitivity",
    "DcfSensitivityMatrix",
    "FinancialSnapshot",
    "FundamentalMemoError",
    "GroundingAuditError",
    "HistoricalYearPoint",
    "InvestmentMemoOutput",
    "InvestmentMemoSchema",
    "MarketDataBundle",
    "MemoWordLimitError",
    "NegativeFreeCashFlowError",
    "PeerComparable",
    "QuarterlyPoint",
    "SynthesisError",
    "ValuationAnalysis",
    "ValuationError",
    "WorkingCapitalMetrics",
    "__version__",
    "build_html_report",
    "run_watchlist_scan",
]

__version__ = "0.1.0"
