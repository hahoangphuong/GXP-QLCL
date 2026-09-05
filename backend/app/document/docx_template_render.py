from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from backend.app.document.c5e_certificate_detail_runtime import (
    CertificateDetailRuntimeError,
    build_certificate_detail_runtime_docx,
)
from backend.app.document.c5e_certificate_detail_semantic_projection import (
    CERTIFICATE_DETAIL_DESTINATION_BOOKMARK,
)
from backend.app.document.c5e_certificate_detail_source_asset_locator import (
    build_runtime_source_asset_locator,
)
from backend.app.document.output_version import finalize_output_document_version_write
from backend.app.document.template_contract_runtime import (
    build_scalar_replacement_plan_for_template,
    load_default_template_contract_reconciliation,
)
from backend.app.document.template_binary import open_template_binary_stream

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from backend.app.document.service import TemplateAwareAllocatedDocumentGeneration
    from backend.app.storage.types import StorageServiceProtocol


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NSMAP = {"w": WORD_NS}


class DocxTemplateRenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class DocxTemplateRenderResult:
    document_version_id: str
    generation_run_id: str
    checksum_sha256: str
    byte_size: int
    replaced_bookmarks: tuple[str, ...]
    replaced_table_regions: tuple[str, ...]
    replaced_parts: tuple[str, ...]
    scalar_replacement_mode: str
    template_variant_key: str | None


def _w(tag: str) -> str:
    return f"{{{WORD_NS}}}{tag}"


def _replace_bookmark_in_paragraph(paragraph: ET.Element, bookmark_name: str, replacement_text: str) -> bool:
    children = list(paragraph)
    start_index = None
    end_index = None
    start_id = None
    for index, child in enumerate(children):
        if child.tag == _w("bookmarkStart") and child.attrib.get(_w("name")) == bookmark_name:
            start_index = index
            start_id = child.attrib.get(_w("id"))
            continue
        if (
            start_index is not None
            and child.tag == _w("bookmarkEnd")
            and child.attrib.get(_w("id")) == start_id
        ):
            end_index = index
            break
    if start_index is None or end_index is None:
        return False

    text_nodes: list[ET.Element] = []
    for child in children[start_index + 1 : end_index]:
        for text_node in child.findall(".//w:t", NSMAP):
            text_nodes.append(text_node)

    if text_nodes:
        text_nodes[0].text = replacement_text
        text_nodes[0].set(f"{{{XML_NS}}}space", "preserve")
        for text_node in text_nodes[1:]:
            text_node.text = ""
        return True

    run = ET.Element(_w("r"))
    text_node = ET.SubElement(run, _w("t"))
    text_node.text = replacement_text
    text_node.set(f"{{{XML_NS}}}space", "preserve")
    paragraph.insert(start_index + 1, run)
    return True


def _replace_bookmarks_in_container(
    container: ET.Element,
    replacements: dict[str, str],
    *,
    require_all: bool = True,
) -> tuple[str, ...]:
    paragraphs = container.findall(".//w:p", NSMAP)
    replaced: list[str] = []
    for bookmark_name, replacement_text in replacements.items():
        matched = False
        for paragraph in paragraphs:
            if _replace_bookmark_in_paragraph(paragraph, bookmark_name, replacement_text):
                matched = True
                replaced.append(bookmark_name)
                break
        if not matched and require_all:
            raise DocxTemplateRenderError(
                f"Template-aware scalar render could not find bookmark {bookmark_name!r} in word/document.xml."
            )
    return tuple(replaced)


def _is_supported_scalar_part(name: str) -> bool:
    if name == "word/document.xml":
        return True
    if name.startswith("word/header") and name.endswith(".xml"):
        return True
    if name.startswith("word/footer") and name.endswith(".xml"):
        return True
    return False


def _apply_scalar_bookmarks(document_xml: bytes, replacements: dict[str, str]) -> tuple[bytes, tuple[str, ...]]:
    root = ET.fromstring(document_xml)
    replaced = _replace_bookmarks_in_container(root, replacements)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), replaced


def _find_table_row_with_region_bookmark(root: ET.Element, region_bookmark_name: str) -> tuple[ET.Element, int, ET.Element] | None:
    for table in root.findall(".//w:tbl", NSMAP):
        rows = list(table.findall("./w:tr", NSMAP))
        for index, row in enumerate(rows):
            for bookmark in row.findall(".//w:bookmarkStart", NSMAP):
                if bookmark.attrib.get(_w("name")) == region_bookmark_name:
                    return table, index, row
    return None


def _strip_bookmark_markup(element: ET.Element) -> None:
    for parent in list(element.iter()):
        for child in list(parent):
            if child.tag in {_w("bookmarkStart"), _w("bookmarkEnd")}:
                parent.remove(child)


def _apply_table_regions(
    root: ET.Element,
    table_regions: tuple["TableRegionRenderInput", ...],
) -> tuple[str, ...]:
    replaced_regions: list[str] = []
    for region in table_regions:
        located = _find_table_row_with_region_bookmark(root, region.region_bookmark_name)
        if located is None:
            raise DocxTemplateRenderError(
                f"Template-aware table render could not find row bookmark {region.region_bookmark_name!r}."
            )
        table, row_index, template_row = located
        cloned_rows: list[ET.Element] = []
        for row_values in region.rows:
            row_clone = deepcopy(template_row)
            _replace_bookmarks_in_container(row_clone, row_values)
            _strip_bookmark_markup(row_clone)
            cloned_rows.append(row_clone)
        table.remove(template_row)
        for offset, row_clone in enumerate(cloned_rows):
            table.insert(row_index + offset, row_clone)
        replaced_regions.append(region.region_bookmark_name)
    return tuple(replaced_regions)


def _apply_certificate_detail_before_generic_render(
    storage: "StorageServiceProtocol",
    *,
    prepared: object,
    template_bytes: bytes,
    replacements: dict[str, str],
) -> bytes:
    projection = getattr(prepared, "certificate_detail_projection", None)
    if projection is None:
        return template_bytes

    if CERTIFICATE_DETAIL_DESTINATION_BOOKMARK in replacements:
        raise DocxTemplateRenderError(
            "C.5e certificate-detail destination bookmark 'Pvi' is owned by "
            "Input_DC_to_CC composition and must not appear in the generic "
            "scalar replacement plan."
        )

    table_regions = getattr(prepared, "table_regions", ())
    if any(
        region.region_bookmark_name == CERTIFICATE_DETAIL_DESTINATION_BOOKMARK
        for region in table_regions
    ):
        raise DocxTemplateRenderError(
            "C.5e certificate-detail destination bookmark 'Pvi' is owned by "
            "Input_DC_to_CC composition and must not be used as a generic "
            "table-region bookmark."
        )

    source_locator = build_runtime_source_asset_locator(
        gxp_type=projection.gxp_type,
    )

    try:
        result = build_certificate_detail_runtime_docx(
            storage,
            destination_template_bytes=template_bytes,
            projection=projection,
            source_locator=source_locator,
        )
    except CertificateDetailRuntimeError as exc:
        raise DocxTemplateRenderError(
            f"C.5e certificate-detail runtime render failed: {exc}"
        ) from exc

    return result.render_result.binary_payload


def build_template_aware_docx_bytes(
    storage: "StorageServiceProtocol",
    allocated: "TemplateAwareAllocatedDocumentGeneration",
) -> tuple[bytes, tuple[str, ...], tuple[str, ...], tuple[str, ...], str, str | None]:
    if not allocated.template_render_ready:
        raise DocxTemplateRenderError(
            f"Template-aware DOCX render is not ready: {allocated.template_binary_requirement.readiness_status}."
        )
    prepared = allocated.allocated.prepared
    if prepared.source_binary_requirements:
        raise DocxTemplateRenderError(
            "Template-aware scalar DOCX render does not implement copy-forward semantics."
        )
    with open_template_binary_stream(storage, allocated.template_binary_requirement) as stream:
        template_bytes = stream.read()
    replacement_plan = build_scalar_replacement_plan_for_template(
        load_default_template_contract_reconciliation(),
        prepared.generation_plan.template.family_code,
        prepared.payload_result.envelope.fields,
        template_bytes=template_bytes,
    )
    replacements = replacement_plan.bookmark_replacements

    # Build the generic replacement plan against the untouched destination
    # package so ownership conflicts are detected before mutation. The C.5e
    # composer then owns Pvi and removes only that bookmark markup; generic
    # scalar/table mutation continues against the composed package.
    template_bytes = _apply_certificate_detail_before_generic_render(
        storage,
        prepared=prepared,
        template_bytes=template_bytes,
        replacements=replacements,
    )

    source_buffer = BytesIO(template_bytes)
    target_buffer = BytesIO()
    with ZipFile(source_buffer, "r") as source_archive, ZipFile(target_buffer, "w", compression=ZIP_DEFLATED) as target_archive:
        if "word/document.xml" not in source_archive.namelist():
            raise DocxTemplateRenderError("Template binary does not contain word/document.xml.")
        replaced_bookmarks: list[str] = []
        replaced_regions: tuple[str, ...] = ()
        replaced_parts: list[str] = []
        for name in source_archive.namelist():
            payload = source_archive.read(name)
            if name == "word/document.xml":
                root = ET.fromstring(payload)
                replaced_regions = _apply_table_regions(root, prepared.table_regions)
                replaced_in_part = _replace_bookmarks_in_container(root, replacements, require_all=False)
                if replaced_in_part:
                    replaced_bookmarks.extend(replaced_in_part)
                    replaced_parts.append(name)
                payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            elif _is_supported_scalar_part(name):
                root = ET.fromstring(payload)
                matched_names = list(_replace_bookmarks_in_container(root, replacements, require_all=False))
                if matched_names:
                    replaced_bookmarks.extend(matched_names)
                    replaced_parts.append(name)
                    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            target_archive.writestr(name, payload)
    unique_bookmarks = tuple(dict.fromkeys(replaced_bookmarks))
    unique_parts = tuple(dict.fromkeys(replaced_parts))
    missing_bookmarks = sorted(set(replacements) - set(unique_bookmarks))
    if missing_bookmarks:
        raise DocxTemplateRenderError(
            "Template-aware scalar render could not find required bookmarks across DOCX parts: "
            + ", ".join(missing_bookmarks)
        )
    return (
        target_buffer.getvalue(),
        unique_bookmarks,
        replaced_regions,
        unique_parts,
        replacement_plan.mode,
        replacement_plan.template_variant_key,
    )


def render_template_aware_docx_and_finalize(
    session: "Session",
    storage: "StorageServiceProtocol",
    allocated: "TemplateAwareAllocatedDocumentGeneration",
) -> DocxTemplateRenderResult:
    binary_payload, replaced_bookmarks, replaced_regions, replaced_parts, scalar_replacement_mode, template_variant_key = build_template_aware_docx_bytes(
        storage,
        allocated,
    )
    checksum = finalize_output_document_version_write(
        session,
        storage,
        allocated.allocated.output_allocation,
        binary_payload=binary_payload,
    )
    return DocxTemplateRenderResult(
        document_version_id=allocated.allocated.output_allocation.document_version_id,
        generation_run_id=allocated.allocated.output_allocation.generation_run_id,
        checksum_sha256=checksum,
        byte_size=len(binary_payload),
        replaced_bookmarks=replaced_bookmarks,
        replaced_table_regions=replaced_regions,
        replaced_parts=replaced_parts,
        scalar_replacement_mode=scalar_replacement_mode,
        template_variant_key=template_variant_key,
    )
