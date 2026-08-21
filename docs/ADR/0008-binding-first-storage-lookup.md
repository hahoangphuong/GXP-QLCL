# ADR 0008: Prefer binding-first storage lookup with live fallback

## Status
Approved

## Date
2026-08-13

## Context
Once a folder mapping has been proven and persisted in `storage_binding`, repeated requests should not need to scan the filesystem every time. However, bindings can become stale if folders are moved or renamed within the private storage tree.

## Decision
- Storage lookup for inspection folders should query `storage_binding` first.
- A binding is accepted only if the bound relative path still exists.
- If the bound path is missing, the system falls back to live resolution.
- A successful live resolution refreshes the persisted binding.
- Storage roots and storage class are configuration concerns loaded from environment.

## Consequences
Positive:
- reduces repeated scans for known folders
- keeps stale bindings self-healing through successful live resolution
- supports non-production private-share injection through environment config

Negative:
- lookup flow becomes two-step instead of single-step
- stale binding handling must stay explicit and observable
