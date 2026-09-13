from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_INPUT = (
    ROOT
    / "tests"
    / "fixtures"
    / "c5e_certificate_detail"
    / "Input_DC_to_CC.active.bas"
)

DEFAULT_OUTPUT = (
    ROOT
    / "artifacts"
    / "legacy_audit"
    / "c5e_certificate_detail_selection_geometry.json"
)


CONTEXTUAL_MEMBERS = frozenset(
    {
        "FormattedText",
        "Text",
    }
)

#
# These can move/replace the active Word Selection and are
# relevant to composition geometry.
#
CURSOR_MUTATING_MEMBERS = frozenset(
    {
        "TypeText",
        "EndKey",
        "MoveRight",
        "MoveLeft",
        "MoveUp",
        "MoveDown",
        "Collapse",
        "HomeKey",
        "InsertAfter",
        "InsertBefore",
        "Delete",
        "InsertParagraphAfter",
        "InsertParagraphBefore",
    }
)

#
# Property containers used only to reach formatting state.
#
FORMATTING_CONTAINER_MEMBERS = frozenset(
    {
        "Font",
        "ParagraphFormat",
    }
)

#
# Known active formatting properties observed in
# Input_DC_to_CC.
#
FORMATTING_LEAF_MEMBERS = frozenset(
    {
        "Bold",
        "Italic",
        "Color",
        "SpaceAfter",
        "SpaceBefore",
    }
)

QUERY_MEMBERS = frozenset(
    {
        "Bookmarks",
        "Range",
        "Start",
        "End",
        "Information",
        "Tables",
        "Paragraphs",
        "Cells",
        "Rows",
        "Columns",
    }
)

KNOWN_MEMBERS = (
    CURSOR_MUTATING_MEMBERS
    | FORMATTING_CONTAINER_MEMBERS
    | FORMATTING_LEAF_MEMBERS
    | QUERY_MEMBERS
    | CONTEXTUAL_MEMBERS
)

IDENTIFIER_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*"
)


def _strip_vba_comment(
    line: str,
) -> str:
    output: list[str] = []

    in_string = False
    index = 0

    while index < len(line):
        char = line[index]

        if char == '"':
            output.append(char)

            if (
                in_string
                and index + 1 < len(line)
                and line[index + 1] == '"'
            ):
                output.append('"')
                index += 2
                continue

            in_string = not in_string
            index += 1
            continue

        if (
            char == "'"
            and not in_string
        ):
            break

        output.append(char)
        index += 1

    return "".join(output)


def _mask_vba_strings(
    line: str,
) -> str:
    chars = list(line)

    in_string = False
    index = 0

    while index < len(chars):
        char = chars[index]

        if char != '"':
            if in_string:
                chars[index] = " "

            index += 1
            continue

        if (
            in_string
            and index + 1 < len(chars)
            and chars[index + 1] == '"'
        ):
            chars[index] = " "
            chars[index + 1] = " "
            index += 2
            continue

        in_string = not in_string
        index += 1

    return "".join(chars)


def _logical_lines(
    text: str,
) -> list[dict]:
    physical = text.splitlines()

    result: list[dict] = []

    buffer: list[str] = []
    start_line: int | None = None

    for line_number, raw in enumerate(
        physical,
        1,
    ):
        code = _strip_vba_comment(
            raw
        ).rstrip()

        if start_line is None:
            start_line = line_number

        continuation = (
            code.endswith(" _")
            or code == "_"
        )

        if continuation:
            if code.endswith(" _"):
                code = code[:-2]
            else:
                code = ""

            buffer.append(code)
            continue

        buffer.append(code)

        logical = " ".join(
            part.strip()
            for part in buffer
            if part.strip()
        )

        if logical:
            result.append(
                {
                    "start_line": start_line,
                    "end_line": line_number,
                    "code": logical,
                }
            )

        buffer = []
        start_line = None

    if buffer:
        logical = " ".join(
            part.strip()
            for part in buffer
            if part.strip()
        )

        if logical:
            result.append(
                {
                    "start_line": start_line,
                    "end_line": len(physical),
                    "code": logical,
                }
            )

    return result


def _canonical_member(
    member: str,
) -> str:
    for known in KNOWN_MEMBERS:
        if (
            known.lower()
            == member.lower()
        ):
            return known

    return member


def _skip_spaces(
    text: str,
    index: int,
) -> int:
    while (
        index < len(text)
        and text[index].isspace()
    ):
        index += 1

    return index


def _skip_parenthesized_expression(
    text: str,
    index: int,
) -> int:
    if (
        index >= len(text)
        or text[index] != "("
    ):
        return index

    depth = 0

    while index < len(text):
        char = text[index]

        if char == "(":
            depth += 1

        elif char == ")":
            depth -= 1

            if depth == 0:
                return index + 1

        index += 1

    return len(text)


def _find_selection_roots(
    masked: str,
) -> list[int]:
    pattern = re.compile(
        r"\bSelection\b",
        re.IGNORECASE,
    )

    return [
        match.start()
        for match in pattern.finditer(
            masked
        )
    ]


def _parse_selection_chain(
    masked: str,
    start: int,
) -> tuple[list[dict], int]:
    index = (
        start
        + len("Selection")
    )

    members: list[dict] = []

    while True:
        index = _skip_spaces(
            masked,
            index,
        )

        if (
            index >= len(masked)
            or masked[index] != "."
        ):
            break

        index += 1

        index = _skip_spaces(
            masked,
            index,
        )

        match = IDENTIFIER_RE.match(
            masked,
            index,
        )

        if match is None:
            break

        member = _canonical_member(
            match.group(0)
        )

        members.append(
            {
                "member": member,
                "member_start": (
                    match.start()
                ),
                "member_end": (
                    match.end()
                ),
            }
        )

        index = match.end()

        index = _skip_spaces(
            masked,
            index,
        )

        if (
            index < len(masked)
            and masked[index] == "("
        ):
            index = (
                _skip_parenthesized_expression(
                    masked,
                    index,
                )
            )

    return members, index


def _chain_is_assignment_target(
    masked: str,
    chain_end: int,
) -> bool:
    index = _skip_spaces(
        masked,
        chain_end,
    )

    return (
        index < len(masked)
        and masked[index] == "="
    )


def _classify_member(
    *,
    member: str,
    member_position: int,
    chain_length: int,
    assignment_target: bool,
) -> str:
    if (
        member
        in CURSOR_MUTATING_MEMBERS
    ):
        return "mutating"

    if (
        member
        in FORMATTING_CONTAINER_MEMBERS
    ):
        return "formatting"

    if (
        member
        in FORMATTING_LEAF_MEMBERS
    ):
        return "formatting"

    if member in QUERY_MEMBERS:
        return "query"

    if member in CONTEXTUAL_MEMBERS:
        if (
            assignment_target
            and member_position
            == chain_length - 1
        ):
            return "mutating"

        return "query"

    return "unknown"


def audit_selection_geometry(
    text: str,
    *,
    require_core_members: bool = False,
) -> dict:
    operations: list[dict] = []
    unknown: list[dict] = []

    member_counts: Counter[str] = (
        Counter()
    )

    classification_counts: Counter[
        str
    ] = Counter()

    sequence = 0

    for logical in _logical_lines(
        text
    ):
        code = logical["code"]

        masked = _mask_vba_strings(
            code
        )

        consumed_until = -1

        for root_start in (
            _find_selection_roots(
                masked
            )
        ):
            if (
                root_start
                < consumed_until
            ):
                continue

            members, chain_end = (
                _parse_selection_chain(
                    masked,
                    root_start,
                )
            )

            if not members:
                continue

            consumed_until = max(
                consumed_until,
                chain_end,
            )

            assignment_target = (
                _chain_is_assignment_target(
                    masked,
                    chain_end,
                )
            )

            chain_length = len(
                members
            )

            for (
                member_position,
                parsed,
            ) in enumerate(
                members
            ):
                member = parsed[
                    "member"
                ]

                classification = (
                    _classify_member(
                        member=member,
                        member_position=(
                            member_position
                        ),
                        chain_length=(
                            chain_length
                        ),
                        assignment_target=(
                            assignment_target
                        ),
                    )
                )

                sequence += 1

                member_counts[
                    member
                ] += 1

                classification_counts[
                    classification
                ] += 1

                item = {
                    "sequence": (
                        sequence
                    ),
                    "start_line": (
                        logical[
                            "start_line"
                        ]
                    ),
                    "end_line": (
                        logical[
                            "end_line"
                        ]
                    ),
                    "member": member,
                    "member_position": (
                        member_position
                    ),
                    "chain_length": (
                        chain_length
                    ),
                    "assignment_target": (
                        assignment_target
                    ),
                    "classification": (
                        classification
                    ),
                    "code": code,
                }

                operations.append(
                    item
                )

                if (
                    classification
                    == "unknown"
                ):
                    unknown.append(
                        item
                    )

    blockers = [
        {
            "code": (
                "UNKNOWN_SELECTION_MEMBER"
            ),
            "sequence": (
                item["sequence"]
            ),
            "line": (
                item["start_line"]
            ),
            "member": (
                item["member"]
            ),
            "statement": (
                item["code"]
            ),
        }
        for item in unknown
    ]

    if require_core_members:
        for required in (
            "TypeText",
            "FormattedText",
        ):
            if (
                member_counts[
                    required
                ]
                == 0
            ):
                blockers.append(
                    {
                        "code": (
                            "REQUIRED_SELECTION_MEMBER_MISSING"
                        ),
                        "member": required,
                    }
                )

    return {
        "schema_version": (
            "c5e-certificate-detail-"
            "selection-geometry/v4"
        ),
        "status": (
            "SELECTION_GEOMETRY_PROFILED"
            if not blockers
            else "SELECTION_GEOMETRY_BLOCKED"
        ),
        "summary": {
            "operation_count": (
                len(operations)
            ),
            "mutating_operation_count": (
                classification_counts[
                    "mutating"
                ]
            ),
            "formatting_operation_count": (
                classification_counts[
                    "formatting"
                ]
            ),
            "query_operation_count": (
                classification_counts[
                    "query"
                ]
            ),
            "distinct_member_count": (
                len(member_counts)
            ),
            "unknown_member_count": (
                classification_counts[
                    "unknown"
                ]
            ),
            "blocker_count": (
                len(blockers)
            ),
        },
        "member_counts": dict(
            sorted(
                member_counts.items()
            )
        ),
        "classification_counts": dict(
            sorted(
                classification_counts.items()
            )
        ),
        "mutating_members": sorted(
            {
                item["member"]
                for item in operations
                if (
                    item[
                        "classification"
                    ]
                    == "mutating"
                )
            }
        ),
        "formatting_members": sorted(
            {
                item["member"]
                for item in operations
                if (
                    item[
                        "classification"
                    ]
                    == "formatting"
                )
            }
        ),
        "query_members": sorted(
            {
                item["member"]
                for item in operations
                if (
                    item[
                        "classification"
                    ]
                    == "query"
                )
            }
        ),
        "unknown_members": sorted(
            {
                item["member"]
                for item in unknown
            }
        ),
        "operations": operations,
        "blockers": blockers,
        "invariants": {
            "strings_are_lexically_masked": True,
            "comments_are_ignored": True,
            "selection_member_chains_are_parsed": True,
            "contextual_properties_are_classified": True,
            "formatting_is_not_cursor_geometry": True,
            "core_member_requirement_is_fixture_gate_only": True,
            "unknown_selection_members_fail_closed": True,
            "gdp_in_scope": False,
            "unkeyed_entries_used": False,
            "production_code_modified": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )

    args = parser.parse_args()

    input_path = (
        args.input.resolve()
    )

    output_path = (
        args.output.resolve()
    )

    if not input_path.is_file():
        raise SystemExit(
            "Input VBA fixture not found: "
            f"{input_path}"
        )

    report = (
        audit_selection_geometry(
            input_path.read_text(
                encoding="utf-8-sig"
            ),
            require_core_members=True,
        )
    )

    report[
        "source_file"
    ] = str(
        input_path
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = report[
        "summary"
    ]

    print(
        f"STATUS={report['status']}"
    )

    print(
        "OPERATIONS="
        f"{summary['operation_count']}"
    )

    print(
        "MUTATING_OPERATIONS="
        f"{summary['mutating_operation_count']}"
    )

    print(
        "FORMATTING_OPERATIONS="
        f"{summary['formatting_operation_count']}"
    )

    print(
        "QUERY_OPERATIONS="
        f"{summary['query_operation_count']}"
    )

    print(
        "DISTINCT_MEMBERS="
        + ",".join(
            sorted(
                report[
                    "member_counts"
                ]
            )
        )
    )

    print(
        "MUTATING_MEMBERS="
        + ",".join(
            report[
                "mutating_members"
            ]
        )
    )

    print(
        "FORMATTING_MEMBERS="
        + ",".join(
            report[
                "formatting_members"
            ]
        )
    )

    print(
        "QUERY_MEMBERS="
        + ",".join(
            report[
                "query_members"
            ]
        )
    )

    print(
        "UNKNOWN_MEMBERS="
        f"{summary['unknown_member_count']}"
    )

    print(
        "BLOCKERS="
        f"{summary['blocker_count']}"
    )

    if report[
        "unknown_members"
    ]:
        print(
            "UNKNOWN_MEMBER_NAMES="
            + ",".join(
                report[
                    "unknown_members"
                ]
            )
        )

    print(
        f"OUTPUT={output_path}"
    )

    return (
        0
        if not report[
            "blockers"
        ]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )