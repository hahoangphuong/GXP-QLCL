from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping


CRLF = "\r\n"
CR = "\r"
LF = "\n"
TAB = "\t"

RUNTIME_DICTIONARY_SCHEMA = (
    "c5e-certificate-detail-translation-dictionary/v1"
)

SUPPORTED_GXP_TYPES = frozenset(
    {
        "GMP",
        "GLP",
        "GSP",
    }
)

REQUIRED_DICTIONARIES = frozenset(
    {
        "TV_Words",
        "TA_Words",
        "TV_Words2",
        "TA_Words2",
        "TA_Words2_Loc",
        "TV_Words4",
        "TA_Words4",
        "TV_Words6",
        "TA_Words6",
    }
)


class CertificateDetailTypeTextError(RuntimeError):
    pass


@dataclass(frozen=True)
class CertificateDetailTranslationDictionary:
    acchs: str
    rgchs: str
    matrices: Mapping[
        str,
        tuple[tuple[str, ...], ...],
    ]


def _cell_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    return str(value)


def load_certificate_detail_translation_dictionary(
    path: Path | None = None,
) -> CertificateDetailTranslationDictionary:
    if path is None:
        path = Path(__file__).with_name(
            "c5e_certificate_detail_translation_dictionary.json"
        )

    try:
        raw = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except FileNotFoundError as exc:
        raise CertificateDetailTypeTextError(
            f"Translation dictionary not found: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise CertificateDetailTypeTextError(
            f"Invalid translation dictionary JSON: {path}"
        ) from exc

    if not isinstance(raw, dict):
        raise CertificateDetailTypeTextError(
            "Translation dictionary root must be an object."
        )

    if raw.get("schema_version") != RUNTIME_DICTIONARY_SCHEMA:
        raise CertificateDetailTypeTextError(
            "Unsupported translation dictionary schema."
        )

    runtime_scope = raw.get("runtime_scope")

    if not isinstance(runtime_scope, dict):
        raise CertificateDetailTypeTextError(
            "Missing runtime_scope contract."
        )

    if runtime_scope.get("gdp_supported") is not False:
        raise CertificateDetailTypeTextError(
            "GDP must remain disabled for C.5e."
        )

    if runtime_scope.get("source_variant") != "certificate_9":
        raise CertificateDetailTypeTextError(
            "Unexpected certificate-detail source variant."
        )

    char_map = raw.get("character_mapping")

    if not isinstance(char_map, dict):
        raise CertificateDetailTypeTextError(
            "Missing character_mapping."
        )

    acchs = char_map.get("AcChS")
    rgchs = char_map.get("RgChS")

    if not isinstance(acchs, str) or not isinstance(rgchs, str):
        raise CertificateDetailTypeTextError(
            "AcChS/RgChS must be strings."
        )

    if len(acchs) != 134 or len(rgchs) != 134:
        raise CertificateDetailTypeTextError(
            "AcChS/RgChS length mismatch."
        )

    dictionaries = raw.get("dictionaries")

    if not isinstance(dictionaries, dict):
        raise CertificateDetailTypeTextError(
            "Missing dictionaries."
        )

    if set(dictionaries) != set(REQUIRED_DICTIONARIES):
        raise CertificateDetailTypeTextError(
            "Dictionary set does not match contract."
        )

    matrices: dict[
        str,
        tuple[tuple[str, ...], ...],
    ] = {}

    for name in REQUIRED_DICTIONARIES:
        record = dictionaries[name]

        if not isinstance(record, dict):
            raise CertificateDetailTypeTextError(
                f"{name} record must be an object."
            )

        shape = record.get("shape")
        values = record.get("values")

        if not isinstance(shape, dict):
            raise CertificateDetailTypeTextError(
                f"{name}.shape missing."
            )

        if not isinstance(values, list):
            raise CertificateDetailTypeTextError(
                f"{name}.values missing."
            )

        expected_rows = shape.get("rows")
        expected_columns = shape.get("columns")

        if len(values) != expected_rows:
            raise CertificateDetailTypeTextError(
                f"{name} row count mismatch."
            )

        rows: list[tuple[str, ...]] = []

        for row in values:
            if not isinstance(row, list):
                raise CertificateDetailTypeTextError(
                    f"{name} row must be an array."
                )

            if len(row) != expected_columns:
                raise CertificateDetailTypeTextError(
                    f"{name} column count mismatch."
                )

            rows.append(
                tuple(
                    _cell_text(cell)
                    for cell in row
                )
            )

        matrices[name] = tuple(rows)

    pair_names = (
        ("TV_Words", "TA_Words"),
        ("TV_Words2", "TA_Words2"),
        ("TV_Words4", "TA_Words4"),
        ("TV_Words6", "TA_Words6"),
    )

    for left, right in pair_names:
        if len(matrices[left]) != len(matrices[right]):
            raise CertificateDetailTypeTextError(
                f"{left}/{right} cardinality mismatch."
            )

    if len(matrices["TV_Words2"]) != len(
        matrices["TA_Words2_Loc"]
    ):
        raise CertificateDetailTypeTextError(
            "Address dictionary cardinality mismatch."
        )

    return CertificateDetailTranslationDictionary(
        acchs=acchs,
        rgchs=rgchs,
        matrices=matrices,
    )


def _trim(value: str) -> str:
    # VBA Trim$/Trim removes leading/trailing spaces.
    return value.strip(" ")


def del_last_if(
    value: str,
    suffix: str,
) -> str:
    if suffix and value.endswith(suffix):
        return value[: -len(suffix)]

    return value


def del_last_if_ins(
    value: str,
    chars: str,
) -> str:
    result = value

    while result:
        last = result[-1]

        if last.casefold() not in chars.casefold():
            break

        result = result[:-1]

    return result


def merge_text(
    s1: str,
    s2: str,
    s3: str = "",
    s4: str = "",
) -> str:
    if s1.endswith(" ") or s2.startswith(" "):
        result = s1 + s2
    else:
        result = s1 + " " + s2

    if s3 != "":
        if result.endswith(" ") or s3.startswith(" "):
            result += s3
        else:
            result += " " + s3

    if s4 != "":
        if result.endswith(" ") or s4.startswith(" "):
            result += s4
        else:
            result += " " + s4

    return result


def khong_dau(
    value: str,
    dictionary: CertificateDetailTranslationDictionary,
) -> str:
    result = value

    for source, target in zip(
        dictionary.acchs,
        dictionary.rgchs,
        strict=True,
    ):
        # VBA uses vbBinaryCompare here.
        result = result.replace(
            source,
            target,
        )

    return result


def _collapse_legacy_spaces(
    value: str,
) -> str:
    # Exact legacy sequence:
    # Replace("   ", " "), then Replace("  ", " ").
    value = value.replace(
        "   ",
        " ",
    )

    value = value.replace(
        "  ",
        " ",
    )

    return value


def split_lines(
    value: str,
    separator: str = ";" + CRLF + TAB,
) -> str:
    result = del_last_if(
        del_last_if(
            del_last_if(
                del_last_if(
                    value,
                    CRLF,
                ),
                CR,
            ),
            LF,
        ),
        ";",
    )

    result = result.replace(
        "  ",
        " ",
    )
    result = result.replace(
        "  ",
        " ",
    )
    result = result.replace(
        "; ",
        ";",
    )

    result = del_last_if(
        del_last_if(
            del_last_if(
                del_last_if(
                    result,
                    CRLF,
                ),
                CR,
            ),
            LF,
        ),
        ";",
    )

    result = del_last_if(
        result,
        ";",
    )

    result = result.replace(
        ";",
        separator,
    )

    return (
        del_last_if(
            result,
            ".",
        )
        + "."
    )


def _replace_text_compare(
    value: str,
    find: str,
    replacement: str,
) -> str:
    if find == "":
        # VBA Replace with zero-length find leaves the
        # expression unchanged.
        return value

    pattern = re.compile(
        re.escape(find),
        flags=re.IGNORECASE,
    )

    return pattern.sub(
        lambda _match: replacement,
        value,
    )


def _starts_with_text_compare(
    value: str,
    prefix: str,
) -> bool:
    if len(value) < len(prefix):
        return False

    return (
        value[: len(prefix)].casefold()
        == prefix.casefold()
    )


def _daychuyen_pair_for_gxp(
    gxp_type: str,
) -> tuple[str, str]:
    if gxp_type in {"GMP", "GLP"}:
        return (
            "TV_Words",
            "TA_Words",
        )

    if gxp_type == "GSP":
        return (
            "TV_Words4",
            "TA_Words4",
        )

    raise CertificateDetailTypeTextError(
        f"Unsupported C.5e GxP type: {gxp_type!r}."
    )


def translate_ve_daychuyen(
    value: str,
    *,
    gxp_type: str,
    dictionary: CertificateDetailTranslationDictionary,
) -> str:
    if gxp_type not in SUPPORTED_GXP_TYPES:
        raise CertificateDetailTypeTextError(
            f"Unsupported C.5e GxP type: {gxp_type!r}."
        )

    result = _trim(value)

    if result == "":
        return ""

    result = _collapse_legacy_spaces(
        result
    )

    viet_name, anh_name = (
        _daychuyen_pair_for_gxp(
            gxp_type
        )
    )

    viet = dictionary.matrices[
        viet_name
    ]
    anh = dictionary.matrices[
        anh_name
    ]

    for index, row in enumerate(viet):
        source_value = row[0]

        if source_value == "":
            continue

        replacement = anh[index][0]

        for variant in source_value.split("|"):
            result = _replace_text_compare(
                result,
                variant,
                replacement,
            )

    result = _collapse_legacy_spaces(
        result
    )

    return _trim(result)


def _first_char(
    value: str,
) -> str:
    return value[:1]


def _starts_digit(
    value: str,
) -> bool:
    first = _first_char(value)
    return "0" <= first <= "9"


def translate_ve_diachi(
    value: str,
    *,
    dictionary: CertificateDetailTranslationDictionary,
) -> str:
    source = _trim(value)

    if source == "":
        return ""

    source = del_last_if_ins(
        source,
        ".,;)" + CRLF,
    )

    result = _trim(source)

    if result == "":
        return ""

    result = _collapse_legacy_spaces(
        result
    )

    viet = dictionary.matrices[
        "TV_Words2"
    ]
    anh = dictionary.matrices[
        "TA_Words2"
    ]
    locations = dictionary.matrices[
        "TA_Words2_Loc"
    ]

    block_lines = result.split(
        CRLF
    )

    multiple_lines = (
        len(block_lines) > 1
    )

    translated_lines: list[str] = []

    for block_line in block_lines:
        line = _trim(block_line)

        if line.startswith("*"):
            line = _trim(
                line[1:]
            )

        segments = line.split(
            ","
        )

        output_segments: list[str] = []

        for segment in segments:
            slk = _trim(segment)
            fspe = ""

            #
            # Exact VBA numeric-prefix extraction.
            #
            if _starts_digit(slk):
                j = 1
                length = len(slk)

                while (
                    j < length
                    and slk[j - 1 : j] != " "
                ):
                    j += 1

                if j < length:
                    fspe = _trim(
                        slk[: j - 1]
                    )

                    slk = _trim(
                        slk[
                            length
                            - (length - j) :
                        ]
                    )

            found = False
            translated_segment = ""

            for index, row in enumerate(viet):
                source_terms = row[0]

                if source_terms == "":
                    continue

                for variant in source_terms.split("|"):
                    if not _starts_with_text_compare(
                        slk,
                        variant,
                    ):
                        continue

                    remainder = slk[
                        len(variant) :
                    ]

                    spe = khong_dau(
                        _trim(remainder),
                        dictionary,
                    )

                    first = _first_char(
                        spe
                    )

                    if (
                        ("0" <= first <= "9")
                        or first == "I"
                    ):
                        location_code = (
                            locations[index][1].upper()
                        )
                    else:
                        location_code = (
                            locations[index][0].upper()
                        )

                    english = anh[index][0]

                    if location_code == "T":
                        translated_segment = (
                            merge_text(
                                english,
                                spe,
                            )
                        )
                    else:
                        translated_segment = (
                            merge_text(
                                spe,
                                english,
                            )
                        )

                    if fspe != "":
                        translated_segment = (
                            merge_text(
                                fspe,
                                translated_segment,
                            )
                        )

                    found = True
                    break

                if found:
                    break

            if not found:
                translated_segment = (
                    khong_dau(
                        _trim(slk),
                        dictionary,
                    )
                )

                if fspe != "":
                    translated_segment = (
                        merge_text(
                            fspe,
                            translated_segment,
                        )
                    )

            output_segments.append(
                translated_segment
            )

        joined = ", ".join(
            output_segments
        )

        if multiple_lines:
            joined = merge_text(
                "*",
                joined,
            )

        translated_lines.append(
            joined
        )

    result = CRLF.join(
        translated_lines
    )

    result = _collapse_legacy_spaces(
        result
    )

    return _trim(result)


def _operation_raw_text(
    operation: Any,
) -> str:
    value = getattr(
        operation,
        "raw_text",
        "",
    )

    if value is None:
        return ""

    if not isinstance(value, str):
        raise CertificateDetailTypeTextError(
            "Semantic operation raw_text must be a string."
        )

    return value


def _resolve_custom_description(
    value: str,
    *,
    branch: str,
) -> str:
    if branch == "main_topic":
        return (
            " ("
            + del_last_if(
                value,
                ";",
            )
            + ")"
        )

    if branch == "packaging_special":
        return (
            ":"
            + CRLF
            + TAB
            + split_lines(
                value,
                "; ",
            )
        )

    if branch == "normal":
        return (
            ":"
            + CRLF
            + TAB
            + split_lines(
                value
            )
        )

    raise CertificateDetailTypeTextError(
        f"Unsupported custom-description branch: {branch!r}."
    )


def resolve_certificate_detail_typetext(
    projection: Any,
    *,
    dictionary: CertificateDetailTranslationDictionary | None = None,
) -> dict[int, str]:
    gxp_type = getattr(
        projection,
        "gxp_type",
        None,
    )

    if gxp_type not in SUPPORTED_GXP_TYPES:
        raise CertificateDetailTypeTextError(
            f"Unsupported C.5e GxP type: {gxp_type!r}."
        )

    source_variant = getattr(
        projection,
        "source_variant",
        None,
    )

    if source_variant != "certificate_9":
        raise CertificateDetailTypeTextError(
            "TypeText resolver only supports certificate_9."
        )

    if dictionary is None:
        dictionary = (
            load_certificate_detail_translation_dictionary()
        )

    operations = getattr(
        projection,
        "operations",
        None,
    )

    if operations is None:
        raise CertificateDetailTypeTextError(
            "Projection has no operations."
        )

    resolved: dict[int, str] = {}

    for operation in operations:
        kind = getattr(
            operation,
            "kind",
            None,
        )

        sequence = getattr(
            operation,
            "sequence",
            None,
        )

        if not isinstance(sequence, int):
            raise CertificateDetailTypeTextError(
                "Semantic operation has invalid sequence."
            )

        if kind == "formatted_fragment_copy":
            continue

        raw_text = _operation_raw_text(
            operation
        )

        if kind == "scope_heading_vi":
            text = (
                "* "
                + del_last_if(
                    raw_text,
                    "¶",
                )
                + " - "
            )

        elif kind == "scope_heading_en":
            text = (
                translate_ve_diachi(
                    del_last_if(
                        raw_text,
                        "¶",
                    ),
                    dictionary=dictionary,
                )
                + CRLF
            )

        elif kind == "append_custom_description_vi":
            branch = getattr(
                operation,
                "branch",
                None,
            )

            text = _resolve_custom_description(
                raw_text,
                branch=branch,
            )

        elif kind == "append_custom_description_en":
            branch = getattr(
                operation,
                "branch",
                None,
            )

            translated = translate_ve_daychuyen(
                raw_text,
                gxp_type=gxp_type,
                dictionary=dictionary,
            )

            if branch == "main_topic":
                translated = translate_ve_daychuyen(
                    del_last_if(
                        raw_text,
                        ";",
                    ),
                    gxp_type=gxp_type,
                    dictionary=dictionary,
                )

            text = _resolve_custom_description(
                translated,
                branch=branch,
            )

        elif kind == "append_scope_note_vi":
            text = (
                TAB
                + raw_text
                + CRLF
            )

        elif kind == "append_scope_note_en":
            once = translate_ve_daychuyen(
                raw_text,
                gxp_type=gxp_type,
                dictionary=dictionary,
            )

            twice = translate_ve_daychuyen(
                once,
                gxp_type=gxp_type,
                dictionary=dictionary,
            )

            text = (
                TAB
                + twice
                + CRLF
            )

        else:
            raise CertificateDetailTypeTextError(
                "Unsupported certificate-detail semantic "
                f"operation kind: {kind!r}."
            )

        if sequence in resolved:
            raise CertificateDetailTypeTextError(
                f"Duplicate semantic operation sequence: {sequence}."
            )

        resolved[sequence] = text

    return resolved