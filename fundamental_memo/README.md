# Equity Fundamental Deep-Dive & One-Page Memo Generator

A modular, deterministic Python CLI and Streamlit application that fetches verified equity financial data, runs institutional pure-Python valuation and capital-efficiency diagnostics (5Y Perpetuity DCF, **Reverse DCF**, **Exit EV/EBITDA Multiple DCF**, peer percentiles, ROIC, SBC-adjusted FCF, and working capital decomposition), and synthesizes a strictly grounded **One-Page Investment Memo** in Markdown with interactive Plotly valuation charts.

## Architecture

```text
fundamental_memo/
├── pyproject.toml
├── README.md
├── src/
│   └── fundamental_memo/
│       ├── __init__.py
│       ├── schemas.py           # Pydantic v2 Audit Trail & InvestmentMemoSchema contracts
│       ├── data_fetcher.py      # yfinance ingestion, margins/ROIC/WC ratios & offline fixtures
│       ├── valuation_engine.py  # Pure-Python 5Y DCF, Reverse DCF, Exit Multiple, & peer comps
│       ├── memo_synthesizer.py  # Local Ollama/MLX client, regex grounding audit, & offline mock
│       ├── renderer.py          # Upgraded 6-section Markdown renderer & <= 750 word guard
│       ├── charts.py            # Plotly Valuation Football Field & Peer Growth Scatter builders
│       ├── cli.py               # CLI entry point & shared pipeline orchestration
│       ├── streamlit_app.py     # Interactive Streamlit UI (model dropdown, 5 KPIs, Plotly charts)
│       └── fixtures/
│           └── mock_market_data.json
└── tests/
    ├── test_valuation_engine.py
    ├── test_schemas.py
    ├── test_data_fetcher.py
    ├── test_synthesizer_and_renderer.py
    ├── test_charts.py
    └── test_cli_e2e.py
```

## Installation

Requires Python 3.10+.

```bash
cd fundamental_memo
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## CLI Usage

### Live Analysis (Yahoo Finance + Local Ollama / MLX)

```bash
python -m fundamental_memo.cli \
  --ticker AVGO \
  --peers NVDA,AMD,MRVL,QCOM \
  --wacc 0.095 \
  --terminal-growth 0.025 \
  --fcf-cagr 0.15 \
  --exit-multiple 15.0 \
  --model inkling-2-mini:latest \
  --base-url http://localhost:11434/v1 \
  --output memo_AVGO.md
```

For an MLX OpenAI-compatible server, point `--base-url` to `http://localhost:8080/v1`.

### Deterministic Offline Dry Run (Zero Network / No LLM Server Required)

```bash
python -m fundamental_memo.cli \
  --ticker AVGO \
  --peers NVDA,AMD,MRVL,QCOM \
  --mock-data \
  --output memo_AVGO.md
```

Combine `--mock-data` with `--live-llm` to run a live local Ollama/MLX model against deterministic offline financials, or pass `--fixture-path path/to/fixture.json` for custom JSON snapshots.

## Streamlit UI

Launch the interactive web interface:

```bash
streamlit run src/fundamental_memo/streamlit_app.py
```

Features:
- **Sidebar controls:** Target ticker, comma-separated peer tickers, WACC, Terminal Growth Rate, `5Y FCF CAGR` (default `0.15`), `Terminal Exit EV/EBITDA Multiple` (default `15.0`), model dropdown (`inkling-2-mini:latest`, `gemma4:31b-mlx`, `qwen3.8:27b-mlx`), editable Base URL (`http://localhost:11434/v1`), and Offline Mock toggles.
- **5-Metric KPI Header Row:** Current Price (with 52-week range), DCF Intrinsic Value, Market-Implied FCF CAGR (vs. Base), ROIC / Operating Margin, and Earnings Quality (with OCF/NI & SBC-Adjusted FCF).
- **Interactive Plotly Charts:** Valuation Football Field (52-week range, Perpetuity DCF sensitivity, Exit Multiple DCF, Peer Comps 25th–75th percentile range + Current Price reference line) and Peer Valuation vs. Growth Scatter Plot.
- **Grounded Memo & Export:** Rendered 6-section institutional Markdown memo (including *Valuation & The Debate*), Audit Trail JSON expander, and one-click `Download memo_<TICKER>.md`.

## Verification & Quality Checks

```bash
pytest -v
ruff check src tests
mypy src tests
```
