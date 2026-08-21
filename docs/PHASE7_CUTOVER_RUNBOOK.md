# Phase 7 Cutover Runbook

## Purpose
Provide the execution surface for the real cutover window once all preconditions are met.

## Pre-cutover requirements
1. Phase 6 desktop/private-share evidence must be closed.
2. Current-projection conflicts must be adjudicated.
3. A change window must be approved.
4. Rollback owners and contact paths must be confirmed.
5. Final reconciliation rerun must complete without unresolved hard errors.

## Cutover sequence
1. Announce legacy write-freeze start time.
2. Disable or administratively block new legacy business writes.
3. Run final import/reconciliation against the frozen legacy baseline.
4. Review reconciliation outputs and obtain sign-off.
5. Switch web system to authoritative mode.
6. Put legacy Excel workflow into read-only/archive mode.
7. Monitor the first production operations closely.

## Rollback trigger examples
- unresolved reconciliation mismatch
- operator workflow failure on active private-share path
- document-generation failure on a must-have family
- storage/network outage that blocks required business operations

## Rollback sequence
1. Stop authoritative use of the web system for business mutation.
2. Re-enable legacy operational writes if the freeze window is being abandoned.
3. Preserve all cutover-window audit artifacts.
4. Record exact stop/go times and issue summary.

## Required evidence to archive
- final reconciliation artifacts
- final cutover checklist
- desktop/private-share validation evidence
- decision log for go/no-go
- rollback notes if rollback occurs
