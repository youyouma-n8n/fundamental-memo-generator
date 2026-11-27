## Purpose

Provide clean, pinned root deployment artifacts so the repository deploys directly to Streamlit Community Cloud with consistent dark institutional styling and zero manual environment setup.

## ADDED Requirements

### Requirement: Root Streamlit Community Cloud dependency manifest and theme configuration
The repository root SHALL provide a `requirements.txt` pinning all runtime dependencies (including editable installation of the local `fundamental_memo` package) and a `.streamlit/config.toml` configuring the dark institutional color theme (`base = "dark"`, `primaryColor = "#3B82F6"`, `backgroundColor = "#0E1117"`, `secondaryBackgroundColor = "#161B22"`, `textColor = "#F8FAFC"`) with `headless = true`.

#### Scenario: Root deployment files exist and parse cleanly
- **WHEN** the repository is checked out for Streamlit Community Cloud deployment
- **THEN** root `requirements.txt` lists all required runtime packages including `./fundamental_memo`, and `.streamlit/config.toml` parses as valid TOML containing the configured `[theme]` and `[server]` sections
