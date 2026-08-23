"""Independently validate the emitted Hefferon modular backend.

This verifier does not import the generator.  It checks serialized bytes,
cross-file identities, topology, source/target hashes, component rights, and
the optional final-build gate directly from the published projections.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


BACKEND = Path(__file__).resolve().parent
LANE = BACKEND.parent
AUTHORITY = (
    LANE
    / "authority"
    / "extracted"
    / "linear-algebra-df2262e089a02651c127f1dd12649c4622ee1383"
)
TARGET = LANE / "source" / "linear-algebra"
TERMINOLOGY_LEDGER = LANE / "00_control" / "TERMINOLOGY.csv"
BUILD_ROOT = LANE / "build" / "hefferon_id"
BUILD_REPORT_PATH = BUILD_ROOT / "build_report.json"
BUILD_PDF_ROOT = BUILD_ROOT / "output" / "pdf"
CROSS_PDF_LINK_AUDIT_PATH = BUILD_ROOT / "cross_pdf_link_audit.json"
LAB_SAGETEX_RUNTIME_MANIFEST_PATH = (
    BUILD_ROOT / "lab_sagetex_runtime_manifest.json"
)
SCHEMA = "hefferon-modular-backend"
SCHEMA_VERSION = "0.5.2"
WORKFLOW_ID = "hefferon-id.complete-corpus-index.v7"
PRODUCTION_PROVENANCE = "OpenAI Codex gpt-5.6-sol, Ultra."
TARGET_EDITION_ID = (
    "r005.hefferon-linear-algebra.edition.derivative.locale.id-id.df2262e"
)
TARGET_PDF_ARTIFACT_IDS = {
    "r005.hefferon-linear-algebra.artifact.answer-pdf.locale.id-id",
    "r005.hefferon-linear-algebra.artifact.sage-lab-pdf.locale.id-id",
    "r005.hefferon-linear-algebra.artifact.textbook-pdf.locale.id-id",
}
FINAL_PDF_SPECS = {
    "r005.hefferon-linear-algebra.artifact.answer-pdf.locale.id-id": (
        "answer-book-shell",
        "jhanswer",
        "jhanswer.pdf",
    ),
    "r005.hefferon-linear-algebra.artifact.sage-lab-pdf.locale.id-id": (
        "sage-lab",
        "lab",
        "lab.pdf",
    ),
    "r005.hefferon-linear-algebra.artifact.textbook-pdf.locale.id-id": (
        "main-textbook",
        "book",
        "book.pdf",
    ),
}
NATIVE_UPSTREAM_ANSWER_COUNT = 1035
TARGET_SUPPLIED_ANSWER_COUNT = 2
EXPECTED_CROSS_PDF_ANSWER_LINKS = 1032
TARGET_SUPPLIED_ANSWER_ANCHORS = {
    "ans.One.V.0.5",
    "ans.One.V.0.6",
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
REQUIRED_TERMINOLOGY_DECISIONS = {
    "HLA-T0113": {
        "english": "null space",
        "preferred_id": "ruang nol",
        "variants": "kernel",
        "rejected": "ruang kosong",
        "scope": "linear_maps",
        "status": "admitted",
        "evidence": (
            "src/map/map2.tex; DOI 10.21070/2020/978-623-6833-41-4 PDF p. 145"
        ),
    },
    "HLA-T0114": {
        "english": "nullity",
        "preferred_id": "nulitas",
        "variants": "kekosongan",
        "rejected": "nullitas",
        "scope": "linear_maps",
        "status": "admitted",
        "evidence": (
            "src/map/map2.tex; DOI 10.21070/2020/978-623-6833-41-4 PDF p. 148"
        ),
    },
}

BASE_FIELDS = {
    "recorded_on",
    "responsible_workflow",
    "schema",
    "schema_version",
    "status",
    "supersedes",
}
ENTITY_EXPORTS = {
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
}
TRANSLATION_STATES = {
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
}
RELATION_TYPES = {
    "adapts",
    "answers",
    "contains",
    "corrects",
    "depends-on",
    "exercises",
    "hints",
    "illustrates",
    "precedes",
    "prerequisite",
    "proves",
    "solves",
    "supersedes",
    "translates",
    "xref",
}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def fail(message: str) -> None:
    raise RuntimeError(message)


def load_jsonl(path: Path) -> list[dict]:
    payload = path.read_bytes()
    if b"\r" in payload or not payload.endswith(b"\n"):
        fail(f"{path.name}: not canonical LF-terminated UTF-8")
    try:
        text = payload.decode("utf-8")
        records = [json.loads(line) for line in text.splitlines()]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{path.name}: invalid JSONL: {exc}")
    expected = "".join(canonical_json(record) + "\n" for record in records).encode(
        "utf-8"
    )
    if payload != expected:
        fail(f"{path.name}: noncanonical JSONL serialization")
    return records


def load_json(path: Path) -> dict:
    payload = path.read_bytes()
    if b"\r" in payload or not payload.endswith(b"\n"):
        fail(f"{path.name}: not canonical LF-terminated UTF-8")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{path.name}: invalid JSON: {exc}")
    if payload != (canonical_json(value) + "\n").encode("utf-8"):
        fail(f"{path.name}: noncanonical JSON serialization")
    if not isinstance(value, dict):
        fail(f"{path.name}: JSON root must be an object")
    return value


def load_external_json(path: Path, label: str) -> tuple[bytes, dict]:
    """Read a live build receipt without assuming backend canonical formatting."""

    try:
        payload = path.read_bytes()
    except OSError as exc:
        fail(f"{label}: cannot read live receipt: {exc}")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{label}: invalid UTF-8 JSON: {exc}")
    if not isinstance(value, dict):
        fail(f"{label}: JSON root must be an object")
    return payload, value


def is_sha256_hex(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def path_matches_receipt(value: object, locator: str) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.replace("\\", "/")
    return normalized == locator or normalized.endswith("/" + locator)


def exact_int(mapping: dict, key: str, expected: int) -> bool:
    """Reject bool-as-int coercion while checking an exact receipt count."""

    value = mapping.get(key)
    return type(value) is int and value == expected


def validate_final_build_live_receipts(
    build_witness: dict, reader_artifacts: list[dict]
) -> None:
    """Replay final-build report and sidecar bytes independently of the generator."""

    if not isinstance(build_witness, dict):
        fail("final-build witness must be an object")
    report_payload, report = load_external_json(BUILD_REPORT_PATH, "build report")
    reported_report_sha = build_witness.get("build_report_sha256")
    if (
        not is_sha256_hex(reported_report_sha)
        or reported_report_sha != sha256(report_payload)
        or report.get("status") != "success"
    ):
        fail("final-build witness is not bound to the live successful build report")

    report_qa = report.get("qa_summary")
    witness_qa = build_witness.get("qa_summary")
    if (
        not isinstance(report_qa, dict)
        or report_qa != witness_qa
        or not exact_int(report_qa, "undefined_reference_lines", 0)
        or not exact_int(report_qa, "generated_english_label_hits", 0)
        or not exact_int(report_qa, "runtime_placeholder_lines", 0)
        or not exact_int(build_witness, "runtime_placeholder_lines", 0)
    ):
        fail("live build report lacks zero diagnostic/runtime closure")

    link_payload, link_audit = load_external_json(
        CROSS_PDF_LINK_AUDIT_PATH, "cross-PDF link audit"
    )
    link_sha = sha256(link_payload)
    cross_pdf = build_witness.get("cross_pdf_link_audit")
    report_link = report.get("cross_pdf_link_audit")
    expected_link_locator = "build/hefferon_id/cross_pdf_link_audit.json"
    if not isinstance(cross_pdf, dict) or not isinstance(report_link, dict):
        fail("cross-PDF link witnesses must be objects")
    if (
        cross_pdf.get("locator") != expected_link_locator
        or type(cross_pdf.get("bytes")) is not int
        or cross_pdf.get("bytes") != len(link_payload)
        or not is_sha256_hex(cross_pdf.get("sha256"))
        or cross_pdf.get("sha256") != link_sha
        or not path_matches_receipt(report_link.get("path"), expected_link_locator)
        or type(report_link.get("bytes")) is not int
        or report_link.get("bytes") != len(link_payload)
        or not is_sha256_hex(report_link.get("sha256"))
        or report_link.get("sha256") != link_sha
        or report_link.get("all_pair_actions_resolved") is not True
        or link_audit.get("all_pair_actions_resolved") is not True
        or report_link.get("counts") != link_audit.get("counts")
    ):
        fail("cross-PDF link witness is stale or malformed")
    link_counts = link_audit.get("counts")
    link_actions = link_audit.get("actions")
    unresolved_actions = link_audit.get("unresolved_pair_actions")
    expected_link_counts = {
        "book_to_jhanswer": EXPECTED_CROSS_PDF_ANSWER_LINKS,
        "jhanswer_to_book": EXPECTED_CROSS_PDF_ANSWER_LINKS,
        "goto_remote_actions": 2 * EXPECTED_CROSS_PDF_ANSWER_LINKS,
        "unresolved_pair_actions": 0,
    }
    if (
        not isinstance(link_counts, dict)
        or not isinstance(link_actions, list)
        or not isinstance(unresolved_actions, list)
        or any(
            not exact_int(link_counts, key, expected)
            for key, expected in expected_link_counts.items()
        )
        or len(link_actions) != 2 * EXPECTED_CROSS_PDF_ANSWER_LINKS
        or unresolved_actions
        or cross_pdf.get("all_pair_actions_resolved") is not True
        or not exact_int(
            cross_pdf,
            "answer_links_each_direction",
            EXPECTED_CROSS_PDF_ANSWER_LINKS,
        )
        or not exact_int(
            cross_pdf,
            "goto_remote_actions",
            2 * EXPECTED_CROSS_PDF_ANSWER_LINKS,
        )
        or not exact_int(cross_pdf, "unresolved_pair_actions", 0)
    ):
        fail("cross-PDF link sidecar fails exact answer-link closure")

    runtime_payload, runtime_sidecar = load_external_json(
        LAB_SAGETEX_RUNTIME_MANIFEST_PATH, "SageTeX runtime manifest"
    )
    runtime_sha = sha256(runtime_payload)
    lab_runtime = build_witness.get("lab_sagetex_runtime")
    runtime = report.get("lab_sagetex")
    expected_runtime_locator = (
        "build/hefferon_id/lab_sagetex_runtime_manifest.json"
    )
    if not isinstance(lab_runtime, dict) or not isinstance(runtime, dict):
        fail("SageTeX runtime witnesses must be objects")
    runtime_artifact = runtime.get("manifest_artifact")
    if not isinstance(runtime_artifact, dict):
        fail("live build report lacks a SageTeX manifest artifact")
    if (
        lab_runtime.get("locator") != expected_runtime_locator
        or type(lab_runtime.get("bytes")) is not int
        or lab_runtime.get("bytes") != len(runtime_payload)
        or not is_sha256_hex(lab_runtime.get("sha256"))
        or lab_runtime.get("sha256") != runtime_sha
        or not path_matches_receipt(runtime_artifact.get("path"), expected_runtime_locator)
        or type(runtime_artifact.get("bytes")) is not int
        or runtime_artifact.get("bytes") != len(runtime_payload)
        or not is_sha256_hex(runtime_artifact.get("sha256"))
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
        fail("SageTeX runtime witness is stale or malformed")

    runtime_outputs = runtime_sidecar.get("outputs")
    runtime_figures = runtime_sidecar.get("figure_execution")
    report_stable = runtime.get("stable_fingerprint")
    sidecar_stable = runtime_sidecar.get("stable_fingerprint")
    runtime_pythontex = runtime.get("pythontex")
    restored_graphics = runtime.get("post_execution_authority_graphics")
    lab_graphics = report.get("lab_graphics")
    if (
        not isinstance(runtime_outputs, dict)
        or not isinstance(runtime_figures, dict)
        or not isinstance(report_stable, dict)
        or not isinstance(sidecar_stable, dict)
        or not isinstance(runtime_pythontex, dict)
        or not isinstance(restored_graphics, dict)
        or not isinstance(lab_graphics, dict)
    ):
        fail("SageTeX/PythonTeX runtime closure contains malformed objects")
    runtime_scmd = runtime_outputs.get("scmd")
    if not isinstance(runtime_scmd, dict):
        fail("SageTeX runtime scmd receipt must be an object")
    expected_runtime_counts = {
        "command_label_count": 148,
        "command_label_first": 0,
        "command_label_last": 147,
        "command_source_listing_count": 1018,
        "maximum_listed_source_line": 1236,
    }
    sage_only_stable = dict(report_stable)
    pythontex_stable = sage_only_stable.pop("pythontex", None)
    restored_manifest_sha = restored_graphics.get("manifest_sha256")
    if (
        any(
            not exact_int(runtime_outputs, key, expected)
            for key, expected in expected_runtime_counts.items()
        )
        or not exact_int(runtime_scmd, "line_count", 1237)
        or not exact_int(runtime_figures, "target_count", 64)
        or not exact_int(runtime_figures, "changed_from_authority_count", 63)
        or runtime_figures.get("unchanged_from_authority_paths")
        != ["asy/ellipsoid1.pdf"]
        or runtime_figures.get("final_state")
        != "all_64_pinned_authority_figures_restored_and_rehashed"
        or sage_only_stable != sidecar_stable
        or runtime_pythontex.get("status") != "pass"
        or runtime_pythontex.get("success_line")
        != "PythonTeX:  lab - 0 error(s), 0 warning(s)"
        or runtime_pythontex.get("stable_fingerprint") != pythontex_stable
        or not exact_int(restored_graphics, "count", 64)
        or not is_sha256_hex(restored_manifest_sha)
        or restored_manifest_sha != lab_graphics.get("manifest_sha256")
        or not exact_int(lab_runtime, "command_labels", 148)
        or not exact_int(lab_runtime, "command_source_listings", 1018)
        or not exact_int(lab_runtime, "maximum_listed_source_line", 1236)
        or not exact_int(lab_runtime, "scmd_lines", 1237)
        or not exact_int(lab_runtime, "sage_changed_figures", 63)
        or not exact_int(lab_runtime, "authority_figures_restored", 64)
        or lab_runtime.get("pythontex_zero_errors_warnings") is not True
    ):
        fail("SageTeX/PythonTeX runtime fails exact live-receipt closure")

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        fail(f"final-build PDF replay requires pypdf: {exc}")
    artifact_map = {artifact.get("id"): artifact for artifact in reader_artifacts}
    report_pdfs = report.get("pdfs")
    witness_pdfs = build_witness.get("pdfs")
    if (
        set(artifact_map) != set(FINAL_PDF_SPECS)
        or not isinstance(report_pdfs, dict)
        or not isinstance(witness_pdfs, dict)
    ):
        fail("final-build PDF receipts are incomplete")
    for artifact_id, (component, job, filename) in FINAL_PDF_SPECS.items():
        artifact = artifact_map[artifact_id]
        report_pdf = report_pdfs.get(job)
        witness_pdf = witness_pdfs.get(component)
        if not isinstance(report_pdf, dict) or not isinstance(witness_pdf, dict):
            fail(f"{artifact_id}: PDF report/witness receipt is missing")
        pdf_path = BUILD_PDF_ROOT / filename
        try:
            pdf_payload = pdf_path.read_bytes()
        except OSError as exc:
            fail(f"{artifact_id}: cannot read live PDF: {exc}")
        pdf_sha = sha256(pdf_payload)
        locator = f"build/hefferon_id/output/pdf/{filename}"
        try:
            page_count = len(PdfReader(io.BytesIO(pdf_payload)).pages)
        except Exception as exc:
            fail(f"{artifact_id}: live PDF cannot be parsed: {exc}")
        for label, receipt, page_key in (
            ("artifact", artifact, "page_count"),
            ("build report", report_pdf, "pages"),
            ("build witness", witness_pdf, "page_count"),
        ):
            locator_matches = (
                path_matches_receipt(receipt.get("path"), locator)
                if label == "build report"
                else receipt.get("target_locator") == locator
            )
            if (
                type(receipt.get("bytes")) is not int
                or receipt.get("bytes") != len(pdf_payload)
                or not is_sha256_hex(receipt.get("sha256"))
                or receipt.get("sha256") != pdf_sha
                or not exact_int(receipt, page_key, page_count)
                or not locator_matches
            ):
                fail(f"{artifact_id}: stale or malformed {label} PDF receipt")


def load_relations(path: Path) -> list[dict[str, str]]:
    payload = path.read_bytes()
    if b"\r" in payload or not payload.endswith(b"\n"):
        fail("relations.csv: not canonical LF-terminated UTF-8")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"relations.csv: invalid UTF-8: {exc}")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    rows = list(reader)
    if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
        fail("relations.csv: missing or duplicate headers")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=reader.fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    if stream.getvalue().encode("utf-8") != payload:
        fail("relations.csv: noncanonical or lossy CSV serialization")
    return rows


def split_semicolon(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def load_terminology_ledger(
    path: Path = TERMINOLOGY_LEDGER,
) -> tuple[list[dict[str, str]], bytes]:
    """Read and independently validate the canonical terminology CSV."""

    payload = path.read_bytes()
    if b"\r" in payload or not payload.endswith(b"\n"):
        fail(f"{path.name}: not canonical LF-terminated UTF-8")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"{path.name}: invalid UTF-8: {exc}")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames != TERM_FIELDS:
        fail(f"{path.name}: header mismatch: {reader.fieldnames!r}")
    rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        fail(f"{path.name}: contains a ragged or over-wide row")

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=TERM_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    round_trip = csv.DictReader(io.StringIO(stream.getvalue(), newline=""))
    if round_trip.fieldnames != TERM_FIELDS or list(round_trip) != rows:
        fail(f"{path.name}: lossy CSV semantic round trip")

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
            fail(
                f"{path.name}: noncontiguous term_id at record {ordinal}: "
                f"expected {expected_id}, got {row['term_id']!r}"
            )
        for field in TERM_FIELDS:
            if row[field] != row[field].strip():
                fail(
                    f"{path.name}: {expected_id} has surrounding whitespace in {field}"
                )
        for field in required_fields:
            if not row[field]:
                fail(f"{path.name}: {expected_id} has an empty required field: {field}")

        variants = split_semicolon(row["variants"])
        rejected = split_semicolon(row["rejected"])
        if len(variants) != len(set(variants)):
            fail(f"{path.name}: {expected_id} has duplicate variants")
        if len(rejected) != len(set(rejected)):
            fail(f"{path.name}: {expected_id} has duplicate rejected forms")
        if row["preferred_id"] in variants:
            fail(f"{path.name}: {expected_id} repeats its preferred form as a variant")
        if row["preferred_id"] in rejected:
            fail(f"{path.name}: {expected_id} rejects its preferred form")
        overlap = sorted(set(variants) & set(rejected))
        if overlap:
            fail(f"{path.name}: {expected_id} both admits and rejects {overlap!r}")

        english_key = row["english"].casefold()
        prior_preferred = preferred_by_english.setdefault(
            english_key, row["preferred_id"]
        )
        if prior_preferred != row["preferred_id"]:
            fail(
                f"{path.name}: conflicting preferred forms for {row['english']!r}: "
                f"{prior_preferred!r} and {row['preferred_id']!r}"
            )

    row_by_id = {row["term_id"]: row for row in rows}
    for local_id, expected in REQUIRED_TERMINOLOGY_DECISIONS.items():
        row = row_by_id.get(local_id)
        if row is None:
            fail(f"{path.name}: required terminology decision is absent: {local_id}")
        for field, value in expected.items():
            if row[field] != value:
                fail(
                    f"{path.name}: {local_id} has the wrong {field}: "
                    f"expected {value!r}, got {row[field]!r}"
                )
    return rows, payload


def validate_terminology_projection(
    rows: list[dict[str, str]], payload: bytes, terms: list[dict]
) -> None:
    if len(terms) != len(rows):
        fail(
            "terminology projection count does not match the live ledger: "
            f"{len(terms)} != {len(rows)}"
        )
    term_by_local_id = {term.get("source_local_id"): term for term in terms}
    if len(term_by_local_id) != len(terms) or None in term_by_local_id:
        fail("terminology projection has missing or duplicate source-local IDs")
    ledger_sha = sha256(payload)
    for row_number, row in enumerate(rows, 2):
        local_id = row["term_id"]
        term = term_by_local_id.get(local_id)
        if term is None:
            fail(f"terminology projection lacks live ledger row {local_id}")
        expected = {
            "evidence": row["evidence"],
            "id": (
                "r005.hefferon-linear-algebra.term."
                f"{local_id.lower()}.locale.id-id"
            ),
            "language": "id",
            "ledger_status": row["status"],
            "locale": "id-ID",
            "notes": row["notes"],
            "preferred": row["preferred_id"],
            "record_type": "term",
            "rejected": split_semicolon(row["rejected"]),
            "scope": row["scope"],
            "source_ledger_row": row_number,
            "source_ledger_sha256": ledger_sha,
            "source_local_id": local_id,
            "source_locator": f"00_control/TERMINOLOGY.csv#row-{row_number}",
            "source_sha256": ledger_sha,
            "source_term": row["english"],
            "target_edition_id": TARGET_EDITION_ID,
            "translation_state": "translated",
            "variants": split_semicolon(row["variants"]),
        }
        for field, value in expected.items():
            if term.get(field) != value:
                fail(
                    f"{term.get('id', local_id)}: terminology ledger round-trip "
                    f"mismatch in {field}"
                )


def validate_derivative_provenance(record: dict) -> None:
    if record.get("production_provenance") != PRODUCTION_PROVENANCE:
        fail("derivative edition has missing or inexact production provenance")


def verify_manifest() -> tuple[dict, dict[str, bytes]]:
    manifest = load_json(BACKEND / "manifest.json")
    if manifest.get("schema") != SCHEMA or manifest.get("schema_version") != SCHEMA_VERSION:
        fail("manifest schema identity mismatch")
    entries = manifest.get("files")
    if not isinstance(entries, list) or manifest.get("generated_file_count") != len(entries):
        fail("manifest count mismatch")
    payloads: dict[str, bytes] = {}
    seen: set[str] = set()
    for entry in entries:
        name = entry.get("path")
        if not isinstance(name, str) or name in seen or Path(name).name != name:
            fail(f"unsafe or duplicate manifest path: {name!r}")
        seen.add(name)
        payload = (BACKEND / name).read_bytes()
        if entry.get("bytes") != len(payload) or entry.get("sha256") != sha256(payload):
            fail(f"manifest replay failed: {name}")
        payloads[name] = payload
    expected = set(ENTITY_EXPORTS.values()) | {
        "interoperability.json",
        "source_closure.json",
    }
    if seen != expected:
        fail(f"manifest file set mismatch: missing={sorted(expected-seen)}, extra={sorted(seen-expected)}")
    return manifest, payloads


def validate(require_final_build: bool) -> dict:
    manifest, _payloads = verify_manifest()
    interoperability = load_json(BACKEND / "interoperability.json")
    closure = load_json(BACKEND / "source_closure.json")
    terminology_rows, terminology_payload = load_terminology_ledger()
    if interoperability.get("entity_exports") != ENTITY_EXPORTS:
        fail("interoperability entity-export map mismatch")
    state_map = interoperability.get("translation_state_mapping")
    if state_map != {state: state for state in sorted(TRANSLATION_STATES)}:
        fail("translation-state interchange map is incomplete or lossy")

    records_by_file = {
        name: load_jsonl(BACKEND / name)
        for name in sorted(set(ENTITY_EXPORTS.values()) - {"relations.csv"})
    }
    relations = load_relations(BACKEND / "relations.csv")
    validate_terminology_projection(
        terminology_rows,
        terminology_payload,
        records_by_file["terminology.jsonl"],
    )
    terminology_ledger_witnesses = [
        witness
        for witness in closure.get("ledgers", [])
        if witness.get("path") == "00_control/TERMINOLOGY.csv"
    ]
    expected_terminology_witness = {
        "path": "00_control/TERMINOLOGY.csv",
        "record_count": len(terminology_rows),
        "sha256": sha256(terminology_payload),
    }
    if terminology_ledger_witnesses != [expected_terminology_witness]:
        fail("source closure has a stale or ambiguous terminology-ledger witness")
    all_records = [record for records in records_by_file.values() for record in records]
    ids = [record.get("id") for record in all_records]
    if any(not isinstance(record_id, str) or not record_id for record_id in ids):
        fail("a JSONL record lacks a stable ID")
    duplicate_ids = [record_id for record_id, count in Counter(ids).items() if count != 1]
    if duplicate_ids:
        fail(f"duplicate stable IDs: {duplicate_ids[:3]}")
    id_map = {record["id"]: record for record in all_records}

    type_counts = Counter(record.get("record_type") for record in all_records)
    missing_types = set(ENTITY_EXPORTS) - set(type_counts) - {"relation"}
    if missing_types:
        fail(f"required entity classes absent: {sorted(missing_types)}")
    for record in all_records:
        missing = BASE_FIELDS - set(record)
        if missing:
            fail(f"{record['id']}: missing base fields {sorted(missing)}")
        if record["schema"] != SCHEMA or record["schema_version"] != SCHEMA_VERSION:
            fail(f"{record['id']}: schema identity mismatch")
        if record["responsible_workflow"] != WORKFLOW_ID:
            fail(f"{record['id']}: stale or foreign workflow identity")
        state = record.get("translation_state")
        if state is not None and state not in TRANSLATION_STATES:
            fail(f"{record['id']}: unknown translation state {state!r}")

    target_editions = [
        record
        for record in records_by_file["authority.jsonl"]
        if record.get("derivative_kind")
        == "translation_and_machine-readable_build_derivative"
    ]
    if len(target_editions) != 1:
        fail("expected exactly one id-ID derivative-edition authority record")
    target_edition_id = target_editions[0]["id"]
    if (
        target_edition_id != TARGET_EDITION_ID
        or target_editions[0].get("locale") != "id-ID"
        or ".locale.id-id." not in target_edition_id
    ):
        fail("derivative edition is not explicitly locale-scoped")
    validate_derivative_provenance(target_editions[0])
    for record in [
        *records_by_file["programs.jsonl"],
        *records_by_file["courses.jsonl"],
        *records_by_file["terminology.jsonl"],
        *records_by_file["corrections.jsonl"],
        *records_by_file["qa_events.jsonl"],
    ]:
        if ".locale.id-id" not in record["id"]:
            fail(f"{record['id']}: localized entity ID is not locale-scoped")
        if record.get("target_edition_id", record.get("derivative_edition_id")) != target_edition_id:
            fail(f"{record['id']}: localized entity is not bound to the derivative edition")
    for term in records_by_file["terminology.jsonl"]:
        if not term.get("preferred") or not term.get("evidence"):
            fail(f"{term['id']}: terminology choice lacks preferred form or evidence")
        for field in ("examples", "variants", "rejected"):
            if not isinstance(term.get(field), list):
                fail(f"{term['id']}: terminology field {field} must be a list")
        if not term["examples"]:
            fail(f"{term['id']}: terminology choice lacks a usage/evidence example")

    relation_ids: set[str] = set()
    relation_counts: Counter[str] = Counter()
    relations_by_type: dict[str, list[dict[str, str]]] = defaultdict(list)
    for relation in relations:
        relation_id = relation.get("relation_id")
        if not relation_id or relation_id in relation_ids:
            fail(f"missing or duplicate relation ID: {relation_id!r}")
        relation_ids.add(relation_id)
        missing = BASE_FIELDS - set(relation)
        if missing:
            fail(f"{relation_id}: missing base relation fields {sorted(missing)}")
        if relation["responsible_workflow"] != WORKFLOW_ID:
            fail(f"{relation_id}: stale or foreign workflow identity")
        relation_type = relation.get("relation_type")
        if relation_type not in RELATION_TYPES:
            fail(f"{relation_id}: unknown relation type {relation_type!r}")
        for endpoint in (relation.get("source_id"), relation.get("target_id")):
            if endpoint not in id_map:
                fail(f"{relation_id}: unresolved endpoint {endpoint!r}")
        relation_counts[relation_type] += 1
        relations_by_type[relation_type].append(relation)

    target_supplied_endpoint_ids = {
        record["id"]
        for record in all_records
        if record.get("provenance_kind") == "indonesian_edition_supplied"
    }
    target_supplied_relations = [
        relation
        for relation in relations
        if relation.get("source_id") in target_supplied_endpoint_ids
        or relation.get("target_id") in target_supplied_endpoint_ids
    ]
    if len(target_supplied_endpoint_ids) != 4 or len(target_supplied_relations) != 6:
        fail("expected four target-supplied endpoints and six touching relations")
    for relation in target_supplied_relations:
        if relation.get("edition_id") != target_edition_id:
            fail(
                f"{relation['relation_id']}: target-supplied relation lacks derivative edition"
            )

    rights_ids = {
        record["id"] for record in records_by_file["rights.jsonl"]
    }
    for record in all_records:
        rights_id = record.get("rights_id")
        if rights_id is not None and rights_id not in rights_ids:
            fail(f"{record['id']}: unresolved rights component {rights_id}")
    for relation in relations:
        if relation.get("rights_id") not in rights_ids:
            fail(f"{relation['relation_id']}: unresolved rights component")

    unit_ids = {record["id"] for record in records_by_file["units.jsonl"]}
    concept_ids = {record["id"] for record in records_by_file["concepts.jsonl"]}
    if any(".locale." in concept_id for concept_id in concept_ids):
        fail("concept identities must remain locale-neutral")
    for unit in records_by_file["units.jsonl"]:
        is_target_supplied = (
            unit.get("provenance_kind") == "indonesian_edition_supplied"
        )
        if is_target_supplied:
            if (
                ".locale.id-id" not in unit["id"]
                or unit.get("edition_id") != target_edition_id
                or unit.get("language") != "id"
                or unit.get("locale") != "id-ID"
                or unit.get("source_locator") is not None
                or unit.get("source_sha256") is not None
            ):
                fail(f"{unit['id']}: invalid locale-scoped target-supplied unit")
        elif ".locale." in unit["id"] or unit.get("target_edition_id") != target_edition_id:
            fail(f"{unit['id']}: unit identity/derivative binding is not cross-locale safe")
        target_variant = unit.get("target_variant", {})
        if (
            target_variant.get("edition_id") != target_edition_id
            or target_variant.get("locale") != "id-ID"
            or target_variant.get("sha256") != unit.get("target_sha256")
        ):
            fail(f"{unit['id']}: unit target variant is missing or inconsistent")
        parent_id = unit.get("parent_id")
        path = unit.get("path")
        if not isinstance(path, list) or not path or path[-1] != unit["id"]:
            fail(f"{unit['id']}: invalid topology path")
        if parent_id in unit_ids and (len(path) < 2 or path[-2] != parent_id):
            fail(f"{unit['id']}: parent/path mismatch")
        for concept_id in unit.get("concept_ids", []):
            if concept_id not in concept_ids:
                fail(f"{unit['id']}: unresolved concept {concept_id}")
    qa_types = Counter(
        record.get("qa_type") for record in records_by_file["qa_events.jsonl"]
    )
    for required_qa_type in (
        "mathematical_and_source_correction_traceability",
        "language_terminology_consistency",
        "visual_render_coverage",
    ):
        if qa_types[required_qa_type] != 1:
            fail(f"expected exactly one {required_qa_type} QA event")
    for event in records_by_file["qa_events.jsonl"]:
        for unit_id in event.get("unit_ids", []):
            if unit_id not in unit_ids:
                fail(f"{event['id']}: unresolved QA unit {unit_id}")

    segments = records_by_file["segments.jsonl"]
    for segment in segments:
        if segment.get("parent_unit_id") not in unit_ids:
            fail(f"{segment['id']}: unresolved parent unit")
        if segment.get("target_edition_id") != target_edition_id:
            fail(f"{segment['id']}: target segment lacks derivative-edition binding")
        target_variant = segment.get("target_variant", {})
        if (
            target_variant.get("edition_id") != target_edition_id
            or target_variant.get("locale") != "id-ID"
            or target_variant.get("text") != segment.get("target_text")
            or target_variant.get("sha256") != segment.get("target_sha256")
        ):
            fail(f"{segment['id']}: segment target variant is missing or inconsistent")
        is_target_supplied = (
            segment.get("provenance_kind") == "indonesian_edition_supplied"
        )
        if is_target_supplied:
            if (
                ".locale.id-id" not in segment["id"]
                or segment.get("edition_id") != target_edition_id
                or segment.get("language") != "id"
                or segment.get("locale") != "id-ID"
                or segment.get("source_text") is not None
                or segment.get("source_locator") is not None
                or segment.get("source_sha256") is not None
            ):
                fail(f"{segment['id']}: invalid target-supplied segment provenance")
            sides = ("target",)
        else:
            sides = ("source", "target")
        for side in sides:
            text = segment.get(f"{side}_text")
            if not isinstance(text, str) or sha256(text.encode("utf-8")) != segment.get(
                f"{side}_sha256"
            ):
                fail(f"{segment['id']}: {side} text/hash mismatch")

    exercises = {
        record["id"]: record
        for record in records_by_file["units.jsonl"]
        if record.get("unit_kind") == "exercise"
    }
    answers = {
        record["id"]: record
        for record in records_by_file["units.jsonl"]
        if record.get("unit_kind") == "answer"
    }
    answer_links = relations_by_type["answers"]
    if len(answer_links) != len(answers):
        fail("answer relation count does not equal answer unit count")
    linked_answers: Counter[str] = Counter()
    linked_exercises: Counter[str] = Counter()
    for relation in answer_links:
        if relation["source_id"] not in answers or relation["target_id"] not in exercises:
            fail(f"{relation['relation_id']}: invalid answer/exercise endpoint types")
        linked_answers[relation["source_id"]] += 1
        linked_exercises[relation["target_id"]] += 1
    if any(count != 1 for count in linked_answers.values()) or set(linked_answers) != set(answers):
        fail("each answer must link to exactly one exercise")
    unanswered = sorted(
        exercise_id for exercise_id in exercises if linked_exercises[exercise_id] == 0
    )
    if unanswered:
        fail("target deliverable contains unanswered exercises")
    target_supplied_answers = {
        answer_id: answer
        for answer_id, answer in answers.items()
        if answer.get("provenance_kind") == "indonesian_edition_supplied"
    }
    native_answers = {
        answer_id: answer
        for answer_id, answer in answers.items()
        if answer.get("provenance_kind") != "indonesian_edition_supplied"
    }
    if len(native_answers) != NATIVE_UPSTREAM_ANSWER_COUNT:
        fail("native upstream answer count is not 1,035")
    if len(target_supplied_answers) != TARGET_SUPPLIED_ANSWER_COUNT:
        fail("target-supplied answer count is not 2")
    if len(answers) != NATIVE_UPSTREAM_ANSWER_COUNT + TARGET_SUPPLIED_ANSWER_COUNT:
        fail("deliverable answer count is not 1,037")
    if {
        answer.get("authority_answer_anchor")
        for answer in target_supplied_answers.values()
    } != TARGET_SUPPLIED_ANSWER_ANCHORS:
        fail("target-supplied answer anchors do not match ans.One.V.0.5-.6")
    correction_id = (
        "r005.hefferon-linear-algebra.correction.hla-a0300.locale.id-id"
    )
    correction = id_map.get(correction_id)
    if correction is None:
        fail("target-supplied answers lack HLA-A0300 correction authority")
    target_supplied_segments = [
        segment
        for segment in segments
        if segment.get("provenance_kind") == "indonesian_edition_supplied"
    ]
    if len(target_supplied_segments) != TARGET_SUPPLIED_ANSWER_COUNT:
        fail("target-supplied answer segment count is not 2")
    for answer in target_supplied_answers.values():
        if (
            answer.get("answer_link_status") != "linked_target_supplied"
            or answer.get("authorization_event_id") != "HLA-A0300"
            or answer.get("authorization_correction_id") != correction_id
            or answer.get("authorization_ledger_locator")
            != correction.get("source_locator")
            or answer.get("authorization_ledger_sha256")
            != correction.get("source_ledger_sha256")
            or answer.get("authority_exercise_unit_id")
            != answer.get("answers_unit_id")
            or answer.get("authority_exercise_unit_id") not in exercises
            or answer.get("authority_exercise_locator")
            != exercises[answer["authority_exercise_unit_id"]].get("source_locator")
            or answer.get("authority_exercise_sha256")
            != exercises[answer["authority_exercise_unit_id"]].get("source_sha256")
            or answer.get("target_text") is not None
        ):
            fail(f"{answer['id']}: incomplete target-supplied provenance")
        target_locator = answer.get("target_locator")
        target_sha256 = answer.get("target_sha256")
        if not isinstance(target_locator, str) or not isinstance(target_sha256, str):
            fail(f"{answer['id']}: target locator/hash is missing")
        answer_segments = [
            segment
            for segment in target_supplied_segments
            if segment.get("parent_unit_id") == answer["id"]
        ]
        if len(answer_segments) != 1:
            fail(f"{answer['id']}: expected one target-supplied segment")
        segment = answer_segments[0]
        if (
            segment.get("target_locator") != target_locator
            or segment.get("target_sha256") != target_sha256
            or segment.get("authority_exercise_locator")
            != answer.get("authority_exercise_locator")
            or segment.get("authorization_event_id") != "HLA-A0300"
            or segment.get("authorization_ledger_locator")
            != correction.get("source_locator")
            or segment.get("authorization_ledger_sha256")
            != correction.get("source_ledger_sha256")
        ):
            fail(f"{answer['id']}: target-supplied unit/segment witness mismatch")
        target_relative = target_locator.split("#", 1)[0]
        live_target_text = (TARGET / target_relative).read_text(encoding="utf-8")
        if segment["target_text"] not in live_target_text:
            fail(f"{answer['id']}: target-supplied text is absent from target file")
    declared_target_supplied = sorted(
        exercise_id
        for exercise_id, exercise in exercises.items()
        if exercise.get("answer_status") == "linked_target_supplied"
    )
    linked_target_supplied = sorted(
        answer["answers_unit_id"] for answer in target_supplied_answers.values()
    )
    if declared_target_supplied != linked_target_supplied or len(declared_target_supplied) != 2:
        fail("declared upstream answer gaps are not linked to target-supplied answers")

    closure_files = closure.get("files", [])
    for entry in closure_files:
        relative = entry["source_locator"]
        source_payload = (AUTHORITY / relative).read_bytes()
        target_payload = (TARGET / entry["target_locator"]).read_bytes()
        if len(source_payload) != entry["source_bytes"] or sha256(source_payload) != entry[
            "source_sha256"
        ]:
            fail(f"source closure byte mismatch: {relative}")
        if len(target_payload) != entry["target_bytes"] or sha256(target_payload) != entry[
            "target_sha256"
        ]:
            fail(f"target closure byte mismatch: {relative}")
    for entry in closure.get("assets", []):
        source_locator = entry.get("source_locator")
        if source_locator is not None:
            payload = (AUTHORITY / source_locator).read_bytes()
            if sha256(payload) != entry.get("source_sha256"):
                fail(f"source asset byte mismatch: {source_locator}")
        target_locator = entry.get("target_locator")
        if target_locator is not None:
            payload = (TARGET / target_locator).read_bytes()
            if sha256(payload) != entry.get("target_sha256"):
                fail(f"target asset byte mismatch: {target_locator}")

    source_editions = [
        record
        for record in records_by_file["authority.jsonl"]
        if record.get("commit") == "df2262e089a02651c127f1dd12649c4622ee1383"
    ]
    if len(source_editions) != 1:
        fail("expected exactly one pinned source-edition record")
    source_edition = source_editions[0]
    archive_payload = (LANE / source_edition["archive_locator"]).read_bytes()
    if (
        len(archive_payload) != source_edition.get("archive_bytes")
        or sha256(archive_payload) != source_edition.get("archive_sha256")
    ):
        fail("source-edition archive receipt mismatch")

    artifacts = records_by_file["artifacts.jsonl"]
    for artifact in artifacts:
        if artifact.get("publication_status") == "published_upstream":
            payload = (LANE / artifact["source_locator"]).read_bytes()
            if (
                len(payload) != artifact.get("bytes")
                or sha256(payload) != artifact.get("sha256")
            ):
                fail(f"{artifact['id']}: upstream artifact byte mismatch")
    backend_snapshots = [
        artifact
        for artifact in artifacts
        if artifact.get("artifact_kind") == "machine_registry_snapshot"
    ]
    if len(backend_snapshots) != 1:
        fail("expected exactly one machine-registry snapshot artifact")
    toolchain = backend_snapshots[0].get("toolchain", {})
    for role in ("builder", "validator"):
        locator = toolchain.get(role)
        expected_sha = toolchain.get(f"{role}_sha256")
        if not locator or sha256((LANE / locator).read_bytes()) != expected_sha:
            fail(f"machine-registry {role} byte witness mismatch")

    rights_by_id = {record["id"]: record for record in records_by_file["rights.jsonl"]}
    core = rights_by_id["r005.hefferon-linear-algebra.rights.core-dual-license"]
    if core.get("selected_license_identifier") != "CC-BY-SA-2.5" or core.get(
        "license_choice"
    ) != "Creative Commons Attribution-ShareAlike 2.5":
        fail("derivative license route is not uniquely pinned to CC BY-SA 2.5")
    expected_rights = {
        "src/sty/bookans.sty": "r005.hefferon-linear-algebra.rights.bookans-lppl",
        "src/mp/compile_mp.sh": "r005.hefferon-linear-algebra.rights.build-script-gpl-2",
        "src/lab/runlab.sh": "r005.hefferon-linear-algebra.rights.build-script-gpl-3",
        "src/lab/pix/greatwave.png": "r005.hefferon-linear-algebra.rights.great-wave-cc0",
    }
    assets_by_locator = {
        record.get("source_locator"): record
        for record in records_by_file["assets.jsonl"]
        if record.get("source_locator")
    }
    for asset in records_by_file["assets.jsonl"]:
        if asset.get("target_locator") is not None:
            target_variant = asset.get("target_variant", {})
            if (
                asset.get("target_edition_id") != target_edition_id
                or target_variant.get("edition_id") != target_edition_id
                or target_variant.get("sha256") != asset.get("target_sha256")
            ):
                fail(f"{asset['id']}: asset target variant is missing or inconsistent")
    for locator, rights_id in expected_rights.items():
        if assets_by_locator.get(locator, {}).get("rights_id") != rights_id:
            fail(f"component rights mismatch: {locator}")

    build_events = [
        record
        for record in records_by_file["qa_events.jsonl"]
        if record.get("qa_type") == "build"
    ]
    if len(build_events) != 1:
        fail("expected exactly one full-build QA event")
    reader_artifacts = [
        record
        for record in artifacts
        if record.get("corpus_component") in {
            "main-textbook",
            "answer-book-shell",
            "sage-lab",
        }
        and record.get("language") == "id"
    ]
    if {artifact["id"] for artifact in reader_artifacts} != TARGET_PDF_ARTIFACT_IDS:
        fail("Indonesian PDF artifact IDs do not satisfy the locale-ID contract")
    for artifact in reader_artifacts:
        if (
            ".locale.id-id" not in artifact["id"]
            or artifact.get("locale") != "id-ID"
            or artifact.get("edition_id") != target_edition_id
            or artifact.get("target_edition_id") != target_edition_id
        ):
            fail(f"{artifact['id']}: localized PDF artifact binding is invalid")
    if require_final_build:
        build_event = build_events[0]
        if build_event.get("result") != "pass" or build_event.get(
            "translation_state"
        ) != "built":
            fail("final-build gate requires a reproducibly verified successful build")
        if build_event.get("witness", {}).get("reproducibility_verified") is not True:
            fail("final-build gate lacks a matched second-build fingerprint")
        build_witness = build_event.get("witness", {})
        validate_final_build_live_receipts(build_witness, reader_artifacts)
        qa_summary = build_witness.get("qa_summary", {})
        if (
            not isinstance(qa_summary, dict)
            or qa_summary.get("undefined_reference_lines") != 0
            or qa_summary.get("generated_english_label_hits") != 0
            or qa_summary.get("runtime_placeholder_lines") != 0
            or build_witness.get("runtime_placeholder_lines") != 0
        ):
            fail("final-build gate lacks zero diagnostic/runtime closure")
        cross_pdf = build_witness.get("cross_pdf_link_audit", {})
        if (
            not isinstance(cross_pdf, dict)
            or cross_pdf.get("all_pair_actions_resolved") is not True
            or cross_pdf.get("answer_links_each_direction")
            != EXPECTED_CROSS_PDF_ANSWER_LINKS
            or cross_pdf.get("goto_remote_actions")
            != 2 * EXPECTED_CROSS_PDF_ANSWER_LINKS
            or cross_pdf.get("unresolved_pair_actions") != 0
            or cross_pdf.get("locator")
            != "build/hefferon_id/cross_pdf_link_audit.json"
            or not isinstance(cross_pdf.get("bytes"), int)
            or cross_pdf.get("bytes", 0) <= 0
            or not isinstance(cross_pdf.get("sha256"), str)
            or len(cross_pdf.get("sha256", "")) != 64
        ):
            fail("final-build gate lacks exact cross-PDF sidecar closure")
        lab_runtime = build_witness.get("lab_sagetex_runtime", {})
        if (
            not isinstance(lab_runtime, dict)
            or lab_runtime.get("command_labels") != 148
            or lab_runtime.get("command_source_listings") != 1018
            or lab_runtime.get("maximum_listed_source_line") != 1236
            or lab_runtime.get("scmd_lines") != 1237
            or lab_runtime.get("sage_changed_figures") != 63
            or lab_runtime.get("authority_figures_restored") != 64
            or lab_runtime.get("pythontex_zero_errors_warnings") is not True
            or lab_runtime.get("locator")
            != "build/hefferon_id/lab_sagetex_runtime_manifest.json"
            or not isinstance(lab_runtime.get("bytes"), int)
            or lab_runtime.get("bytes", 0) <= 0
            or not isinstance(lab_runtime.get("sha256"), str)
            or len(lab_runtime.get("sha256", "")) != 64
        ):
            fail("final-build gate lacks exact SageTeX/PythonTeX sidecar closure")
        visual_events = [
            event
            for event in records_by_file["qa_events.jsonl"]
            if event.get("qa_type") == "visual_render_coverage"
        ]
        if visual_events[0].get("result") != "pass":
            fail("final-build gate lacks passing all-page visual-render coverage")
        if len(reader_artifacts) != 3:
            fail("final-build gate requires exactly three Indonesian reader artifacts")
        for artifact in reader_artifacts:
            if (
                artifact.get("artifact_kind") != "reader_pdf"
                or artifact.get("translation_state") != "built"
                or not artifact.get("sha256")
                or not artifact.get("bytes")
                or not artifact.get("page_count")
            ):
                fail(f"{artifact['id']}: incomplete final reader artifact")

    return {
        "answer_count": len(answers),
        "artifact_count": type_counts["artifact"],
        "asset_count": type_counts["asset"],
        "build_result": build_events[0]["result"],
        "correction_count": type_counts["correction"],
        "exercise_count": len(exercises),
        "final_build_required": require_final_build,
        "manifest_sha256": sha256((BACKEND / "manifest.json").read_bytes()),
        "native_upstream_answer_count": len(native_answers),
        "record_count": len(all_records),
        "relation_count": len(relations),
        "relation_types": dict(sorted(relation_counts.items())),
        "schema_version": SCHEMA_VERSION,
        "segment_count": len(segments),
        "status": "pass",
        "target_supplied_answer_count": len(target_supplied_answers),
        "unanswered_exercise_count": len(unanswered),
        "unit_count": len(unit_ids),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-final-build",
        action="store_true",
        help="require three built PDFs and a matched second-build fingerprint",
    )
    args = parser.parse_args()
    print(canonical_json(validate(args.require_final_build)))


if __name__ == "__main__":
    main()
