from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from backend.app.document.c5e_certificate_detail_fragment_extractor import (
    extract_bookmark_table_fragment_from_docx_bytes,
)
from backend.app.document.c5e_certificate_detail_ooxml_composer import (
    CertificateDetailOOXMLCompositionError,
    compose_certificate_detail_document_xml,
)
from backend.app.document.c5e_certificate_detail_semantic_projection import (
    CERTIFICATE_DETAIL_DESTINATION_BOOKMARK,
    CERTIFICATE_DETAIL_FAMILY,
    CERTIFICATE_DETAIL_SOURCE_VARIANT,
    CertificateDetailSemanticProjection,
)
from backend.app.document.c5e_certificate_detail_typetext_resolver import (
    CertificateDetailTranslationDictionary,
    CertificateDetailTypeTextError,
    resolve_certificate_detail_typetext,
)


DOCUMENT_XML_PART = "word/document.xml"

SUPPORTED_GXP_TYPES = frozenset(
    {
        "GMP",
        "GLP",
        "GSP",
    }
)


class CertificateDetailDocxRenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class CertificateDetailDocxRenderResult:
    binary_payload: bytes
    destination_bookmark: str
    source_variant: str
    gxp_type: str
    extracted_bookmarks: tuple[str, ...]
    inserted_fragment_count: int
    emitted_text_operation_count: int


def _validate_projection(
    projection: CertificateDetailSemanticProjection,
) -> None:
    if projection.family_code != CERTIFICATE_DETAIL_FAMILY:
        raise CertificateDetailDocxRenderError(
            "C.5e certificate-detail DOCX renderer only supports "
            f"family_code={CERTIFICATE_DETAIL_FAMILY!r}; "
            f"got {projection.family_code!r}."
        )

    if projection.source_variant != CERTIFICATE_DETAIL_SOURCE_VARIANT:
        raise CertificateDetailDocxRenderError(
            "C.5e certificate-detail DOCX renderer only supports "
            f"source_variant={CERTIFICATE_DETAIL_SOURCE_VARIANT!r}; "
            f"got {projection.source_variant!r}."
        )

    if (
        projection.destination_bookmark
        != CERTIFICATE_DETAIL_DESTINATION_BOOKMARK
    ):
        raise CertificateDetailDocxRenderError(
            "C.5e certificate-detail destination bookmark mismatch: "
            f"{projection.destination_bookmark!r}."
        )

    if projection.gxp_type not in SUPPORTED_GXP_TYPES:
        raise CertificateDetailDocxRenderError(
            "Unsupported C.5e certificate-detail GxP type: "
            f"{projection.gxp_type!r}."
        )


def _ordered_source_bookmarks(
    projection: CertificateDetailSemanticProjection,
) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()

    for operation in projection.operations:
        if operation.kind != "formatted_fragment_copy":
            continue

        bookmark = operation.source_bookmark

        if not isinstance(bookmark, str) or not bookmark:
            raise CertificateDetailDocxRenderError(
                "formatted_fragment_copy operation has no source bookmark."
            )

        if bookmark in seen:
            continue

        seen.add(bookmark)
        ordered.append(bookmark)

    return tuple(ordered)


def _read_destination_package(
    destination_template_bytes: bytes,
) -> tuple[
    tuple[
        tuple[object, bytes],
        ...
    ],
    bytes,
]:
    """
    Validate the destination DOCX/DOTX package before touching any
    certificate-detail source fragment.

    This gives deterministic fail-closed ownership:
      destination package invalid
        -> destination error
      source fragment invalid
        -> fragment extraction error

    The returned entry list preserves package entry order and does not
    collapse duplicate ZIP entry names.
    """

    source_buffer = BytesIO(
        destination_template_bytes
    )

    try:
        with ZipFile(
            source_buffer,
            "r",
        ) as archive:
            if DOCUMENT_XML_PART not in archive.namelist():
                raise CertificateDetailDocxRenderError(
                    "Destination certificate template does not contain "
                    "word/document.xml."
                )

            entries: list[
                tuple[object, bytes]
            ] = []

            document_xml: bytes | None = None

            for info in archive.infolist():
                payload = archive.read(
                    info.filename
                )

                entries.append(
                    (
                        info,
                        payload,
                    )
                )

                if (
                    info.filename
                    == DOCUMENT_XML_PART
                    and document_xml is None
                ):
                    document_xml = payload

            if document_xml is None:
                raise CertificateDetailDocxRenderError(
                    "Destination certificate template does not contain "
                    "word/document.xml."
                )

            return (
                tuple(entries),
                document_xml,
            )

    except BadZipFile as exc:
        raise CertificateDetailDocxRenderError(
            "Destination certificate template is not a valid "
            "DOCX/DOTX ZIP package."
        ) from exc


def _extract_fragment_map(
    source_docx_bytes: bytes,
    *,
    source_bookmarks: tuple[str, ...],
) -> dict[str, str]:
    fragments: dict[str, str] = {}

    for bookmark in source_bookmarks:
        try:
            extracted = (
                extract_bookmark_table_fragment_from_docx_bytes(
                    source_docx_bytes,
                    bookmark_name=bookmark,
                )
            )
        except Exception as exc:
            raise CertificateDetailDocxRenderError(
                "Failed to extract certificate-detail source fragment "
                f"for bookmark={bookmark!r}."
            ) from exc

        if extracted.bookmark_name != bookmark:
            raise CertificateDetailDocxRenderError(
                "Certificate-detail fragment extractor returned "
                "an unexpected bookmark identity: "
                f"requested={bookmark!r}, "
                f"actual={extracted.bookmark_name!r}."
            )

        if not extracted.fragment_xml:
            raise CertificateDetailDocxRenderError(
                "Certificate-detail fragment extractor returned "
                f"empty XML for bookmark={bookmark!r}."
            )

        fragments[
            bookmark
        ] = extracted.fragment_xml

    return fragments


def _compose_document_xml(
    document_xml: bytes,
    *,
    projection: CertificateDetailSemanticProjection,
    fragment_xml_by_bookmark: dict[str, str],
    dictionary: CertificateDetailTranslationDictionary | None,
):
    try:
        rendered_text_by_sequence = (
            resolve_certificate_detail_typetext(
                projection,
                dictionary=dictionary,
            )
        )

        return compose_certificate_detail_document_xml(
            document_xml,
            projection=projection,
            fragment_xml_by_bookmark=fragment_xml_by_bookmark,
            rendered_text_by_sequence=rendered_text_by_sequence,
        )

    except (
        CertificateDetailTypeTextError,
        CertificateDetailOOXMLCompositionError,
    ) as exc:
        raise CertificateDetailDocxRenderError(
            "C.5e certificate-detail composition failed: "
            f"{exc}"
        ) from exc


def build_certificate_detail_docx_bytes(
    destination_template_bytes: bytes,
    *,
    source_docx_bytes: bytes,
    projection: CertificateDetailSemanticProjection,
    dictionary: CertificateDetailTranslationDictionary | None = None,
) -> CertificateDetailDocxRenderResult:
    """
    Build the certificate-detail DOCX region owned by legacy Input_DC_to_CC.

    Boundary:

        canonical evaluation scope
            -> semantic projection
            -> verified certificate_9 source document
            -> exact bookmark fragment extraction
            -> legacy-compatible TypeText resolution
            -> deterministic OOXML composition at Pvi

    Validation order is deliberate:

        projection contract
            -> destination package
            -> source bookmarks/fragments
            -> TypeText
            -> OOXML composition

    This function deliberately does NOT:
    - locate source assets;
    - read legacy Excel/VBA at runtime;
    - support appendix_z3;
    - support GDP;
    - consume unkeyed_entries;
    - perform scalar/template-registry rendering;
    - perform persistence/finalization.

    Those responsibilities remain outside this owner.
    """

    _validate_projection(
        projection
    )

    (
        destination_entries,
        destination_document_xml,
    ) = _read_destination_package(
        destination_template_bytes
    )

    source_bookmarks = _ordered_source_bookmarks(
        projection
    )

    fragment_xml_by_bookmark = _extract_fragment_map(
        source_docx_bytes,
        source_bookmarks=source_bookmarks,
    )

    composition_result = _compose_document_xml(
        destination_document_xml,
        projection=projection,
        fragment_xml_by_bookmark=fragment_xml_by_bookmark,
        dictionary=dictionary,
    )

    target_buffer = BytesIO()

    with ZipFile(
        target_buffer,
        "w",
        compression=ZIP_DEFLATED,
    ) as target_archive:
        document_part_written = False

        for info, original_payload in destination_entries:
            payload = original_payload

            if (
                info.filename
                == DOCUMENT_XML_PART
                and not document_part_written
            ):
                payload = (
                    composition_result.document_xml
                )

                document_part_written = True

            target_archive.writestr(
                info,
                payload,
            )

    if not document_part_written:
        raise CertificateDetailDocxRenderError(
            "C.5e certificate-detail composition did not write "
            "word/document.xml."
        )

    return CertificateDetailDocxRenderResult(
        binary_payload=(
            target_buffer.getvalue()
        ),
        destination_bookmark=(
            composition_result.destination_bookmark
        ),
        source_variant=(
            projection.source_variant
        ),
        gxp_type=(
            projection.gxp_type
        ),
        extracted_bookmarks=(
            source_bookmarks
        ),
        inserted_fragment_count=(
            composition_result.inserted_fragment_count
        ),
        emitted_text_operation_count=(
            composition_result.emitted_text_operation_count
        ),
    )