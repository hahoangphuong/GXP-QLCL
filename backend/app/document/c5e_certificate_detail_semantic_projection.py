from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal


CERTIFICATE_DETAIL_FAMILY = "CERTIFICATE_ISSUANCE_WORD"
CERTIFICATE_DETAIL_SOURCE_VARIANT = "certificate_9"
CERTIFICATE_DETAIL_DESTINATION_BOOKMARK = "Pvi"

# Proven:
# PVCN_rowPriPack = 93 -> key 6.1.1
# PVCN_rowSecPack = 96 -> key 6.2.1
PACKAGING_SPECIAL_KEYS = frozenset(
    {
        "6.1.1",
        "6.2.1",
    }
)


class CertificateDetailSemanticProjectionError(
    RuntimeError
):
    pass


OperationKind = Literal[
    "scope_heading_vi",
    "scope_heading_en",
    "formatted_fragment_copy",
    "append_custom_description_vi",
    "append_custom_description_en",
    "append_scope_note_vi",
    "append_scope_note_en",
]


@dataclass(frozen=True)
class CertificateDetailSemanticOperation:
    sequence: int
    kind: OperationKind
    block_id: str

    taxonomy_node_id: str | None = None
    node_key: str | None = None
    source_bookmark: str | None = None

    raw_text: str | None = None
    branch: str | None = None
    translation_intent: str | None = None

    split_separator: str | None = None
    text_prefix: str = ""
    text_suffix: str = ""


@dataclass(frozen=True)
class CertificateDetailSemanticProjection:
    family_code: str
    source_variant: str
    destination_bookmark: str
    gxp_type: str
    eng_part: bool

    operations: tuple[
        CertificateDetailSemanticOperation,
        ...,
    ]


def key2bookmark(
    node_key: str,
) -> str:
    value = str(
        node_key or ""
    ).strip()

    if not value:
        raise (
            CertificateDetailSemanticProjectionError(
                "Taxonomy node_key must not be blank."
            )
        )

    # Exact legacy contract:
    # trim
    # -> remove ONE trailing "."
    # -> prefix L
    # -> "." to "_"
    if value.endswith("."):
        value = value[:-1]

    return (
        "L"
        + value.replace(
            ".",
            "_",
        )
    )


def _clean_scope_name(
    value: Any,
) -> str:
    result = str(
        value or ""
    ).strip()

    # DelLastIf(s_N, "¶")
    if result.endswith("¶"):
        result = result[:-1]

    return result


def _selection_order(
    selection: dict[str, Any],
) -> tuple[int, str]:
    try:
        source_order = int(
            selection.get("source_order")
        )
    except (TypeError, ValueError):
        source_order = 2**31 - 1

    return (
        source_order,
        str(
            selection.get(
                "taxonomy_node_id"
            )
            or ""
        ),
    )


def _block_order(
    block: dict[str, Any],
) -> tuple[int, str]:
    try:
        ordinal = int(
            block.get("ordinal")
        )
    except (TypeError, ValueError):
        ordinal = 2**31 - 1

    return (
        ordinal,
        str(
            block.get("id")
            or ""
        ),
    )


def project_certificate_detail_semantic_operations(
    *,
    family_code: str,
    blocks: Iterable[
        dict[str, Any]
    ],
    taxonomy_nodes: Iterable[
        dict[str, Any]
    ],
    gxp_type: str,
    eng_part: bool,
) -> CertificateDetailSemanticProjection:
    """
    Port the semantic operation order of active
    RecordForm.Input_DC_to_CC.

    This owner does NOT:
    - mutate DOCX;
    - invoke Word/COM;
    - perform translations;
    - use prose/fuzzy matching;
    - consume unkeyed_entries.
    """

    if (
        family_code
        != CERTIFICATE_DETAIL_FAMILY
    ):
        raise (
            CertificateDetailSemanticProjectionError(
                "Unsupported C.5e "
                "certificate-detail family: "
                f"{family_code!r}."
            )
        )

    if gxp_type not in {
        "GMP",
        "GLP",
        "GSP",
    }:
        raise (
            CertificateDetailSemanticProjectionError(
                "Unsupported C.5e "
                "certificate-detail GxP type: "
                f"{gxp_type!r}."
            )
        )

    node_by_id: dict[
        str,
        dict[str, Any],
    ] = {}

    for node in taxonomy_nodes:
        node_id = str(
            node.get("id")
            or ""
        )

        if not node_id:
            raise (
                CertificateDetailSemanticProjectionError(
                    "Taxonomy node id "
                    "must not be blank."
                )
            )

        if node_id in node_by_id:
            raise (
                CertificateDetailSemanticProjectionError(
                    "Duplicate taxonomy node id: "
                    f"{node_id!r}."
                )
            )

        node_by_id[
            node_id
        ] = node

    operations: list[
        CertificateDetailSemanticOperation
    ] = []

    sequence = 0

    def emit(
        **kwargs: Any,
    ) -> None:
        nonlocal sequence

        sequence += 1

        operations.append(
            CertificateDetailSemanticOperation(
                sequence=sequence,
                **kwargs,
            )
        )

    for block in sorted(
        list(blocks),
        key=_block_order,
    ):
        block_id = str(
            block.get("id")
            or ""
        )

        if not block_id:
            raise (
                CertificateDetailSemanticProjectionError(
                    "Certificate-detail block id "
                    "must not be blank."
                )
            )

        #
        # Scope name
        #
        # VBA:
        # "* " & DelLastIf(s_N, "¶") & " - "
        # Translate_VE_Diachi(...) & vbCrLf
        #
        # IMPORTANT:
        # neither line is gated by EngPart.
        #
        scope_name = _clean_scope_name(
            block.get("name")
        )

        if scope_name:
            emit(
                kind="scope_heading_vi",
                block_id=block_id,
                raw_text=scope_name,
                branch=(
                    "scope_name_nonblank"
                ),
                text_prefix="* ",
                text_suffix=" - ",
            )

            emit(
                kind="scope_heading_en",
                block_id=block_id,
                raw_text=scope_name,
                branch=(
                    "scope_name_nonblank"
                ),
                translation_intent=(
                    "legacy_translate_ve_diachi"
                ),
                text_prefix="",
                text_suffix="\r\n",
            )

        selections = sorted(
            list(
                block.get(
                    "selections"
                )
                or ()
            ),
            key=_selection_order,
        )

        seen_node_ids: set[
            str
        ] = set()

        for selection in selections:
            taxonomy_node_id = str(
                selection.get(
                    "taxonomy_node_id"
                )
                or ""
            )

            if not taxonomy_node_id:
                raise (
                    CertificateDetailSemanticProjectionError(
                        "Selection in block "
                        f"{block_id!r} "
                        "has no taxonomy_node_id."
                    )
                )

            if (
                taxonomy_node_id
                in seen_node_ids
            ):
                raise (
                    CertificateDetailSemanticProjectionError(
                        "Duplicate taxonomy "
                        "selection "
                        f"{taxonomy_node_id!r} "
                        "in block "
                        f"{block_id!r}."
                    )
                )

            seen_node_ids.add(
                taxonomy_node_id
            )

            node = node_by_id.get(
                taxonomy_node_id
            )

            if node is None:
                raise (
                    CertificateDetailSemanticProjectionError(
                        "Selection is outside "
                        "the current taxonomy: "
                        "taxonomy_node_id="
                        f"{taxonomy_node_id!r}."
                    )
                )

            node_key = str(
                node.get("key")
                or ""
            ).strip()

            source_bookmark = (
                key2bookmark(
                    node_key
                )
            )

            emit(
                kind=(
                    "formatted_fragment_copy"
                ),
                block_id=block_id,
                taxonomy_node_id=(
                    taxonomy_node_id
                ),
                node_key=node_key,
                source_bookmark=(
                    source_bookmark
                ),
                branch=(
                    "exact_key2bookmark"
                ),
            )

            custom_description = str(
                selection.get(
                    "custom_description"
                )
                or ""
            ).strip()

            if not custom_description:
                continue

            main_topic = str(
                node.get(
                    "main_topic"
                )
                or ""
            ).strip()

            #
            # Exact VBA branch order:
            #
            # 1. main_topic
            # 2. PVCN_rowPriPack /
            #    PVCN_rowSecPack
            # 3. normal
            #
            if main_topic:
                branch = "main_topic"

                # DelLastIf(desc, ";")
                split_separator = None

                text_prefix = " ("
                text_suffix = ")"

            elif (
                gxp_type == "GMP"
                and node_key
                in PACKAGING_SPECIAL_KEYS
            ):
                branch = (
                    "packaging_special"
                )

                # SplitLines(desc, "; ")
                split_separator = "; "

                text_prefix = (
                    ":\r\n\t"
                )
                text_suffix = ""

            else:
                branch = "normal"

                # SplitLines(desc)
                split_separator = ";"

                text_prefix = (
                    ":\r\n\t"
                )
                text_suffix = ""

            emit(
                kind=(
                    "append_custom_description_vi"
                ),
                block_id=block_id,
                taxonomy_node_id=(
                    taxonomy_node_id
                ),
                node_key=node_key,
                raw_text=(
                    custom_description
                ),
                branch=branch,
                split_separator=(
                    split_separator
                ),
                text_prefix=(
                    text_prefix
                ),
                text_suffix=(
                    text_suffix
                ),
            )

            #
            # This is the ONLY text append branch
            # gated by EngPart.
            #
            if eng_part:
                emit(
                    kind=(
                        "append_custom_description_en"
                    ),
                    block_id=(
                        block_id
                    ),
                    taxonomy_node_id=(
                        taxonomy_node_id
                    ),
                    node_key=node_key,
                    raw_text=(
                        custom_description
                    ),
                    branch=branch,
                    translation_intent=(
                        "legacy_translate_ve_daychuyen"
                    ),
                    split_separator=(
                        split_separator
                    ),
                    text_prefix=(
                        text_prefix
                    ),
                    text_suffix=(
                        text_suffix
                    ),
                )

        #
        # Scope note
        #
        # VBA:
        # TAB + s_Note + CRLF
        # TAB +
        # Translate_VE_Daychuyen(
        #   Translate_VE_Daychuyen(s_Note)
        # ) + CRLF
        #
        # IMPORTANT:
        # this is NOT gated by EngPart.
        #
        note = str(
            block.get("note")
            or ""
        ).strip()

        if note:
            emit(
                kind=(
                    "append_scope_note_vi"
                ),
                block_id=block_id,
                raw_text=note,
                branch=(
                    "scope_note_nonblank"
                ),
                text_prefix="\t",
                text_suffix="\r\n",
            )

            emit(
                kind=(
                    "append_scope_note_en"
                ),
                block_id=block_id,
                raw_text=note,
                branch=(
                    "scope_note_nonblank"
                ),
                translation_intent=(
                    "legacy_translate_ve_daychuyen_double_pass"
                ),
                text_prefix="\t",
                text_suffix="\r\n",
            )

    return (
        CertificateDetailSemanticProjection(
            family_code=(
                family_code
            ),
            source_variant=(
                CERTIFICATE_DETAIL_SOURCE_VARIANT
            ),
            destination_bookmark=(
                CERTIFICATE_DETAIL_DESTINATION_BOOKMARK
            ),
            gxp_type=gxp_type,
            eng_part=eng_part,
            operations=tuple(
                operations
            ),
        )
    )