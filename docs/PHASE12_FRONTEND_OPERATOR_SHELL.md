# Phase 12 Frontend Operator Shell

## Goal
Create the first usable web operator shell on top of the backend APIs delivered in Phases 8 through 11.

## Delivered
- frontend package scaffold: [frontend/package.json](/D:/GXP-QLCL/frontend/package.json)
- Vite + TypeScript config:
  - [frontend/tsconfig.json](/D:/GXP-QLCL/frontend/tsconfig.json)
  - [frontend/tsconfig.app.json](/D:/GXP-QLCL/frontend/tsconfig.app.json)
  - [frontend/tsconfig.node.json](/D:/GXP-QLCL/frontend/tsconfig.node.json)
  - [frontend/vite.config.ts](/D:/GXP-QLCL/frontend/vite.config.ts)
  - [frontend/index.html](/D:/GXP-QLCL/frontend/index.html)
  - [frontend/src/vite-env.d.ts](/D:/GXP-QLCL/frontend/src/vite-env.d.ts)
- operator shell implementation:
  - [frontend/src/main.tsx](/D:/GXP-QLCL/frontend/src/main.tsx)
  - [frontend/src/App.tsx](/D:/GXP-QLCL/frontend/src/App.tsx)
  - [frontend/src/styles.css](/D:/GXP-QLCL/frontend/src/styles.css)
  - [frontend/src/types.ts](/D:/GXP-QLCL/frontend/src/types.ts)
  - [frontend/src/lib/api.ts](/D:/GXP-QLCL/frontend/src/lib/api.ts)
  - [frontend/src/lib/storage.ts](/D:/GXP-QLCL/frontend/src/lib/storage.ts)
- ADR: [docs/ADR/0040-phase12-frontend-uses-vite-react-router-client-shell.md](/D:/GXP-QLCL/docs/ADR/0040-phase12-frontend-uses-vite-react-router-client-shell.md)

## Current shell scope
- dashboard:
  - app status
  - migration/cutover phase visibility
  - basic catalog counts
- case workspace:
  - client-side search across loaded cases/sites/companies
  - selected case detail
  - navigation to dedicated case route
- document workbench:
  - choose `family_code`
  - send `prepare` request
  - send `render-template-docx` request
  - inspect blocked reasons
  - inspect generation-run status
  - inspect logical-document lineage

## Current rules
- the shell only calls backend APIs; it does not implement workflow or document logic locally
- auth remains the current backend stub-header model and is configurable from the shell header
- no NAS credentials or storage ownership are present in frontend code
- local development defaults to same-origin API calls and relies on the Vite proxy for:
  - `/app`
  - `/companies`
  - `/sites`
  - `/cases`
  - `/documents`
  - `/document-generation-runs`
  - `/certificates`
  - `/business-eligibility-certificates`
  - `/storage`
- `VITE_API_BASE_URL` can override the API origin when same-origin/proxy is not the intended runtime

## UX direction
- keep the shell intentional and operational rather than spreadsheet-like
- show blocked document reasons explicitly instead of hiding them behind generic failure messages
- keep document workbench payload editing thin and backend-owned until family-specific operator forms are actually justified

## Scope boundary
- no production auth integration yet
- no final deployment packaging of frontend with Cloud Run yet
- no duplication of backend workflow validation in the browser
- no attempt to expose raw file management or direct SMB/NAS access in the shell
