# Targeted backend feedback (non-authoritative)

Use this **before opening a PR** or while fixing a failing regression, instead of
waiting for a complete GitHub full-suite run after every small edit.

This opt-in local tool does **not** replace the six required exact-HEAD CI checks,
the PostgreSQL B6/cross-head gate, post-merge verification, authenticated UAT,
or any deployment/release approval.

## List a fixed suite

```bash
python -m tools.targeted_backend_feedback --suite reassessment --list
python -m tools.targeted_backend_feedback --suite certificate-owner --list
python -m tools.targeted_backend_feedback --suite ci --list
```

Presets: `ci`, `reassessment`, `case-owner`, `certificate-owner`,
`capa-owner`, `change-request`. All suites select only tracked-style
`tests/test_*.py` files from fixed allowlisted patterns. Missing expected
test files cause a failure, not a silent skip.

## Execute

For pure CI-infrastructure tests (no database needed):

```bash
python -m tools.targeted_backend_feedback --suite ci --execute
```

For a business owner regression, **only** with your already provisioned
local disposable PostgreSQL database:

```bash
export DATABASE_URL='postgresql+psycopg://postgres:postgres@127.0.0.1:5432/gxp_qlcl_test'
python -m tools.targeted_backend_feedback --suite reassessment --execute
```

The helper **never** creates or migrates a database, deploys anything, calls a
cloud service, or runs against a non-loopback database or a database named
`gxp_qlcl`/`gxp_legacy_rehearsal`. Prepare the disposable test schema through
the established local test workflow before executing integration regressions.

For a newly changed test module outside a preset, use explicit pytest directly:

```bash
python -m pytest -q tests/test_exact_changed_module.py
```

A targeted PASS is only developer feedback and says nothing about other tests.
Merge requires all six full exact-HEAD GitHub checks to run and succeed; CI
cannot infer application readiness from the targeted result.
