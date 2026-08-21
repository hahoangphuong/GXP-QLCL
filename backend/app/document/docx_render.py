from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from backend.app.document.output_version import OutputVersionAllocation, finalize_output_document_version_write

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from backend.app.document.service import AllocatedDocumentGeneration
    from backend.app.storage.local import LocalStorageService


class DocxRenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class DocxRenderResult:
    output_allocation: OutputVersionAllocation
    checksum_sha256: str
    byte_size: int


def _render_paragraph_xml(text: str) -> str:
    safe = escape(text)
    return (
        "<w:p>"
        "<w:r>"
        f"<w:t xml:space=\"preserve\">{safe}</w:t>"
        "</w:r>"
        "</w:p>"
    )


def _build_document_xml(lines: list[str]) -> str:
    paragraphs = "".join(_render_paragraph_xml(line) for line in lines)
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document "
        "xmlns:wpc=\"http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas\" "
        "xmlns:mc=\"http://schemas.openxmlformats.org/markup-compatibility/2006\" "
        "xmlns:o=\"urn:schemas-microsoft-com:office:office\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" "
        "xmlns:m=\"http://schemas.openxmlformats.org/officeDocument/2006/math\" "
        "xmlns:v=\"urn:schemas-microsoft-com:vml\" "
        "xmlns:wp14=\"http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing\" "
        "xmlns:wp=\"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing\" "
        "xmlns:w10=\"urn:schemas-microsoft-com:office:word\" "
        "xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\" "
        "xmlns:w14=\"http://schemas.microsoft.com/office/word/2010/wordml\" "
        "xmlns:w15=\"http://schemas.microsoft.com/office/word/2012/wordml\" "
        "xmlns:wpg=\"http://schemas.microsoft.com/office/word/2010/wordprocessingGroup\" "
        "xmlns:wpi=\"http://schemas.microsoft.com/office/word/2010/wordprocessingInk\" "
        "xmlns:wne=\"http://schemas.microsoft.com/office/word/2006/wordml\" "
        "xmlns:wps=\"http://schemas.microsoft.com/office/word/2010/wordprocessingShape\" "
        "mc:Ignorable=\"w14 w15 wp14\">"
        "<w:body>"
        f"{paragraphs}"
        "<w:sectPr>"
        "<w:pgSz w:w=\"12240\" w:h=\"15840\"/>"
        "<w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\" w:header=\"720\" w:footer=\"720\" w:gutter=\"0\"/>"
        "</w:sectPr>"
        "</w:body>"
        "</w:document>"
    )


def build_baseline_docx_bytes(allocated: "AllocatedDocumentGeneration") -> bytes:
    prepared = allocated.prepared
    if prepared.generation_plan.template.source_application != "Word":
        raise DocxRenderError("Baseline DOCX renderer only supports Word-backed document families.")
    if prepared.source_binary_requirements:
        raise DocxRenderError(
            "Baseline DOCX renderer does not implement copy-forward semantics; families with source dependencies must fail closed."
        )

    lines: list[str] = [
        "GxP Document Baseline Render",
        f"Logical name: {prepared.generation_plan.template.logical_name}",
        f"Family code: {prepared.generation_plan.template.family_code}",
        f"Output file: {allocated.output_allocation.original_filename}",
        f"Document id: {allocated.output_allocation.document_id}",
        f"Generation run id: {allocated.output_allocation.generation_run_id}",
        f"Template pattern: {prepared.generation_plan.template.template_pattern}",
        "",
        "Payload fields:",
    ]
    for field in sorted(prepared.payload_result.envelope.fields, key=lambda item: item.field_name):
        value = "<redacted>" if field.is_sensitive else field.value
        lines.append(f"- {field.field_name}: {value}")
    if prepared.payload_result.missing_registry_fields:
        lines.extend(["", "Registry fields not provided:"])
        for field_name in prepared.payload_result.missing_registry_fields:
            lines.append(f"- {field_name}")

    document_xml = _build_document_xml(lines)
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>""",
        )
        archive.writestr("word/document.xml", document_xml)
        archive.writestr(
            "docProps/core.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>GxP Baseline Render</dc:title>
  <dc:creator>Codex Phase 5</dc:creator>
</cp:coreProperties>""",
        )
        archive.writestr(
            "docProps/app.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Codex GxP Baseline</Application>
</Properties>""",
        )
    return buffer.getvalue()


def render_baseline_docx_and_finalize(
    session: "Session",
    storage: "LocalStorageService",
    allocated: "AllocatedDocumentGeneration",
) -> DocxRenderResult:
    binary_payload = build_baseline_docx_bytes(allocated)
    checksum = finalize_output_document_version_write(
        session,
        storage,
        allocated.output_allocation,
        binary_payload=binary_payload,
    )
    return DocxRenderResult(
        output_allocation=allocated.output_allocation,
        checksum_sha256=checksum,
        byte_size=len(binary_payload),
    )
