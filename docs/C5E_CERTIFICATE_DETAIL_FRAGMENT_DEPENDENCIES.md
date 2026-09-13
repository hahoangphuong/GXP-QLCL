# C.5e certificate-detail fragment dependency audit

Before production renderer integration, all extracted certificate-detail
fragments must be checked for OOXML dependencies outside
`word/document.xml`.

The audit covers:

- `w:pStyle`
- `w:rStyle`
- `w:tblStyle`
- `w:numId`
- relationship attributes in the Office relationships namespace
- drawings
- embedded objects
- altChunk
- section properties

Missing source definitions or unsupported structural dependencies fail closed.

Scope is GMP, GLP and GSP only. GDP is excluded.