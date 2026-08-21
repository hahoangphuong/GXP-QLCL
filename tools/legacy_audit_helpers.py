import re
from dataclasses import dataclass
from typing import Iterable


PROC_DEF_RE = re.compile(
    r"(?im)^\s*(Public |Private |Friend |Static )?"
    r"(Sub|Function|Property Get|Property Let|Property Set)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)"
)
PROC_START_RE = re.compile(
    r"(?im)^\s*(?:Public |Private |Friend |Static )?"
    r"(?:Sub|Function|Property Get|Property Let|Property Set)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)"
)

APP_RUN_RE = re.compile(
    r'Application\.Run\s*(?:\(|\s+)\s*"(?:(?P<workbook>[^"!]+)!)?(?P<proc>[A-Za-z_][A-Za-z0-9_]*)',
    re.IGNORECASE,
)

WORD_OP_RE = re.compile(r"\bWord\.Application\b|\bDocuments\.(Open|Add)\b|\.Bookmarks\(", re.IGNORECASE)

FILE_OP_PATTERNS = {
    "fso": re.compile(r"\b(CreateObject\(\"Scripting\.FileSystemObject\"\)|FileSystemObject)\b", re.IGNORECASE),
    "shell": re.compile(r"\b(Shell|ShellExecute)\b", re.IGNORECASE),
    "open": re.compile(r"(?im)^\s*Open\s+.+\s+For\s+(Output|Input|Append|Binary|Random)", re.IGNORECASE),
    "copy_move": re.compile(r"\b(CopyFile|MoveFile|Name\s+.+\s+As\s+.+|FileCopy)\b", re.IGNORECASE),
    "mkdir": re.compile(r"\b(MkDir|CreateFolderx?|FolderExists|FindFirstDir)\b", re.IGNORECASE),
    "save_as": re.compile(r"\.(SaveAs|ExportAsFixedFormat)\b", re.IGNORECASE),
}

COMMENT_LINE_RE = re.compile(r"^\s*'")


@dataclass(frozen=True)
class ProcedureDef:
    kind: str
    name: str


def normalize_vba_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")


def extract_procedure_defs(source: str) -> list[ProcedureDef]:
    return [ProcedureDef(kind=kind, name=name) for _, kind, name in PROC_DEF_RE.findall(source)]


def strip_vba_comments(source: str) -> str:
    lines = []
    for line in source.splitlines():
        if COMMENT_LINE_RE.match(line):
            continue
        if "'" in line:
            line = line.split("'", 1)[0]
        lines.append(line)
    return "\n".join(lines)


def find_application_run_targets(source: str) -> list[dict[str, str]]:
    results = []
    for match in APP_RUN_RE.finditer(source):
        workbook = (match.group("workbook") or "").strip()
        proc = match.group("proc").strip()
        results.append({"workbook": workbook, "procedure": proc})
    return results


def find_direct_calls(source: str, known_proc_names: Iterable[str], current_proc: str) -> list[str]:
    clean_source = strip_vba_comments(source)
    tokens = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", clean_source))
    called: set[str] = set()
    for candidate in known_proc_names:
        if candidate.lower() == current_proc.lower():
            continue
        if candidate in tokens:
            called.add(candidate)
    return sorted(called, key=str.lower)


def detect_word_ops(source: str) -> bool:
    return bool(WORD_OP_RE.search(strip_vba_comments(source)))


def detect_file_ops(source: str) -> list[str]:
    clean_source = strip_vba_comments(source)
    ops = [label for label, pattern in FILE_OP_PATTERNS.items() if pattern.search(clean_source)]
    return sorted(ops)


def detect_header_row(rows: list[list[object]]) -> int:
    best_idx = 0
    best_score = -1
    for idx, row in enumerate(rows):
        values = [str(cell).strip() for cell in row if cell not in (None, "")]
        score = len(values)
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx


def split_procedure_blocks(source: str) -> dict[str, str]:
    matches = list(PROC_START_RE.finditer(source))
    blocks: dict[str, str] = {}
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(source)
        blocks[match.group(1)] = source[start:end]
    return blocks
