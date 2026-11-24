# richer-business-summary Specification

## Purpose

Retain richer multi-sentence segment descriptions (first 3–4 complete sentences up to 700 characters) in `business_summary` across live and offline runs so synthesized Bull and Bear cases accurately ground operating segments without triggering numeric grounding false positives.

## Requirements

### Requirement: Multi-sentence business summary extraction up to 700 characters
When extracting a company business description, the ingestion layer SHALL split on sentence boundaries and greedily retain up to the first 4 complete sentences fitting within 700 characters (truncating with an ellipsis only when the first sentence alone exceeds 700 characters), and SHALL whitelist every numeric token appearing inside `business_summary` in the numeric grounding auditor.

#### Scenario: Four short sentences are retained intact within 700 characters
- **WHEN** a raw business description contains 5 sentences whose first 4 sentences total 580 characters
- **THEN** `business_summary` retains the first 4 complete sentences, excludes the 5th sentence, and stays at or below 700 characters

#### Scenario: Greedy sentence accumulation retains 3 sentences when 4 exceed 700 characters
- **WHEN** a raw business description has 4 sentences totaling 780 characters while the first 3 sentences total 610 characters
- **THEN** `business_summary` retains all 3 complete sentences rather than falling back to a single sentence

#### Scenario: Bundled offline mock profiles provide 3-sentence segment summaries
- **WHEN** market data is loaded in `Use Offline Mock Data` mode for bundled mock tickers
- **THEN** each snapshot's `business_summary` contains 3 complete sentences covering core operating segments and stays within 700 characters
