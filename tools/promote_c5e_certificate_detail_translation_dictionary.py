from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


OUTPUT_SCHEMA = "c5e-certificate-detail-translation-dictionary/v1"

DICTIONARY_CAPTURE_STATUS = "TRANSLATION_DICTIONARIES_CAPTURED"
CHARACTER_CAPTURE_STATUS = "CHARACTER_MAPPING_CAPTURED"

EXPECTED_DICTIONARIES = {
    "TV_Words": (426, 1),
    "TA_Words": (426, 1),
    "TV_Words2": (36, 1),
    "TA_Words2": (36, 1),
    "TA_Words2_Loc": (36, 2),
    "TV_Words4": (108, 1),
    "TA_Words4": (108, 1),
    "TV_Words6": (60, 1),
    "TA_Words6": (60, 1),
}

EXPECTED_ACCHS_REFERS_TO_SHA256 = (
    "e2c11944987d991cff291d40429b6d1fbe733ab847487ec9b42e650f013d3422"
)
EXPECTED_RGCHS_REFERS_TO_SHA256 = (
    "e69c5ba617a3b7a6f0453baac433507231ed16a860768823e9ba59d3d92359da"
)
EXPECTED_ACCHS_VALUE_SHA256 = (
    "896a98e92e66ce6d5123f617b2f2fdb66dac55a499b4c046b24d3f96c86ae798"
)
EXPECTED_RGCHS_VALUE_SHA256 = (
    "836682c783b32586ba75cc9052cf2ca04af246c70922c380f7639fa454c1d392"
)


class PromotionError(RuntimeError):
    pass


def _object(
    value: Any,
    *,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PromotionError(f"{label} must be an object.")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PromotionError(f"Input not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PromotionError(f"Invalid JSON: {path}: {exc}") from exc

    return _object(value, label=str(path))


def _validate_dictionary_capture(
    capture: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    if capture.get("status") != DICTIONARY_CAPTURE_STATUS:
        raise PromotionError(
            "Translation dictionary capture is not verified."
        )

    summary = _object(
        capture.get("summary"),
        label="dictionary_capture.summary",
    )

    if summary.get("blockers") != 0:
        raise PromotionError(
            "Translation dictionary capture contains blockers."
        )

    dictionaries = _object(
        capture.get("dictionaries"),
        label="dictionary_capture.dictionaries",
    )

    if set(dictionaries) != set(EXPECTED_DICTIONARIES):
        raise PromotionError(
            "Translation dictionary names do not match contract."
        )

    source_workbook: str | None = None
    source_sha256: str | None = None

    promoted: dict[str, Any] = {}

    for name, (expected_rows, expected_columns) in (
        EXPECTED_DICTIONARIES.items()
    ):
        record = _object(
            dictionaries[name],
            label=name,
        )

        source = _object(
            record.get("source"),
            label=f"{name}.source",
        )

        workbook = source.get("workbook")
        workbook_sha256 = source.get("workbook_sha256")

        if not isinstance(workbook, str) or not workbook:
            raise PromotionError(
                f"{name} has invalid source workbook."
            )

        if (
            not isinstance(workbook_sha256, str)
            or len(workbook_sha256) != 64
        ):
            raise PromotionError(
                f"{name} has invalid source workbook SHA256."
            )

        if source_workbook is None:
            source_workbook = workbook
            source_sha256 = workbook_sha256
        elif (
            workbook != source_workbook
            or workbook_sha256 != source_sha256
        ):
            raise PromotionError(
                "Translation dictionaries do not share one "
                "authoritative workbook."
            )

        shape = _object(
            record.get("shape"),
            label=f"{name}.shape",
        )

        if shape.get("rows") != expected_rows:
            raise PromotionError(
                f"{name} row count mismatch."
            )

        if shape.get("columns") != expected_columns:
            raise PromotionError(
                f"{name} column count mismatch."
            )

        values = record.get("values")

        if not isinstance(values, list):
            raise PromotionError(
                f"{name}.values must be an array."
            )

        if len(values) != expected_rows:
            raise PromotionError(
                f"{name}.values row count mismatch."
            )

        copied_values: list[list[Any]] = []

        for index, row in enumerate(values, start=1):
            if not isinstance(row, list):
                raise PromotionError(
                    f"{name} row {index} is not an array."
                )

            if len(row) != expected_columns:
                raise PromotionError(
                    f"{name} row {index} column count mismatch."
                )

            # Preserve blanks/duplicates/value order exactly.
            copied_values.append(list(row))

        promoted[name] = {
            "shape": {
                "rows": expected_rows,
                "columns": expected_columns,
            },
            "values_sha256": record.get("values_sha256"),
            "values": copied_values,
        }

    assert source_workbook is not None
    assert source_sha256 is not None

    return source_workbook, source_sha256, promoted


def _validate_character_capture(
    capture: dict[str, Any],
) -> tuple[str, str, str, str]:
    if capture.get("status") != CHARACTER_CAPTURE_STATUS:
        raise PromotionError(
            "Character mapping capture is not verified."
        )

    summary = _object(
        capture.get("summary"),
        label="character_capture.summary",
    )

    if summary.get("blockers") != 0:
        raise PromotionError(
            "Character mapping capture contains blockers."
        )

    source = _object(
        capture.get("source"),
        label="character_capture.source",
    )

    workbook = source.get("workbook")
    workbook_sha256 = source.get("workbook_sha256")

    if not isinstance(workbook, str) or not workbook:
        raise PromotionError(
            "Character capture has invalid source workbook."
        )

    if (
        not isinstance(workbook_sha256, str)
        or len(workbook_sha256) != 64
    ):
        raise PromotionError(
            "Character capture has invalid workbook SHA256."
        )

    mappings = _object(
        capture.get("mappings"),
        label="character_capture.mappings",
    )

    if set(mappings) != {"AcChS", "RgChS"}:
        raise PromotionError(
            "Character mapping names do not match contract."
        )

    ac = _object(mappings["AcChS"], label="AcChS")
    rg = _object(mappings["RgChS"], label="RgChS")

    expected_hashes = (
        (
            ac,
            EXPECTED_ACCHS_REFERS_TO_SHA256,
            EXPECTED_ACCHS_VALUE_SHA256,
            "AcChS",
        ),
        (
            rg,
            EXPECTED_RGCHS_REFERS_TO_SHA256,
            EXPECTED_RGCHS_VALUE_SHA256,
            "RgChS",
        ),
    )

    for record, refers_hash, value_hash, label in expected_hashes:
        if record.get("refers_to_sha256") != refers_hash:
            raise PromotionError(
                f"{label} RefersTo checksum mismatch."
            )

        if record.get("value_sha256") != value_hash:
            raise PromotionError(
                f"{label} value checksum mismatch."
            )

    ac_value = ac.get("value")
    rg_value = rg.get("value")

    if not isinstance(ac_value, str):
        raise PromotionError("AcChS value must be a string.")

    if not isinstance(rg_value, str):
        raise PromotionError("RgChS value must be a string.")

    if len(ac_value) != 134 or len(rg_value) != 134:
        raise PromotionError(
            "Character mapping length must be exactly 134."
        )

    if len(ac_value) != len(rg_value):
        raise PromotionError(
            "Character mapping cardinality mismatch."
        )

    return workbook, workbook_sha256, ac_value, rg_value


def promote(
    dictionary_capture_path: Path,
    character_capture_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    dictionary_capture = _read_json(
        dictionary_capture_path
    )

    character_capture = _read_json(
        character_capture_path
    )

    (
        dictionary_workbook,
        dictionary_workbook_sha256,
        dictionaries,
    ) = _validate_dictionary_capture(
        dictionary_capture
    )

    (
        character_workbook,
        character_workbook_sha256,
        acchs,
        rgchs,
    ) = _validate_character_capture(
        character_capture
    )

    if dictionary_workbook != character_workbook:
        raise PromotionError(
            "Dictionary and character captures come from "
            "different workbook filenames."
        )

    if (
        dictionary_workbook_sha256
        != character_workbook_sha256
    ):
        raise PromotionError(
            "Dictionary and character captures come from "
            "different workbook versions."
        )

    result = {
        "schema_version": OUTPUT_SCHEMA,
        "source": {
            "workbook": dictionary_workbook,
            "workbook_sha256": dictionary_workbook_sha256,
            "dictionary_capture_schema": (
                dictionary_capture.get("schema_version")
            ),
            "character_capture_schema": (
                character_capture.get("schema_version")
            ),
        },
        "character_mapping": {
            "AcChS": acchs,
            "RgChS": rgchs,
            "length": 134,
            "AcChS_refers_to_sha256": (
                EXPECTED_ACCHS_REFERS_TO_SHA256
            ),
            "RgChS_refers_to_sha256": (
                EXPECTED_RGCHS_REFERS_TO_SHA256
            ),
            "AcChS_value_sha256": (
                EXPECTED_ACCHS_VALUE_SHA256
            ),
            "RgChS_value_sha256": (
                EXPECTED_RGCHS_VALUE_SHA256
            ),
        },
        "dictionaries": dictionaries,
        "runtime_scope": {
            "supported_gxp_types": [
                "GMP",
                "GLP",
                "GSP",
            ],
            "gdp_supported": False,
            "source_variant": "certificate_9",
            "family_code": "CERTIFICATE_ISSUANCE_WORD",
        },
        "invariants": {
            "blank_values_preserved": True,
            "duplicate_values_preserved": True,
            "row_order_preserved": True,
            "runtime_excel_dependency": False,
            "runtime_legacy_workbook_dependency": False,
            "unicode_mapping_reconstructed_manually": False,
            "gdp_in_scope": False,
            "unkeyed_entries_used": False,
        },
    }

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return result


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--dictionary-capture",
        default=(
            "artifacts/legacy_audit/"
            "c5e_certificate_detail_translation_dictionary_capture.json"
        ),
    )

    parser.add_argument(
        "--character-capture",
        default=(
            "artifacts/legacy_audit/"
            "c5e_certificate_detail_character_mapping_capture.json"
        ),
    )

    parser.add_argument(
        "--output",
        default=(
            "backend/app/document/"
            "c5e_certificate_detail_translation_dictionary.json"
        ),
    )

    args = parser.parse_args()

    try:
        result = promote(
            Path(args.dictionary_capture),
            Path(args.character_capture),
            Path(args.output),
        )
    except PromotionError as exc:
        print(
            "STATUS=TRANSLATION_DICTIONARY_PROMOTION_BLOCKED"
        )
        print(f"ERROR={exc}")
        return 1

    print(
        "STATUS=TRANSLATION_DICTIONARY_PROMOTED"
    )
    print(
        f"DICTIONARIES={len(result['dictionaries'])}"
    )
    print(
        "CHARACTER_MAPPING_LENGTH="
        f"{result['character_mapping']['length']}"
    )
    print(
        "SOURCE_WORKBOOK="
        f"{result['source']['workbook']}"
    )
    print(
        "SOURCE_WORKBOOK_SHA256="
        f"{result['source']['workbook_sha256']}"
    )
    print(
        "GXP_SCOPE=GMP,GLP,GSP"
    )
    print(
        f"OUTPUT={Path(args.output).resolve()}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())