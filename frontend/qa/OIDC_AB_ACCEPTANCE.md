# Google OIDC A/B acceptance — evidence matrix

Version1.0,2026-11-01. Starting main `e15bfd06eb86789976d3cfc863f2b63124be8dff`;
audited main `011dc59a103a18bd868fca0bbb4f062c4191cd8b` adds only PR252 SQL/service
parity assertions. This document does not authorize deployment, provisioning,
OAuth changes, migrations or writes to rehearsal/production/NAS/GCS.

## Evidence classes and execution boundary

`UNIT_VERIFIED`, `COMPONENT_VERIFIED`, `BROWSER_FIXTURE_VERIFIED` and
`DISPOSABLE_API_VERIFIED` are distinct from `AUTHENTICATED_OIDC_VERIFIED`.
Real Google A/B: **AUTHENTICATED_OIDC_NOT_EXECUTED / BLOCKED_BY_ENVIRONMENT**.
Two permitted accounts, their expected permissions, approved synthetic records
and confirmation of the exact authorized origin have not been supplied.

Fresh, unauthenticated Edge contexts observed `https://gxp.qlcl-dav.cc` at
1366×768,1920×1080,390×844. GIS loaded; no origin rejection was observed. That
does not establish that Google will issue a credential for the selected client.
The existing user's browser tab could not be inspected: computer-use kernel
initialization failed after retry/reset. No login dialog was automated and no
credential, cookie or real browser-session storage was read or recorded.

The supported disposable server used FastAPI/SQLite/header_stub. A=admin,
B=inspector, with a separate reader-role request for a restricted-role negative.
Expected permissions come from `backend/app/rbac.py`, not a frontend role map.
Header-role changes are not production DB permission-revocation proof. Browser
GIS callbacks/JWT-shaped strings/clock were synthetic, never Google-verified.

## Authorization and account matrix

| Scenario | Expected current contract | Observed evidence | Google A/B |
| --- | --- | --- | --- |
| Login/token issuance | Real Google credential, correct audience/issuer/expiry | Fresh public browser only; no credential issued/tested | BLOCKED |
| No credential `/auth/me` |401| Runtime HTTPS401; disposable401 | Negative boundary only |
| Canonical identity A/B | Backend role/permission source | Disposable `/auth/me` matches admin/inspector permissions | NOT_EXECUTED |
| Facility/Case/certificate reads | Permission-based reads | A/B200 | NOT_EXECUTED |
| Cross-Case/cross-Site read | `case.view` is global in current contract | A/B200 on another Site's Case; no inferred tenant ACL | NOT_EXECUTED |
| Application write | Inspector has `case.edit` | B200, one audit; stale/missing existing token409, unchanged DB | NOT_EXECUTED |
| Restricted reader write | No `case.edit` |403, no audit/state change | NOT_EXECUTED |
| Inspection/CAPA | Preserve readiness and separate assess permission | Existing workflow checks; B assess403; new CAPA after advancement409 | NOT_EXECUTED |
| PCT/CT | Inspector may create/complete; explicit Case-owned parent | B200; duplicate completion409; foreign parent422 | NOT_EXECUTED |
| GxP GMP/GLP/GMPbb | Issue/update/promote require server permissions | A workflow200; B403 on all three actions/types; missing422/stale409 | NOT_EXECUTED |
| ĐĐK | Same server-owned permission/concurrency boundary | A issue/read; B issue/update/promote403; missing422/stale409 | NOT_EXECUTED |
| Permission refresh | Revalidate every accepted credential generation, even identical string | RED→GREEN; synthetic browser + real disposable `/auth/me` | NOT_EXECUTED |
| Account/owner transition | No A permissions/data/error in B's first commit | Component first-commit probes; browser A metadata removed before B403 | NOT_EXECUTED |
| Expiry during committed POST | Clear A draft; no old readback/replay into B | Real disposable PCT committed, synthetic clock expiry; B draft survives late response | NOT_EXECUTED |
| Accepted write/GET failure | Retain readable draft; block replay through remount/Cancel | Real disposable PUT + injected GET503 at three widths | NOT_EXECUTED |
| Logout/Back/Forward/reload | No restoration of old draft or admin rights | Synthetic session/browser checks;0 navigation mutations | NOT_EXECUTED |

Additional security matrix:45HTTP checks (17×200,1×401,14×403,8×409,5×422).
Each denied/conflicting/invalid write and every GET preserves the whole disposable
database state hash and audit count. Three authorized commands add exactly three
events. The initial workflow matrix contributes166checks/68events. Later browser
commands bring the isolated database to83audit events; no remote data changed.
Request/response evidence uses synthetic UUID aliases and account A/B only.

## Frontend defects and regression owner

Last correct: a protected response belonged to the credential that requested it.
First incorrect: accepting another generation left `/auth/me` permissions and
admin metadata/error unowned; identical credentials did not refetch identity.
Dashboard also depended on the mutable access wrapper and repeated a GET when
only that wrapper changed.

App now binds identity to access generation. Dashboard and system status bind
data/error to an opaque memoized request owner and hide mismatches during render,
before passive effects. Pending/new owners cannot display the previous result.
Existing cancellation still rejects late responses. No shared cache, authorization
policy, session persistence, business mutation or backend contract was added.

Controlled RED:7FAIL/3PASS. GREEN:10PASS, repeated twice. Full frontend686PASS
in40files. Typecheck/lint/buildPASS; backend identity/auth/status/workflow
contracts198PASS plus5audited main-boundary tests. No timeout/assertion relaxation.

CI follow-up: initial PR run41268142328 had685PASS/1FAIL in the existing CAPA
submit interaction, while the same SHA's push run passed. Local baseline stress
passed20/20; no CAPA product defect was reproduced. Await each controlled-input
commit in that test, preserving every assertion, payload and request count;
input-commit stress passed20/20. This is test synchronization, not a CAPA runtime
fix or proof that an intermittent failure cannot recur. Final CI remains a gate.
The first local follow-up full run recorded683PASS/3FAIL: the analogous assess
date assertion plus two unrelated navigation timeouts. Assess input commits are
also awaited explicitly; no timeout is increased or assertion removed. The final
full run must pass separately before merge; failed logs remain in local evidence.
After main255 integration, CI run41295109360 recorded685PASS/1FAIL in the header
test: the public logo appeared before `/app/status` selected header_stub. Await
the required signed-in identity before checking authenticated chrome; retain all
header assertions. This is a test readiness barrier, not a production header fix.
Audited main PR254 adds an isolated pure evidence module/tests only; its18tests
pass. No backend owner file is modified by this slice.

Production-build browser at1366×768,1920×1080,390×844: client=scroll at all widths;
one dashboard GET, same-credential identity revalidation, first-owner hiding,
logout/Back/Forward/reload isolation, canonical Case/Line selection, pending expiry,
late response, real409, unknown-commit recovery and keyboard probes. Development
StrictMode mount replay was recorded separately; it is not a production request
count regression. StrictMode remains enabled in source.

## Release-readiness assessment (read-only)

| Dimension | Observation / verdict |
| --- | --- |
| Candidate source | Current Codex branch from audited main011dc59; exact tested/merged SHA recorded in completion evidence |
| Backend runtime | Public endpoints report97182e58c3a673938d1b263c7eeaab41d28147b4; executable/release symlink not independently attested |
| Frontend runtime | Git SHA UNATTESTED; served entry asset SHA25654530256db621527e9d17ed546fb04bff3a64a711a53cf963184903279b6ba99 |
| Candidate frontend | Built entry asset SHA256ae2eac6b5157ee38c84e39bb1e5d3d4ec7a5b355530ac0a53434eb2336d08000; differs from served asset |
| Database/schema | Public `/api/readyz` reports actual=expected20261012_0023 for that runtime; physical DB identity requires operator attestation |
| Candidate schema | Source expects20261025_0026;0024/0025/0026 were read, not executed.0025 fails closed on nonempty unlinked snapshots |
| API compatibility | Runtime61paths vs candidate67; six candidate document/readiness/render paths absent. Shared path presence is not payload compatibility proof |
| Authentication | Runtime reportsgoogle_oidc; no valid A/B authentication acceptance |
| Runtime mobile | Old served bundle scroll469/client390, distinct from candidate390/390; do not patch candidate to mask version drift |
| CI | Exact candidate six required jobs plus push backend and postmerge verification required; links in completion report |
| Backup/rollback | Mandatory approved backup, restore evidence, exact-source wrapper and rollback prerequisites remain external gates; symlink rollback is not DB rollback |
| NAS/documents | No binary/storage/legal-output acceptance; metadata checks are not Word UAT |

**CI-ready is not deployment-ready, authenticated-UAT-ready or production-ready.**
Verdict: **HOLD_DEPLOY / AUTHENTICATED_UAT_BLOCKED**. No new OAuth/client/DNS/env
setting, deployment, migration, backup/timer or restore operation was performed.
Source/runtime metadata and OpenAPI drift require operator attestation and an
approved release pairing before any real acceptance against candidate contracts.

## Protocol when external prerequisites are provided

1. Operator provides approved URL, role expectations and synthetic record aliases;
   no password, token, cookie or email identity in the evidence package.
2. Human signs in through Google. Never extract credentials from the browser or
   inject fixture identities into a real environment. Observe exact origin and
   canonical `/auth/me`, recording role/permission results with account aliases.
3. This session's rehearsal/production scope is read-only. Authorized write/deny,
   audit and concurrency probes remain disposable until a separate explicit
   operation scope exists. A local proxy405 is not backend authorization proof.
4. Run the matrix, record expected/actual HTTP authorization and redacted canonical
   identities/state/audit differences. Mark unexecuted scenarios separately.
5. Keep Issue6 backend-owned and QĐKT206/Issues74/144/ready_to_render=False unchanged.
   No cross-Case/reload/logout/account draft persistence policy is inferred.

Evidence: `.codex/evidence/oidc-ab-acceptance-20261101/` outside Git. Native speech,
Google A/B, original VBA runtime, signed binaries and production UAT remain
NOT_EXECUTED. The existing inline automatic-focus-return evidence gap is unchanged.
