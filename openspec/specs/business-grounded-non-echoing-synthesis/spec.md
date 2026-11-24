# business-grounded-non-echoing-synthesis Specification

## Purpose

Eliminate prose echoing of top-of-section Key Metrics Ribbons, ground Bull Case and Bear Case commentary in concrete business and product drivers from `business_summary`, and maintain strict zero-hallucination numeric verification when qualitative context is included.

## Requirements

### Requirement: Anti-echoing prose constraint
The system SHALL instruct LLM synthesis—and construct offline mock synthesis—so that section body prose does not open by re-listing metrics already displayed in that section's italicized top Key Metrics Ribbon, jumping directly into analytical interpretation instead.

#### Scenario: Profitability and Cash Quality prose avoids repeating ribbon metrics verbatim
- **WHEN** a memo is synthesized and rendered for a company with a populated top Key Metrics Ribbon
- **THEN** the section body leads with analytical interpretation (drivers, capital efficiency, and cash conversion mechanics) rather than opening by reciting the full metric ribbon verbatim

### Requirement: Business-grounded Bull and Bear cases
The system SHALL require `bull_case` and `bear_case` bullets to integrate at least one specific business, segment, or product driver from `financial_snapshot.business_summary` alongside financial durability or risk factors when `business_summary` is present.

#### Scenario: Offline mock and LLM synthesis incorporate business summary drivers
- **WHEN** `financial_snapshot.business_summary` describes specific segments or product lines (for example custom AI accelerators, networking switches, and infrastructure software)
- **THEN** both the LLM prompt contract and deterministic offline mock synthesis ground `bull_case` and `bear_case` bullets in those business drivers alongside quantitative durability and risk factors

### Requirement: Numeric grounding compatibility with business summary context
The system SHALL whitelist any numeric tokens appearing inside `financial_snapshot.business_summary` (or sanitize them cleanly) within the deterministic post-generation numeric grounding auditor so qualitative business facts never trigger false-positive grounding errors while fabricated financial numbers remain rejected.

#### Scenario: Grounding audit passes with business summary numbers present
- **WHEN** `financial_snapshot.business_summary` is included in the Audit Trail JSON and referenced in synthesized memo prose
- **THEN** `verify_memo_grounding_and_repetition` passes with zero false-positive violations while still rejecting any unverified fabricated financial figure
