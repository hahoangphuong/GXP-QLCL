# GxP Web — Codex Handoff Pack

## Setup
1. Put this pack at repository root.
2. Put legacy artifacts under a protected `legacy/` folder:
   - `Danh sách Kiểm tra GPs.xlsb`
   - `GPs.xlam`
3. Use a private repository/environment approved for sensitive data.
4. Keep `legacy/`, `artifacts/`, local databases, `.env*`, and generated frontend/build outputs out of git.
5. If you need committable test data, create sanitized fixtures under dedicated test paths instead of reusing private production inputs.
6. Give Codex `CODEX_START_PROMPT.md` as the first task.
7. Codex must complete Phase 0 before main application implementation.

Recommended layout:

```text
/
  AGENTS.md
  CODEX_START_PROMPT.md
  README_HANDOFF.md
  legacy/
    Danh sách Kiểm tra GPs.xlsb
    GPs.xlam
  docs/
    DECISIONS.md
    ARCHITECTURE.md
    FILE_STORAGE_CONTRACT.md
    MIGRATION_PLAN.md
    CODEX_WORKFLOW.md
    IT_VPN_REQUEST_GUIDE.md
    LEGACY_REVERSE_ENGINEERING_CHECKLIST.md
    ADR/
  backend/
  frontend/
  migrations/
  tools/
  tests/
```
