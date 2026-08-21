# Implementation Backlog

## Phase 8 - Application Foundation
- modularize backend API registration
- expose deployment-aware application status endpoint
- preserve existing read-only and storage lookup routes

## Phase 9 - Authenticated Read Models
- add auth boundary and role-aware read access
- expose case/site/company detail endpoints
- add pagination/filter contracts that match real operator workflows
- replace header-stub auth with Google Cloud compatible identity integration in a later productionization pass

## Phase 10 - Workflow Mutation APIs
- case lifecycle transitions
- inspection planning/execution mutations
- inspection team mutation
- certificate issuance/update flows
- audit-first business mutation boundaries
- start with controlled case-state transition instead of free-form row editing
- stage-record upserts should stay explicit (`application`, `assessment`, `plan`, `outcome`) rather than wide-row mutation
- keep certificate/DDKD issue separate from current/effective promotion

## Phase 11 - Document Workflow Integration
- connect document selection/generation contracts into authenticated APIs
- expose generation run status and document lineage
- keep fail-closed behavior for unresolved families
- keep render blocked on `payload_passthrough`, missing template locator, or unresolved source-document readiness

## Phase 12 - Frontend Operator Shell
- choose React framework by explicit ADR before implementation
- implement operator dashboard, search, case detail, and document access shell
- keep NAS credentials and storage ownership fully server-side
- keep document-family payload shaping thin until backend-owned family-specific forms are justified

## Phase 13 - Cloud Auth Productionization
- replace provisional browser-supplied header trust with Google Cloud IAP JWT verification
- keep `header_stub` only for local/dev and explicit compatibility tests
- move role ownership to server-side mapping/default policy
- make frontend auth behavior depend on backend-reported `auth_mode`

## Phase 14 - Cloud Run Deployment Baseline
- add backend runtime manifest and container entrypoint for Cloud Run
- support Cloud SQL PostgreSQL URL composition from component env vars
- add explicit Cloud Run env contract example
- add pre-deploy validation for auth, database, and Synology storage configuration

## Phase 15 - Cloud Run Service Bootstrap
- add repository-owned Cloud Run bootstrap config and deploy script
- add Secret Manager binding contract
- add rollout/runbook steps for staging and production
- make storage connectivity mode explicit and reject in-container SMB/Tailscale mount assumptions

## Phase 16 - Storage Strategy Decision Pack
- compare application-protocol, bridge-host, and experimental NFS transports explicitly against project constraints
- document the future storage bridge contract without moving business logic into it
- keep NFS optional/experimental only, run PoC A first, and defer any separate bridge host until evidence shows it is needed

## Phase 17 - External Bridge Runtime Baseline
- add a runnable main-app storage adapter for `external_bridge_http`
- add a standalone bridge app entrypoint backed by the current filesystem storage adapter
- add dedicated env/runtime artifacts for bridge-mode execution
- prepare operator guidance for either PoC A transport validation or a future private-host bridge deployment

## Phase 18 - Storage Bridge Non-Production Deployment Pack
- add dedicated bootstrap config and validator for the bridge service itself
- generate deploy and invoker-binding command previews for non-production rollout
- separate bridge env contract from main app env contract
- keep bridge-host rollout as contingent fallback, not default next action
