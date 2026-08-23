"""Build a deterministic, fail-closed index for the complete R005 corpus.

The admitted closure is discovered from the textbook, answer-book shell, and
Sage lab entry points.  Reader-facing TeX is paired with the upstream authority
at file, heading, semantic-environment, exercise, and inline-answer levels.
All output is locale-neutral at the identity layer and UTF-8/LF on disk.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import zipfile
from bisect import bisect_left
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable


BACKEND = Path(__file__).resolve().parent
LANE = BACKEND.parent
AUTHORITY_ROOT = (
    LANE
    / "authority"
    / "extracted"
    / "linear-algebra-df2262e089a02651c127f1dd12649c4622ee1383"
)
TARGET_ROOT = LANE / "source" / "linear-algebra"
OFFICIAL_ROOT = LANE / "authority" / "official"
BUILD_ROOT = LANE / "build" / "hefferon_id"
BUILD_REPORT_PATH = BUILD_ROOT / "build_report.json"
BUILD_PDF_ROOT = BUILD_ROOT / "output" / "pdf"
CROSS_PDF_LINK_AUDIT_PATH = BUILD_ROOT / "cross_pdf_link_audit.json"
LAB_SAGETEX_RUNTIME_MANIFEST_PATH = (
    BUILD_ROOT / "lab_sagetex_runtime_manifest.json"
)
ARCHIVE_PATH = (
    LANE
    / "authority"
    / "archives"
    / "linear-algebra-df2262e089a02651c127f1dd12649c4622ee1383.zip"
)
SOURCE_SRC = AUTHORITY_ROOT / "src"
TARGET_SRC = TARGET_ROOT / "src"
TERMINOLOGY_LEDGER = LANE / "00_control" / "TERMINOLOGY.csv"
CORRECTION_LEDGER = LANE / "00_control" / "ADVERSE_LEDGER.csv"

SCHEMA = "hefferon-modular-backend"
SCHEMA_VERSION = "0.5.2"
RESOURCE_ID = "r005.hefferon-linear-algebra"
EDITION_ID = f"{RESOURCE_ID}.edition.df2262e"
TARGET_EDITION_ID = (
    f"{RESOURCE_ID}.edition.derivative.locale.id-id.df2262e"
)
PROGRAM_ID = f"{RESOURCE_ID}.program.b40.locale.id-id"
COURSE_ID = f"{RESOURCE_ID}.course.b40.locale.id-id"
RIGHTS_CORE = f"{RESOURCE_ID}.rights.core-dual-license"
RIGHTS_LAB = f"{RESOURCE_ID}.rights.sage-lab-dual-license"
RIGHTS_THIRD_PARTY = f"{RESOURCE_ID}.rights.third-party-review"
RIGHTS_EXTERNAL = f"{RESOURCE_ID}.rights.external-toolchain"
RIGHTS_BOOKANS = f"{RESOURCE_ID}.rights.bookans-lppl"
RIGHTS_BUILD_GPL2 = f"{RESOURCE_ID}.rights.build-script-gpl-2"
RIGHTS_BUILD_GPL3 = f"{RESOURCE_ID}.rights.build-script-gpl-3"
RIGHTS_PROGGY = f"{RESOURCE_ID}.rights.proggy-font-permissive"
RIGHTS_EULER = f"{RESOURCE_ID}.rights.euler-font-ofl-1.1"
RIGHTS_GREAT_WAVE = f"{RESOURCE_ID}.rights.great-wave-cc0"
RIGHTS_ASY_GRAPH = f"{RESOURCE_ID}.rights.asy-graphtheory-unresolved"
WORKFLOW_ID = "hefferon-id.complete-corpus-index.v7"
RECORDED_ON = "2026-08-21"
PRODUCTION_PROVENANCE = "OpenAI Codex gpt-5.6-sol, Ultra."
NATIVE_UPSTREAM_ANSWER_COUNT = 1035
TARGET_SUPPLIED_ANSWER_SPECS = {
    ("src/gr/leontief.tex", 1, 5): {
        "authority_answer_anchor": "ans.One.V.0.5",
        "authorization_event_id": "HLA-A0300",
    },
    ("src/gr/leontief.tex", 1, 6): {
        "authority_answer_anchor": "ans.One.V.0.6",
        "authorization_event_id": "HLA-A0300",
    },
}

ROOT_SPECS = (
    ("main-textbook", "src/book.tex", "textbook", 1),
    ("answer-book-shell", "src/jhanswer.tex", "answer_book", 2),
    ("sage-lab", "src/lab/lab.tex", "sage_lab", 3),
)
OFFICIAL_PDF_SPECS = (
    ("main-textbook", "book.pdf", "textbook_pdf", 10),
    ("answer-book-shell", "jhanswer.pdf", "answer_book_pdf", 11),
    ("sage-lab", "lab.pdf", "sage_lab_pdf", 12),
)
OFFICIAL_PDF_METADATA = {
    "main-textbook": {
        "bytes": 7626685,
        "pages": 525,
        "sha256": "5240f2782e645bc6351ad9eba69d8c19500142a5cca9c90450c17b3765a1a400",
        "url": "https://jheffero.w3.uvm.edu/linearalgebra/book.pdf",
    },
    "answer-book-shell": {
        "bytes": 1789766,
        "pages": 404,
        "sha256": "6e1761061c136a984400198f62253cf208ca36ddee81415ae13de81319b5429d",
        "url": "https://jheffero.w3.uvm.edu/linearalgebra/jhanswer.pdf",
    },
    "sage-lab": {
        "bytes": 13121660,
        "pages": 105,
        "sha256": "0ca33cb79632c3b27c964a6dc8e31f8315d5a529f9e7214ced7f8cb49003b6a2",
        "url": "https://jheffero.w3.uvm.edu/linearalgebra/lab.pdf",
    },
}
TARGET_PDF_NAMES = {
    "main-textbook": "book.pdf",
    "answer-book-shell": "jhanswer.pdf",
    "sage-lab": "lab.pdf",
}
TARGET_PDF_JOBS = {
    "main-textbook": "book",
    "answer-book-shell": "jhanswer",
    "sage-lab": "lab",
}

TERM_FIELDS = [
    "term_id",
    "english",
    "preferred_id",
    "variants",
    "rejected",
    "scope",
    "status",
    "evidence",
    "notes",
]
CORRECTION_FIELDS = [
    "event_id",
    "date",
    "status",
    "severity",
    "scope",
    "summary",
    "evidence",
    "disposition",
]

HEADING_LEVEL = {
    "chapter": 1,
    "section": 2,
    "subsection": 3,
    "subsectionoptional": 3,
}
SEMANTIC_ENVIRONMENTS = {
    "definition": "definition",
    "theorem": "theorem",
    "lemma": "theorem",
    "corollary": "theorem",
    "example": "example",
    "counterexample": "example",
    "remark": "remark",
    "proof": "proof",
    "figure": "figure",
    "tabular": "table",
    "lstlisting": "program",
    "computercode": "program",
    "sagecommandline": "interactive",
    "pythonconsole": "interactive",
    "sagesilent": "program",
}
OPAQUE_ENVIRONMENTS = {
    "verbatim",
    "lstlisting",
    "sagecommandline",
    "pythonconsole",
    "sagesilent",
    "Filesave",
}
ASSET_EXTENSIONS = {
    ".asy",
    ".bib",
    ".cls",
    ".dat",
    ".eps",
    ".jpg",
    ".jpeg",
    ".lua",
    ".ltx",
    ".md",
    ".mp",
    ".otf",
    ".pdf",
    ".pl",
    ".png",
    ".py",
    ".sage",
    ".sh",
    ".sty",
    ".sfd",
    ".ttf",
    ".txt",
    ".zip",
}
IMAGE_EXTENSIONS = {".eps", ".jpg", ".jpeg", ".pdf", ".png"}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def normalized_text(payload: bytes, path: Path) -> str:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"{path} is not valid UTF-8") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n")


class InputSnapshot:
    """Cache input bytes and prove that none changed before projections emit."""

    def __init__(self) -> None:
        self.payloads: dict[Path, bytes] = {}

    def read_bytes(self, path: Path) -> bytes:
        resolved = path.resolve()
        payload = resolved.read_bytes()
        previous = self.payloads.setdefault(resolved, payload)
        if previous != payload:
            raise RuntimeError(f"input changed while indexing: {resolved}")
        return payload

    def read_text(self, path: Path) -> str:
        return normalized_text(self.read_bytes(path), path)

    def assert_unchanged(self) -> None:
        changed = [
            str(path)
            for path, payload in sorted(
                self.payloads.items(), key=lambda item: str(item[0]).lower()
            )
            if path.read_bytes() != payload
        ]
        if changed:
            raise RuntimeError(
                "live inputs changed before final serialization: " + ", ".join(changed)
            )


def canonical_tree_snapshot(inputs: InputSnapshot, root: Path) -> tuple[list[dict], str]:
    """Hash a bounded source tree exactly as the isolated PDF builder does."""

    rows: list[dict] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        payload = inputs.read_bytes(path)
        rows.append(
            {
                "bytes": len(payload),
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_bytes(payload),
            }
        )
    descriptor = canonical_json(rows).encode("utf-8")
    return rows, sha256_bytes(descriptor)


def base_record(record_id: str, record_type: str) -> dict:
    return {
        "id": record_id,
        "record_type": record_type,
        "recorded_on": RECORDED_ON,
        "responsible_workflow": WORKFLOW_ID,
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "status": "active",
        "supersedes": None,
    }


def authoritative_record(record_id: str, record_type: str) -> dict:
    record = base_record(record_id, record_type)
    record.update(
        {
            "edition_id": EDITION_ID,
            "resource_id": RESOURCE_ID,
        }
    )
    return record


def posix_relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def portable_lane_locator(value: str) -> str:
    try:
        return Path(value).resolve().relative_to(LANE.resolve()).as_posix()
    except ValueError as exc:
        raise RuntimeError(f"build receipt path escapes lane: {value}") from exc


def id_token(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", ".", value.lower()).strip(".")
    if not token:
        raise RuntimeError(f"cannot derive stable token from {value!r}")
    return token


def short_hash(value: str, length: int = 20) -> str:
    return sha256_bytes(value.encode("utf-8"))[:length]


def file_unit_id(relative_path: str) -> str:
    return f"{RESOURCE_ID}.unit.file.{id_token(relative_path)}"


def work_unit_id(component: str) -> str:
    return f"{RESOURCE_ID}.unit.work.{id_token(component)}"


@lru_cache(maxsize=None)
def newline_offsets(text: str) -> tuple[int, ...]:
    return tuple(index for index, char in enumerate(text) if char == "\n")


def line_at(text: str, offset: int) -> int:
    return bisect_left(newline_offsets(text), offset) + 1


def locator(relative_path: str, text: str, start: int, end: int) -> str:
    return (
        f"{relative_path}#L{line_at(text, start)}-"
        f"L{line_at(text, max(start, end - 1))}"
    )


@lru_cache(maxsize=None)
def mask_comments(text: str) -> str:
    """Mask active TeX comments while preserving every character offset."""

    result: list[str] = []
    for line in text.splitlines(keepends=True):
        body = line[:-1] if line.endswith("\n") else line
        newline = "\n" if line.endswith("\n") else ""
        comment_at: int | None = None
        for index, char in enumerate(body):
            if char != "%":
                continue
            backslashes = 0
            cursor = index - 1
            while cursor >= 0 and body[cursor] == "\\":
                backslashes += 1
                cursor -= 1
            if backslashes % 2 == 0:
                comment_at = index
                break
        if comment_at is not None:
            body = body[:comment_at] + " " * (len(body) - comment_at)
        result.append(body + newline)
    return "".join(result)


def parse_braced(text: str, open_at: int) -> tuple[str, int]:
    if open_at >= len(text) or text[open_at] != "{":
        raise ValueError("expected opening brace")
    depth = 0
    index = open_at
    while index < len(text):
        char = text[index]
        if char in "{}":
            backslashes = 0
            cursor = index - 1
            while cursor >= 0 and text[cursor] == "\\":
                backslashes += 1
                cursor -= 1
            if backslashes % 2 == 0:
                depth += 1 if char == "{" else -1
                if depth == 0:
                    return text[open_at + 1 : index], index + 1
        index += 1
    raise RuntimeError(f"unclosed brace at offset {open_at}")


def split_semicolon(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def read_csv_rows(
    inputs: InputSnapshot, path: Path, expected_fields: list[str]
) -> list[dict[str, str]]:
    text = inputs.read_text(path)
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames != expected_fields:
        raise RuntimeError(
            f"{path.name} header mismatch: {reader.fieldnames!r}"
        )
    rows = list(reader)
    if any(None in row for row in rows):
        raise RuntimeError(f"{path.name} contains an over-wide row")
    return rows


def validate_unique_local_ids(
    rows: list[dict[str, str]], key: str, path: Path
) -> None:
    values = [row[key].strip() for row in rows]
    if any(not value for value in values):
        raise RuntimeError(f"{path.name} contains an empty {key}")
    duplicates = sorted(
        value for value in set(values) if values.count(value) > 1
    )
    if duplicates:
        raise RuntimeError(f"{path.name} duplicate {key}: {duplicates}")


def validate_terminology_rows(
    rows: list[dict[str, str]], path: Path = TERMINOLOGY_LEDGER
) -> None:
    """Require a contiguous, lossless, semantically coherent term ledger."""

    validate_unique_local_ids(rows, "term_id", path)
    required_fields = (
        "english",
        "preferred_id",
        "scope",
        "status",
        "evidence",
    )
    preferred_by_english: dict[str, str] = {}
    for ordinal, row in enumerate(rows, 1):
        expected_id = f"HLA-T{ordinal:04d}"
        if row["term_id"] != expected_id:
            raise RuntimeError(
                f"{path.name} noncontiguous term_id at record {ordinal}: "
                f"expected {expected_id}, got {row['term_id']!r}"
            )
        for field in TERM_FIELDS:
            value = row[field]
            if value != value.strip():
                raise RuntimeError(
                    f"{path.name} {expected_id} has surrounding whitespace in {field}"
                )
        for field in required_fields:
            if not row[field]:
                raise RuntimeError(
                    f"{path.name} {expected_id} has an empty required field: {field}"
                )

        variants = split_semicolon(row["variants"])
        rejected = split_semicolon(row["rejected"])
        if len(variants) != len(set(variants)):
            raise RuntimeError(f"{path.name} {expected_id} has duplicate variants")
        if len(rejected) != len(set(rejected)):
            raise RuntimeError(f"{path.name} {expected_id} has duplicate rejected forms")
        if row["preferred_id"] in variants:
            raise RuntimeError(
                f"{path.name} {expected_id} repeats the preferred form as a variant"
            )
        if row["preferred_id"] in rejected:
            raise RuntimeError(
                f"{path.name} {expected_id} rejects its preferred form"
            )
        overlap = sorted(set(variants) & set(rejected))
        if overlap:
            raise RuntimeError(
                f"{path.name} {expected_id} both admits and rejects {overlap!r}"
            )

        english_key = row["english"].casefold()
        prior_preferred = preferred_by_english.setdefault(
            english_key, row["preferred_id"]
        )
        if prior_preferred != row["preferred_id"]:
            raise RuntimeError(
                f"{path.name} has conflicting preferred forms for "
                f"{row['english']!r}: {prior_preferred!r} and "
                f"{row['preferred_id']!r}"
            )


def extract_tex_dependencies(text: str) -> list[tuple[int, str, str]]:
    masked = mask_comments(text)
    pattern = re.compile(
        r"\\(?P<command>include|input)\b\s*"
        r"(?:\{(?P<braced>[^{}\n]*)\}|(?P<plain>[^\s%{}]+))"
    )
    dependencies: list[tuple[int, str, str]] = []
    for match in pattern.finditer(masked):
        value = (match.group("braced") or match.group("plain") or "").strip()
        if value:
            dependencies.append((match.start(), match.group("command"), value))
    return dependencies


def resolve_tex_dependency(
    repository_root: Path,
    owner_relative: str,
    declared: str,
    component: str,
) -> str | None:
    if "\\" in declared or "#" in declared:
        return None
    candidate_value = declared.strip().strip("\"'")
    if not candidate_value:
        return None
    candidate_path = Path(candidate_value)
    if not candidate_path.suffix:
        candidate_path = candidate_path.with_suffix(".tex")
    owner = repository_root / owner_relative
    candidates = [
        owner.parent / candidate_path,
        repository_root / "src" / candidate_path,
    ]
    if component == "sage-lab":
        candidates.insert(1, repository_root / "src" / "lab" / candidate_path)
    candidates.extend(
        [
            repository_root / "src" / "cover" / candidate_path,
            repository_root / "src" / "sty" / candidate_path,
        ]
    )
    resolved_candidates: list[str] = []
    for candidate in candidates:
        try:
            relative = candidate.resolve().relative_to(repository_root.resolve())
        except ValueError:
            continue
        if candidate.is_file():
            relative_text = relative.as_posix()
            if relative_text not in resolved_candidates:
                resolved_candidates.append(relative_text)
    # TeX searches the including file's directory before the configured
    # repository-wide paths.  This matters for lab/cover.tex versus the
    # textbook's cover/cover.tex; candidate order above is authoritative.
    return resolved_candidates[0] if resolved_candidates else None


@dataclass(frozen=True)
class Closure:
    component: str
    root: str
    files: tuple[str, ...]
    dynamic_dependencies: tuple[tuple[str, int, str, str], ...]


def discover_closure(
    inputs: InputSnapshot,
    repository_root: Path,
    component: str,
    root_relative: str,
) -> Closure:
    queue: deque[str] = deque([root_relative])
    seen: set[str] = set()
    ordered: list[str] = []
    dynamic: list[tuple[str, int, str, str]] = []
    while queue:
        relative = queue.popleft()
        if relative in seen:
            continue
        path = repository_root / relative
        if not path.is_file():
            raise RuntimeError(f"closure file missing: {path}")
        seen.add(relative)
        ordered.append(relative)
        text = inputs.read_text(path)
        for offset, command, declared in extract_tex_dependencies(text):
            resolved = resolve_tex_dependency(
                repository_root, relative, declared, component
            )
            if resolved is None:
                dynamic.append(
                    (relative, line_at(text, offset), command, declared)
                )
            elif resolved not in seen:
                queue.append(resolved)
    return Closure(
        component=component,
        root=root_relative,
        files=tuple(ordered),
        dynamic_dependencies=tuple(dynamic),
    )


@dataclass(frozen=True)
class Heading:
    command: str
    kind: str
    level: int
    start: int
    command_end: int
    title: str


def find_headings(text: str) -> list[Heading]:
    masked = mask_comments(text)
    pattern = re.compile(
        r"\\(?P<command>chapter|section|subsectionoptional|subsection)"
        r"(?P<star>\*)?\s*"
    )
    headings: list[Heading] = []
    for match in pattern.finditer(masked):
        open_at = match.end()
        if open_at >= len(masked) or masked[open_at] != "{":
            continue
        title, command_end = parse_braced(text, open_at)
        command = match.group("command")
        kind = (
            "subsection"
            if command in {"subsection", "subsectionoptional"}
            else command
        )
        headings.append(
            Heading(
                command=command + ("*" if match.group("star") else ""),
                kind=kind,
                level=HEADING_LEVEL[command],
                start=match.start(),
                command_end=command_end,
                title=title,
            )
        )
    return headings


@dataclass(frozen=True)
class EnvironmentSpan:
    name: str
    open_start: int
    open_end: int
    close_start: int
    close_end: int
    depth: int


def find_environment_spans(text: str, source_name: str) -> list[EnvironmentSpan]:
    masked = mask_comments(text)
    token_pattern = re.compile(r"\\(?P<edge>begin|end)\{(?P<name>[^{}\n]+)\}")
    stack: list[tuple[str, int, int, int]] = []
    spans: list[EnvironmentSpan] = []
    for token in token_pattern.finditer(masked):
        edge = token.group("edge")
        name = token.group("name")
        if stack and stack[-1][0] in OPAQUE_ENVIRONMENTS:
            if edge == "end" and name == stack[-1][0]:
                open_name, open_start, open_end, depth = stack.pop()
                spans.append(
                    EnvironmentSpan(
                        open_name,
                        open_start,
                        open_end,
                        token.start(),
                        token.end(),
                        depth,
                    )
                )
            continue
        if edge == "begin":
            stack.append((name, token.start(), token.end(), len(stack)))
            continue
        if not stack or stack[-1][0] != name:
            raise RuntimeError(
                f"{source_name}: environment mismatch near line "
                f"{line_at(text, token.start())}: closing {name!r}, "
                f"stack={[entry[0] for entry in stack]!r}"
            )
        open_name, open_start, open_end, depth = stack.pop()
        spans.append(
            EnvironmentSpan(
                open_name,
                open_start,
                open_end,
                token.start(),
                token.end(),
                depth,
            )
        )
    if stack:
        raise RuntimeError(
            f"{source_name}: unclosed environments "
            f"{[entry[0] for entry in stack]!r}"
        )
    return sorted(spans, key=lambda span: (span.open_start, -span.close_end))


def labels_in(text: str, start: int = 0, end: int | None = None) -> list[str]:
    masked = mask_comments(text)
    return re.findall(r"\\label\{([^{}\n]+)\}", masked[start:end])


def label_matches(text: str) -> list[tuple[int, str]]:
    masked = mask_comments(text)
    return [
        (match.start(), match.group(1))
        for match in re.finditer(r"\\label\{([^{}\n]+)\}", masked)
    ]


def top_level_item_starts(text: str, span: EnvironmentSpan) -> list[int]:
    masked = mask_comments(text)
    token_pattern = re.compile(
        r"\\begin\{(?P<begin>[^{}\n]+)\}|"
        r"\\end\{(?P<end>[^{}\n]+)\}|\\item\b"
    )
    stack: list[str] = []
    starts: list[int] = []
    for token in token_pattern.finditer(
        masked, span.open_start, span.close_end
    ):
        begin_name = token.group("begin")
        end_name = token.group("end")
        if stack and stack[-1] in OPAQUE_ENVIRONMENTS:
            if end_name == stack[-1]:
                stack.pop()
            continue
        if begin_name is not None:
            stack.append(begin_name)
            continue
        if end_name is not None:
            if not stack or stack[-1] != end_name:
                raise RuntimeError(
                    f"item scan environment mismatch near offset {token.start()}"
                )
            stack.pop()
            continue
        if stack == ["exercises"]:
            line_start = masked.rfind("\n", span.open_start, token.start()) + 1
            prefix = masked[line_start : token.start()]
            starts.append(line_start if prefix.strip() else token.start())
    return starts


def is_unnumbered_item_header(text: str, start: int, end: int) -> bool:
    """Return whether a top-level item is an optional-label rubric/header."""

    fragment = mask_comments(text[start : min(end, start + 500)])
    pattern = re.compile(
        r"\s*(?:(?:\\recommended|\\puzzle)\s+)*\\item\s*\["
    )
    return pattern.match(fragment) is not None


def find_xrefs(text: str) -> list[tuple[int, str, str]]:
    masked = mask_comments(text)
    pattern = re.compile(
        r"\\(?P<command>ref|pageref|nearby[A-Za-z]+)\{(?P<label>[^{}\n]+)\}"
    )
    return [
        (match.start(), match.group("command"), match.group("label"))
        for match in pattern.finditer(masked)
    ]


def clean_title(value: str) -> str:
    cleaned = re.sub(r"\\label\{[^{}]*\}", "", value)
    cleaned = re.sub(r"\\[A-Za-z@]+\*?", " ", cleaned)
    cleaned = re.sub(r"[{}$]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def stable_node_id(
    owner_file_id: str, kind: str, ordinal: int, native_label: str | None
) -> str:
    if native_label:
        suffix = f"label.{short_hash(native_label)}"
    else:
        suffix = f"source-order.{ordinal:04d}"
    return f"{owner_file_id}.{id_token(kind)}.{suffix}"


def unit_authority_fields(
    *,
    parent_id: str,
    order: int,
    path: list[str],
    unit_kind: str,
    source_locator: str | None,
    source_sha256: str | None,
    target_locator: str | None,
    target_sha256: str | None,
    rights_id: str,
    translation_state: str | None = "structurally_verified",
) -> dict:
    return {
        "concept_ids": [],
        "edition_id": EDITION_ID,
        "language": None,
        "locale": None,
        "order": order,
        "parent_id": parent_id,
        "path": path,
        "prerequisite_ids": [],
        "prerequisite_status": "not asserted without curated evidence",
        "resource_id": RESOURCE_ID,
        "rights_id": rights_id,
        "source_language": "en",
        "source_locator": source_locator,
        "source_sha256": source_sha256,
        "target_language": "id",
        "target_edition_id": TARGET_EDITION_ID,
        "target_locale": "id-ID",
        "target_locator": target_locator,
        "target_sha256": target_sha256,
        "target_variant": {
            "edition_id": TARGET_EDITION_ID,
            "language": "id",
            "locale": "id-ID",
            "locator": target_locator,
            "sha256": target_sha256,
        },
        "translation_state": translation_state,
        "unit_kind": unit_kind,
    }


def rights_for_path(relative_path: str, component: str) -> str:
    lower = relative_path.lower()
    if lower == "src/sty/bookans.sty":
        return RIGHTS_BOOKANS
    if lower == "src/mp/compile_mp.sh":
        return RIGHTS_BUILD_GPL2
    if lower == "src/lab/runlab.sh":
        return RIGHTS_BUILD_GPL3
    if lower.startswith("src/lab/fonts/euler-otf-master/"):
        return RIGHTS_EULER
    if lower.startswith("src/lab/fonts/"):
        return RIGHTS_PROGGY
    if lower in {"src/lab/pix/greatwave.png", "src/lab/pix/greatwave.txt"}:
        return RIGHTS_GREAT_WAVE
    if "asy-graphtheory-master/" in lower:
        return RIGHTS_ASY_GRAPH
    third_party_markers = (
        "lastsupper",
        "melencolia",
        "loshu",
        "salt.jpg",
        "suzy_cover",
        "kdp_diagram",
    )
    if any(marker in lower for marker in third_party_markers):
        return RIGHTS_THIRD_PARTY
    return RIGHTS_LAB if component == "sage-lab" else RIGHTS_CORE


def classify_asset(relative_path: str, reference_kind: str | None = None) -> str:
    suffix = Path(relative_path).suffix.lower()
    if reference_kind in {"documentclass", "usepackage"} or suffix in {
        ".cls",
        ".sty",
    }:
        return "latex_build_dependency"
    if suffix in IMAGE_EXTENSIONS:
        return "figure_or_media"
    if suffix in {".otf", ".sfd", ".ttf"}:
        return "font_or_font_source"
    if suffix in {".sage", ".py", ".asy", ".mp", ".pl", ".sh"}:
        return "source_code"
    if suffix == ".bib":
        return "bibliography_data"
    if suffix in {".dat", ".txt"}:
        return "data"
    return reference_kind or "build_asset"


@dataclass(frozen=True)
class AssetReference:
    component: str
    owner_relative: str
    offset: int
    kind: str
    declared: str


def extract_asset_references(
    text: str, component: str, owner_relative: str
) -> list[AssetReference]:
    masked = mask_comments(text)
    patterns = {
        "includegraphics": re.compile(
            r"\\includegraphics(?:\[[^\]\n]*\])?\{([^{}\n]+)\}"
        ),
        "lstinputlisting": re.compile(
            r"\\lstinputlisting(?:\[[^\]\n]*\])?\{([^{}\n]+)\}"
        ),
        "bibliography": re.compile(r"\\bibliography\{([^{}\n]+)\}"),
        "documentclass": re.compile(
            r"\\documentclass(?:\[[^\]\n]*\])?\{([^{}\n]+)\}"
        ),
        "usepackage": re.compile(
            r"\\usepackage(?:\[[^\]\n]*\])?\{([^{}\n]+)\}"
        ),
    }
    references: list[AssetReference] = []
    for kind, pattern in patterns.items():
        for match in pattern.finditer(masked):
            declared_values = [match.group(1)]
            if kind in {"bibliography", "usepackage"}:
                declared_values = match.group(1).split(",")
            for declared in declared_values:
                value = declared.strip()
                if value:
                    references.append(
                        AssetReference(
                            component, owner_relative, match.start(), kind, value
                        )
                    )
    return sorted(
        references,
        key=lambda ref: (ref.offset, ref.kind, ref.declared),
    )


def asset_candidates(
    repository_root: Path,
    reference: AssetReference,
) -> list[Path]:
    declared = reference.declared.strip().strip("\"'")
    if "\\" in declared or not declared:
        return []
    raw = Path(declared)
    owner = repository_root / reference.owner_relative
    base_candidates = [
        owner.parent / raw,
        repository_root / "src" / raw,
    ]
    if reference.component == "sage-lab":
        base_candidates.insert(1, repository_root / "src" / "lab" / raw)
    if reference.kind in {"documentclass", "usepackage"}:
        base_candidates.extend(
            [
                repository_root / "src" / "sty" / raw,
                repository_root / "src" / "lab" / raw,
            ]
        )
    suffixes: list[str]
    if raw.suffix:
        suffixes = [""]
    elif reference.kind == "includegraphics":
        suffixes = ["", ".pdf", ".png", ".jpg", ".jpeg", ".eps"]
    elif reference.kind == "lstinputlisting":
        suffixes = [""]
    elif reference.kind == "bibliography":
        suffixes = [".bib"]
    elif reference.kind == "documentclass":
        suffixes = [".cls"]
    elif reference.kind == "usepackage":
        suffixes = [".sty"]
    else:
        suffixes = [""]
    candidates: list[Path] = []
    for base in base_candidates:
        for suffix in suffixes:
            candidate = Path(str(base) + suffix)
            try:
                candidate.resolve().relative_to(repository_root.resolve())
            except ValueError:
                continue
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def resolve_asset(
    repository_root: Path, reference: AssetReference
) -> str | None:
    found = [
        posix_relative(path, repository_root)
        for path in asset_candidates(repository_root, reference)
        if path.is_file()
    ]
    found = list(dict.fromkeys(found))
    # Match TeX's ordered lookup: owner-local, component-local, then shared.
    return found[0] if found else None


def supplemental_asset_paths(
    repository_root: Path, closure_files: Iterable[str]
) -> set[str]:
    paths: set[str] = set()
    main_dirs = {
        Path(relative).parts[1]
        for relative in closure_files
        if len(Path(relative).parts) > 2
        and Path(relative).parts[1]
        in {"appen", "bib", "cover", "det", "gr", "jc", "map", "pref", "vs"}
    }
    for directory in sorted(main_dirs):
        root = repository_root / "src" / directory
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in ASSET_EXTENSIONS:
                paths.add(posix_relative(path, repository_root))
    for path in (repository_root / "src" / "asy").glob("*.asy"):
        if path.is_file():
            paths.add(posix_relative(path, repository_root))
    for path in (repository_root / "src" / "mp").glob("*"):
        if path.is_file() and path.suffix.lower() in ASSET_EXTENSIONS:
            paths.add(posix_relative(path, repository_root))
    lab_root = repository_root / "src" / "lab"
    if lab_root.is_dir():
        for path in lab_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() == ".tex":
                continue
            relative_parts = path.relative_to(lab_root).parts
            if relative_parts and relative_parts[0] == "fonts":
                paths.add(posix_relative(path, repository_root))
                continue
            if (
                path.suffix.lower() in ASSET_EXTENSIONS
                or path.name in {"README", "INSTALL"}
            ):
                paths.add(posix_relative(path, repository_root))
    license_path = repository_root / "LICENSE"
    if license_path.is_file():
        paths.add("LICENSE")
    return paths


def serialize_jsonl(records: list[dict]) -> bytes:
    return (
        "".join(canonical_json(record) + "\n" for record in records)
    ).encode("utf-8")


def serialize_csv(records: list[dict], fieldnames: list[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=fieldnames, lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(records)
    return stream.getvalue().encode("utf-8")


def assert_lf_utf8(name: str, payload: bytes) -> None:
    normalized_text(payload, Path(name))
    if b"\r" in payload:
        raise RuntimeError(f"{name} is not LF-normalized")


def atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def main() -> None:
    inputs = InputSnapshot()

    source_closures: list[Closure] = []
    target_closures: list[Closure] = []
    root_metadata: dict[str, tuple[str, int]] = {}
    for component, root, work_kind, root_order in ROOT_SPECS:
        source_closure = discover_closure(
            inputs, AUTHORITY_ROOT, component, root
        )
        target_closure = discover_closure(inputs, TARGET_ROOT, component, root)
        if source_closure.files != target_closure.files:
            raise RuntimeError(
                f"{component} source/target closure mismatch: "
                f"{source_closure.files!r} != {target_closure.files!r}"
            )
        source_dynamic_signature = [
            (owner, command, declared)
            for owner, _line, command, declared
            in source_closure.dynamic_dependencies
        ]
        target_dynamic_signature = [
            (owner, command, declared)
            for owner, _line, command, declared
            in target_closure.dynamic_dependencies
        ]
        if source_dynamic_signature != target_dynamic_signature:
            raise RuntimeError(
                f"{component} dynamic TeX dependencies differ: "
                f"{source_dynamic_signature!r} != {target_dynamic_signature!r}"
            )
        source_closures.append(source_closure)
        target_closures.append(target_closure)
        root_metadata[component] = (work_kind, root_order)

    component_files = {
        closure.component: list(closure.files) for closure in source_closures
    }
    file_components: dict[str, list[str]] = defaultdict(list)
    all_files: list[str] = []
    for closure in source_closures:
        for relative in closure.files:
            if closure.component not in file_components[relative]:
                file_components[relative].append(closure.component)
            if relative not in all_files:
                all_files.append(relative)

    source_file_data: dict[str, tuple[bytes, str]] = {}
    target_file_data: dict[str, tuple[bytes, str]] = {}
    for relative in all_files:
        source_payload = inputs.read_bytes(AUTHORITY_ROOT / relative)
        target_payload = inputs.read_bytes(TARGET_ROOT / relative)
        source_file_data[relative] = (
            source_payload,
            normalized_text(source_payload, AUTHORITY_ROOT / relative),
        )
        target_file_data[relative] = (
            target_payload,
            normalized_text(target_payload, TARGET_ROOT / relative),
        )

    terminology_rows = read_csv_rows(
        inputs, TERMINOLOGY_LEDGER, TERM_FIELDS
    )
    correction_rows = read_csv_rows(
        inputs, CORRECTION_LEDGER, CORRECTION_FIELDS
    )
    validate_terminology_rows(terminology_rows, TERMINOLOGY_LEDGER)
    validate_unique_local_ids(
        correction_rows, "event_id", CORRECTION_LEDGER
    )
    terminology_sha = sha256_bytes(inputs.read_bytes(TERMINOLOGY_LEDGER))
    correction_sha = sha256_bytes(inputs.read_bytes(CORRECTION_LEDGER))
    correction_row_by_id = {
        row["event_id"].strip(): (row_number, row)
        for row_number, row in enumerate(correction_rows, 2)
    }
    target_answer_authorization = correction_row_by_id.get("HLA-A0300")
    if target_answer_authorization is None:
        raise RuntimeError("target-supplied answers require ledger event HLA-A0300")
    if target_answer_authorization[1]["status"] != "corrected_in_target":
        raise RuntimeError("HLA-A0300 does not authorize a corrected target")

    build_report: dict | None = None
    build_report_sha: str | None = None
    live_target_tree_sha: str | None = None
    if BUILD_REPORT_PATH.is_file():
        build_report_payload = inputs.read_bytes(BUILD_REPORT_PATH)
        build_report_sha = sha256_bytes(build_report_payload)
        try:
            candidate = json.loads(build_report_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("build report is not valid UTF-8 JSON") from exc
        if not isinstance(candidate, dict) or candidate.get("status") not in {
            "failed",
            "running",
            "success",
        }:
            raise RuntimeError("build report has an invalid status or root type")
        build_report = candidate
        if build_report["status"] == "success":
            _target_tree_rows, live_target_tree_sha = canonical_tree_snapshot(
                inputs, TARGET_ROOT
            )
            source_witness = build_report.get("source", {})
            if source_witness.get("tree_sha256") != live_target_tree_sha:
                raise RuntimeError(
                    "successful build report is not bound to the current target tree"
                )
            if source_witness.get("live_end_tree_sha256") != live_target_tree_sha:
                raise RuntimeError(
                    "successful build report ended on a different target tree"
                )
            if source_witness.get("unchanged_during_build") is not True:
                raise RuntimeError(
                    "successful build report does not prove source stability"
                )

    authority_records: list[dict] = []
    resource = base_record(RESOURCE_ID, "resource")
    resource.update(
        {
            "author": "Jim Hefferon",
            "course_role": "B40",
            "gitlab_project_id": 1354502,
            "official_repository": "https://gitlab.com/jim.hefferon/linear-algebra",
            "source_language": "en",
            "source_title": "Linear Algebra",
            "target_locale": "id-ID",
        }
    )
    authority_records.append(resource)
    edition = base_record(EDITION_ID, "edition")
    archive_payload = inputs.read_bytes(ARCHIVE_PATH)
    archive_sha = sha256_bytes(archive_payload)
    if len(archive_payload) != 42547343 or archive_sha != (
        "b409fc82a8323578e71d8095b9ab4bc9ca814d5a0d9cc6d125dd6b4d81dc23d0"
    ):
        raise RuntimeError("pinned source archive authority mismatch")
    edition.update(
        {
            "archive_bytes": len(archive_payload),
            "archive_locator": "authority/archives/linear-algebra-df2262e089a02651c127f1dd12649c4622ee1383.zip",
            "archive_role": "retrieval receipt; commit and tree are canonical",
            "archive_sha256": archive_sha,
            "commit": "df2262e089a02651c127f1dd12649c4622ee1383",
            "default_branch": "master",
            "edition_statement": "Fourth edition, second printing",
            "parent_commit": "f2b9b985e6576d144a81f7382479dde5f0e8670f",
            "parent_resource_id": RESOURCE_ID,
            "source_tree": "30340725aa2641b3c617b1584c59f6df83e1fdf3",
            "tag": None,
            "tag_status": "no upstream tag or release exists",
            "translation_state": "source_frozen",
        }
    )
    authority_records.append(edition)
    target_edition = base_record(TARGET_EDITION_ID, "edition")
    target_edition.update(
        {
            "derivative_kind": "translation_and_machine-readable_build_derivative",
            "language": "id",
            "locale": "id-ID",
            "parent_resource_id": RESOURCE_ID,
            "parent_source_edition_id": EDITION_ID,
            "production_provenance": PRODUCTION_PROVENANCE,
            "rights_id": RIGHTS_CORE,
            "source_commit": "df2262e089a02651c127f1dd12649c4622ee1383",
            "source_tree": "30340725aa2641b3c617b1584c59f6df83e1fdf3",
            "translation_state": "structurally_verified",
        }
    )
    authority_records.append(target_edition)

    program_records: list[dict] = []
    program = authoritative_record(PROGRAM_ID, "program")
    program.update(
        {
            "curriculum_role": "B40",
            "derivative_edition_id": TARGET_EDITION_ID,
            "language": "id",
            "locale": "id-ID",
            "program_scope": "complete R005 textbook, inline answers, and Sage lab",
            "resource_ids": [RESOURCE_ID],
            "rights_id": RIGHTS_CORE,
            "translation_state": "structurally_verified",
            "version": "v0",
        }
    )
    program_records.append(program)

    course_records: list[dict] = []
    course = authoritative_record(COURSE_ID, "course")
    course.update(
        {
            "course_role": "B40",
            "derivative_edition_id": TARGET_EDITION_ID,
            "language": "id",
            "locale": "id-ID",
            "parent_program_id": PROGRAM_ID,
            "prerequisite_ids": [],
            "prerequisite_status": "not asserted without curriculum evidence",
            "resource_ids": [RESOURCE_ID],
            "rights_id": RIGHTS_CORE,
            "source_title": "Linear Algebra",
            "target_title": "Aljabar Linear",
            "translation_state": "structurally_verified",
        }
    )
    course_records.append(course)

    def input_sha(relative: str) -> str:
        return sha256_bytes(inputs.read_bytes(AUTHORITY_ROOT / relative))

    license_sha = input_sha("LICENSE")
    if license_sha != "45e69a5115ce82fb4566271045b1777d4c506929f866fa12c2ca0ef9b23bb140":
        raise RuntimeError("pinned license authority mismatch")
    rights_records: list[dict] = []
    core_rights = authoritative_record(RIGHTS_CORE, "rights")
    core_rights.update(
        {
            "attribution": "Jim Hefferon, Linear Algebra",
            "change_notice_required": True,
            "component_scope": "main textbook, inline answers, and repository-authored assets",
            "license_authority_locator": "LICENSE",
            "license_authority_sha256": license_sha,
            "license_choice": "Creative Commons Attribution-ShareAlike 2.5",
            "selected_license_identifier": "CC-BY-SA-2.5",
            "upstream_license_options": [
                "GNU Free Documentation License",
                "Creative Commons Attribution-ShareAlike 2.5",
            ],
            "non_endorsement": True,
            "third_party_status": "separate components excluded from this grant",
        }
    )
    rights_records.append(core_rights)
    lab_rights = authoritative_record(RIGHTS_LAB, "rights")
    lab_rights.update(
        {
            "attribution": "Jim Hefferon, Linear Algebra Sage lab manual",
            "change_notice_required": True,
            "component_scope": "Sage lab prose and repository-authored code",
            "license_authority_locator": "LICENSE; src/lab/README",
            "license_authority_sha256": license_sha,
            "license_choice": "Creative Commons Attribution-ShareAlike 2.5",
            "selected_license_identifier": "CC-BY-SA-2.5",
            "upstream_license_options": [
                "GNU Free Documentation License",
                "Creative Commons Attribution-ShareAlike 2.5",
            ],
            "non_endorsement": True,
            "third_party_status": "fonts and incorporated media remain separate",
        }
    )
    rights_records.append(lab_rights)
    third_party_rights = authoritative_record(
        RIGHTS_THIRD_PARTY, "rights"
    )
    third_party_rights.update(
        {
            "attribution": None,
            "change_notice_required": None,
            "component_scope": "unresolved photographs, artwork, and cover media",
            "license_authority_locator": None,
            "license_authority_sha256": None,
            "license_choice": None,
            "selected_license_identifier": None,
            "upstream_license_options": [],
            "non_endorsement": None,
            "third_party_status": "component-specific rights review required",
        }
    )
    rights_records.append(third_party_rights)
    external_rights = authoritative_record(RIGHTS_EXTERNAL, "rights")
    external_rights.update(
        {
            "attribution": None,
            "change_notice_required": None,
            "component_scope": "external TeX/Sage/Python toolchain dependencies",
            "license_authority_locator": None,
            "license_authority_sha256": None,
            "license_choice": None,
            "selected_license_identifier": None,
            "upstream_license_options": [],
            "non_endorsement": None,
            "third_party_status": "governed by respective upstream packages",
        }
    )
    rights_records.append(external_rights)

    component_rights_specs = [
        (
            RIGHTS_BOOKANS,
            "Jim Hefferon",
            "src/sty/bookans.sty",
            "src/sty/bookans.sty",
            "LaTeX Project Public License (version not stated)",
            None,
            "bookans.sty answer-extraction and reciprocal-link package",
        ),
        (
            RIGHTS_BUILD_GPL2,
            "Jim Hefferon",
            "src/mp/compile_mp.sh",
            "src/mp/compile_mp.sh",
            "GNU General Public License 2 (as declared in file header)",
            "GPL-2.0-only",
            "MetaPost build helper src/mp/compile_mp.sh",
        ),
        (
            RIGHTS_BUILD_GPL3,
            "Jim Hefferon",
            "src/lab/runlab.sh",
            "src/lab/runlab.sh",
            "GNU General Public License 3 (as declared in file header)",
            "GPL-3.0-only",
            "Sage lab build helper src/lab/runlab.sh",
        ),
        (
            RIGHTS_PROGGY,
            "Tristan Grimmer",
            "src/lab/fonts/Licence.txt",
            "src/lab/fonts/Licence.txt",
            "Proggy permissive license",
            None,
            "ProggyClean and ProggyCleanSage font bundle and documentation",
        ),
        (
            RIGHTS_EULER,
            "American Mathematical Society; Hermann Zapf; Khaled Hosny",
            "src/lab/fonts/euler-otf-master/OFL.txt",
            "src/lab/fonts/euler-otf-master/OFL.txt",
            "SIL Open Font License 1.1",
            "OFL-1.1",
            "Euler OTF font, sources, tests, utilities, and license documentation",
        ),
        (
            RIGHTS_GREAT_WAVE,
            "Katsushika Hokusai; Art Institute of Chicago",
            "src/lab/pix/greatwave.txt",
            "src/lab/pix/greatwave.txt",
            "Creative Commons Zero",
            "CC0-1.0",
            "Great Wave image and provenance notice",
        ),
    ]
    for (
        rights_id,
        attribution,
        authority_locator,
        hash_path,
        license_choice,
        license_identifier,
        component_scope,
    ) in component_rights_specs:
        record = authoritative_record(rights_id, "rights")
        record.update(
            {
                "attribution": attribution,
                "change_notice_required": None,
                "component_scope": component_scope,
                "license_authority_locator": authority_locator,
                "license_authority_sha256": input_sha(hash_path),
                "license_choice": license_choice,
                "non_endorsement": None,
                "selected_license_identifier": license_identifier,
                "third_party_status": "component-specific authority resolved",
                "upstream_license_options": [license_choice],
            }
        )
        rights_records.append(record)

    asy_graph_rights = authoritative_record(RIGHTS_ASY_GRAPH, "rights")
    asy_graph_rights.update(
        {
            "attribution": None,
            "change_notice_required": None,
            "component_scope": "embedded asy-graphtheory source subtree",
            "license_authority_locator": None,
            "license_authority_sha256": None,
            "license_choice": None,
            "non_endorsement": None,
            "selected_license_identifier": None,
            "third_party_status": "no component license file in pinned snapshot; review required before separate reuse",
            "upstream_license_options": [],
        }
    )
    rights_records.append(asy_graph_rights)

    relation_specs: list[dict] = []

    def add_relation(
        relation_type: str,
        source_id: str,
        target_id: str,
        order: int,
        source_locator: str | None = None,
    ) -> None:
        relation_specs.append(
            {
                "relation_type": relation_type,
                "source_id": source_id,
                "target_id": target_id,
                "order": order,
                "source_locator": source_locator,
            }
        )

    unit_records: list[dict] = []
    unit_by_id: dict[str, dict] = {}
    unit_meta: dict[str, dict] = {}
    segment_records: list[dict] = []

    def register_unit(record: dict, meta: dict | None = None) -> None:
        if record["id"] in unit_by_id:
            raise RuntimeError(f"duplicate unit ID: {record['id']}")
        unit_records.append(record)
        unit_by_id[record["id"]] = record
        if meta is not None:
            unit_meta[record["id"]] = meta
        parent_id = record.get("parent_id")
        if parent_id:
            add_relation(
                "contains",
                parent_id,
                record["id"],
                int(record.get("order", 0)),
                record.get("source_locator"),
            )

    def register_segment(
        unit_id: str,
        source_relative: str,
        target_relative: str,
        source_text: str,
        target_text: str,
        source_start: int,
        source_end: int,
        target_start: int,
        target_end: int,
        projection_role: str,
        order: int = 1,
    ) -> str:
        segment_id = f"{unit_id}.segment.{order:03d}"
        segment = authoritative_record(segment_id, "segment")
        source_value = source_text[source_start:source_end]
        target_value = target_text[target_start:target_end]
        segment.update(
            {
                "language": "mul",
                "locale": None,
                "order": order,
                "parent_unit_id": unit_id,
                "projection_role": projection_role,
                "provenance": {
                    "method": "paired authority/derivative structural projection",
                    "source_edition_id": EDITION_ID,
                },
                "rights_id": unit_by_id[unit_id]["rights_id"],
                "source_end_line": line_at(
                    source_text, max(source_start, source_end - 1)
                ),
                "source_language": "en",
                "source_locator": locator(
                    source_relative, source_text, source_start, source_end
                ),
                "source_sha256": sha256_bytes(source_value.encode("utf-8")),
                "source_start_line": line_at(source_text, source_start),
                "source_text": source_value,
                "source_unit_id": unit_id,
                "target_end_line": line_at(
                    target_text, max(target_start, target_end - 1)
                ),
                "target_language": "id",
                "target_edition_id": TARGET_EDITION_ID,
                "target_locale": "id-ID",
                "target_locator": locator(
                    target_relative, target_text, target_start, target_end
                ),
                "target_sha256": sha256_bytes(target_value.encode("utf-8")),
                "target_start_line": line_at(target_text, target_start),
                "target_text": target_value,
                "target_variant": {
                    "edition_id": TARGET_EDITION_ID,
                    "end_line": line_at(
                        target_text, max(target_start, target_end - 1)
                    ),
                    "language": "id",
                    "locale": "id-ID",
                    "locator": locator(
                        target_relative, target_text, target_start, target_end
                    ),
                    "sha256": sha256_bytes(target_value.encode("utf-8")),
                    "start_line": line_at(target_text, target_start),
                    "text": target_value,
                },
                "translation_state": "structurally_verified",
            }
        )
        segment_records.append(segment)
        unit_by_id[unit_id].setdefault("segment_ids", []).append(segment_id)
        add_relation("contains", unit_id, segment_id, order, segment["source_locator"])
        return segment_id

    def register_target_supplied_answer_segment(
        unit_id: str,
        authority_exercise_unit_id: str,
        authority_exercise_locator: str,
        target_relative: str,
        target_text: str,
        target_start: int,
        target_end: int,
        authority_answer_anchor: str,
        authorization_event_id: str,
    ) -> str:
        segment_id = f"{unit_id}.segment.001"
        target_value = target_text[target_start:target_end]
        ledger_row, _ledger_record = correction_row_by_id[authorization_event_id]
        authorization_locator = f"00_control/ADVERSE_LEDGER.csv#row-{ledger_row}"
        segment = base_record(segment_id, "segment")
        segment.update(
            {
                "authority_answer_anchor": authority_answer_anchor,
                "authority_exercise_locator": authority_exercise_locator,
                "authority_exercise_unit_id": authority_exercise_unit_id,
                "authorization_event_id": authorization_event_id,
                "authorization_ledger_locator": authorization_locator,
                "authorization_ledger_sha256": correction_sha,
                "edition_id": TARGET_EDITION_ID,
                "language": "id",
                "locale": "id-ID",
                "order": 1,
                "parent_unit_id": unit_id,
                "projection_role": "indonesian-edition-supplied-answer",
                "provenance": {
                    "authority_answer_status": "absent_from_pinned_source_and_official_answer_book",
                    "authorization_event_id": authorization_event_id,
                    "method": "independently derived and exact-rationally verified for the Indonesian edition",
                    "target_edition_id": TARGET_EDITION_ID,
                },
                "provenance_kind": "indonesian_edition_supplied",
                "resource_id": RESOURCE_ID,
                "rights_id": unit_by_id[unit_id]["rights_id"],
                "source_language": None,
                "source_locator": None,
                "source_sha256": None,
                "source_text": None,
                "source_unit_id": None,
                "target_end_line": line_at(
                    target_text, max(target_start, target_end - 1)
                ),
                "target_language": "id",
                "target_edition_id": TARGET_EDITION_ID,
                "target_locale": "id-ID",
                "target_locator": locator(
                    target_relative, target_text, target_start, target_end
                ),
                "target_sha256": sha256_bytes(target_value.encode("utf-8")),
                "target_start_line": line_at(target_text, target_start),
                "target_text": target_value,
                "target_variant": {
                    "edition_id": TARGET_EDITION_ID,
                    "end_line": line_at(
                        target_text, max(target_start, target_end - 1)
                    ),
                    "language": "id",
                    "locale": "id-ID",
                    "locator": locator(
                        target_relative, target_text, target_start, target_end
                    ),
                    "sha256": sha256_bytes(target_value.encode("utf-8")),
                    "start_line": line_at(target_text, target_start),
                    "text": target_value,
                },
                "translation_state": "mathematically_reviewed",
            }
        )
        segment_records.append(segment)
        unit_by_id[unit_id].setdefault("segment_ids", []).append(segment_id)
        add_relation(
            "contains", unit_id, segment_id, 1, segment["target_locator"]
        )
        return segment_id

    for component, root, work_kind, root_order in ROOT_SPECS:
        unit_id = work_unit_id(component)
        rights_id = RIGHTS_LAB if component == "sage-lab" else RIGHTS_CORE
        root_record = authoritative_record(unit_id, "unit")
        root_record.update(
            unit_authority_fields(
                parent_id=COURSE_ID,
                order=root_order,
                path=[PROGRAM_ID, COURSE_ID, unit_id],
                unit_kind=work_kind,
                source_locator=root,
                source_sha256=sha256_bytes(source_file_data[root][0]),
                target_locator=root,
                target_sha256=sha256_bytes(target_file_data[root][0]),
                rights_id=rights_id,
            )
        )
        root_record.update(
            {
                "corpus_component": component,
                "source_local_id": root,
                "source_title": {
                    "main-textbook": "Linear Algebra",
                    "answer-book-shell": "Answers to Exercises",
                    "sage-lab": "Sage Linear Algebra Lab Manual",
                }[component],
                "target_title": {
                    "main-textbook": "Aljabar Linear",
                    "answer-book-shell": "Jawaban Latihan",
                    "sage-lab": "Manual Laboratorium Sage untuk Aljabar Linear",
                }[component],
            }
        )
        register_unit(root_record)

    file_order_by_component: dict[str, dict[str, int]] = {
        component: {
            relative: order
            for order, relative in enumerate(component_files[component], 1)
        }
        for component, *_ in ROOT_SPECS
    }
    for relative in all_files:
        components = file_components[relative]
        primary_component = components[0]
        source_payload, source_text = source_file_data[relative]
        target_payload, target_text = target_file_data[relative]
        unit_id = file_unit_id(relative)
        parent_id = work_unit_id(primary_component)
        rights_id = rights_for_path(relative, primary_component)
        file_record = authoritative_record(unit_id, "unit")
        file_record.update(
            unit_authority_fields(
                parent_id=parent_id,
                order=file_order_by_component[primary_component][relative],
                path=[parent_id, unit_id],
                unit_kind="source_file",
                source_locator=relative,
                source_sha256=sha256_bytes(source_payload),
                target_locator=relative,
                target_sha256=sha256_bytes(target_payload),
                rights_id=rights_id,
            )
        )
        file_record.update(
            {
                "bytes": len(source_payload),
                "corpus_components": components,
                "media_type": "application/x-tex",
                "source_local_id": relative,
                "target_bytes": len(target_payload),
                "topology_role": (
                    "entrypoint"
                    if any(relative == closure.root for closure in source_closures)
                    else "included_file"
                ),
            }
        )
        register_unit(
            file_record,
            {
                "component": primary_component,
                "relative": relative,
                "source_span": (0, len(source_text)),
                "source_text": source_text,
                "target_span": (0, len(target_text)),
                "target_text": target_text,
            },
        )
        for component in components[1:]:
            add_relation(
                "contains",
                work_unit_id(component),
                unit_id,
                file_order_by_component[component][relative],
                relative,
            )

    qa_records: list[dict] = []
    file_heading_pairs: dict[str, tuple[list[Heading], list[Heading]]] = {}
    file_environment_pairs: dict[
        str, tuple[list[EnvironmentSpan], list[EnvironmentSpan]]
    ] = {}
    heading_units_by_file: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    semantic_spans_by_file: dict[str, list[tuple[int, int, str]]] = defaultdict(list)

    for relative in all_files:
        source_text = source_file_data[relative][1]
        target_text = target_file_data[relative][1]
        source_headings = find_headings(source_text)
        target_headings = find_headings(target_text)
        source_heading_signature = [
            (heading.command, heading.kind, heading.level)
            for heading in source_headings
        ]
        target_heading_signature = [
            (heading.command, heading.kind, heading.level)
            for heading in target_headings
        ]
        if source_heading_signature != target_heading_signature:
            raise RuntimeError(
                f"{relative}: heading topology differs: "
                f"{source_heading_signature!r} != {target_heading_signature!r}"
            )
        source_environments = find_environment_spans(source_text, relative)
        target_environments = find_environment_spans(target_text, relative)
        # Exercise/answer and mathematical-semantic topology is invariant.
        # Presentation/code environments may be inserted as an explicit target
        # adaptation (for example a correction that supplies runnable code),
        # and are indexed below without pretending that they existed upstream.
        tracked_names = {
            "corollary",
            "counterexample",
            "definition",
            "example",
            "exercises",
            "figure",
            "lemma",
            "proof",
            "remark",
            "theorem",
        }
        source_env_signature = [
            span.name for span in source_environments if span.name in tracked_names
        ]
        target_env_signature = [
            span.name for span in target_environments if span.name in tracked_names
        ]
        if source_env_signature != target_env_signature:
            raise RuntimeError(
                f"{relative}: semantic environment topology differs"
            )
        source_answer_count = sum(
            span.name == "answer" for span in source_environments
        )
        target_answer_count = sum(
            span.name == "answer" for span in target_environments
        )
        expected_target_additions = sum(
            spec_relative == relative
            for spec_relative, _group_order, _item_order
            in TARGET_SUPPLIED_ANSWER_SPECS
        )
        if target_answer_count != source_answer_count + expected_target_additions:
            raise RuntimeError(
                f"{relative}: answer environment topology differs outside the "
                "authorized target-supplied closure"
            )
        source_labels = [label for _, label in label_matches(source_text)]
        target_labels = [label for _, label in label_matches(target_text)]
        if source_labels != target_labels:
            raise RuntimeError(f"{relative}: active LaTeX labels differ")
        file_heading_pairs[relative] = (source_headings, target_headings)
        file_environment_pairs[relative] = (
            source_environments,
            target_environments,
        )
        qa_id = f"{file_unit_id(relative)}.qa.structure.001.locale.id-id"
        qa = authoritative_record(qa_id, "qa_event")
        qa.update(
            {
                "qa_type": "source_topology",
                "result": "pass",
                "rights_id": rights_for_path(
                    relative, file_components[relative][0]
                ),
                "source_locator": relative,
                "translation_state": "structurally_verified",
                "unit_ids": [file_unit_id(relative)],
                "witness": {
                    "active_label_count": len(source_labels),
                    "answer_environment_count": source_env_signature.count(
                        "answer"
                    ),
                    "exercise_environment_count": source_env_signature.count(
                        "exercises"
                    ),
                    "heading_count": len(source_headings),
                    "semantic_environment_count": len(source_env_signature),
                    "source_file_sha256": sha256_bytes(
                        source_file_data[relative][0]
                    ),
                    "target_file_sha256": sha256_bytes(
                        target_file_data[relative][0]
                    ),
                },
            }
        )
        qa_records.append(qa)

    heading_global_order: dict[str, int] = defaultdict(int)
    for component, *_ in ROOT_SPECS:
        hierarchy_stack: list[tuple[int, str]] = []
        for relative in component_files[component]:
            if file_components[relative][0] != component:
                continue
            source_text = source_file_data[relative][1]
            target_text = target_file_data[relative][1]
            source_headings, target_headings = file_heading_pairs[relative]
            file_id = file_unit_id(relative)
            if not source_headings:
                register_segment(
                    file_id,
                    relative,
                    relative,
                    source_text,
                    target_text,
                    0,
                    len(source_text),
                    0,
                    len(target_text),
                    "complete-file-reader-surface",
                )
                continue
            if source_headings[0].start > 0 or target_headings[0].start > 0:
                register_segment(
                    file_id,
                    relative,
                    relative,
                    source_text,
                    target_text,
                    0,
                    source_headings[0].start,
                    0,
                    target_headings[0].start,
                    "file-preamble",
                )
            for index, (source_heading, target_heading) in enumerate(
                zip(source_headings, target_headings), 1
            ):
                source_end = (
                    source_headings[index].start
                    if index < len(source_headings)
                    else len(source_text)
                )
                target_end = (
                    target_headings[index].start
                    if index < len(target_headings)
                    else len(target_text)
                )
                lookahead_end = min(source_end, source_heading.command_end + 300)
                native_labels = labels_in(
                    source_text, source_heading.start, lookahead_end
                )
                target_native_labels = labels_in(
                    target_text,
                    target_heading.start,
                    min(target_end, target_heading.command_end + 300),
                )
                if native_labels != target_native_labels:
                    raise RuntimeError(
                        f"{relative}: heading label drift at heading {index}"
                    )
                native_label = native_labels[0] if native_labels else None
                unit_id = stable_node_id(
                    file_id, source_heading.kind, index, native_label
                )
                while hierarchy_stack and hierarchy_stack[-1][0] >= source_heading.level:
                    hierarchy_stack.pop()
                parent_id = (
                    hierarchy_stack[-1][1]
                    if hierarchy_stack
                    else work_unit_id(component)
                )
                heading_global_order[parent_id] += 1
                parent_path = unit_by_id[parent_id]["path"]
                record = authoritative_record(unit_id, "unit")
                record.update(
                    unit_authority_fields(
                        parent_id=parent_id,
                        order=heading_global_order[parent_id],
                        path=[*parent_path, unit_id],
                        unit_kind=source_heading.kind,
                        source_locator=locator(
                            relative,
                            source_text,
                            source_heading.start,
                            source_end,
                        ),
                        source_sha256=sha256_bytes(
                            source_text[
                                source_heading.start : source_end
                            ].encode("utf-8")
                        ),
                        target_locator=locator(
                            relative,
                            target_text,
                            target_heading.start,
                            target_end,
                        ),
                        target_sha256=sha256_bytes(
                            target_text[
                                target_heading.start : target_end
                            ].encode("utf-8")
                        ),
                        rights_id=rights_for_path(relative, component),
                    )
                )
                record.update(
                    {
                        "heading_command": source_heading.command,
                        "source_file_unit_id": file_id,
                        "source_local_id": (
                            native_label
                            or f"{relative}#heading-source-order-{index:04d}"
                        ),
                        "source_labels": native_labels,
                        "source_title": clean_title(source_heading.title),
                        "target_title": clean_title(target_heading.title),
                    }
                )
                register_unit(
                    record,
                    {
                        "component": component,
                        "relative": relative,
                        "source_span": (source_heading.start, source_end),
                        "source_text": source_text[
                            source_heading.start : source_end
                        ],
                        "target_span": (target_heading.start, target_end),
                        "target_text": target_text[
                            target_heading.start : target_end
                        ],
                    },
                )
                register_segment(
                    unit_id,
                    relative,
                    relative,
                    source_text,
                    target_text,
                    source_heading.start,
                    source_end,
                    target_heading.start,
                    target_end,
                    "heading-and-following-reader-block",
                )
                heading_units_by_file[relative].append(
                    (source_heading.start, source_end, unit_id)
                )
                semantic_spans_by_file[relative].append(
                    (source_heading.start, source_end, unit_id)
                )
                hierarchy_stack.append((source_heading.level, unit_id))

    def nearest_heading_or_file(relative: str, offset: int) -> str:
        candidates = [
            (end - start, unit_id)
            for start, end, unit_id in heading_units_by_file[relative]
            if start <= offset < end
        ]
        return min(candidates)[1] if candidates else file_unit_id(relative)

    semantic_order_by_parent: dict[str, int] = defaultdict(int)
    generic_environment_count = 0
    for relative in all_files:
        source_text = source_file_data[relative][1]
        target_text = target_file_data[relative][1]
        source_envs, target_envs = file_environment_pairs[relative]
        source_by_name = {
            name: [span for span in source_envs if span.name == name]
            for name in SEMANTIC_ENVIRONMENTS
        }
        target_by_name = {
            name: [span for span in target_envs if span.name == name]
            for name in SEMANTIC_ENVIRONMENTS
        }
        paired_environments: list[tuple[EnvironmentSpan, EnvironmentSpan]] = []
        target_only_environments: list[tuple[str, int, EnvironmentSpan]] = []
        source_only_environments: list[tuple[str, int, EnvironmentSpan]] = []
        for name in SEMANTIC_ENVIRONMENTS:
            source_named = source_by_name[name]
            target_named = target_by_name[name]
            paired_count = min(len(source_named), len(target_named))
            paired_environments.extend(
                zip(source_named[:paired_count], target_named[:paired_count])
            )
            source_only_environments.extend(
                (name, ordinal, span)
                for ordinal, span in enumerate(
                    source_named[paired_count:], paired_count + 1
                )
            )
            target_only_environments.extend(
                (name, ordinal, span)
                for ordinal, span in enumerate(
                    target_named[paired_count:], paired_count + 1
                )
            )
        paired_environments.sort(key=lambda pair: pair[0].open_start)
        per_kind_ordinal: dict[str, int] = defaultdict(int)
        for source_span, target_span in paired_environments:
            kind = SEMANTIC_ENVIRONMENTS[source_span.name]
            per_kind_ordinal[source_span.name] += 1
            ordinal = per_kind_ordinal[source_span.name]
            source_labels = labels_in(
                source_text, source_span.open_start, source_span.close_end
            )
            target_labels = labels_in(
                target_text, target_span.open_start, target_span.close_end
            )
            if source_labels != target_labels:
                raise RuntimeError(
                    f"{relative}: labels differ in {source_span.name} {ordinal}"
                )
            native_label = source_labels[0] if source_labels else None
            file_id = file_unit_id(relative)
            unit_id = stable_node_id(
                file_id, source_span.name, ordinal, native_label
            )
            parent_id = nearest_heading_or_file(relative, source_span.open_start)
            semantic_order_by_parent[parent_id] += 1
            record = authoritative_record(unit_id, "unit")
            source_value = source_text[
                source_span.open_start : source_span.close_end
            ]
            target_value = target_text[
                target_span.open_start : target_span.close_end
            ]
            record.update(
                unit_authority_fields(
                    parent_id=parent_id,
                    order=semantic_order_by_parent[parent_id],
                    path=[*unit_by_id[parent_id]["path"], unit_id],
                    unit_kind=kind,
                    source_locator=locator(
                        relative,
                        source_text,
                        source_span.open_start,
                        source_span.close_end,
                    ),
                    source_sha256=sha256_bytes(source_value.encode("utf-8")),
                    target_locator=locator(
                        relative,
                        target_text,
                        target_span.open_start,
                        target_span.close_end,
                    ),
                    target_sha256=sha256_bytes(target_value.encode("utf-8")),
                    rights_id=rights_for_path(
                        relative, file_components[relative][0]
                    ),
                )
            )
            record.update(
                {
                    "native_kind": source_span.name,
                    "source_file_unit_id": file_id,
                    "source_labels": source_labels,
                    "source_local_id": (
                        native_label
                        or f"{relative}#{source_span.name}-source-order-{ordinal:04d}"
                    ),
                }
            )
            register_unit(
                record,
                {
                    "component": file_components[relative][0],
                    "relative": relative,
                    "source_span": (
                        source_span.open_start,
                        source_span.close_end,
                    ),
                    "source_text": source_value,
                    "target_span": (
                        target_span.open_start,
                        target_span.close_end,
                    ),
                    "target_text": target_value,
                },
            )
            register_segment(
                unit_id,
                relative,
                relative,
                source_text,
                target_text,
                source_span.open_start,
                source_span.close_end,
                target_span.open_start,
                target_span.close_end,
                f"native-{source_span.name}-environment",
            )
            semantic_spans_by_file[relative].append(
                (source_span.open_start, source_span.close_end, unit_id)
            )
            generic_environment_count += 1

        for side, extras in (
            ("source", source_only_environments),
            ("target", target_only_environments),
        ):
            for name, ordinal, span in extras:
                kind = SEMANTIC_ENVIRONMENTS[name]
                unit_id = (
                    f"{file_unit_id(relative)}.{id_token(name)}."
                    f"{side}-only.source-order.{ordinal:04d}"
                )
                parent_id = file_unit_id(relative)
                semantic_order_by_parent[parent_id] += 1
                record = authoritative_record(unit_id, "unit")
                source_value = (
                    source_text[span.open_start : span.close_end]
                    if side == "source"
                    else ""
                )
                target_value = (
                    target_text[span.open_start : span.close_end]
                    if side == "target"
                    else ""
                )
                record.update(
                    unit_authority_fields(
                        parent_id=parent_id,
                        order=semantic_order_by_parent[parent_id],
                        path=[*unit_by_id[parent_id]["path"], unit_id],
                        unit_kind=kind,
                        source_locator=(
                            locator(
                                relative,
                                source_text,
                                span.open_start,
                                span.close_end,
                            )
                            if side == "source"
                            else f"{relative}#target-only-{name}-{ordinal:04d}"
                        ),
                        source_sha256=sha256_bytes(source_value.encode("utf-8")),
                        target_locator=(
                            locator(
                                relative,
                                target_text,
                                span.open_start,
                                span.close_end,
                            )
                            if side == "target"
                            else f"{relative}#source-only-{name}-{ordinal:04d}"
                        ),
                        target_sha256=sha256_bytes(target_value.encode("utf-8")),
                        rights_id=rights_for_path(
                            relative, file_components[relative][0]
                        ),
                        translation_state=(
                            "translated" if side == "target" else "source_frozen"
                        ),
                    )
                )
                record.update(
                    {
                        "adaptation_status": f"{side}_only_semantic_environment",
                        "native_kind": name,
                        "source_file_unit_id": file_unit_id(relative),
                        "source_local_id": (
                            f"{relative}#{side}-only-{name}-{ordinal:04d}"
                        ),
                    }
                )
                register_unit(
                    record,
                    {
                        "component": file_components[relative][0],
                        "relative": relative,
                        "source_span": (
                            (span.open_start, span.close_end)
                            if side == "source"
                            else (0, 0)
                        ),
                        "source_text": source_value,
                        "target_span": (
                            (span.open_start, span.close_end)
                            if side == "target"
                            else (0, 0)
                        ),
                        "target_text": target_value,
                    },
                )
                if side == "target":
                    register_segment(
                        unit_id,
                        relative,
                        relative,
                        source_text,
                        target_text,
                        0,
                        0,
                        span.open_start,
                        span.close_end,
                        "explicit-target-only-adaptation",
                    )
                else:
                    register_segment(
                        unit_id,
                        relative,
                        relative,
                        source_text,
                        target_text,
                        span.open_start,
                        span.close_end,
                        0,
                        0,
                        "explicit-source-only-surface",
                    )
                semantic_spans_by_file[relative].append(
                    (span.open_start, span.close_end, unit_id)
                )
                add_relation(
                    "adapts",
                    unit_id,
                    parent_id,
                    ordinal,
                    record["source_locator"],
                )
                generic_environment_count += 1

    exercise_ids: list[str] = []
    answer_ids: list[str] = []
    native_answer_ids: list[str] = []
    target_supplied_answer_ids: list[str] = []
    unanswered_exercise_ids: list[str] = []
    upstream_answer_gap_ids: list[str] = []
    used_source_answer_offsets: set[tuple[str, int]] = set()
    exercise_group_count = 0
    for relative in all_files:
        source_text = source_file_data[relative][1]
        target_text = target_file_data[relative][1]
        source_envs, target_envs = file_environment_pairs[relative]
        source_groups = [span for span in source_envs if span.name == "exercises"]
        target_groups = [span for span in target_envs if span.name == "exercises"]
        source_answers = [span for span in source_envs if span.name == "answer"]
        target_answers = [span for span in target_envs if span.name == "answer"]
        if len(source_groups) != len(target_groups):
            raise RuntimeError(f"{relative}: exercise group count differs")
        for group_order, (source_group, target_group) in enumerate(
            zip(source_groups, target_groups), 1
        ):
            source_items = top_level_item_starts(source_text, source_group)
            target_items = top_level_item_starts(target_text, target_group)
            if len(source_items) != len(target_items):
                raise RuntimeError(
                    f"{relative}: exercise item count differs in group {group_order}"
                )
            source_item_ends = [
                source_items[index + 1]
                if index + 1 < len(source_items)
                else source_group.close_start
                for index in range(len(source_items))
            ]
            target_item_ends = [
                target_items[index + 1]
                if index + 1 < len(target_items)
                else target_group.close_start
                for index in range(len(target_items))
            ]
            source_header_flags = [
                is_unnumbered_item_header(source_text, start, end)
                for start, end in zip(source_items, source_item_ends)
            ]
            target_header_flags = [
                is_unnumbered_item_header(target_text, start, end)
                for start, end in zip(target_items, target_item_ends)
            ]
            if source_header_flags != target_header_flags:
                raise RuntimeError(
                    f"{relative}: exercise rubric/header topology differs in "
                    f"group {group_order}"
                )
            group_id = (
                f"{file_unit_id(relative)}.exercise-group."
                f"source-order.{group_order:04d}"
            )
            group_parent = nearest_heading_or_file(
                relative, source_group.open_start
            )
            semantic_order_by_parent[group_parent] += 1
            group = authoritative_record(group_id, "unit")
            group.update(
                unit_authority_fields(
                    parent_id=group_parent,
                    order=semantic_order_by_parent[group_parent],
                    path=[*unit_by_id[group_parent]["path"], group_id],
                    unit_kind="exercise_group",
                    source_locator=locator(
                        relative,
                        source_text,
                        source_group.open_start,
                        source_group.close_end,
                    ),
                    source_sha256=sha256_bytes(
                        source_text[
                            source_group.open_start : source_group.close_end
                        ].encode("utf-8")
                    ),
                    target_locator=locator(
                        relative,
                        target_text,
                        target_group.open_start,
                        target_group.close_end,
                    ),
                    target_sha256=sha256_bytes(
                        target_text[
                            target_group.open_start : target_group.close_end
                        ].encode("utf-8")
                    ),
                    rights_id=rights_for_path(
                        relative, file_components[relative][0]
                    ),
                )
            )
            group.update(
                {
                    "exercise_count": sum(
                        not is_header for is_header in source_header_flags
                    ),
                    "item_count_including_rubrics": len(source_items),
                    "source_file_unit_id": file_unit_id(relative),
                    "source_local_id": (
                        f"{relative}#exercise-group-source-order-{group_order:04d}"
                    ),
                }
            )
            register_unit(
                group,
                {
                    "component": file_components[relative][0],
                    "relative": relative,
                    "source_span": (
                        source_group.open_start,
                        source_group.close_end,
                    ),
                    "source_text": source_text[
                        source_group.open_start : source_group.close_end
                    ],
                    "target_span": (
                        target_group.open_start,
                        target_group.close_end,
                    ),
                    "target_text": target_text[
                        target_group.open_start : target_group.close_end
                    ],
                },
            )
            register_segment(
                group_id,
                relative,
                relative,
                source_text,
                target_text,
                source_group.open_start,
                source_group.close_end,
                target_group.open_start,
                target_group.close_end,
                "native-exercises-environment",
            )
            semantic_spans_by_file[relative].append(
                (source_group.open_start, source_group.close_end, group_id)
            )
            exercise_group_count += 1
            for item_order, (source_start, target_start) in enumerate(
                zip(source_items, target_items), 1
            ):
                source_end = (
                    source_items[item_order]
                    if item_order < len(source_items)
                    else source_group.close_start
                )
                target_end = (
                    target_items[item_order]
                    if item_order < len(target_items)
                    else target_group.close_start
                )
                item_source_answers = [
                    span
                    for span in source_answers
                    if source_start <= span.open_start
                    and span.close_end <= source_end
                ]
                item_target_answers = [
                    span
                    for span in target_answers
                    if target_start <= span.open_start
                    and span.close_end <= target_end
                ]
                supplied_spec = TARGET_SUPPLIED_ANSWER_SPECS.get(
                    (relative, group_order, item_order)
                )
                is_target_supplied = (
                    supplied_spec is not None
                    and not item_source_answers
                    and len(item_target_answers) == 1
                )
                if len(item_source_answers) != len(item_target_answers) and not is_target_supplied:
                    raise RuntimeError(
                        f"{relative}: inline answer count differs in exercise "
                        f"{group_order}.{item_order}"
                    )
                if supplied_spec is not None and not is_target_supplied:
                    raise RuntimeError(
                        f"{relative}: authorized target-supplied answer topology is "
                        f"invalid in exercise {group_order}.{item_order}"
                    )
                prompt_end = (
                    item_source_answers[0].open_start
                    if item_source_answers
                    else source_end
                )
                target_prompt_end = (
                    item_target_answers[0].open_start
                    if item_target_answers
                    else target_end
                )
                source_labels = labels_in(source_text, source_start, prompt_end)
                target_labels = labels_in(
                    target_text, target_start, target_prompt_end
                )
                if source_labels != target_labels:
                    raise RuntimeError(
                        f"{relative}: exercise label drift in "
                        f"{group_order}.{item_order}"
                    )
                native_label = source_labels[0] if source_labels else None
                is_header = source_header_flags[item_order - 1]
                item_kind = "exercise_note" if is_header else "exercise"
                exercise_id = stable_node_id(
                    file_unit_id(relative),
                    item_kind,
                    group_order * 10000 + item_order,
                    native_label,
                )
                exercise = authoritative_record(exercise_id, "unit")
                source_item_value = source_text[source_start:source_end]
                unit_target_end = target_prompt_end if is_target_supplied else target_end
                target_item_value = target_text[target_start:unit_target_end]
                exercise.update(
                    unit_authority_fields(
                        parent_id=group_id,
                        order=item_order,
                        path=[*unit_by_id[group_id]["path"], exercise_id],
                        unit_kind=item_kind,
                        source_locator=locator(
                            relative, source_text, source_start, source_end
                        ),
                        source_sha256=sha256_bytes(
                            source_item_value.encode("utf-8")
                        ),
                        target_locator=locator(
                            relative, target_text, target_start, unit_target_end
                        ),
                        target_sha256=sha256_bytes(
                            target_item_value.encode("utf-8")
                        ),
                        rights_id=rights_for_path(
                            relative, file_components[relative][0]
                        ),
                    )
                )
                exercise.update(
                    {
                        "answer_count": len(item_source_answers) + int(is_target_supplied),
                        "answer_status": (
                            "not_applicable_to_unnumbered_rubric"
                            if is_header
                            else
                            "linked_target_supplied"
                            if is_target_supplied
                            else
                            "linked"
                            if item_source_answers
                            else "no_inline_answer_in_authority"
                        ),
                        "native_upstream_answer_count": len(item_source_answers),
                        "target_supplied_answer_count": int(is_target_supplied),
                        "exercise_environment_order": group_order,
                        "exercise_order": item_order,
                        "native_kind": (
                            "latex_unnumbered_exercise_rubric"
                            if is_header
                            else "latex_exercise_item"
                        ),
                        "source_file_unit_id": file_unit_id(relative),
                        "source_labels": source_labels,
                        "source_local_id": (
                            native_label
                            or f"{relative}#exercise-{group_order:04d}-{item_order:04d}"
                        ),
                    }
                )
                register_unit(
                    exercise,
                    {
                        "component": file_components[relative][0],
                        "relative": relative,
                        "source_span": (source_start, source_end),
                        "source_text": source_item_value,
                        "target_span": (target_start, target_end),
                        "target_text": target_item_value,
                    },
                )
                register_segment(
                    exercise_id,
                    relative,
                    relative,
                    source_text,
                    target_text,
                    source_start,
                    source_end,
                    target_start,
                    unit_target_end,
                    (
                        "native-exercise-item-prompt-with-target-supplied-answer-excluded"
                        if is_target_supplied
                        else "complete-native-exercise-item-with-inline-answer"
                    ),
                )
                semantic_spans_by_file[relative].append(
                    (source_start, source_end, exercise_id)
                )
                if not is_header:
                    exercise_ids.append(exercise_id)
                if not is_header and not item_source_answers:
                    upstream_answer_gap_ids.append(exercise_id)
                if not is_header and not item_source_answers and not is_target_supplied:
                    unanswered_exercise_ids.append(exercise_id)
                for answer_order, (
                    source_answer,
                    target_answer,
                ) in enumerate(
                    zip(item_source_answers, item_target_answers), 1
                ):
                    answer_id = (
                        f"{exercise_id}.answer.source-order.{answer_order:03d}"
                    )
                    source_answer_value = source_text[
                        source_answer.open_start : source_answer.close_end
                    ]
                    target_answer_value = target_text[
                        target_answer.open_start : target_answer.close_end
                    ]
                    answer = authoritative_record(answer_id, "unit")
                    answer.update(
                        unit_authority_fields(
                            parent_id=exercise_id,
                            order=answer_order,
                            path=[
                                *unit_by_id[exercise_id]["path"],
                                answer_id,
                            ],
                            unit_kind="answer",
                            source_locator=locator(
                                relative,
                                source_text,
                                source_answer.open_start,
                                source_answer.close_end,
                            ),
                            source_sha256=sha256_bytes(
                                source_answer_value.encode("utf-8")
                            ),
                            target_locator=locator(
                                relative,
                                target_text,
                                target_answer.open_start,
                                target_answer.close_end,
                            ),
                            target_sha256=sha256_bytes(
                                target_answer_value.encode("utf-8")
                            ),
                            rights_id=rights_for_path(
                                relative, file_components[relative][0]
                            ),
                        )
                    )
                    answer.update(
                        {
                            "answers_unit_id": exercise_id,
                            "exercise_environment_order": group_order,
                            "exercise_order": item_order,
                            "native_kind": "latex_answer_environment",
                            "source_file_unit_id": file_unit_id(relative),
                            "source_local_id": (
                                f"{exercise['source_local_id']}#answer-{answer_order:03d}"
                            ),
                        }
                    )
                    register_unit(
                        answer,
                        {
                            "component": file_components[relative][0],
                            "relative": relative,
                            "source_span": (
                                source_answer.open_start,
                                source_answer.close_end,
                            ),
                            "source_text": source_answer_value,
                            "target_span": (
                                target_answer.open_start,
                                target_answer.close_end,
                            ),
                            "target_text": target_answer_value,
                        },
                    )
                    register_segment(
                        answer_id,
                        relative,
                        relative,
                        source_text,
                        target_text,
                        source_answer.open_start,
                        source_answer.close_end,
                        target_answer.open_start,
                        target_answer.close_end,
                        "native-inline-answer",
                    )
                    semantic_spans_by_file[relative].append(
                        (
                            source_answer.open_start,
                            source_answer.close_end,
                            answer_id,
                        )
                    )
                    add_relation(
                        "answers",
                        answer_id,
                        exercise_id,
                        answer_order,
                        answer["source_locator"],
                    )
                    answer_ids.append(answer_id)
                    native_answer_ids.append(answer_id)
                    used_source_answer_offsets.add(
                        (relative, source_answer.open_start)
                    )

                if is_target_supplied:
                    assert supplied_spec is not None
                    target_answer = item_target_answers[0]
                    authority_answer_anchor = supplied_spec[
                        "authority_answer_anchor"
                    ]
                    authorization_event_id = supplied_spec[
                        "authorization_event_id"
                    ]
                    ledger_row, _ledger_record = correction_row_by_id[
                        authorization_event_id
                    ]
                    answer_id = (
                        f"{RESOURCE_ID}.unit.answer."
                        f"{id_token(authority_answer_anchor)}.locale.id-id"
                    )
                    target_answer_value = target_text[
                        target_answer.open_start : target_answer.close_end
                    ]
                    target_answer_locator = locator(
                        relative,
                        target_text,
                        target_answer.open_start,
                        target_answer.close_end,
                    )
                    answer = base_record(answer_id, "unit")
                    answer.update(
                        {
                            "answer_link_status": "linked_target_supplied",
                            "answers_unit_id": exercise_id,
                            "authority_answer_anchor": authority_answer_anchor,
                            "authority_answer_status": "absent_from_pinned_source_and_official_answer_book",
                            "authority_exercise_locator": exercise[
                                "source_locator"
                            ],
                            "authority_exercise_sha256": exercise[
                                "source_sha256"
                            ],
                            "authority_exercise_unit_id": exercise_id,
                            "authorization_correction_id": (
                                f"{RESOURCE_ID}.correction."
                                f"{authorization_event_id.lower()}.locale.id-id"
                            ),
                            "authorization_event_id": authorization_event_id,
                            "authorization_ledger_locator": (
                                f"00_control/ADVERSE_LEDGER.csv#row-{ledger_row}"
                            ),
                            "authorization_ledger_sha256": correction_sha,
                            "concept_ids": [],
                            "derivative_kind": "target_supplied_answer",
                            "edition_id": TARGET_EDITION_ID,
                            "exercise_environment_order": group_order,
                            "exercise_order": item_order,
                            "language": "id",
                            "locale": "id-ID",
                            "order": 1,
                            "parent_id": exercise_id,
                            "path": [
                                *unit_by_id[exercise_id]["path"],
                                answer_id,
                            ],
                            "prerequisite_ids": [],
                            "prerequisite_status": "not asserted without curated evidence",
                            "provenance_kind": "indonesian_edition_supplied",
                            "resource_id": RESOURCE_ID,
                            "rights_id": rights_for_path(
                                relative, file_components[relative][0]
                            ),
                            "source_language": None,
                            "source_locator": None,
                            "source_sha256": None,
                            "target_edition_id": TARGET_EDITION_ID,
                            "target_language": "id",
                            "target_locale": "id-ID",
                            "target_local_id": authority_answer_anchor,
                            "target_locator": target_answer_locator,
                            "target_sha256": sha256_bytes(
                                target_answer_value.encode("utf-8")
                            ),
                            "target_variant": {
                                "edition_id": TARGET_EDITION_ID,
                                "language": "id",
                                "locale": "id-ID",
                                "locator": target_answer_locator,
                                "sha256": sha256_bytes(
                                    target_answer_value.encode("utf-8")
                                ),
                            },
                            "translation_state": "mathematically_reviewed",
                            "unit_kind": "answer",
                        }
                    )
                    register_unit(
                        answer,
                        {
                            "component": file_components[relative][0],
                            "relative": relative,
                            "source_span": (0, 0),
                            "source_text": "",
                            "target_span": (
                                target_answer.open_start,
                                target_answer.close_end,
                            ),
                            "target_text": target_answer_value,
                        },
                    )
                    register_target_supplied_answer_segment(
                        answer_id,
                        exercise_id,
                        exercise["source_locator"],
                        relative,
                        target_text,
                        target_answer.open_start,
                        target_answer.close_end,
                        authority_answer_anchor,
                        authorization_event_id,
                    )
                    add_relation(
                        "answers",
                        answer_id,
                        exercise_id,
                        1,
                        answer["authorization_ledger_locator"],
                    )
                    answer_ids.append(answer_id)
                    target_supplied_answer_ids.append(answer_id)

        orphan_source_answers = [
            span
            for span in source_answers
            if (relative, span.open_start) not in used_source_answer_offsets
        ]
        orphan_target_answers = [
            span
            for span in target_answers
            if not any(
                target_start <= span.open_start and span.close_end <= target_end
                for target_group in target_groups
                for target_start, target_end in [
                    (target_group.open_start, target_group.close_end)
                ]
            )
        ]
        if len(orphan_source_answers) != len(orphan_target_answers):
            raise RuntimeError(f"{relative}: orphan answer topology differs")
        for orphan_order, (source_answer, target_answer) in enumerate(
            zip(orphan_source_answers, orphan_target_answers), 1
        ):
            parent_id = nearest_heading_or_file(
                relative, source_answer.open_start
            )
            answer_id = (
                f"{file_unit_id(relative)}.answer.unlinked."
                f"source-order.{orphan_order:04d}"
            )
            semantic_order_by_parent[parent_id] += 1
            answer = authoritative_record(answer_id, "unit")
            source_value = source_text[
                source_answer.open_start : source_answer.close_end
            ]
            target_value = target_text[
                target_answer.open_start : target_answer.close_end
            ]
            answer.update(
                unit_authority_fields(
                    parent_id=parent_id,
                    order=semantic_order_by_parent[parent_id],
                    path=[*unit_by_id[parent_id]["path"], answer_id],
                    unit_kind="answer",
                    source_locator=locator(
                        relative,
                        source_text,
                        source_answer.open_start,
                        source_answer.close_end,
                    ),
                    source_sha256=sha256_bytes(source_value.encode("utf-8")),
                    target_locator=locator(
                        relative,
                        target_text,
                        target_answer.open_start,
                        target_answer.close_end,
                    ),
                    target_sha256=sha256_bytes(target_value.encode("utf-8")),
                    rights_id=rights_for_path(
                        relative, file_components[relative][0]
                    ),
                )
            )
            answer.update(
                {
                    "answer_link_status": "not enclosed by a top-level exercise item",
                    "native_kind": "latex_answer_environment",
                    "source_file_unit_id": file_unit_id(relative),
                    "source_local_id": (
                        f"{relative}#orphan-answer-source-order-{orphan_order:04d}"
                    ),
                }
            )
            register_unit(
                answer,
                {
                    "component": file_components[relative][0],
                    "relative": relative,
                    "source_span": (
                        source_answer.open_start,
                        source_answer.close_end,
                    ),
                    "source_text": source_value,
                    "target_span": (
                        target_answer.open_start,
                        target_answer.close_end,
                    ),
                    "target_text": target_value,
                },
            )
            register_segment(
                answer_id,
                relative,
                relative,
                source_text,
                target_text,
                source_answer.open_start,
                source_answer.close_end,
                target_answer.open_start,
                target_answer.close_end,
                "native-unlinked-inline-answer",
            )
            semantic_spans_by_file[relative].append(
                (source_answer.open_start, source_answer.close_end, answer_id)
            )
            answer_ids.append(answer_id)
            native_answer_ids.append(answer_id)

    if len(native_answer_ids) != NATIVE_UPSTREAM_ANSWER_COUNT:
        raise RuntimeError(
            "native upstream answer count changed: "
            f"expected {NATIVE_UPSTREAM_ANSWER_COUNT}, got {len(native_answer_ids)}"
        )
    if len(target_supplied_answer_ids) != len(TARGET_SUPPLIED_ANSWER_SPECS):
        raise RuntimeError(
            "authorized target-supplied answer count changed: "
            f"expected {len(TARGET_SUPPLIED_ANSWER_SPECS)}, "
            f"got {len(target_supplied_answer_ids)}"
        )

    terminology_records: list[dict] = []
    concept_records: list[dict] = []
    concept_terms: list[tuple[str, str]] = []
    term_record_by_concept: dict[str, dict] = {}
    for row_number, row in enumerate(terminology_rows, 2):
        local_id = row["term_id"].strip()
        term_id = f"{RESOURCE_ID}.term.{local_id.lower()}.locale.id-id"
        concept_id = f"{RESOURCE_ID}.concept.term-ledger.{local_id.lower()}"
        term = authoritative_record(term_id, "term")
        term.update(
            {
                "evidence": row["evidence"],
                "examples": [],
                "language": "id",
                "ledger_status": row["status"],
                "locale": "id-ID",
                "notes": row["notes"],
                "preferred": row["preferred_id"],
                "register": None,
                "rejected": split_semicolon(row["rejected"]),
                "rights_id": RIGHTS_CORE,
                "scope": row["scope"],
                "source_locator": f"00_control/TERMINOLOGY.csv#row-{row_number}",
                "source_ledger_row": row_number,
                "source_ledger_sha256": terminology_sha,
                "source_local_id": local_id,
                "source_sha256": terminology_sha,
                "source_term": row["english"],
                "target_edition_id": TARGET_EDITION_ID,
                "translation_state": "translated",
                "variants": split_semicolon(row["variants"]),
            }
        )
        terminology_records.append(term)
        term_record_by_concept[concept_id] = term
        concept = authoritative_record(concept_id, "concept")
        concept.update(
            {
                "canonical_source_term": row["english"],
                "language": None,
                "locale": None,
                "prerequisite_ids": [],
                "prerequisite_status": "not asserted without curated evidence",
                "rights_id": RIGHTS_CORE,
                "source_locator": f"00_control/TERMINOLOGY.csv#row-{row_number}",
                "source_sha256": terminology_sha,
                "source_local_id": local_id,
                "source_local_id_kind": "stable_terminology_ledger_id",
                "target_term_ids": [term_id],
                "translation_state": None,
                "translation_state_status": "locale-neutral semantic identity",
            }
        )
        concept_records.append(concept)
        concept_terms.append((concept_id, row["english"]))
        add_relation("translates", concept_id, term_id, 1, row["evidence"])

    concept_patterns = [
        (
            concept_id,
            re.compile(
                r"(?<![A-Za-z])"
                + re.escape(source_term).replace(r"\ ", r"\s+")
                + r"(?![A-Za-z])",
                re.IGNORECASE,
            ),
        )
        for concept_id, source_term in concept_terms
        if source_term.strip()
    ]
    def excerpt(text: str, start: int, end: int, radius: int = 120) -> str:
        value = text[max(0, start - radius) : min(len(text), end + radius)]
        return re.sub(r"\s+", " ", value).strip()

    for unit_id, meta in unit_meta.items():
        unit = unit_by_id[unit_id]
        if unit["unit_kind"] in {
            "source_file",
            "textbook",
            "answer_book",
            "sage_lab",
        }:
            continue
        source_text = meta["source_text"]
        matched_pairs = [
            (concept_id, match)
            for concept_id, pattern in concept_patterns
            if (match := pattern.search(source_text)) is not None
        ]
        matched = [concept_id for concept_id, _match in matched_pairs]
        unit["concept_ids"] = matched
        for concept_id, source_match in matched_pairs:
            term = term_record_by_concept[concept_id]
            if len(term["examples"]) >= 3:
                continue
            target_text = meta["target_text"]
            preferred = term["preferred"].strip()
            target_match = (
                re.search(re.escape(preferred), target_text, re.IGNORECASE)
                if preferred
                else None
            )
            term["examples"].append(
                {
                    "source_excerpt": excerpt(
                        source_text, source_match.start(), source_match.end()
                    ),
                    "source_locator": unit["source_locator"],
                    "target_excerpt": (
                        excerpt(
                            target_text,
                            target_match.start(),
                            target_match.end(),
                        )
                        if target_match is not None
                        else None
                    ),
                    "target_locator": unit["target_locator"],
                    "unit_id": unit_id,
                }
            )
        if unit["unit_kind"] == "exercise":
            for order, concept_id in enumerate(matched, 1):
                add_relation(
                    "exercises",
                    unit_id,
                    concept_id,
                    order,
                    unit["source_locator"],
                )

    for _concept_id, term in term_record_by_concept.items():
        if term["examples"]:
            continue
        term["examples"].append(
            {
                "example_kind": "terminology-ledger-evidence-fallback",
                "source_excerpt": term["evidence"],
                "source_locator": term["source_locator"],
                "target_excerpt": term["preferred"],
                "target_locator": term["source_locator"],
                "unit_id": None,
            }
        )

    def unit_for_offset(relative: str, offset: int) -> str:
        candidates = [
            (end - start, unit_id)
            for start, end, unit_id in semantic_spans_by_file[relative]
            if start <= offset < end
        ]
        return min(candidates)[1] if candidates else file_unit_id(relative)

    label_to_unit: dict[str, str] = {}
    for relative in all_files:
        source_text = source_file_data[relative][1]
        for offset, label in label_matches(source_text):
            unit_id = unit_for_offset(relative, offset)
            if label in label_to_unit and label_to_unit[label] != unit_id:
                raise RuntimeError(
                    f"duplicate active source label {label!r}: "
                    f"{label_to_unit[label]}, {unit_id}"
                )
            label_to_unit[label] = unit_id

    unresolved_label_units: dict[tuple[str, str], str] = {}
    for relative in all_files:
        source_text = source_file_data[relative][1]
        component = file_components[relative][0]
        xref_order: dict[tuple[str, str], int] = defaultdict(int)
        for offset, command, label in find_xrefs(source_text):
            origin_id = unit_for_offset(relative, offset)
            target_id = label_to_unit.get(label)
            if target_id is None:
                key = (component, label)
                target_id = unresolved_label_units.get(key)
                if target_id is None:
                    target_id = (
                        f"{RESOURCE_ID}.unit.external-label."
                        f"{short_hash(component + ':' + label)}"
                    )
                    unresolved_label_units[key] = target_id
                    parent_id = work_unit_id(component)
                    placeholder = authoritative_record(target_id, "unit")
                    placeholder.update(
                        unit_authority_fields(
                            parent_id=parent_id,
                            order=900000 + len(unresolved_label_units),
                            path=[*unit_by_id[parent_id]["path"], target_id],
                            unit_kind="external_reference",
                            source_locator=f"latex-label:{label}",
                            source_sha256=None,
                            target_locator=None,
                            target_sha256=None,
                            rights_id=(
                                RIGHTS_LAB
                                if component == "sage-lab"
                                else RIGHTS_CORE
                            ),
                            translation_state="source_frozen",
                        )
                    )
                    placeholder.update(
                        {
                            "closure_status": "label target outside admitted closure",
                            "source_local_id": label,
                        }
                    )
                    register_unit(placeholder)
            key = (origin_id, target_id)
            xref_order[key] += 1
            add_relation(
                "xref",
                origin_id,
                target_id,
                xref_order[key],
                f"{relative}#L{line_at(source_text, offset)}:{command}",
            )

    source_references: list[AssetReference] = []
    target_references: list[AssetReference] = []
    for relative in all_files:
        component = file_components[relative][0]
        source_references.extend(
            extract_asset_references(
                source_file_data[relative][1], component, relative
            )
        )
        target_references.extend(
            extract_asset_references(
                target_file_data[relative][1], component, relative
            )
        )

    resolved_source_refs: dict[AssetReference, str | None] = {
        ref: resolve_asset(AUTHORITY_ROOT, ref) for ref in source_references
    }
    resolved_target_refs: dict[AssetReference, str | None] = {
        ref: resolve_asset(TARGET_ROOT, ref) for ref in target_references
    }
    for ref, resolved in resolved_source_refs.items():
        if ref.kind == "lstinputlisting" and resolved is None:
            raise RuntimeError(
                f"required listed source missing: {ref.owner_relative}: "
                f"{ref.declared}"
            )
    for ref, resolved in resolved_target_refs.items():
        if ref.kind == "lstinputlisting" and resolved is None:
            raise RuntimeError(
                f"required target listed source missing: {ref.owner_relative}: "
                f"{ref.declared}"
            )

    supplemental_source = supplemental_asset_paths(
        AUTHORITY_ROOT, all_files
    )
    supplemental_target = supplemental_asset_paths(TARGET_ROOT, all_files)
    actual_asset_paths = {
        resolved
        for resolved in [
            *resolved_source_refs.values(),
            *resolved_target_refs.values(),
        ]
        if resolved is not None
    }
    actual_asset_paths.update(supplemental_source)
    actual_asset_paths.update(supplemental_target)
    actual_asset_paths.difference_update(all_files)

    asset_records: list[dict] = []
    asset_id_by_path: dict[str, str] = {}
    reference_origins_by_asset: dict[str, list[dict]] = defaultdict(list)

    def component_for_asset(relative: str) -> str:
        return "sage-lab" if relative.startswith("src/lab/") else "main-textbook"

    for relative in sorted(actual_asset_paths):
        source_path = AUTHORITY_ROOT / relative
        target_path = TARGET_ROOT / relative
        source_exists = source_path.is_file()
        target_exists = target_path.is_file()
        if not source_exists and not target_exists:
            raise RuntimeError(f"resolved asset disappeared: {relative}")
        component = component_for_asset(relative)
        asset_id = f"{RESOURCE_ID}.asset.file.{id_token(relative)}"
        asset_id_by_path[relative] = asset_id
        source_payload = inputs.read_bytes(source_path) if source_exists else None
        target_payload = inputs.read_bytes(target_path) if target_exists else None
        asset = authoritative_record(asset_id, "asset")
        asset.update(
            {
                "asset_kind": classify_asset(relative),
                "availability": (
                    "source_and_target"
                    if source_exists and target_exists
                    else "source_only"
                    if source_exists
                    else "target_only"
                ),
                "bytes": len(source_payload) if source_payload is not None else None,
                "corpus_component": component,
                "language": None,
                "locale": None,
                "media_type": None,
                "rights_id": rights_for_path(relative, component),
                "source_locator": relative if source_exists else None,
                "source_sha256": (
                    sha256_bytes(source_payload)
                    if source_payload is not None
                    else None
                ),
                "target_bytes": (
                    len(target_payload) if target_payload is not None else None
                ),
                "target_edition_id": (
                    TARGET_EDITION_ID if target_payload is not None else None
                ),
                "target_locator": relative if target_exists else None,
                "target_sha256": (
                    sha256_bytes(target_payload)
                    if target_payload is not None
                    else None
                ),
                "target_variant": (
                    {
                        "bytes": len(target_payload),
                        "edition_id": TARGET_EDITION_ID,
                        "language": (
                            "id"
                            if target_payload != source_payload
                            and classify_asset(relative) == "source_code"
                            else None
                        ),
                        "locale": "id-ID",
                        "locator": relative,
                        "sha256": sha256_bytes(target_payload),
                    }
                    if target_payload is not None
                    else None
                ),
                "translation_state": (
                    "source_frozen"
                    if source_payload == target_payload
                    else "structurally_verified"
                    if source_exists and target_exists
                    else "blocked"
                ),
            }
        )
        asset_records.append(asset)

    virtual_asset_id_by_key: dict[tuple[str, str, str], str] = {}
    all_reference_pairs = [
        ("source", ref, resolved)
        for ref, resolved in resolved_source_refs.items()
    ] + [
        ("target", ref, resolved)
        for ref, resolved in resolved_target_refs.items()
    ]
    for side, ref, resolved in all_reference_pairs:
        if resolved is not None:
            asset_id = asset_id_by_path[resolved]
        else:
            key = (ref.component, ref.kind, ref.declared)
            asset_id = virtual_asset_id_by_key.get(key)
            if asset_id is None:
                asset_id = (
                    f"{RESOURCE_ID}.asset.dependency."
                    f"{short_hash('|'.join(key))}"
                )
                virtual_asset_id_by_key[key] = asset_id
                external = ref.kind in {"documentclass", "usepackage"}
                virtual = authoritative_record(asset_id, "asset")
                virtual.update(
                    {
                        "asset_kind": classify_asset(
                            ref.declared, ref.kind
                        ),
                        "availability": (
                            "external_toolchain"
                            if external
                            else "build_generated_unmaterialized"
                            if ref.kind == "includegraphics"
                            else "declared_dependency_unresolved"
                        ),
                        "bytes": None,
                        "corpus_component": ref.component,
                        "declared_reference": ref.declared,
                        "language": None,
                        "locale": None,
                        "rights_id": (
                            RIGHTS_EXTERNAL if external else RIGHTS_CORE
                        ),
                        "source_locator": None,
                        "source_sha256": None,
                        "target_locator": None,
                        "target_sha256": None,
                        "target_edition_id": TARGET_EDITION_ID,
                        "target_variant": {
                            "bytes": None,
                            "declared_reference": ref.declared,
                            "edition_id": TARGET_EDITION_ID,
                            "language": None,
                            "locale": "id-ID",
                            "locator": None,
                            "sha256": None,
                        },
                        "translation_state": "source_frozen",
                    }
                )
                asset_records.append(virtual)
        origin_text = (
            source_file_data[ref.owner_relative][1]
            if side == "source"
            else target_file_data[ref.owner_relative][1]
        )
        origin_id = unit_for_offset(ref.owner_relative, ref.offset)
        origin = {
            "component": ref.component,
            "declared": ref.declared,
            "kind": ref.kind,
            "line": line_at(origin_text, ref.offset),
            "owner": ref.owner_relative,
            "side": side,
        }
        reference_origins_by_asset[asset_id].append(origin)
        if side == "source":
            add_relation(
                "depends-on",
                origin_id,
                asset_id,
                len(reference_origins_by_asset[asset_id]),
                f"{ref.owner_relative}#L{origin['line']}:{ref.kind}",
            )

    for asset in asset_records:
        origins = sorted(
            reference_origins_by_asset.get(asset["id"], []),
            key=lambda item: (
                item["side"],
                item["owner"],
                item["line"],
                item["kind"],
                item["declared"],
            ),
        )
        asset["references"] = origins
        if not origins and asset.get("source_locator"):
            component = asset["corpus_component"]
            add_relation(
                "contains",
                work_unit_id(component),
                asset["id"],
                800000 + len(origins),
                asset["source_locator"],
            )

    file_id_by_relative = {
        relative: file_unit_id(relative) for relative in all_files
    }
    asset_id_by_relative = {
        asset.get("source_locator") or asset.get("target_locator"): asset["id"]
        for asset in asset_records
        if asset.get("source_locator") or asset.get("target_locator")
    }
    correction_records: list[dict] = []
    unmapped_correction_ids: list[str] = []
    locator_pattern = re.compile(
        r"src/[A-Za-z0-9_.\-/]+\.(?:tex|sty|cls|sage|py|mp|asy)"
    )
    for row_number, row in enumerate(correction_rows, 2):
        local_id = row["event_id"].strip()
        correction_id = (
            f"{RESOURCE_ID}.correction.{local_id.lower()}.locale.id-id"
        )
        affected_locators = sorted(
            set(locator_pattern.findall(row["evidence"] + " " + row["scope"]))
        )
        affected_ids = sorted(
            {
                candidate
                for affected in affected_locators
                for candidate in [
                    file_id_by_relative.get(affected),
                    asset_id_by_relative.get(affected),
                ]
                if candidate is not None
            }
        )
        if not affected_ids and row["scope"] in {"authority", "rights"}:
            affected_ids = sorted(
                work_unit_id(component) for component, *_ in ROOT_SPECS
            )
        elif not affected_ids and row["scope"] in {"build", "layout"}:
            affected_ids = [work_unit_id("main-textbook")]
        correction = authoritative_record(correction_id, "correction")
        correction.update(
            {
                "affected_source_locators": affected_locators,
                "affected_unit_ids": affected_ids,
                "affected_unit_mapping_status": (
                    "mapped_to_complete_corpus_closure"
                    if affected_ids
                    else "ledger evidence has no admitted closure locator"
                ),
                "date": row["date"],
                "disposition": row["disposition"],
                "evidence": row["evidence"],
                "language": "id",
                "ledger_status": row["status"],
                "locale": "id-ID",
                "rationale": row["summary"],
                "rights_id": RIGHTS_CORE,
                "scope": row["scope"],
                "severity": row["severity"],
                "source_defect": row["summary"],
                "source_locator": f"00_control/ADVERSE_LEDGER.csv#row-{row_number}",
                "source_ledger_row": row_number,
                "source_ledger_sha256": correction_sha,
                "source_local_id": local_id,
                "source_sha256": correction_sha,
                "target_correction": row["disposition"],
                "target_edition_id": TARGET_EDITION_ID,
                "translation_state": None,
                "translation_state_status": "not applicable to correction metadata",
                "upstream_report_disposition": (
                    "ledger disposition recorded; no production contact by indexer"
                ),
            }
        )
        correction_records.append(correction)
        if not affected_ids:
            unmapped_correction_ids.append(correction_id)
        for order, affected_id in enumerate(affected_ids, 1):
            add_relation(
                "corrects",
                correction_id,
                affected_id,
                order,
                row["evidence"],
            )

    for parent_id, children in defaultdict(list).items():
        del parent_id, children
    children_by_parent: dict[str, list[dict]] = defaultdict(list)
    for unit in unit_records:
        if unit.get("parent_id") in unit_by_id:
            children_by_parent[unit["parent_id"]].append(unit)
    for parent_id, children in children_by_parent.items():
        ordered = sorted(children, key=lambda item: (item["order"], item["id"]))
        for previous, following in zip(ordered, ordered[1:]):
            add_relation(
                "precedes",
                previous["id"],
                following["id"],
                int(previous["order"]),
                previous.get("source_locator"),
            )

    dynamic_dependencies = sorted(
        {
            item
            for closure in source_closures
            for item in closure.dynamic_dependencies
        }
    )
    closure_qa_id = f"{RESOURCE_ID}.qa.complete-source-closure.001.locale.id-id"
    closure_qa = authoritative_record(closure_qa_id, "qa_event")
    closure_qa.update(
        {
            "qa_type": "source_closure",
            "result": "pass",
            "rights_id": RIGHTS_CORE,
            "source_locator": "; ".join(
                closure.root for closure in source_closures
            ),
            "translation_state": "structurally_verified",
            "unit_ids": [
                work_unit_id(component) for component, *_ in ROOT_SPECS
            ],
            "witness": {
                "component_file_counts": {
                    component: len(files)
                    for component, files in component_files.items()
                },
                "dynamic_dependency_count": len(dynamic_dependencies),
                "paired_file_count": len(all_files),
                "source_target_closures_equal": True,
            },
        }
    )
    qa_records.append(closure_qa)
    exercise_qa_id = (
        f"{RESOURCE_ID}.qa.exercise-answer-completeness.001.locale.id-id"
    )
    exercise_qa = authoritative_record(exercise_qa_id, "qa_event")
    exercise_qa.update(
        {
            "qa_type": "exercise_answer_topology",
            "result": (
                "pass" if not unanswered_exercise_ids else "pass_with_declared_gaps"
            ),
            "rights_id": RIGHTS_CORE,
            "source_locator": "complete admitted TeX closure",
            "translation_state": "structurally_verified",
            "unit_ids": exercise_ids,
            "witness": {
                "answer_count": len(answer_ids),
                "exercise_count": len(exercise_ids),
                "exercise_group_count": exercise_group_count,
                "native_upstream_answer_count": len(native_answer_ids),
                "target_supplied_answer_count": len(target_supplied_answer_ids),
                "target_supplied_answer_ids": target_supplied_answer_ids,
                "unanswered_exercise_count": len(unanswered_exercise_ids),
                "unanswered_exercise_ids": unanswered_exercise_ids,
                "upstream_answer_gap_count": len(upstream_answer_gap_ids),
                "upstream_answer_gap_ids": upstream_answer_gap_ids,
            },
        }
    )
    qa_records.append(exercise_qa)
    ledger_qa_id = f"{RESOURCE_ID}.qa.control-ledgers.001.locale.id-id"
    ledger_qa = authoritative_record(ledger_qa_id, "qa_event")
    ledger_qa.update(
        {
            "qa_type": "source_and_language_control",
            "result": (
                "pass" if not unmapped_correction_ids else "pass_with_declared_gaps"
            ),
            "rights_id": RIGHTS_CORE,
            "source_locator": "00_control/TERMINOLOGY.csv; 00_control/ADVERSE_LEDGER.csv",
            "translation_state": "structurally_verified",
            "unit_ids": [],
            "witness": {
                "correction_count": len(correction_records),
                "correction_ledger_sha256": correction_sha,
                "terminology_count": len(terminology_records),
                "terminology_ledger_sha256": terminology_sha,
                "unmapped_correction_count": len(unmapped_correction_ids),
                "unmapped_correction_ids": unmapped_correction_ids,
            },
        }
    )
    qa_records.append(ledger_qa)
    asset_qa_id = f"{RESOURCE_ID}.qa.asset-closure.001.locale.id-id"
    virtual_assets = [
        asset
        for asset in asset_records
        if asset["availability"]
        in {
            "external_toolchain",
            "build_generated_unmaterialized",
            "declared_dependency_unresolved",
        }
    ]
    asset_qa = authoritative_record(asset_qa_id, "qa_event")
    asset_qa.update(
        {
            "qa_type": "asset_and_code_closure",
            "result": "pass_with_declared_gaps" if virtual_assets else "pass",
            "rights_id": RIGHTS_CORE,
            "source_locator": "complete admitted TeX closure",
            "translation_state": "structurally_verified",
            "unit_ids": [],
            "witness": {
                "asset_count": len(asset_records),
                "declared_unmaterialized_or_external_count": len(virtual_assets),
                "declared_unmaterialized_or_external_ids": [
                    asset["id"] for asset in sorted(virtual_assets, key=lambda a: a["id"])
                ],
            },
        }
    )
    qa_records.append(asset_qa)
    correction_trace_qa = authoritative_record(
        f"{RESOURCE_ID}.qa.correction-traceability.001.locale.id-id",
        "qa_event",
    )
    correction_trace_qa.update(
        {
            "qa_type": "mathematical_and_source_correction_traceability",
            "result": "pass_with_declared_findings",
            "rights_id": RIGHTS_CORE,
            "source_locator": "00_control/ADVERSE_LEDGER.csv",
            "translation_state": "mathematically_reviewed",
            "unit_ids": sorted(
                {
                    affected_id
                    for correction in correction_records
                    for affected_id in correction["affected_unit_ids"]
                    if affected_id in unit_by_id
                }
            ),
            "witness": {
                "correction_count": len(correction_records),
                "ledger_sha256": correction_sha,
                "scope_counts": dict(
                    sorted(Counter(row["scope"] for row in correction_rows).items())
                ),
                "severity_counts": dict(
                    sorted(
                        Counter(row["severity"] for row in correction_rows).items()
                    )
                ),
                "status_counts": dict(
                    sorted(Counter(row["status"] for row in correction_rows).items())
                ),
                "unmapped_correction_ids": sorted(unmapped_correction_ids),
            },
        }
    )
    qa_records.append(correction_trace_qa)
    terminology_qa = authoritative_record(
        f"{RESOURCE_ID}.qa.terminology-consistency.001.locale.id-id",
        "qa_event",
    )
    terminology_qa.update(
        {
            "qa_type": "language_terminology_consistency",
            "result": "pass",
            "rights_id": RIGHTS_CORE,
            "source_locator": "00_control/TERMINOLOGY.csv",
            "translation_state": "language_reviewed",
            "unit_ids": sorted(
                unit["id"] for unit in unit_records if unit.get("concept_ids")
            ),
            "witness": {
                "example_count": sum(
                    len(term["examples"]) for term in terminology_records
                ),
                "preferred_form_count": sum(
                    bool(term["preferred"]) for term in terminology_records
                ),
                "rejected_form_count": sum(
                    len(term["rejected"]) for term in terminology_records
                ),
                "term_count": len(terminology_records),
                "terminology_ledger_sha256": terminology_sha,
                "variant_count": sum(
                    len(term["variants"]) for term in terminology_records
                ),
            },
        }
    )
    qa_records.append(terminology_qa)
    built_pdf_witnesses: dict[str, dict] = {}
    reproducibility_command: str | None = None
    visual_witness: dict | None = None
    cross_pdf_witness: dict | None = None
    lab_runtime_witness: dict | None = None
    if build_report is None:
        build_result = "not_run"
        build_translation_state = "structurally_verified"
        build_witness: dict = {
            "reason": "no isolated build report is present",
            "structural_indexing_completed": True,
        }
    elif build_report["status"] != "success":
        build_result = "fail"
        build_translation_state = "structurally_verified"
        build_witness = {
            "build_report_sha256": build_report_sha,
            "failure": build_report.get("failure"),
            "status": build_report["status"],
            "structural_indexing_completed": True,
        }
    else:
        qa_summary = build_report.get("qa_summary", {})
        link_witness = build_report.get("cross_pdf_link_audit", {})
        expected_zero_diagnostics = (
            "undefined_reference_lines",
            "generated_english_label_hits",
            "runtime_placeholder_lines",
        )
        if not isinstance(qa_summary, dict) or any(
            type(qa_summary.get(key)) is not int or qa_summary.get(key) != 0
            for key in expected_zero_diagnostics
        ):
            raise RuntimeError(
                "successful build report lacks exact zero diagnostic/runtime closure"
            )
        if link_witness.get("all_pair_actions_resolved") is not True:
            raise RuntimeError("successful build report has unresolved cross-PDF links")
        answer_stream = build_report.get("generated_answer_stream", {})
        if (
            answer_stream.get("topic_answers") != 133
            or answer_stream.get("expected_topic_answers") != 133
        ):
            raise RuntimeError("successful build report fails the topic-answer gate")
        expected_answer_links = answer_stream.get("all_answers")
        if expected_answer_links != 1032:
            raise RuntimeError("successful build report has an unexpected answer stream")

        link_audit_payload = inputs.read_bytes(CROSS_PDF_LINK_AUDIT_PATH)
        try:
            link_audit = json.loads(link_audit_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("cross-PDF link audit is not valid UTF-8 JSON") from exc
        if not isinstance(link_audit, dict):
            raise RuntimeError("cross-PDF link audit has an invalid root type")
        reported_link_path = str(link_witness.get("path", "")).replace("\\", "/")
        expected_link_locator = "build/hefferon_id/cross_pdf_link_audit.json"
        if not (
            reported_link_path == expected_link_locator
            or reported_link_path.endswith("/" + expected_link_locator)
        ):
            raise RuntimeError("successful build report has a stale link-audit path")
        link_audit_sha = sha256_bytes(link_audit_payload)
        if (
            link_witness.get("bytes") != len(link_audit_payload)
            or link_witness.get("sha256") != link_audit_sha
            or link_audit.get("all_pair_actions_resolved") is not True
            or link_audit.get("counts") != link_witness.get("counts")
        ):
            raise RuntimeError("successful build report has a stale link-audit sidecar")
        link_counts = link_audit.get("counts", {})
        link_actions = link_audit.get("actions")
        unresolved_actions = link_audit.get("unresolved_pair_actions")
        expected_link_counts = {
            "book_to_jhanswer": expected_answer_links,
            "jhanswer_to_book": expected_answer_links,
            "goto_remote_actions": 2 * expected_answer_links,
            "unresolved_pair_actions": 0,
        }
        if (
            not isinstance(link_counts, dict)
            or not isinstance(link_actions, list)
            or not isinstance(unresolved_actions, list)
            or any(
                type(link_counts.get(key)) is not int
                or link_counts.get(key) != expected
                for key, expected in expected_link_counts.items()
            )
            or len(link_actions) != 2 * expected_answer_links
            or unresolved_actions
        ):
            raise RuntimeError("cross-PDF link sidecar fails exact answer-link closure")
        cross_pdf_witness = {
            "all_pair_actions_resolved": True,
            "answer_links_each_direction": expected_answer_links,
            "bytes": len(link_audit_payload),
            "goto_remote_actions": 2 * expected_answer_links,
            "locator": expected_link_locator,
            "sha256": link_audit_sha,
            "unresolved_pair_actions": 0,
        }

        runtime = build_report.get("lab_sagetex", {})
        runtime_artifact = runtime.get("manifest_artifact", {}) if isinstance(runtime, dict) else {}
        runtime_payload = inputs.read_bytes(LAB_SAGETEX_RUNTIME_MANIFEST_PATH)
        try:
            runtime_sidecar = json.loads(runtime_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("SageTeX runtime manifest is not valid UTF-8 JSON") from exc
        if not isinstance(runtime_sidecar, dict) or not isinstance(runtime, dict):
            raise RuntimeError("SageTeX runtime manifest has an invalid root type")
        expected_runtime_locator = (
            "build/hefferon_id/lab_sagetex_runtime_manifest.json"
        )
        reported_runtime_path = str(runtime_artifact.get("path", "")).replace(
            "\\", "/"
        )
        runtime_sha = sha256_bytes(runtime_payload)
        if not (
            reported_runtime_path == expected_runtime_locator
            or reported_runtime_path.endswith("/" + expected_runtime_locator)
        ):
            raise RuntimeError("successful build report has a stale SageTeX path")
        if (
            runtime_artifact.get("bytes") != len(runtime_payload)
            or runtime_artifact.get("sha256") != runtime_sha
            or runtime_sidecar.get("schema_version")
            != "hefferon-id-sagetex-runtime-v1"
            or runtime_sidecar.get("status") != "pass"
            or runtime.get("schema_version") != runtime_sidecar.get("schema_version")
            or runtime.get("status") != "pass"
            or runtime.get("outputs") != runtime_sidecar.get("outputs")
            or runtime.get("figure_execution")
            != runtime_sidecar.get("figure_execution")
        ):
            raise RuntimeError("successful build report has a stale SageTeX sidecar")
        runtime_outputs = runtime_sidecar.get("outputs", {})
        runtime_scmd = runtime_outputs.get("scmd", {}) if isinstance(runtime_outputs, dict) else {}
        runtime_figures = runtime_sidecar.get("figure_execution", {})
        runtime_pythontex = runtime.get("pythontex", {})
        report_stable = runtime.get("stable_fingerprint", {})
        sidecar_stable = runtime_sidecar.get("stable_fingerprint", {})
        if not isinstance(report_stable, dict) or not isinstance(sidecar_stable, dict):
            raise RuntimeError("SageTeX stable fingerprint is invalid")
        sage_only_stable = dict(report_stable)
        pythontex_stable = sage_only_stable.pop("pythontex", None)
        restored_graphics = runtime.get("post_execution_authority_graphics", {})
        lab_graphics = build_report.get("lab_graphics", {})
        restored_manifest_sha = (
            restored_graphics.get("manifest_sha256")
            if isinstance(restored_graphics, dict)
            else None
        )
        expected_runtime_counts = {
            "command_label_count": 148,
            "command_label_first": 0,
            "command_label_last": 147,
            "command_source_listing_count": 1018,
            "maximum_listed_source_line": 1236,
        }
        if (
            not isinstance(runtime_outputs, dict)
            or not isinstance(runtime_scmd, dict)
            or not isinstance(runtime_figures, dict)
            or not isinstance(runtime_pythontex, dict)
            or any(
                type(runtime_outputs.get(key)) is not int
                or runtime_outputs.get(key) != expected
                for key, expected in expected_runtime_counts.items()
            )
            or type(runtime_scmd.get("line_count")) is not int
            or runtime_scmd.get("line_count") != 1237
            or type(runtime_figures.get("target_count")) is not int
            or runtime_figures.get("target_count") != 64
            or type(runtime_figures.get("changed_from_authority_count")) is not int
            or runtime_figures.get("changed_from_authority_count") != 63
            or runtime_figures.get("unchanged_from_authority_paths")
            != ["asy/ellipsoid1.pdf"]
            or runtime_figures.get("final_state")
            != "all_64_pinned_authority_figures_restored_and_rehashed"
            or sage_only_stable != sidecar_stable
            or runtime_pythontex.get("status") != "pass"
            or runtime_pythontex.get("success_line")
            != "PythonTeX:  lab - 0 error(s), 0 warning(s)"
            or runtime_pythontex.get("stable_fingerprint") != pythontex_stable
            or not isinstance(restored_graphics, dict)
            or not isinstance(lab_graphics, dict)
            or type(restored_graphics.get("count")) is not int
            or restored_graphics.get("count") != 64
            or not isinstance(restored_manifest_sha, str)
            or re.fullmatch(r"[0-9a-f]{64}", restored_manifest_sha) is None
            or restored_manifest_sha != lab_graphics.get("manifest_sha256")
        ):
            raise RuntimeError("SageTeX/PythonTeX runtime fails exact closure")
        lab_runtime_witness = {
            "authority_figures_restored": 64,
            "bytes": len(runtime_payload),
            "command_labels": 148,
            "command_source_listings": 1018,
            "locator": expected_runtime_locator,
            "maximum_listed_source_line": 1236,
            "pythontex_zero_errors_warnings": True,
            "sage_changed_figures": 63,
            "scmd_lines": 1237,
            "sha256": runtime_sha,
        }
        for component, pdf_name in TARGET_PDF_NAMES.items():
            job = TARGET_PDF_JOBS[component]
            reported = build_report.get("pdfs", {}).get(job)
            if not isinstance(reported, dict):
                raise RuntimeError(f"successful build report lacks {job} PDF witness")
            pdf_path = BUILD_PDF_ROOT / pdf_name
            expected_pdf_locator = f"build/hefferon_id/output/pdf/{pdf_name}"
            reported_pdf_path = str(reported.get("path", "")).replace("\\", "/")
            if not (
                reported_pdf_path == expected_pdf_locator
                or reported_pdf_path.endswith("/" + expected_pdf_locator)
            ):
                raise RuntimeError(f"successful build report has a stale {job} PDF path")
            pdf_payload = inputs.read_bytes(pdf_path)
            actual = {
                "bytes": len(pdf_payload),
                "page_count": reported.get("pages"),
                "sha256": sha256_bytes(pdf_payload),
                "target_locator": expected_pdf_locator,
            }
            if not isinstance(actual["page_count"], int) or actual["page_count"] <= 0:
                raise RuntimeError(f"successful build report has invalid {job} page count")
            if reported.get("bytes") != actual["bytes"]:
                raise RuntimeError(f"successful build report has stale {job} byte count")
            if reported.get("sha256") != actual["sha256"]:
                raise RuntimeError(f"successful build report has stale {job} SHA-256")
            renders = reported.get("all_page_renders", {})
            contact_sheets = reported.get("contact_sheets", {})
            if renders.get("count") != actual["page_count"]:
                raise RuntimeError(f"successful build report lacks all-page {job} renders")
            actual["all_page_renders"] = {
                "bytes": renders.get("bytes"),
                "canonical_sha256": renders.get("canonical_sha256"),
                "count": renders.get("count"),
            }
            actual["contact_sheets"] = {
                "bytes": contact_sheets.get("bytes"),
                "count": contact_sheets.get("count"),
                "sha256": contact_sheets.get("sha256"),
            }
            built_pdf_witnesses[component] = actual
        render_manifest = build_report.get("all_page_render_manifest", {})
        render_manifest_path = BUILD_ROOT / "all_page_render_manifest.json"
        render_manifest_payload = inputs.read_bytes(render_manifest_path)
        if (
            render_manifest.get("count")
            != sum(item["page_count"] for item in built_pdf_witnesses.values())
            or render_manifest.get("manifest_bytes") != len(render_manifest_payload)
            or render_manifest.get("manifest_sha256")
            != sha256_bytes(render_manifest_payload)
        ):
            raise RuntimeError("successful build report has a stale all-page render manifest")
        visual_witness = {
            "all_page_render_manifest": {
                "bytes": len(render_manifest_payload),
                "count": render_manifest["count"],
                "locator": "build/hefferon_id/all_page_render_manifest.json",
                "sha256": sha256_bytes(render_manifest_payload),
            },
            "inspection_scope": "automated all-page rendering, image integrity/luminance gates, and contact-sheet generation; human visual review is separate",
            "pdfs": built_pdf_witnesses,
        }
        reproducibility = build_report.get("reproducibility", {})
        if not isinstance(reproducibility, dict):
            raise RuntimeError("successful build report has invalid reproducibility data")
        reproducibility_portable = dict(reproducibility)
        baseline_path = reproducibility.get("path")
        if baseline_path is not None:
            if not isinstance(baseline_path, str):
                raise RuntimeError("reproducibility baseline path must be a string")
            baseline_locator = portable_lane_locator(baseline_path)
            reproducibility_portable["path"] = baseline_locator
            reproducibility_command = (
                "python -B tools/build_hefferon_id.py "
                f"--reproducibility-baseline {baseline_locator}"
            )
        reproducibly_verified = reproducibility.get("matched") is True
        build_result = "pass" if reproducibly_verified else "pass_with_declared_gaps"
        build_translation_state = "built"
        build_witness = {
            "all_pair_actions_resolved": True,
            "build_report_sha256": build_report_sha,
            "cross_pdf_link_audit": cross_pdf_witness,
            "generated_english_label_hits": 0,
            "lab_sagetex_runtime": lab_runtime_witness,
            "live_target_tree_sha256": live_target_tree_sha,
            "pdfs": built_pdf_witnesses,
            "qa_summary": qa_summary,
            "reproducibility": reproducibility_portable,
            "reproducibility_verified": reproducibly_verified,
            "status": "success",
            "structural_indexing_completed": True,
            "topic_answer_count": 133,
            "topic_answer_stream_sha256": answer_stream.get("sha256"),
            "tool_versions": build_report.get("tool_versions", {}),
            "undefined_reference_lines": 0,
            "runtime_placeholder_lines": 0,
        }
    build_qa_id = f"{RESOURCE_ID}.qa.full-build.001.locale.id-id"
    build_qa = authoritative_record(build_qa_id, "qa_event")
    build_qa.update(
        {
            "qa_type": "build",
            "result": build_result,
            "rights_id": RIGHTS_CORE,
            "source_locator": "src/book.tex; src/jhanswer.tex; src/lab/lab.tex",
            "translation_state": build_translation_state,
            "unit_ids": [
                work_unit_id(component) for component, *_ in ROOT_SPECS
            ],
            "witness": build_witness,
        }
    )
    qa_records.append(build_qa)
    visual_qa = authoritative_record(
        f"{RESOURCE_ID}.qa.visual-render-coverage.001.locale.id-id",
        "qa_event",
    )
    visual_qa.update(
        {
            "qa_type": "visual_render_coverage",
            "result": (
                "pass"
                if visual_witness is not None
                else "fail"
                if build_report is not None and build_report["status"] == "failed"
                else "not_run"
            ),
            "rights_id": RIGHTS_CORE,
            "source_locator": "build/hefferon_id/all_page_render_manifest.json",
            "translation_state": (
                "built" if visual_witness is not None else "structurally_verified"
            ),
            "unit_ids": [
                work_unit_id(component) for component, *_ in ROOT_SPECS
            ],
            "witness": (
                visual_witness
                if visual_witness is not None
                else {"reason": "no successful isolated PDF build is admitted"}
            ),
        }
    )
    qa_records.append(visual_qa)
    for qa_record in qa_records:
        qa_record["target_edition_id"] = TARGET_EDITION_ID

    source_snapshot_artifact_id = (
        f"{RESOURCE_ID}.artifact.source-snapshot.locale.id-id.current"
    )
    backend_snapshot_artifact_id = (
        f"{RESOURCE_ID}.artifact.backend-snapshot.locale.id-id.current"
    )
    expected_artifact_ids = {
        "main-textbook": f"{RESOURCE_ID}.artifact.textbook-pdf.locale.id-id",
        "answer-book-shell": f"{RESOURCE_ID}.artifact.answer-pdf.locale.id-id",
        "sage-lab": f"{RESOURCE_ID}.artifact.sage-lab-pdf.locale.id-id",
    }
    official_artifact_ids = {
        component: (
            f"{RESOURCE_ID}.artifact.authority-{id_token(artifact_kind)}.df2262e"
        )
        for component, _name, artifact_kind, _order in OFFICIAL_PDF_SPECS
    }
    add_relation("contains", RESOURCE_ID, EDITION_ID, 1, "authority")
    add_relation("contains", RESOURCE_ID, TARGET_EDITION_ID, 2, "id-ID derivative")
    add_relation("adapts", TARGET_EDITION_ID, EDITION_ID, 1, "source authority")
    add_relation("contains", PROGRAM_ID, COURSE_ID, 1, "curriculum role B40")
    add_relation("depends-on", COURSE_ID, RESOURCE_ID, 1, "resource authority")
    for component, *_ in ROOT_SPECS:
        add_relation(
            "contains",
            COURSE_ID,
            work_unit_id(component),
            root_metadata[component][1],
            component,
        )
        add_relation(
            "contains",
            work_unit_id(component),
            expected_artifact_ids[component],
            999999,
            component,
        )
    add_relation(
        "contains", EDITION_ID, source_snapshot_artifact_id, 1, "source closure"
    )
    add_relation(
        "contains", TARGET_EDITION_ID, source_snapshot_artifact_id, 1, "paired derivative closure"
    )
    for component, name, _artifact_kind, order in OFFICIAL_PDF_SPECS:
        add_relation(
            "contains",
            EDITION_ID,
            official_artifact_ids[component],
            order,
            f"authority/official/{name}",
        )
    add_relation(
        "contains", PROGRAM_ID, backend_snapshot_artifact_id, 1, "backend"
    )

    source_closure_projection = {
        "assets": [
            {
                "asset_id": asset["id"],
                "availability": asset["availability"],
                "source_locator": asset.get("source_locator"),
                "source_sha256": asset.get("source_sha256"),
                "target_locator": asset.get("target_locator"),
                "target_sha256": asset.get("target_sha256"),
            }
            for asset in sorted(asset_records, key=lambda item: item["id"])
        ],
        "dynamic_tex_dependencies": [
            {
                "command": command,
                "declared": declared,
                "line": line,
                "owner": owner,
            }
            for owner, line, command, declared in dynamic_dependencies
        ],
        "files": [
            {
                "components": file_components[relative],
                "file_unit_id": file_unit_id(relative),
                "source_bytes": len(source_file_data[relative][0]),
                "source_locator": relative,
                "source_sha256": sha256_bytes(source_file_data[relative][0]),
                "target_bytes": len(target_file_data[relative][0]),
                "target_locator": relative,
                "target_sha256": sha256_bytes(target_file_data[relative][0]),
            }
            for relative in all_files
        ],
        "ledgers": [
            {
                "path": "00_control/TERMINOLOGY.csv",
                "record_count": len(terminology_records),
                "sha256": terminology_sha,
            },
            {
                "path": "00_control/ADVERSE_LEDGER.csv",
                "record_count": len(correction_records),
                "sha256": correction_sha,
            },
        ],
        "roots": [
            {
                "component": closure.component,
                "file_count": len(closure.files),
                "files": list(closure.files),
                "source_entrypoint": closure.root,
                "target_entrypoint": closure.root,
                "work_unit_id": work_unit_id(closure.component),
            }
            for closure in source_closures
        ],
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
    }
    closure_descriptor = canonical_json(source_closure_projection).encode("utf-8")
    source_closure_projection["closure_sha256"] = sha256_bytes(
        closure_descriptor
    )

    interoperability_projection = {
        "deterministic_serialization": {
            "csv": "UTF-8, LF, explicit header order, canonical record order",
            "json": "UTF-8, LF, sorted keys, compact separators",
            "jsonl": "one canonical JSON object per LF-terminated line",
        },
        "entity_exports": {
            "artifact": "artifacts.jsonl",
            "asset": "assets.jsonl",
            "concept": "concepts.jsonl",
            "correction": "corrections.jsonl",
            "course": "courses.jsonl",
            "edition": "authority.jsonl",
            "program": "programs.jsonl",
            "qa_event": "qa_events.jsonl",
            "relation": "relations.csv",
            "resource": "authority.jsonl",
            "rights": "rights.jsonl",
            "segment": "segments.jsonl",
            "term": "terminology.jsonl",
            "unit": "units.jsonl",
        },
        "exercise_answer_model": {
            "answer_relation": "answers",
            "exercise_relation": "exercises",
            "deliverable_answer_count": len(answer_ids),
            "deliverable_unanswered_exercise_count": len(unanswered_exercise_ids),
            "known_authority_gap_count": len(upstream_answer_gap_ids),
            "native_upstream_answer_count": len(native_answer_ids),
            "native_answer_unit_kind": "answer",
            "native_exercise_unit_kind": "exercise",
            "target_supplied_answer_count": len(target_supplied_answer_ids),
            "target_supplied_provenance_kind": "indonesian_edition_supplied",
        },
        "identity_contract": {
            "locale_scoped_entities": [
                "derivative_edition",
                "program",
                "course",
                "term",
                "target_artifact",
                "target_supplied_answer_segment",
                "target_supplied_answer_unit",
            ],
            "locale_neutral": True,
            "mutable_title_or_page_derived": False,
            "native_labels_preferred": True,
            "shared_cross_locale_entities": [
                "resource",
                "source_edition",
                "unit",
                "concept",
                "source_asset_identity",
                "source_correction_identity",
            ],
            "source_order_fallback": True,
        },
        "interoperability_envelope": "modular-translation-backend-v0",
        "merge_contract": {
            "localized_record_ids": "include .locale.<BCP47-normalized-lowercase>",
            "shared_record_conflicts": "source authority fields and hashes must be identical; collect target_variant objects by locale",
            "target_variant_carriers": ["unit", "segment", "asset"],
        },
        "required_entity_classes": [
            "program",
            "course",
            "resource",
            "edition",
            "unit",
            "concept",
            "segment",
            "term",
            "asset",
            "relation",
            "rights",
            "qa_event",
            "artifact",
            "correction",
        ],
        "round_trip_gate": "backend/build_index.py validates every emitted JSON, JSONL, and CSV projection before atomic replacement",
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "translation_state_mapping": {
            state: state
            for state in [
                "source_frozen",
                "queued",
                "draft",
                "translated",
                "structurally_verified",
                "mathematically_reviewed",
                "language_reviewed",
                "built",
                "visually_checked",
                "published",
                "superseded",
                "blocked",
            ]
        },
    }

    record_groups: dict[str, list[dict]] = {
        "assets.jsonl": asset_records,
        "authority.jsonl": authority_records,
        "concepts.jsonl": concept_records,
        "corrections.jsonl": correction_records,
        "courses.jsonl": course_records,
        "programs.jsonl": program_records,
        "qa_events.jsonl": qa_records,
        "rights.jsonl": rights_records,
        "segments.jsonl": segment_records,
        "terminology.jsonl": terminology_records,
        "units.jsonl": unit_records,
    }
    for records in record_groups.values():
        records.sort(key=lambda record: record["id"])

    known_artifact_ids = {
        source_snapshot_artifact_id,
        backend_snapshot_artifact_id,
        *expected_artifact_ids.values(),
        *official_artifact_ids.values(),
    }
    endpoint_ids = {
        record["id"]
        for records in record_groups.values()
        for record in records
    } | known_artifact_ids

    relation_specs.sort(
        key=lambda relation: (
            relation["relation_type"],
            relation["source_id"],
            relation["target_id"],
            relation["order"],
            relation["source_locator"] or "",
        )
    )
    relation_records: list[dict] = []
    seen_relation_keys: dict[str, str] = {}
    seen_relation_payloads: set[str] = set()
    target_supplied_relation_endpoint_ids = set(target_supplied_answer_ids)
    target_supplied_relation_endpoint_ids.update(
        segment_id
        for answer_id in target_supplied_answer_ids
        for segment_id in unit_by_id[answer_id].get("segment_ids", [])
    )
    for relation in relation_specs:
        key = canonical_json(relation)
        relation_id = (
            f"{RESOURCE_ID}.relation.{id_token(relation['relation_type'])}."
            f"{short_hash(key, 24)}"
        )
        if relation_id in seen_relation_keys and seen_relation_keys[relation_id] != key:
            raise RuntimeError(f"relation ID hash collision: {relation_id}")
        if key in seen_relation_payloads:
            continue
        seen_relation_keys[relation_id] = key
        seen_relation_payloads.add(key)
        relation_edition_id = (
            TARGET_EDITION_ID
            if relation["source_id"] in target_supplied_relation_endpoint_ids
            or relation["target_id"] in target_supplied_relation_endpoint_ids
            else EDITION_ID
        )
        record = {
            "relation_id": relation_id,
            **relation,
            "edition_id": relation_edition_id,
            "recorded_on": RECORDED_ON,
            "responsible_workflow": WORKFLOW_ID,
            "rights_id": RIGHTS_CORE,
            "schema": SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "status": "active",
            "supersedes": None,
        }
        relation_records.append(record)
    target_supplied_relation_records = [
        relation
        for relation in relation_records
        if relation["source_id"] in target_supplied_relation_endpoint_ids
        or relation["target_id"] in target_supplied_relation_endpoint_ids
    ]
    if (
        len(target_supplied_relation_endpoint_ids) != 4
        or len(target_supplied_relation_records) != 6
        or any(
            relation["edition_id"] != TARGET_EDITION_ID
            for relation in target_supplied_relation_records
        )
    ):
        raise RuntimeError(
            "target-supplied answer relation derivative binding is incomplete"
        )
    unresolved_endpoints = sorted(
        {
            endpoint
            for relation in relation_records
            for endpoint in (relation["source_id"], relation["target_id"])
            if endpoint not in endpoint_ids
        }
    )
    if unresolved_endpoints:
        raise RuntimeError(
            f"unresolved relation endpoints: {unresolved_endpoints}"
        )

    all_record_ids = [
        record["id"]
        for records in record_groups.values()
        for record in records
    ]
    duplicates = sorted(
        record_id
        for record_id in set(all_record_ids)
        if all_record_ids.count(record_id) > 1
    )
    if duplicates:
        raise RuntimeError(f"duplicate exported record IDs: {duplicates}")
    for unit in unit_records:
        parent_id = unit.get("parent_id")
        if parent_id and parent_id not in endpoint_ids:
            raise RuntimeError(
                f"unit {unit['id']} has unresolved parent {parent_id}"
            )
    for segment in segment_records:
        if segment["parent_unit_id"] not in unit_by_id:
            raise RuntimeError(
                f"segment {segment['id']} has unresolved parent"
            )

    relation_fields = [
        "relation_id",
        "relation_type",
        "source_id",
        "target_id",
        "order",
        "source_locator",
        "edition_id",
        "rights_id",
        "schema",
        "schema_version",
        "status",
        "recorded_on",
        "responsible_workflow",
        "supersedes",
    ]
    core_payloads = {
        name: serialize_jsonl(records)
        for name, records in record_groups.items()
    }
    core_payloads["relations.csv"] = serialize_csv(
        relation_records, relation_fields
    )
    json_documents = {
        "interoperability.json": interoperability_projection,
        "source_closure.json": source_closure_projection,
    }
    core_payloads.update(
        {
            name: (canonical_json(document) + "\n").encode("utf-8")
            for name, document in json_documents.items()
        }
    )

    for name, payload in core_payloads.items():
        assert_lf_utf8(name, payload)
        if name.endswith(".jsonl"):
            parsed = [
                json.loads(line)
                for line in payload.decode("utf-8").splitlines()
                if line
            ]
            if parsed != record_groups[name]:
                raise RuntimeError(f"{name} failed JSONL round trip")
        elif name.endswith(".json"):
            if json.loads(payload.decode("utf-8")) != json_documents[name]:
                raise RuntimeError(f"{name} failed JSON round trip")
        else:
            parsed_rows = list(
                csv.DictReader(io.StringIO(payload.decode("utf-8"), newline=""))
            )
            normalized_rows = [
                {
                    field: "" if row.get(field) is None else str(row.get(field))
                    for field in relation_fields
                }
                for row in relation_records
            ]
            if parsed_rows != normalized_rows:
                raise RuntimeError(f"{name} failed CSV round trip")

    source_components = [
        {
            "bytes": len(source_file_data[relative][0]),
            "kind": "reader_source",
            "path": f"authority/{relative}",
            "sha256": sha256_bytes(source_file_data[relative][0]),
        }
        for relative in all_files
    ] + [
        {
            "bytes": asset["bytes"],
            "kind": "asset",
            "path": f"authority/{asset['source_locator']}",
            "sha256": asset["source_sha256"],
        }
        for asset in asset_records
        if asset.get("source_locator") and asset.get("source_sha256")
    ]
    target_components = [
        {
            "bytes": len(target_file_data[relative][0]),
            "kind": "reader_target",
            "path": f"source/linear-algebra/{relative}",
            "sha256": sha256_bytes(target_file_data[relative][0]),
        }
        for relative in all_files
    ] + [
        {
            "bytes": asset["target_bytes"],
            "kind": "asset",
            "path": f"source/linear-algebra/{asset['target_locator']}",
            "sha256": asset["target_sha256"],
        }
        for asset in asset_records
        if asset.get("target_locator") and asset.get("target_sha256")
    ]
    source_components.sort(key=lambda item: item["path"])
    target_components.sort(key=lambda item: item["path"])
    archive_prefix = (
        "linear-algebra-df2262e089a02651c127f1dd12649c4622ee1383/"
    )
    with zipfile.ZipFile(ARCHIVE_PATH) as source_archive:
        archive_names = set(source_archive.namelist())
        for component_file in source_components:
            relative = component_file["path"].removeprefix("authority/")
            archive_name = archive_prefix + relative
            if archive_name not in archive_names:
                raise RuntimeError(
                    f"source component is absent from pinned archive: {relative}"
                )
            archived_payload = source_archive.read(archive_name)
            if (
                len(archived_payload) != component_file["bytes"]
                or sha256_bytes(archived_payload) != component_file["sha256"]
            ):
                raise RuntimeError(
                    f"extracted source differs from pinned archive: {relative}"
                )
    source_snapshot = authoritative_record(
        source_snapshot_artifact_id, "artifact"
    )
    source_snapshot_descriptor = {
        "authority_components": source_components,
        "closure_sha256": source_closure_projection["closure_sha256"],
        "target_components": target_components,
    }
    source_snapshot.update(
        {
            "artifact_kind": "paired_source_closure_snapshot",
            "build_receipt": {
                "command": "python -B backend/build_index.py",
                "result": "pass",
                "scope": "backend projections only",
            },
            "bytes": sum(
                int(component["bytes"] or 0)
                for component in [*source_components, *target_components]
            ),
            "component_files": source_snapshot_descriptor,
            "edition_id": EDITION_ID,
            "language": "mul",
            "locale": None,
            "publication_status": "unpublished",
            "rights_id": RIGHTS_CORE,
            "sha256": sha256_bytes(
                canonical_json(source_snapshot_descriptor).encode("utf-8")
            ),
            "target_edition_id": TARGET_EDITION_ID,
            "toolchain": "Python standard library",
            "translation_state": "structurally_verified",
        }
    )

    core_manifest_records = [
        {
            "bytes": len(payload),
            "path": name,
            "sha256": sha256_bytes(payload),
        }
        for name, payload in sorted(core_payloads.items())
    ]
    backend_descriptor = {
        "files": core_manifest_records,
        "schema_version": SCHEMA_VERSION,
    }
    backend_snapshot = authoritative_record(
        backend_snapshot_artifact_id, "artifact"
    )
    backend_snapshot.update(
        {
            "artifact_kind": "machine_registry_snapshot",
            "build_receipt": {
                "command": "python -B backend/build_index.py",
                "result": "pass",
                "scope": "backend projections only",
            },
            "bytes": sum(item["bytes"] for item in core_manifest_records),
            "component_files": core_manifest_records,
            "edition_id": EDITION_ID,
            "language": None,
            "locale": None,
            "manifest_locator": "backend/manifest.json",
            "manifest_sha256": None,
            "manifest_sha256_status": "excluded to avoid a self-referential hash",
            "publication_status": "unpublished",
            "rights_id": RIGHTS_CORE,
            "sha256": sha256_bytes(
                canonical_json(backend_descriptor).encode("utf-8")
            ),
            "source_snapshot_artifact_id": source_snapshot_artifact_id,
            "target_edition_id": TARGET_EDITION_ID,
            "toolchain": {
                "builder": "backend/build_index.py",
                "builder_sha256": sha256_bytes(inputs.read_bytes(Path(__file__))),
                "runtime": "Python standard library",
                "validator": "backend/validate_backend.py",
                "validator_sha256": sha256_bytes(
                    inputs.read_bytes(BACKEND / "validate_backend.py")
                ),
            },
            "translation_state": None,
            "translation_state_status": "not applicable to registry artifact",
        }
    )
    artifact_records = [source_snapshot, backend_snapshot]
    for component, name, artifact_kind, _order in OFFICIAL_PDF_SPECS:
        official_path = OFFICIAL_ROOT / name
        official_payload = inputs.read_bytes(official_path)
        official_meta = OFFICIAL_PDF_METADATA[component]
        official_sha = sha256_bytes(official_payload)
        if (
            len(official_payload) != official_meta["bytes"]
            or official_sha != official_meta["sha256"]
        ):
            raise RuntimeError(f"pinned official PDF authority mismatch: {name}")
        artifact = authoritative_record(
            official_artifact_ids[component], "artifact"
        )
        artifact.update(
            {
                "artifact_kind": f"upstream_official_{artifact_kind}",
                "build_receipt": None,
                "build_status": "official authority comparison artifact",
                "bytes": len(official_payload),
                "corpus_component": component,
                "edition_id": EDITION_ID,
                "language": "en",
                "locale": None,
                "page_count": OFFICIAL_PDF_METADATA[component]["pages"],
                "publication_status": "published_upstream",
                "rights_id": (
                    RIGHTS_LAB if component == "sage-lab" else RIGHTS_CORE
                ),
                "sha256": official_sha,
                "source_locator": f"authority/official/{name}",
                "source_url": OFFICIAL_PDF_METADATA[component]["url"],
                "target_locator": None,
                "toolchain": None,
                "translation_state": "source_frozen",
            }
        )
        artifact_records.append(artifact)
    for component, *_ in ROOT_SPECS:
        built = built_pdf_witnesses.get(component)
        artifact = authoritative_record(
            expected_artifact_ids[component], "artifact"
        )
        artifact.update(
            {
                "artifact_kind": "reader_pdf" if built else "expected_reader_pdf",
                "build_receipt": (
                    {
                        "build_report_locator": "build/hefferon_id/build_report.json",
                        "build_report_sha256": build_report_sha,
                        "command": (
                            reproducibility_command
                            or "python -B tools/build_hefferon_id.py"
                        ),
                        "reproducibility_verified": build_witness.get(
                            "reproducibility_verified"
                        ),
                        "result": build_result,
                    }
                    if built
                    else None
                ),
                "build_status": (
                    "success" if built else "not built or no successful report admitted"
                ),
                "bytes": built["bytes"] if built else None,
                "corpus_component": component,
                "edition_id": TARGET_EDITION_ID,
                "language": "id",
                "locale": "id-ID",
                "page_count": built["page_count"] if built else None,
                "publication_status": "unpublished",
                "rights_id": (
                    RIGHTS_LAB if component == "sage-lab" else RIGHTS_CORE
                ),
                "sha256": built["sha256"] if built else None,
                "target_edition_id": TARGET_EDITION_ID,
                "target_locator": built["target_locator"] if built else None,
                "toolchain": (
                    build_report.get("tool_versions", {}) if built else None
                ),
                "translation_state": "built" if built else "structurally_verified",
            }
        )
        artifact_records.append(artifact)
    artifact_records.sort(key=lambda record: record["id"])
    artifacts_payload = serialize_jsonl(artifact_records)
    assert_lf_utf8("artifacts.jsonl", artifacts_payload)
    if [
        json.loads(line)
        for line in artifacts_payload.decode("utf-8").splitlines()
        if line
    ] != artifact_records:
        raise RuntimeError("artifacts.jsonl failed JSONL round trip")

    payloads = {"artifacts.jsonl": artifacts_payload, **core_payloads}
    manifest_records = [
        {
            "bytes": len(payload),
            "path": name,
            "sha256": sha256_bytes(payload),
        }
        for name, payload in sorted(payloads.items())
    ]
    manifest = {
        "files": manifest_records,
        "generated_file_count": len(manifest_records),
        "manifest_self_hash": None,
        "manifest_self_hash_status": "excluded to avoid self-referential hashing",
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "source_closure_sha256": source_closure_projection["closure_sha256"],
        "source_snapshot_artifact_id": source_snapshot_artifact_id,
    }
    manifest_payload = (canonical_json(manifest) + "\n").encode("utf-8")
    assert_lf_utf8("manifest.json", manifest_payload)
    if json.loads(manifest_payload.decode("utf-8")) != manifest:
        raise RuntimeError("manifest.json failed JSON round trip")
    payloads["manifest.json"] = manifest_payload

    # This is the final live-byte gate.  It rereads every authority, target,
    # asset, ledger, and builder byte used above before any projection changes.
    inputs.assert_unchanged()

    for name, payload in sorted(payloads.items()):
        atomic_write(BACKEND / name, payload)
    for entry in manifest_records:
        payload = (BACKEND / entry["path"]).read_bytes()
        if len(payload) != entry["bytes"] or sha256_bytes(payload) != entry["sha256"]:
            raise RuntimeError(f"manifest replay failed for {entry['path']}")
    if (BACKEND / "manifest.json").read_bytes() != manifest_payload:
        raise RuntimeError("manifest write replay failed")

    summary = {
        "answer_unit_count": len(answer_ids),
        "native_upstream_answer_unit_count": len(native_answer_ids),
        "artifact_count": len(artifact_records),
        "asset_count": len(asset_records),
        "backend_snapshot_sha256": backend_snapshot["sha256"],
        "concept_count": len(concept_records),
        "correction_count": len(correction_records),
        "correction_ledger_last_id": (
            correction_rows[-1]["event_id"] if correction_rows else None
        ),
        "correction_ledger_sha256": correction_sha,
        "exercise_group_count": exercise_group_count,
        "exercise_unit_count": len(exercise_ids),
        "generated_file_count": len(manifest_records),
        "manifest_sha256": sha256_bytes(manifest_payload),
        "paired_source_file_count": len(all_files),
        "qa_event_count": len(qa_records),
        "relation_count": len(relation_records),
        "schema_version": SCHEMA_VERSION,
        "segment_count": len(segment_records),
        "semantic_environment_unit_count": generic_environment_count,
        "source_closure_sha256": source_closure_projection["closure_sha256"],
        "source_snapshot_sha256": source_snapshot["sha256"],
        "term_count": len(terminology_records),
        "target_supplied_answer_unit_count": len(target_supplied_answer_ids),
        "terminology_ledger_sha256": terminology_sha,
        "unanswered_exercise_count": len(unanswered_exercise_ids),
        "unmapped_correction_count": len(unmapped_correction_ids),
        "unit_count": len(unit_records),
        "virtual_or_unmaterialized_asset_count": len(virtual_assets),
    }
    print(canonical_json(summary))


if __name__ == "__main__":
    main()
