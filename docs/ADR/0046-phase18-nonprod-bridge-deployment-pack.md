# ADR 0046: Phase 18 non-production bridge deployment pack

## Status
Approved

## Context
Phase 17 introduced a runnable bridge baseline, but there was still no repository-owned deployment pack dedicated to the bridge service itself. That left an operational gap:
- the main app could point to a bridge
- but the bridge had no validated deployment bootstrap of its own
- and the IAM step that allows the main app to invoke the bridge remained easy to forget

For a private bridge deployment, the following must all be explicit:
- bridge runtime env contract
- bridge image/runtime config
- NFS volume assumptions if Cloud Run hosts the bridge
- the `roles/run.invoker` grant from the bridge service to the main app service account

## Decision
- Add a dedicated bridge bootstrap config example for non-production Cloud Run deployment.
- Add a dedicated validator that checks bridge env/runtime constraints and generates:
  - a deploy command preview
  - an invoker IAM binding command preview
- Add a dedicated PowerShell deploy wrapper for the bridge.
- Keep this phase non-production and operator-assisted; it does not yet automate real Google Cloud resource creation.

## Consequences
- The bridge now has a first-class deployment pack instead of borrowing the main app's bootstrap flow.
- The repo can now guide a real non-production bridge deployment with fewer hidden manual steps.
- ADR 0047 later clarified that this deployment pack is a contingent fallback path, not the default next rollout step.
