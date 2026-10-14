# Rehearsal read-only validation

This runner uses the current PR #3 source and `src/lib/api.ts`, not the VM's
deployed frontend. No deployment, migration or backend modification is required.
The local proxy blocks all methods except GET/HEAD on API/health routes before
forwarding. It forces same-origin `/api` and does not inject identity headers,
tokens or roles. Use it only for the authorized `gxp_legacy_rehearsal` runtime.

## Establish the connection

The project/VM are user-authorized; the zone in `docs/VM_PRODUCTION_BASELINE.md`
is `asia-southeast1-a`. Verify current control-plane values instead of guessing
an IP from a hostname. With an already authenticated Google Cloud CLI:

```powershell
$rehearsalZone = gcloud compute instances list --project=gxp-qlcl-vm --filter='name=gxp-web-prod' --format='value(zone.basename())'
if ($LASTEXITCODE -ne 0 -or @($rehearsalZone).Count -ne 1 -or -not $rehearsalZone) { throw 'Cannot uniquely resolve authorized VM' }
gcloud compute start-iap-tunnel gxp-web-prod 22 --project=gxp-qlcl-vm --zone=$rehearsalZone --local-host-port=127.0.0.1:2222
```

Verify VM/project metadata, the active backend listener, release metadata and
the configured DB name before proceeding. Do not print `/etc/gxp/runtime.env`,
database passwords or tokens. Check only approved metadata fields. Do not install
tools on the VM, change firewall/IAM/authentication, or restart any service.

Keep that IAP process open. Use an existing authorized SSH key and a verified
known-host alias to inspect the VM and forward its loopback FastAPI listener:

```powershell
ssh -p 2222 -i <existing-key> -o HostKeyAlias=<verified-known-host-alias> -o StrictHostKeyChecking=yes -o BatchMode=yes <existing-user>@127.0.0.1 'hostname; readlink -f /opt/gxp/current-backend; sudo ss -ltnp'
# Only after confirming port 8000:
ssh -N -L 127.0.0.1:8000:127.0.0.1:8000 -p 2222 -i <existing-key> -o HostKeyAlias=<verified-known-host-alias> -o StrictHostKeyChecking=yes -o BatchMode=yes -o ExitOnForwardFailure=yes <existing-user>@127.0.0.1
```

If port 8000 differs, use the verified listener as the right-hand port. Keep the
local port on loopback. An existing approved SSH configuration is also usable;
do not guess usernames/IPs or disable host-key verification. On this workstation,
Google Cloud CLI is available in Ubuntu/WSL rather than Windows PATH. Control-plane
discovery verified project/VM/zone, then IAP + existing-key SSH in WSL succeeded.
Direct SSH timed out because public port 22 is disabled. Windows-to-WSL SSH
forwarding failed; execute the SSH client in WSL. Existing Windows private keys
need a temporary mode-0600 copy for Linux OpenSSH; remove it when the tunnel exits,
never commit or print it. Do not use `gcloud compute ssh` to provision a new key.

## Run current frontend and API probe

In `D:\GXP-QLCL\frontend`:

```powershell
# Optional only if the verified local tunnel uses another port:
$env:GXP_REHEARSAL_PROXY_TARGET = 'http://127.0.0.1:8000'
# Direct FastAPI uses /app/status, while VM Nginx strips /api/.
# Set only for the verified direct-FastAPI tunnel; omit for Nginx/fixture APIs:
$env:GXP_REHEARSAL_STRIP_API_PREFIX = '1'
pnpm exec vite --config qa/rehearsal.vite.config.ts
```

Open `http://127.0.0.1:4173/search`. Read `/healthz`, `/readyz` and `/api/app/status`
through this same proxy. `/readyz` establishes current schema readiness; read
`alembic_version` through an authorized read-only VM session if the exact revision
is not exposed by that endpoint. Confirm runtime deployment SHA independently of
the tooling checkout. Do not assume backend tooling SHA equals web-service SHA.

Sign in using the actual Google OIDC button and a provisioned account. If the
OAuth client does not allow the local origin, stop live UI verification and report
that boundary; do not forge a token, use header_stub or change the VM auth config.
The probe reads the existing valid in-memory/browser session; it never accepts
tokens in URLs or prints them. In the browser development console:

```javascript
const { runRehearsalSmoke } = await import('/src/qa/rehearsalSmoke.ts');
const report = await runRehearsalSmoke();
console.log(report);
```

Alternatively navigate to `/qa/rehearsal.html` in the same signed-in tab and
activate **Chạy probe chỉ đọc**. Leave the fixture checkbox unchecked for the VM.
This separate development-only page is not imported into the production bundle.

It reads one bounded search page, selects one returned result (or an exact
`resultKey` on that page), its facility/case workspace, up to two distinct document
UUIDs and up to two GPs/ĐĐK certificate details plus their persisted `/versions`
histories. History checks fail closed on aggregate mismatch, duplicate/missing
version identity, malformed scope/link collections or a ĐĐK response that includes
source tokens as canonical history. Zero persisted versions is a valid response;
the probe never fabricates a current snapshot. Shared filenames/numbers do not
deduplicate different identities. No mutation, folder lookup, binary download or
automatic retry is performed. Overlapping runs are rejected. Only check names,
counts, HTTP codes, auth mode and deployment SHA are reported; dossier values,
IDs, credentials and server error details are omitted.

`READ_API_PASS` verifies only the bounded API checks. `uiVerified` stays false;
it is not a real-backend browser, storage or screen-reader PASS. Empty/unavailable
data is SKIPPED and leaves live verification BLOCKED. `FIXTURE_ONLY` is produced
only with explicit `{ fixture: true }`; that flag permits header_stub solely for
the synthetic fixture server. Never use it against the VM.

## Manual browser evidence

At 1920×1080, 1366×768, 390×844 and 375×812, activate General Information,
registration, inspection, CAPA, processing, Case GPs/ĐĐK and Facility GPs/ĐĐK.
Record activation/loading/empty/unavailable outcomes separately. Verify URL and
selected Site/ProductionLine/history across tab round trips, refresh and
Back/Forward. Arrow/Home/End change focus; Enter/Space activates. Check F2,
Escape/F6 only where already implemented. Compare request counters before/after
focus-only actions and verify no mutations reached the upstream.

Store sensitive runtime screenshots/network traces outside Git and redact before
sharing. Record viewport, `document.documentElement.clientWidth/scrollWidth`,
request method/status counts and whether late responses retain current selection.
Do not force a live 409 through writes: conflict/draft tests remain fixture-only
unless a separately authorized scenario exists. The local proxy's 405 is a local
safety block, not proof of backend RBAC or concurrency.

## Current boundary (2026-10-14)

Live IAP/SSH/tunnel observations: `/healthz` and `/readyz` return 200;
schema `20261012_0023` is current, and `/app/status` reports
`google_oidc`, `gxp_legacy_rehearsal`, deployment
`97182e58c3a673938d1b263c7eeaab41d28147b4`. Live OpenAPI contains both
canonical aggregate history endpoints and their exact response schemas. No-token
`/auth/me` returns 401.
The actual PR #3 frontend renders its login boundary through this proxy at all
four viewports, without horizontal overflow. Google sign-in rejects
`http://127.0.0.1:4173` with **The given origin is not allowed for the given client
ID**. The browser probe performs two reads and reports BLOCKED/401.

Authenticated workspace UI is `REAL_BACKEND_NOT_VERIFIED`: it needs an approved
OAuth origin plus an interactive sign-in using a provisioned account. No OAuth,
VM or RBAC configuration was changed. Do not insert a token or stub identity to
bypass this boundary. Real 403/409/draft/stale-response behavior, binary storage
and screen-reader speech remain unverified.

Read-only aggregate queries independently confirm 3,120 source groups
(780 each GMP/GLP/GSP/GDP), with 861 reference tokens and no new canonical links.
The transaction used BEGIN READ ONLY and ROLLBACK; no data changed. Runtime
OpenAPI now exposes the source-evidence endpoint. Facility ĐĐK consumes it by
canonical UUID, preserving its source-only meaning. Certificate-version/history
contracts are now deployed. Their authenticated response/UI remains unverified.

Persisted history remains `FIXTURE_VERIFIED_ONLY`: the read-only probe now covers
the two history endpoints, but cannot reach them against the VM without a valid
interactive session. This is not `REAL_BACKEND_VERIFIED`.

The only HTTPS host observed in VM Nginx is `gxp.qlcl-dav.cc`; that does not
establish an approved development origin for this local frontend source. No
HTTPS development origin was found in available configuration. Infrastructure
owner must approve/add exactly `http://127.0.0.1:4173` to **Authorized JavaScript
Origins** of the existing web OAuth client reported by `/app/status`, or provide
an already-approved HTTPS development origin. Do not change the client/CORS/IAP
or inject identity headers within the frontend verification slice.

Minimum handoff for a future authenticated run: confirm the existing OAuth web
client, approve one exact development origin, provide one already-provisioned
least-privilege account, and identify sanitized read-only Site aggregates that
cover zero, one and multiple saved versions where available. Keep credentials and
record identities outside Git. No frontend-auth fallback or new client is needed.
