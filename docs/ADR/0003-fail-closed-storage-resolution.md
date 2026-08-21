# ADR 0003: Fail-Closed Storage Resolution By Stable Legacy Tokens

## Status
Accepted

## Context
Legacy folders carry descriptive text and stable tokens such as `(ID-103)` and `(KT-1376-GMP)`.
Descriptive names are not reliable business keys.
VBA code navigates and filters folders by file/path patterns, which is unsafe to reproduce directly in business logic.

## Decision
The target system resolves inspection folders by:
- year
- legacy site ID
- legacy inspection code

Resolver outcomes are:
- `RESOLVED`
- `NOT_FOUND`
- `AMBIGUOUS`
- `INVALID`

`AMBIGUOUS` and `NOT_FOUND` fail closed.

## Consequences
- Storage logic becomes testable and infrastructure-agnostic.
- No silent fallback to descriptive-name matching.
- Early migration keeps legacy folder layout unchanged.
