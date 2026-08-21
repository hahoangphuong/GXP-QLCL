# ADR 0054: Database identity matching fails closed on ambiguity

## Status
Accepted

## Context
Production-compatible authorization is database-backed, but authenticated requests can carry both email and subject claims. A naive `email OR subject` lookup can silently select the wrong `AppUser` when claims map to different rows.

## Decision
- `external_subject` is the preferred stable external identifier when it is present.
- `external_email` remains a useful secondary locator and consistency signal.
- If email and subject resolve to two different provisioned users, authorization fails closed.
- If one claim uniquely resolves a user and the other contradicts that user's provisioned external identity, authorization fails closed.
- Unknown or unprovisioned identities continue to return `403`.

## Consequences
- Production auth avoids `.first()` ambiguity and silent user selection.
- User provisioning must keep subject/email mappings coherent.
- Operational failures surface early instead of creating misattributed mutations or audit records.
