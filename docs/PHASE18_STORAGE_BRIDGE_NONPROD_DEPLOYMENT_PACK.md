# Phase 18 Storage Bridge Non-Production Deployment Pack

## Goal
Prepare a validated, operator-usable non-production deployment path for the storage bridge service itself.

## Delivered
- bridge env example: [.env.storage_bridge.cloudrun.example](/D:/GXP-QLCL/backend/.env.storage_bridge.cloudrun.example)
- bridge bootstrap config: [storage_bridge_bootstrap.example.json](/D:/GXP-QLCL/infra/cloudrun/storage_bridge_bootstrap.example.json)
- bridge bootstrap validator: [validate_phase18_storage_bridge_bootstrap.py](/D:/GXP-QLCL/tools/validate_phase18_storage_bridge_bootstrap.py)
- bridge deploy script: [deploy_storage_bridge.ps1](/D:/GXP-QLCL/infra/cloudrun/deploy_storage_bridge.ps1)
- tests: [test_phase18_storage_bridge_bootstrap.py](/D:/GXP-QLCL/tests/test_phase18_storage_bridge_bootstrap.py)
- ADR: [0046-phase18-nonprod-bridge-deployment-pack.md](/D:/GXP-QLCL/docs/ADR/0046-phase18-nonprod-bridge-deployment-pack.md)

## What changed
- The bridge now has its own validated deployment pack instead of relying on the main app bootstrap flow.
- The validator now produces both:
  - a `gcloud run deploy` preview for the bridge service
  - a `gcloud run services add-iam-policy-binding` preview that grants the main app service account `roles/run.invoker`
- The bridge env contract now explicitly rejects `STORAGE_CLASS=external_bridge_http`, preventing accidental loop configuration.

## Scope boundary
- This phase does not actually deploy the bridge yet.
- This phase does not create Artifact Registry repositories or service accounts automatically.
- This phase is intentionally non-production and operator-assisted.
- This phase is a fallback pack, not the default next step after ADR 0047.

## When user action will be needed
If PoC A fails and you decide to test the dedicated bridge-host path on Google Cloud, I can walk you through:
1. filling in real values in the bridge bootstrap file
2. building/pushing the bridge image
3. deploying the bridge service
4. granting invoker access to the main app service account
5. pointing the main app at the deployed bridge URL
