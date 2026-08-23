#!/usr/bin/env python3
"""Deterministic, task-local final-PDF audit for the Hefferon id-ID edition.

The auditor is deliberately read-only over the completed build and all-page
render trees.  Its sole write is ``qa/final_pdf_qa.json``.  It binds the build
report, the three PDF artifacts, every manifest-addressed page PNG, PDF page
geometry, embedded-font inventory, final TeX diagnostics, extracted-text
review targets, and odd/even layout measurements.

Broad English and layout heuristics produce human-review candidates.  They do
not automatically reject title pages, intentional blanks, bibliographic
English, code, or mathematical notation.  Byte mismatches, invalid PDF boxes,
unembedded fonts, missing glyphs, and unresolved runtime/reference warnings do
fail the automated integrity gate.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import contextmanager, redirect_stderr
import hashlib
import io
import json
import logging
from pathlib import Path
import re
import statistics
import subprocess
import sys
from typing import Any, Iterable

import numpy as np
from PIL import Image
from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = PROJECT_ROOT / "build" / "hefferon_id"
BUILD_REPORT_PATH = BUILD_ROOT / "build_report.json"
RENDER_MANIFEST_PATH = BUILD_ROOT / "all_page_render_manifest.json"
OUTPUT_PDF_ROOT = BUILD_ROOT / "output" / "pdf"
RENDER_ROOT = PROJECT_ROOT / "tmp" / "pdfs" / "hefferon_id"
QA_ROOT = PROJECT_ROOT / "qa"
OUTPUT_REPORT_PATH = QA_ROOT / "final_pdf_qa.json"

JOBS = ("book", "jhanswer", "lab")
JOB_ORDER = {name: index for index, name in enumerate(JOBS)}
EXPECTED_PDFS = {job: OUTPUT_PDF_ROOT / f"{job}.pdf" for job in JOBS}
EXPECTED_LOGS = {
    "book": BUILD_ROOT / "staging" / "linear-algebra" / "src" / "book.log",
    "jhanswer": BUILD_ROOT / "staging" / "linear-algebra" / "src" / "jhanswer.log",
    "lab": BUILD_ROOT / "staging" / "linear-algebra" / "src" / "lab" / "lab.log",
}

BODY_TOP_FRACTION = 0.06
BODY_BOTTOM_FRACTION = 0.94
BODY_INK_THRESHOLD = 245
MANIFEST_INK_THRESHOLD = 250
ROBUST_OUTLIER_Z = 4.5


class AuditFailure(RuntimeError):
    """The final-PDF audit could not establish its required input closure."""


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(value: Any, *, indent: int | None = None) -> bytes:
    separators = (",", ":") if indent is None else None
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=indent,
            separators=separators,
        )
        + "\n"
    ).encode("utf-8")


def relative_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise AuditFailure(f"path escapes the Hefferon lane: {resolved}") from exc


def require_exact_path(path: Path, expected: Path, label: str) -> Path:
    resolved = path.resolve()
    if resolved != expected.resolve():
        raise AuditFailure(f"{label} points outside its exact task path: {resolved}")
    return resolved


def load_json(path: Path, label: str) -> tuple[Any, dict[str, Any]]:
    if not path.is_file():
        raise AuditFailure(f"missing {label}: {path}")
    payload = path.read_bytes()
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditFailure(f"invalid UTF-8 JSON in {label}: {path}") from exc
    return value, {
        "path": relative_path(path),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def round_number(value: float, places: int = 8) -> float:
    return round(float(value), places)


def box_values(box: Any) -> list[float]:
    return [round_number(float(item), 4) for item in (box.left, box.bottom, box.right, box.top)]


def inspect_pdf_geometry_reader(reader: PdfReader) -> dict[str, Any]:
    page_rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    media_variants: Counter[str] = Counter()
    crop_variants: Counter[str] = Counter()
    rotation_variants: Counter[str] = Counter()
    tolerance = 0.01

    for page_number, page in enumerate(reader.pages, start=1):
        media = box_values(page.mediabox)
        crop = box_values(page.cropbox)
        try:
            rotation = int(page.rotation or 0)
        except (TypeError, ValueError):
            rotation = -1
        media_width = media[2] - media[0]
        media_height = media[3] - media[1]
        crop_width = crop[2] - crop[0]
        crop_height = crop[3] - crop[1]
        valid_dimensions = min(media_width, media_height, crop_width, crop_height) > 0
        crop_inside_media = (
            crop[0] >= media[0] - tolerance
            and crop[1] >= media[1] - tolerance
            and crop[2] <= media[2] + tolerance
            and crop[3] <= media[3] + tolerance
        )
        valid_rotation = rotation in {0, 90, 180, 270}
        valid = valid_dimensions and crop_inside_media and valid_rotation
        row = {
            "page": page_number,
            "media_box": media,
            "crop_box": crop,
            "media_width": round_number(media_width, 4),
            "media_height": round_number(media_height, 4),
            "crop_width": round_number(crop_width, 4),
            "crop_height": round_number(crop_height, 4),
            "rotation": rotation,
            "valid_dimensions": valid_dimensions,
            "crop_inside_media_box": crop_inside_media,
            "valid_rotation": valid_rotation,
            "valid": valid,
        }
        page_rows.append(row)
        media_variants[json.dumps(media, separators=(",", ":"))] += 1
        crop_variants[json.dumps(crop, separators=(",", ":"))] += 1
        rotation_variants[str(rotation)] += 1
        if not valid:
            reasons: list[str] = []
            if not valid_dimensions:
                reasons.append("nonpositive_page_box_dimension")
            if not crop_inside_media:
                reasons.append("crop_box_outside_media_box")
            if not valid_rotation:
                reasons.append("rotation_not_one_of_0_90_180_270")
            issues.append({"page": page_number, "reasons": reasons})

    return {
        "page_count": len(page_rows),
        "all_pages_valid": not issues,
        "media_box_variants": [
            {"box": json.loads(key), "count": count}
            for key, count in sorted(media_variants.items())
        ],
        "crop_box_variants": [
            {"box": json.loads(key), "count": count}
            for key, count in sorted(crop_variants.items())
        ],
        "rotation_variants": dict(sorted(rotation_variants.items(), key=lambda item: int(item[0]))),
        "issues": issues,
        "pages": page_rows,
    }


def inspect_pdf_geometry(path: Path) -> dict[str, Any]:
    """Convenience wrapper used by focused tests and independent callers."""
    return inspect_pdf_geometry_reader(PdfReader(path))


DUPLICATE_DICTIONARY_KEY = re.compile(
    r"(?:multiple\s+definitions?\s+in\s+dictionary.*?\bkey\b|"
    r"duplicate\s+(?:dictionary\s+)?(?:key|entry)|"
    r"duplicate.*?\bdictionary\b)",
    re.IGNORECASE,
)


class _ListLogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.rows: list[dict[str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.rows.append(
            {
                "logger": record.name,
                "level": record.levelname,
                "text": compact_line(record.getMessage()),
            }
        )


def _finalize_pypdf_notices(
    logger_rows: list[dict[str, str]], stderr_text: str
) -> dict[str, Any]:
    counted: Counter[tuple[str, str, str, str]] = Counter()
    for row in logger_rows:
        counted[("logger", row["logger"], row["level"], row["text"])] += 1
    for line in stderr_text.splitlines():
        text = compact_line(line)
        if text:
            counted[("stderr", "", "WARNING", text)] += 1
    notices: list[dict[str, Any]] = []
    for (channel, logger_name, level, text), count in sorted(counted.items()):
        duplicate_dictionary = bool(DUPLICATE_DICTIONARY_KEY.search(text))
        notices.append(
            {
                "channel": channel,
                "logger": logger_name or None,
                "level": level,
                "text": text,
                "count": count,
                "classification": (
                    "human_review_duplicate_dictionary_key"
                    if duplicate_dictionary
                    else "human_review_pypdf_notice"
                ),
            }
        )
    duplicate_count = sum(
        int(row["count"])
        for row in notices
        if row["classification"] == "human_review_duplicate_dictionary_key"
    )
    duplicate_group_count = sum(
        int(row["count"])
        for row in notices
        if row["classification"] == "human_review_duplicate_dictionary_key"
        and "/Group" in row["text"]
    )
    return {
        "notice_count": sum(int(row["count"]) for row in notices),
        "duplicate_dictionary_key_notice_count": duplicate_count,
        "duplicate_group_dictionary_notice_count": duplicate_group_count,
        "other_notice_count": sum(int(row["count"]) for row in notices) - duplicate_count,
        "notices": notices,
        "disposition": "human_review_evidence" if notices else "none",
    }


@contextmanager
def capture_pypdf_notices() -> Iterable[dict[str, Any]]:
    """Capture pypdf logging and direct stderr once around one full PDF read."""
    logger = logging.getLogger("pypdf")
    handler = _ListLogHandler()
    previous_level = logger.level
    previous_propagate = logger.propagate
    stderr = io.StringIO()
    result: dict[str, Any] = {}
    logger.addHandler(handler)
    if logger.getEffectiveLevel() > logging.WARNING:
        logger.setLevel(logging.WARNING)
    logger.propagate = False
    try:
        with redirect_stderr(stderr):
            yield result
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
        result.update(_finalize_pypdf_notices(handler.rows, stderr.getvalue()))


MUTOOL_PARSE_ERROR = re.compile(
    r"(?:\berror\b|syntax error|malformed|corrupt|cannot (?:open|read|parse)|"
    r"failed to|unexpected (?:eof|end)|broken xref|repair failed)",
    re.IGNORECASE,
)


def classify_mutool_stderr(stderr: str) -> dict[str, Any]:
    notices: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(stderr.splitlines(), start=1):
        text = compact_line(raw_line)
        if not text:
            continue
        duplicate_dictionary = bool(DUPLICATE_DICTIONARY_KEY.search(text))
        parse_error = bool(MUTOOL_PARSE_ERROR.search(text)) and not duplicate_dictionary
        notices.append(
            {
                "line": line_number,
                "text": text,
                "classification": (
                    "human_review_duplicate_dictionary_key"
                    if duplicate_dictionary
                    else ("hard_parse_error" if parse_error else "human_review_warning")
                ),
            }
        )
    return {
        "notices": notices,
        "hard_parse_error_count": sum(
            row["classification"] == "hard_parse_error" for row in notices
        ),
        "duplicate_dictionary_key_notice_count": sum(
            row["classification"] == "human_review_duplicate_dictionary_key"
            for row in notices
        ),
        "other_warning_count": sum(
            row["classification"] == "human_review_warning" for row in notices
        ),
    }


def run_mutool_info(path: Path) -> dict[str, Any]:
    command = ["mutool", "info", "-M", str(path)]
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {
            "command": ["mutool", "info", "-M", relative_path(path)],
            "stdout": "discarded",
            "returncode": None,
            "execution_error": type(exc).__name__,
            "stderr": {
                "notices": [],
                "hard_parse_error_count": 1,
                "duplicate_dictionary_key_notice_count": 0,
                "other_warning_count": 0,
            },
            "status": "fail",
        }
    stderr = classify_mutool_stderr(completed.stderr)
    status = (
        "fail"
        if completed.returncode != 0 or stderr["hard_parse_error_count"]
        else (
            "human_review"
            if stderr["duplicate_dictionary_key_notice_count"] or stderr["other_warning_count"]
            else "pass"
        )
    )
    return {
        "command": ["mutool", "info", "-M", relative_path(path)],
        "stdout": "discarded",
        "returncode": completed.returncode,
        "execution_error": None,
        "stderr": stderr,
        "status": status,
    }


PDFFONTS_ROW = re.compile(
    r"^(?P<name>\S+)\s+(?P<type>.+?)\s+(?P<encoding>\S+)\s+"
    r"(?P<embedded>yes|no)\s+(?P<subset>yes|no)\s+(?P<unicode>yes|no)\s+"
    r"(?P<object>\d+\s+\d+)\s*$",
    re.IGNORECASE,
)


def parse_pdffonts_output(stdout: str) -> tuple[list[dict[str, Any]], list[str]]:
    fonts: list[dict[str, Any]] = []
    unparsed: list[str] = []
    for raw_line in stdout.splitlines():
        line = raw_line.rstrip()
        if not line or line.lower().startswith("name") or set(line) <= {"-", " "}:
            continue
        match = PDFFONTS_ROW.fullmatch(line)
        if match is None:
            unparsed.append(line)
            continue
        values = match.groupdict()
        fonts.append(
            {
                "name": values["name"],
                "type": values["type"].strip(),
                "encoding": values["encoding"],
                "embedded": values["embedded"].lower() == "yes",
                "subset": values["subset"].lower() == "yes",
                "unicode_map": values["unicode"].lower() == "yes",
                "object_id": " ".join(values["object"].split()),
            }
        )
    fonts.sort(key=lambda row: (row["name"], row["object_id"], row["type"]))
    return fonts, sorted(unparsed)


def run_pdffonts(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        ["pdffonts", str(path)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    fonts, unparsed = parse_pdffonts_output(completed.stdout)
    stderr_lines = [line.strip() for line in completed.stderr.splitlines() if line.strip()]
    unembedded = [font for font in fonts if not font["embedded"]]
    return {
        "command": ["pdffonts", relative_path(path)],
        "returncode": completed.returncode,
        "font_count": len(fonts),
        "fonts": fonts,
        "unembedded_fonts": unembedded,
        "unparsed_stdout_lines": unparsed,
        "stderr_lines": stderr_lines,
        "all_fonts_embedded": completed.returncode == 0 and bool(fonts) and not unembedded and not unparsed,
        "completed_without_stderr": completed.returncode == 0 and not stderr_lines,
    }


def pdffonts_version() -> dict[str, Any]:
    completed = subprocess.run(
        ["pdffonts", "-v"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    lines = [
        line.strip()
        for line in (completed.stdout + "\n" + completed.stderr).splitlines()
        if line.strip()
    ]
    return {
        "command": ["pdffonts", "-v"],
        "returncode": completed.returncode,
        "version_line": lines[0] if lines else None,
    }


LOG_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "missing_glyph",
        re.compile(r"Missing character:|There is no .* in font", re.IGNORECASE),
    ),
    (
        "font_warning",
        re.compile(
            r"(?:LaTeX|Package .*?) Font Warning|Font shape .* undefined|"
            r"Some font shapes were not available|fontspec warning",
            re.IGNORECASE,
        ),
    ),
    (
        "undefined_reference_or_citation",
        re.compile(
            r"undefined references?|reference .* undefined|citation .* undefined",
            re.IGNORECASE,
        ),
    ),
    (
        "rerun_reference_warning",
        re.compile(r"label\(s\) may have changed|rerun to get cross-references right", re.IGNORECASE),
    ),
    (
        "runtime_placeholder",
        re.compile(
            r"Run (?:Sage|PythonTeX)|No file .*sagetex\.sout|"
            r"Non-existent (?:console|Pygments) content|"
            r"SageTeX.*(?:rerun|not processed)|PythonTeX.*(?:rerun|required)",
            re.IGNORECASE,
        ),
    ),
    (
        "overfull_box",
        re.compile(r"overfull \\[hv]box", re.IGNORECASE),
    ),
    (
        "tex_error",
        re.compile(r"^!|fatal error|emergency stop", re.IGNORECASE),
    ),
)

HARD_LOG_CATEGORIES = {
    "missing_glyph",
    "undefined_reference_or_citation",
    "rerun_reference_warning",
    "runtime_placeholder",
    "tex_error",
}


def scan_log_text(text: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        for category, pattern in LOG_PATTERNS:
            if pattern.search(line):
                hits.append(
                    {
                        "line": line_number,
                        "category": category,
                        "severity": "hard_failure" if category in HARD_LOG_CATEGORIES else "human_review",
                        "text": line,
                    }
                )
    return hits


def inspect_log(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "path": relative_path(path),
            "present": False,
            "bytes": None,
            "sha256": None,
            "hits": [],
            "counts": {},
        }
    payload = path.read_bytes()
    text = payload.decode("utf-8", errors="replace")
    hits = scan_log_text(text)
    return {
        "path": relative_path(path),
        "present": True,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "hits": hits,
        "counts": dict(sorted(Counter(hit["category"] for hit in hits).items())),
    }


ENGLISH_STRUCTURAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "document_heading",
        re.compile(
            r"^(?:table of contents|contents|index|bibliography|references|answers?|exercises?)$",
            re.IGNORECASE,
        ),
    ),
    (
        "numbered_division",
        re.compile(
            r"^(?:chapter|section|appendix)\s+(?:\d+|[IVXLCDM]+|one|two|three|four|five|six)\b.*$",
            re.IGNORECASE,
        ),
    ),
    (
        "numbered_statement",
        re.compile(
            r"^(?:definition|theorem|lemma|corollary|example|exercise|remark|figure|table)\s+"
            r"(?:[A-Za-z]+\.)?[IVXLCDM\d]+(?:[.:-][IVXLCDM\d]+)*\b.*$",
            re.IGNORECASE,
        ),
    ),
    ("proof_heading", re.compile(r"^proof\s*[.:]?$", re.IGNORECASE)),
    ("page_label", re.compile(r"^page\s+\d+\s*$", re.IGNORECASE)),
)

PLACEHOLDER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("double_question_mark", re.compile(r"\?\?")),
    ("replacement_character", re.compile("\ufffd")),
    ("work_marker", re.compile(r"\b(?:TODO|FIXME|TBD)\b", re.IGNORECASE)),
    ("lorem_ipsum", re.compile(r"\blorem ipsum\b", re.IGNORECASE)),
    (
        "runtime_instruction",
        re.compile(
            r"Run (?:Sage|PythonTeX)|SageTeX.*(?:not processed|rerun)|"
            r"Non-existent (?:console|Pygments) content",
            re.IGNORECASE,
        ),
    ),
    ("explicit_placeholder", re.compile(r"\[(?:missing|placeholder)\]", re.IGNORECASE)),
)


def compact_line(line: str, limit: int = 240) -> str:
    compact = " ".join(line.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def scan_page_text(job: str, page_number: int, text: str) -> dict[str, Any]:
    english_hits: list[dict[str, Any]] = []
    placeholder_hits: list[dict[str, Any]] = []
    lines = text.splitlines()
    for line_number, raw_line in enumerate(lines, start=1):
        line = compact_line(raw_line)
        if not line:
            continue
        for kind, pattern in ENGLISH_STRUCTURAL_PATTERNS:
            if pattern.fullmatch(line):
                english_hits.append(
                    {
                        "pdf": job,
                        "page": page_number,
                        "extracted_line": line_number,
                        "kind": kind,
                        "text": line,
                        "disposition": "human_review_required",
                    }
                )
                break
        for kind, pattern in PLACEHOLDER_PATTERNS:
            if pattern.search(line):
                placeholder_hits.append(
                    {
                        "pdf": job,
                        "page": page_number,
                        "extracted_line": line_number,
                        "kind": kind,
                        "text": line,
                        "disposition": "human_review_required",
                    }
                )
    return {
        "binding": {
            "pdf": job,
            "page": page_number,
            "characters": len(text),
            "lines": len(lines),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        },
        "english_hits": english_hits,
        "placeholder_hits": placeholder_hits,
    }


def extract_and_scan_text_reader(
    reader: PdfReader, job: str
) -> tuple[list[str], dict[str, Any]]:
    texts: list[str] = []
    bindings: list[dict[str, Any]] = []
    english_hits: list[dict[str, Any]] = []
    placeholder_hits: list[dict[str, Any]] = []
    extraction_errors: list[dict[str, Any]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # pypdf exposes several parser-specific exceptions.
            text = ""
            extraction_errors.append(
                {
                    "pdf": job,
                    "page": page_number,
                    "exception": type(exc).__name__,
                    "message": compact_line(str(exc)),
                }
            )
        texts.append(text)
        scanned = scan_page_text(job, page_number, text)
        bindings.append(scanned["binding"])
        english_hits.extend(scanned["english_hits"])
        placeholder_hits.extend(scanned["placeholder_hits"])
    return texts, {
        "page_bindings": bindings,
        "english_structural_candidates": english_hits,
        "placeholder_candidates": placeholder_hits,
        "extraction_errors": extraction_errors,
    }


def extract_and_scan_text(path: Path, job: str) -> tuple[list[str], dict[str, Any]]:
    """Convenience wrapper for an independently opened PDF."""
    return extract_and_scan_text_reader(PdfReader(path), job)


def first_matching_snippet(text: str, pattern: re.Pattern[str]) -> str | None:
    for line in text.splitlines():
        if pattern.search(line):
            return compact_line(line)
    return None


GREEK_CHARACTER = re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]")
NOTASI = re.compile(r"\bNotasi\b", re.IGNORECASE)
YUNANI = re.compile(r"\b(?:Yunani|Greek)\b", re.IGNORECASE)
INDONESIAN_EDITION_NOTE = re.compile(
    r"\b(?:catatan\s+(?:untuk\s+)?edisi\s+Indonesia|edisi\s+(?:bahasa\s+)?Indonesia)\b",
    re.IGNORECASE,
)


def pages_matching(texts: list[str], pattern: re.Pattern[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page_number, text in enumerate(texts, start=1):
        snippet = first_matching_snippet(text, pattern)
        if snippet is not None:
            rows.append({"page": page_number, "snippet": snippet})
    return rows


def semantic_spot_checks(texts_by_job: dict[str, list[str]]) -> dict[str, Any]:
    notasi: dict[str, list[dict[str, Any]]] = {}
    greek: dict[str, list[dict[str, Any]]] = {}
    edition_notes: dict[str, list[dict[str, Any]]] = {}
    for job in JOBS:
        texts = texts_by_job[job]
        notasi[job] = pages_matching(texts, NOTASI)
        edition_notes[job] = pages_matching(texts, INDONESIAN_EDITION_NOTE)
        greek_rows: list[dict[str, Any]] = []
        for page_number, text in enumerate(texts, start=1):
            characters = sorted(set(GREEK_CHARACTER.findall(text)))
            word_snippet = first_matching_snippet(text, YUNANI)
            if characters or word_snippet is not None:
                greek_rows.append(
                    {
                        "page": page_number,
                        "characters": "".join(characters),
                        "snippet": word_snippet,
                    }
                )
        greek[job] = greek_rows

    lab_texts = texts_by_job["lab"]
    dimension_pages: list[dict[str, Any]] = []
    random_code_pages: list[int] = []
    output_two_pages: list[int] = []
    output_point_57_pages: list[int] = []
    output_occurrences: list[dict[str, Any]] = []
    line_two = re.compile(r"^\s*2\s*$")
    line_point_57 = re.compile(r"^\s*0[.,]57\s*$")
    for page_number, text in enumerate(lab_texts, start=1):
        if "922" in text and "1497" in text:
            snippet = next(
                (compact_line(line) for line in text.splitlines() if "922" in line or "1497" in line),
                "",
            )
            dimension_pages.append({"page": page_number, "snippet": snippet})
        if re.search(r"import\s+random|random\.randint", text):
            random_code_pages.append(page_number)
        lines = text.splitlines()
        two_line_numbers = [
            line_number
            for line_number, line in enumerate(lines, start=1)
            if line_two.fullmatch(line)
        ]
        point_57_line_numbers = [
            line_number
            for line_number, line in enumerate(lines, start=1)
            if line_point_57.fullmatch(line)
        ]
        if two_line_numbers:
            output_two_pages.append(page_number)
            output_occurrences.extend(
                {"page": page_number, "line": line_number, "value": "2"}
                for line_number in two_line_numbers
            )
        if point_57_line_numbers:
            output_point_57_pages.append(page_number)
            output_occurrences.extend(
                {"page": page_number, "line": line_number, "value": "0.57"}
                for line_number in point_57_line_numbers
            )

    random_windows: list[dict[str, Any]] = []
    for code_page in random_code_pages:
        window = {page for page in range(max(1, code_page - 1), min(len(lab_texts), code_page + 1) + 1)}
        occurrences = sorted(
            (row for row in output_occurrences if row["page"] in window),
            key=lambda row: (row["page"], row["line"], row["value"]),
        )
        ordered_pair: list[dict[str, Any]] | None = None
        for index, row in enumerate(occurrences):
            if row["value"] != "2":
                continue
            later = next(
                (candidate for candidate in occurrences[index + 1 :] if candidate["value"] == "0.57"),
                None,
            )
            if later is not None:
                ordered_pair = [row, later]
                break
        if ordered_pair is not None:
            random_windows.append(
                {
                    "code_page": code_page,
                    "window_pages": sorted(window),
                    "ordered_output_evidence": ordered_pair,
                }
            )

    note_count = sum(len(rows) for rows in edition_notes.values())
    return {
        "notasi_pages": notasi,
        "greek_character_or_label_pages": greek,
        "indonesian_edition_note_pages": edition_notes,
        "indonesian_edition_notes_status": "found" if note_count else "human_review_missing",
        "lab_greatwave_dimensions": {
            "expected_rows": 922,
            "expected_columns": 1497,
            "pages_containing_both_values": dimension_pages,
            "status": "pass" if dimension_pages else "human_review_missing",
        },
        "lab_python_random_example": {
            "expected_output_lines": ["2", "0.57"],
            "code_pages": sorted(random_code_pages),
            "output_2_pages": sorted(output_two_pages),
            "output_0_57_pages": sorted(output_point_57_pages),
            "ordered_code_and_outputs_within_one_page_radius": random_windows,
            "status": "pass" if random_windows else "human_review_missing",
        },
    }


def inspect_render_png(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        grayscale = np.asarray(image.convert("L"), dtype=np.uint8)
    height, width = grayscale.shape
    manifest_mask = grayscale < MANIFEST_INK_THRESHOLD
    manifest_ink_fraction = round_number(float(np.count_nonzero(manifest_mask)) / grayscale.size)
    mean_luminance = round_number(float(np.mean(grayscale)), 4)

    body_top = max(0, min(height - 1, int(round(height * BODY_TOP_FRACTION))))
    body_bottom = max(body_top + 1, min(height, int(round(height * BODY_BOTTOM_FRACTION))))
    body = grayscale[body_top:body_bottom, :]
    mask = body < BODY_INK_THRESHOLD
    ink_count = int(np.count_nonzero(mask))
    body_pixels = int(mask.size)
    if ink_count:
        ys, xs = np.nonzero(mask)
        left = int(xs.min())
        right = int(xs.max()) + 1
        top = int(ys.min()) + body_top
        bottom = int(ys.max()) + 1 + body_top
        centroid_x = float(np.mean(xs))
        centroid_y = float(np.mean(ys)) + body_top
        bbox = [left, top, right, bottom]
        bbox_width = right - left
        left_gutter = left
        right_gutter = width - right
    else:
        centroid_x = None
        centroid_y = None
        bbox = None
        bbox_width = 0
        left_gutter = width
        right_gutter = width

    return {
        "width": width,
        "height": height,
        "manifest_ink_fraction": manifest_ink_fraction,
        "mean_luminance": mean_luminance,
        "fully_white_at_manifest_threshold": not bool(np.any(manifest_mask)),
        "body_band": [body_top, body_bottom],
        "body_ink_threshold": BODY_INK_THRESHOLD,
        "body_ink_pixels": ink_count,
        "body_pixels": body_pixels,
        "body_ink_fraction": round_number(ink_count / body_pixels),
        "body_ink_bbox": bbox,
        "body_bbox_width": bbox_width,
        "body_bbox_width_fraction": round_number(bbox_width / width),
        "body_centroid_x": None if centroid_x is None else round_number(centroid_x, 4),
        "body_centroid_y": None if centroid_y is None else round_number(centroid_y, 4),
        "body_centroid_x_fraction": None if centroid_x is None else round_number(centroid_x / width),
        "body_centroid_y_fraction": None if centroid_y is None else round_number(centroid_y / height),
        "left_gutter": left_gutter,
        "right_gutter": right_gutter,
        "left_gutter_fraction": round_number(left_gutter / width),
        "right_gutter_fraction": round_number(right_gutter / width),
        "body_blank": ink_count == 0,
    }


OUTLIER_FIELDS = (
    "body_centroid_x_fraction",
    "body_bbox_width_fraction",
    "body_ink_fraction",
    "inner_gutter_fraction",
    "outer_gutter_fraction",
)


def robust_reference(values: Iterable[float]) -> dict[str, float | int | None]:
    numbers = [float(value) for value in values]
    if not numbers:
        return {"count": 0, "median": None, "mad": None, "scale": None}
    median = float(statistics.median(numbers))
    mad = float(statistics.median(abs(value - median) for value in numbers))
    scale = max(1.4826 * mad, 1e-6)
    return {
        "count": len(numbers),
        "median": round_number(median),
        "mad": round_number(mad),
        "scale": round_number(scale),
    }


def annotate_layout_outliers(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    references: dict[str, Any] = {}
    outliers: list[dict[str, Any]] = []
    for parity in ("odd", "even"):
        group = [row for row in rows if row["parity"] == parity and not row["body_blank"]]
        references[parity] = {}
        for field in OUTLIER_FIELDS:
            reference = robust_reference(row[field] for row in group if row[field] is not None)
            references[parity][field] = reference
            if int(reference["count"] or 0) < 8:
                continue
            median = float(reference["median"])
            scale = float(reference["scale"])
            for row in group:
                if row[field] is None:
                    continue
                robust_z = abs(float(row[field]) - median) / scale
                if robust_z >= ROBUST_OUTLIER_Z:
                    outliers.append(
                        {
                            "pdf": row["pdf"],
                            "page": row["page"],
                            "parity": parity,
                            "metric": field,
                            "value": row[field],
                            "reference_median": reference["median"],
                            "reference_mad": reference["mad"],
                            "robust_z": round_number(robust_z, 4),
                            "disposition": "human_review_required",
                        }
                    )
    outliers.sort(
        key=lambda row: (-float(row["robust_z"]), JOB_ORDER[row["pdf"]], int(row["page"]), row["metric"])
    )
    return references, outliers


def bind_render_manifest(
    manifest: Any,
    build_report: dict[str, Any],
    hard_failures: list[str],
) -> tuple[
    dict[str, Any],
    dict[str, list[dict[str, Any]]],
]:
    if not isinstance(manifest, list):
        raise AuditFailure("all-page render manifest must be a JSON array")
    rows_by_job: dict[str, list[dict[str, Any]]] = {job: [] for job in JOBS}
    seen: set[tuple[str, int]] = set()
    bound_rows: list[dict[str, Any]] = []

    for source_row in manifest:
        if not isinstance(source_row, dict):
            raise AuditFailure("all-page render manifest contains a non-object row")
        job = str(source_row.get("pdf"))
        if job not in JOBS:
            raise AuditFailure(f"unexpected render-manifest PDF id: {job!r}")
        page = int(source_row.get("page"))
        key = (job, page)
        if key in seen:
            raise AuditFailure(f"duplicate render-manifest row: {job} page {page}")
        seen.add(key)
        row_path_text = source_row.get("path")
        if not isinstance(row_path_text, str):
            raise AuditFailure(f"render row lacks a path: {job} page {page}")
        path = (PROJECT_ROOT / Path(row_path_text)).resolve()
        expected_parent = (RENDER_ROOT / job).resolve()
        if path.parent != expected_parent or not re.fullmatch(r"page-\d+\.png", path.name):
            raise AuditFailure(f"render row escapes exact page directory: {path}")
        filename_page = int(path.stem.split("-")[-1])
        if filename_page != page:
            raise AuditFailure(f"render filename/page mismatch: {path.name} versus {page}")
        if not path.is_file():
            raise AuditFailure(f"manifest-addressed page render is missing: {path}")
        current_bytes = path.stat().st_size
        current_sha = sha256_path(path)
        metrics = inspect_render_png(path)
        expected_bytes = int(source_row.get("bytes"))
        expected_sha = str(source_row.get("sha256"))
        metrics_match = (
            int(source_row.get("width")) == metrics["width"]
            and int(source_row.get("height")) == metrics["height"]
            and float(source_row.get("ink_fraction")) == metrics["manifest_ink_fraction"]
            and float(source_row.get("mean_luminance")) == metrics["mean_luminance"]
            and bool(source_row.get("fully_white")) == metrics["fully_white_at_manifest_threshold"]
        )
        bytes_match = current_bytes == expected_bytes
        sha_match = current_sha == expected_sha
        if not bytes_match or not sha_match or not metrics_match:
            hard_failures.append(f"render_manifest_mismatch:{job}:page_{page}")
        parity = "odd" if page % 2 else "even"
        inner = metrics["left_gutter_fraction"] if parity == "odd" else metrics["right_gutter_fraction"]
        outer = metrics["right_gutter_fraction"] if parity == "odd" else metrics["left_gutter_fraction"]
        row = {
            "pdf": job,
            "page": page,
            "parity": parity,
            "path": relative_path(path),
            "expected_bytes": expected_bytes,
            "current_bytes": current_bytes,
            "bytes_match": bytes_match,
            "expected_sha256": expected_sha,
            "current_sha256": current_sha,
            "sha256_match": sha_match,
            "manifest_metrics_match": metrics_match,
            **metrics,
            "inner_gutter_fraction": inner,
            "outer_gutter_fraction": outer,
        }
        rows_by_job[job].append(row)
        bound_rows.append(
            {
                "pdf": job,
                "page": page,
                "path": relative_path(path),
                "bytes": current_bytes,
                "sha256": current_sha,
            }
        )

    for job in JOBS:
        rows_by_job[job].sort(key=lambda row: row["page"])
        expected_pages = int(build_report["pdfs"][job]["pages"])
        pages = [int(row["page"]) for row in rows_by_job[job]]
        if pages != list(range(1, expected_pages + 1)):
            hard_failures.append(f"render_page_closure_mismatch:{job}")

    bound_rows.sort(key=lambda row: (JOB_ORDER[row["pdf"]], row["page"]))
    current_payload = canonical_json_bytes(bound_rows)
    return {
        "row_count": len(bound_rows),
        "all_rows_match": not any(item.startswith("render_") for item in hard_failures),
        "current_inventory_sha256": hashlib.sha256(current_payload).hexdigest(),
        "rows": bound_rows,
    }, rows_by_job


def add_candidate(
    candidates: dict[tuple[str, int], dict[str, Any]],
    job: str,
    page: int,
    reason: str,
    score: float,
    *,
    automatic_failure: bool = False,
) -> None:
    key = (job, int(page))
    candidate = candidates.setdefault(
        key,
        {
            "pdf": job,
            "page": int(page),
            "score": 0.0,
            "automatic_failure": False,
            "reasons": [],
        },
    )
    if reason not in candidate["reasons"]:
        candidate["reasons"].append(reason)
        candidate["score"] += float(score)
    candidate["automatic_failure"] = candidate["automatic_failure"] or automatic_failure


def rank_candidates(candidates: dict[tuple[str, int], dict[str, Any]]) -> list[dict[str, Any]]:
    rows = list(candidates.values())
    for row in rows:
        row["score"] = round_number(row["score"], 4)
        row["reasons"].sort()
        row["disposition"] = (
            "automatic_integrity_failure"
            if row["automatic_failure"]
            else "human_visual_review_required"
        )
    rows.sort(
        key=lambda row: (
            not bool(row["automatic_failure"]),
            -float(row["score"]),
            JOB_ORDER[row["pdf"]],
            int(row["page"]),
        )
    )
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def build_audit_report() -> dict[str, Any]:
    hard_failures: list[str] = []
    review_findings: list[str] = []
    candidates: dict[tuple[str, int], dict[str, Any]] = {}

    build_report_value, build_binding = load_json(BUILD_REPORT_PATH, "build report")
    if not isinstance(build_report_value, dict):
        raise AuditFailure("build report root must be an object")
    build_report: dict[str, Any] = build_report_value
    if build_report.get("status") != "success":
        hard_failures.append(f"build_report_status:{build_report.get('status')!r}")
    if set(build_report.get("pdfs", {})) != set(JOBS):
        raise AuditFailure("build report does not bind exactly book, jhanswer, and lab")

    report_manifest = build_report.get("all_page_render_manifest", {})
    report_manifest_path = Path(str(report_manifest.get("path", "")))
    require_exact_path(report_manifest_path, RENDER_MANIFEST_PATH, "build-report render manifest")
    render_manifest, render_manifest_binding = load_json(
        RENDER_MANIFEST_PATH, "all-page render manifest"
    )
    if (
        int(report_manifest.get("manifest_bytes", -1)) != render_manifest_binding["bytes"]
        or str(report_manifest.get("manifest_sha256")) != render_manifest_binding["sha256"]
    ):
        hard_failures.append("build_report_render_manifest_binding_mismatch")

    pdf_bindings: dict[str, Any] = {}
    geometry: dict[str, Any] = {}
    fonts: dict[str, Any] = {}
    font_tool = pdffonts_version()
    if font_tool["returncode"] != 0 or not font_tool["version_line"]:
        hard_failures.append("pdffonts_version_probe_failed")
    texts_by_job: dict[str, list[str]] = {}
    text_audit: dict[str, Any] = {}
    logs: dict[str, Any] = {}
    pypdf_notices: dict[str, Any] = {}
    mutool_parse: dict[str, Any] = {}

    for job in JOBS:
        path = EXPECTED_PDFS[job]
        if not path.is_file():
            raise AuditFailure(f"missing final PDF: {path}")
        report_pdf = build_report["pdfs"][job]
        report_pdf_path = Path(str(report_pdf.get("path", "")))
        require_exact_path(report_pdf_path, path, f"build-report {job} PDF")
        current_bytes = path.stat().st_size
        current_sha = sha256_path(path)
        with capture_pypdf_notices() as captured_notices:
            reader = PdfReader(path)
            current_pages = len(reader.pages)
            geometry[job] = inspect_pdf_geometry_reader(reader)
            texts, job_text_audit = extract_and_scan_text_reader(reader, job)
        pypdf_notices[job] = captured_notices
        if captured_notices["duplicate_dictionary_key_notice_count"]:
            review_findings.append(
                "pypdf_duplicate_dictionary_key_notices:"
                f"{job}:{captured_notices['duplicate_dictionary_key_notice_count']}"
            )
        if captured_notices["other_notice_count"]:
            review_findings.append(
                f"pypdf_other_notices:{job}:{captured_notices['other_notice_count']}"
            )

        mutool_parse[job] = run_mutool_info(path)
        if mutool_parse[job]["status"] == "fail":
            hard_failures.append(f"mutool_info_parse_failure:{job}")
        elif mutool_parse[job]["status"] == "human_review":
            review_findings.append(f"mutool_info_stderr_requires_review:{job}")

        bytes_match = current_bytes == int(report_pdf.get("bytes", -1))
        sha_match = current_sha == str(report_pdf.get("sha256"))
        pages_match = current_pages == int(report_pdf.get("pages", -1))
        if not (bytes_match and sha_match and pages_match):
            hard_failures.append(f"build_report_pdf_binding_mismatch:{job}")
        pdf_bindings[job] = {
            "path": relative_path(path),
            "bytes": current_bytes,
            "sha256": current_sha,
            "pages": current_pages,
            "build_report_bytes_match": bytes_match,
            "build_report_sha256_match": sha_match,
            "build_report_pages_match": pages_match,
        }

        if geometry[job]["page_count"] != current_pages:
            hard_failures.append(f"geometry_page_count_mismatch:{job}")
        if not geometry[job]["all_pages_valid"]:
            hard_failures.append(f"invalid_page_geometry:{job}")
        for issue in geometry[job]["issues"]:
            add_candidate(
                candidates,
                job,
                issue["page"],
                "invalid_page_geometry:" + ",".join(issue["reasons"]),
                100,
                automatic_failure=True,
            )

        fonts[job] = run_pdffonts(path)
        if not fonts[job]["all_fonts_embedded"]:
            hard_failures.append(f"font_embedding_or_inventory_failure:{job}")
        if fonts[job]["stderr_lines"]:
            review_findings.append(f"pdffonts_stderr_requires_review:{job}")

        texts_by_job[job] = texts
        text_audit[job] = job_text_audit
        if job_text_audit["extraction_errors"]:
            hard_failures.append(f"page_text_extraction_failure:{job}")
        for hit in job_text_audit["english_structural_candidates"]:
            add_candidate(
                candidates,
                job,
                hit["page"],
                f"english_structural_candidate:{hit['kind']}",
                8,
            )
        for hit in job_text_audit["placeholder_candidates"]:
            add_candidate(
                candidates,
                job,
                hit["page"],
                f"placeholder_candidate:{hit['kind']}",
                12,
            )

        logs[job] = inspect_log(EXPECTED_LOGS[job])
        if not logs[job]["present"]:
            hard_failures.append(f"missing_final_tex_log:{job}")
        for hit in logs[job]["hits"]:
            if hit["severity"] == "hard_failure":
                hard_failures.append(
                    f"final_tex_log:{job}:{hit['category']}:line_{hit['line']}"
                )

    render_binding, render_rows_by_job = bind_render_manifest(
        render_manifest, build_report, hard_failures
    )
    if int(report_manifest.get("count", -1)) != render_binding["row_count"]:
        hard_failures.append("build_report_render_count_mismatch")

    layout: dict[str, Any] = {}
    for job in JOBS:
        rows = render_rows_by_job[job]
        references, outliers = annotate_layout_outliers(rows)
        blank_pages: list[dict[str, Any]] = []
        text_bindings = {row["page"]: row for row in text_audit[job]["page_bindings"]}
        for row in rows:
            if row["body_blank"]:
                binding = text_bindings[row["page"]]
                likely_front_matter = row["page"] <= 6
                possible_intentional = likely_front_matter or int(binding["characters"]) < 80
                blank_pages.append(
                    {
                        "page": row["page"],
                        "likely_front_matter": likely_front_matter,
                        "possible_intentional_blank_or_title_page": possible_intentional,
                        "automatic_failure": False,
                        "disposition": "human_review_if_unexpected",
                    }
                )
                add_candidate(candidates, job, row["page"], "body_band_has_no_ink", 0.25)
        for outlier in outliers:
            add_candidate(
                candidates,
                job,
                outlier["page"],
                f"layout_outlier:{outlier['metric']}:z={outlier['robust_z']}",
                min(float(outlier["robust_z"]), 30),
            )
        layout[job] = {
            "method": {
                "render_dpi": 72,
                "body_vertical_fraction": [BODY_TOP_FRACTION, BODY_BOTTOM_FRACTION],
                "ink_luminance_threshold_exclusive": BODY_INK_THRESHOLD,
                "parity_gutter_rule": {
                    "odd": {"inner": "left", "outer": "right"},
                    "even": {"inner": "right", "outer": "left"},
                },
                "outlier_method": "absolute robust z using parity median and 1.4826*MAD",
                "outlier_threshold": ROBUST_OUTLIER_Z,
            },
            "parity_reference": references,
            "outliers": outliers,
            "blank_body_pages": blank_pages,
            "pages": rows,
        }

    semantic = semantic_spot_checks(texts_by_job)
    for job in JOBS:
        for row in semantic["notasi_pages"][job]:
            add_candidate(candidates, job, row["page"], "semantic_spot_check:notasi", 1.5)
        greek_rows = semantic["greek_character_or_label_pages"][job]
        if greek_rows:
            for row in (greek_rows[0], greek_rows[-1]):
                add_candidate(candidates, job, row["page"], "semantic_spot_check:greek", 1)
        for row in semantic["indonesian_edition_note_pages"][job]:
            add_candidate(
                candidates, job, row["page"], "semantic_spot_check:indonesian_edition_note", 2
            )
    for row in semantic["lab_greatwave_dimensions"]["pages_containing_both_values"]:
        add_candidate(candidates, "lab", row["page"], "semantic_spot_check:greatwave_922x1497", 3)
    random_check = semantic["lab_python_random_example"]
    for page in sorted(set(random_check["code_pages"] + random_check["output_2_pages"] + random_check["output_0_57_pages"])):
        add_candidate(candidates, "lab", page, "semantic_spot_check:python_random_output", 3)

    english_count = sum(
        len(text_audit[job]["english_structural_candidates"]) for job in JOBS
    )
    placeholder_count = sum(len(text_audit[job]["placeholder_candidates"]) for job in JOBS)
    log_review_count = sum(
        sum(hit["severity"] == "human_review" for hit in logs[job]["hits"]) for job in JOBS
    )
    layout_outlier_count = sum(len(layout[job]["outliers"]) for job in JOBS)
    blank_count = sum(len(layout[job]["blank_body_pages"]) for job in JOBS)
    if english_count:
        review_findings.append(f"english_structural_candidates:{english_count}")
    if placeholder_count:
        review_findings.append(f"placeholder_candidates:{placeholder_count}")
    if log_review_count:
        review_findings.append(f"font_or_overfull_log_review_lines:{log_review_count}")
    if layout_outlier_count:
        review_findings.append(f"layout_outliers:{layout_outlier_count}")
    if blank_count:
        review_findings.append(f"blank_body_pages_not_auto_failed:{blank_count}")
    if semantic["indonesian_edition_notes_status"] != "found":
        review_findings.append("indonesian_edition_notes_not_found_in_extracted_text")
    if semantic["lab_greatwave_dimensions"]["status"] != "pass":
        review_findings.append("lab_greatwave_922x1497_not_found_in_extracted_text")
    if semantic["lab_python_random_example"]["status"] != "pass":
        review_findings.append("lab_python_random_2_and_0_57_not_jointly_found")

    hard_failures = sorted(set(hard_failures))
    review_findings = sorted(set(review_findings))
    ranked = rank_candidates(candidates)
    status = "fail" if hard_failures else ("human_review_required" if review_findings else "pass")
    reproducibility = dict(build_report.get("reproducibility") or {})
    reproducibility_path = reproducibility.get("path")
    if reproducibility_path:
        resolved_reproducibility_path = Path(str(reproducibility_path))
        if not resolved_reproducibility_path.is_absolute():
            resolved_reproducibility_path = PROJECT_ROOT / resolved_reproducibility_path
        reproducibility["path"] = relative_path(resolved_reproducibility_path)

    return {
        "schema_version": "hefferon-id-final-pdf-qa-v1",
        "status": status,
        "scope": {
            "project_root": ".",
            "input_policy": "read_only_exact_build_report_pdfs_logs_and_manifest_addressed_page_pngs",
            "output": relative_path(OUTPUT_REPORT_PATH),
            "pdfs": list(JOBS),
        },
        "bindings": {
            "build_report": {
                **build_binding,
                "status": build_report.get("status"),
                "source_tree_sha256": build_report.get("source", {}).get("tree_sha256"),
                "qa_summary": build_report.get("qa_summary"),
                "reproducibility": reproducibility,
            },
            "all_page_render_manifest": render_manifest_binding,
            "pdfs": pdf_bindings,
            "current_render_png_inventory": render_binding,
        },
        "page_geometry": geometry,
        "pdf_parser_notices": {
            "pypdf": pypdf_notices,
            "mutool_info_dimensions": mutool_parse,
        },
        "embedded_fonts": {"tool": font_tool, "pdfs": fonts},
        "final_tex_logs": logs,
        "text_audit": {
            "policy": (
                "conservative page-level candidates only; bibliography, code, mathematical notation, "
                "intentional English, and front matter require human disposition"
            ),
            "pdfs": text_audit,
        },
        "semantic_spot_checks": semantic,
        "layout_audit": layout,
        "ranked_candidate_pages": ranked,
        "hard_failures": hard_failures,
        "review_findings": review_findings,
        "summary": {
            "pdf_count": len(pdf_bindings),
            "pdf_pages": sum(int(row["pages"]) for row in pdf_bindings.values()),
            "render_png_count": render_binding["row_count"],
            "all_pdf_bytes_match_build_report": all(
                row["build_report_bytes_match"] and row["build_report_sha256_match"]
                for row in pdf_bindings.values()
            ),
            "all_pdf_page_counts_match_build_report": all(
                row["build_report_pages_match"] for row in pdf_bindings.values()
            ),
            "all_render_pngs_match_manifest": render_binding["all_rows_match"],
            "all_page_geometry_valid": all(
                geometry[job]["all_pages_valid"] for job in JOBS
            ),
            "mutool_parse_checks_pass_or_review_only": all(
                mutool_parse[job]["status"] != "fail" for job in JOBS
            ),
            "pypdf_notice_count": sum(
                int(pypdf_notices[job]["notice_count"]) for job in JOBS
            ),
            "pypdf_duplicate_group_dictionary_notice_count": sum(
                int(pypdf_notices[job]["duplicate_group_dictionary_notice_count"])
                for job in JOBS
            ),
            "all_fonts_embedded": all(fonts[job]["all_fonts_embedded"] for job in JOBS),
            "hard_log_diagnostic_count": sum(
                sum(hit["severity"] == "hard_failure" for hit in logs[job]["hits"])
                for job in JOBS
            ),
            "human_review_log_diagnostic_count": log_review_count,
            "english_structural_candidate_count": english_count,
            "placeholder_candidate_count": placeholder_count,
            "layout_outlier_count": layout_outlier_count,
            "blank_body_page_count": blank_count,
            "ranked_candidate_page_count": len(ranked),
            "hard_failure_count": len(hard_failures),
            "review_finding_count": len(review_findings),
        },
    }


def write_report(report: dict[str, Any]) -> dict[str, Any]:
    if QA_ROOT.resolve() != OUTPUT_REPORT_PATH.parent.resolve():
        raise AuditFailure("QA report output path escaped its exact task directory")
    QA_ROOT.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(report, indent=2)
    OUTPUT_REPORT_PATH.write_bytes(payload)
    return {
        "path": relative_path(OUTPUT_REPORT_PATH),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def main() -> int:
    if len(sys.argv) != 1:
        raise AuditFailure("this task-local auditor accepts no path or scope overrides")
    report = build_audit_report()
    artifact = write_report(report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "hard_failure_count": report["summary"]["hard_failure_count"],
                "review_finding_count": report["summary"]["review_finding_count"],
                "report": artifact,
            },
            sort_keys=True,
        )
    )
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuditFailure as exc:
        print(f"FINAL PDF AUDIT FAILED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
