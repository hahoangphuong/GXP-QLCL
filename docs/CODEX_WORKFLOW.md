# Codex Working Protocol

Repository docs are durable context; do not rely on one giant prompt as memory.

For each task:
1. Read AGENTS and relevant docs.
2. Inspect actual code/data.
3. Identify invariants and owner layer.
4. Plan tests.
5. Make the smallest coherent change.
6. Run tests/lint/typecheck.
7. Inspect diff.
8. Update docs when architecture/storage/data/workflow semantics change.

Parallel agents only with clearly non-overlapping write scopes.

Do not invent legacy behavior. Inspect VBA/data/templates; record uncertainty and create ADR/question.

Handoff format:
Summary; Files changed; Decisions; Tests; Results; Data impact; Storage impact; Security; Compatibility; Risks; Next task.
