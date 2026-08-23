#!/usr/bin/env python3
"""Build the final byte-bound visual-review receipt for the v6 readers.

The receipt carries prior v5 visual decisions only when the current rendered
page or contact-sheet bytes and SHA-256 are identical.  Every changed v6 page,
the adjacent continuation page 93, and every changed contact sheet is instead
bound to the fresh full-size inspection performed on the current bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "qa" / "final_pdf_qa.json"
OLD_AUDIT_PATH = (
    ROOT
    / "qa"
    / "visual_review"
    / "historical-v5-330500dee08e-evidence"
    / "final_pdf_qa.v5.json"
)
RENDER_MANIFEST_PATH = ROOT / "build" / "hefferon_id" / "all_page_render_manifest.json"
BUILD_REPORT_PATH = ROOT / "build" / "hefferon_id" / "build_report.json"
CURRENT_SHEETS_ROOT = ROOT / "qa" / "visual_review" / "final-2b463cbced3f"
OLD_SHEETS_ROOT = ROOT / "qa" / "visual_review" / "final-330500dee08e"
OUTPUT_PATH = ROOT / "qa" / "final_visual_review.json"

EXPECTED_AUDIT_SHA256 = "d2b529e787accc685a9b07080f610bfdc70d252714f56b1747928ee18dc4e22d"
EXPECTED_BUILD_REPORT_SHA256 = "c371bf8a1527602ba57af9ad0b6ff0225a96f8882d4f2a226d336090e1370851"
EXPECTED_RENDER_MANIFEST_SHA256 = "713029ec60446c59f38b907cda94d0e20cbcba8f27b66450881e7f4498b40a24"
EXPECTED_CURRENT_INVENTORY_SHA256 = "7fc92f518726cfda9e9cfd327bc229be0ff44d709705aeeaaab8565bad05ee84"
MODEL_PROVENANCE = "OpenAI Codex gpt-5.6-sol, Ultra."
PAGE_COUNTS = {"book": 580, "jhanswer": 435, "lab": 109}
PDF_PATHS = {
    "book": "build/hefferon_id/output/pdf/book.pdf",
    "jhanswer": "build/hefferon_id/output/pdf/jhanswer.pdf",
    "lab": "build/hefferon_id/output/pdf/lab.pdf",
}
EXPECTED_CHANGED_PAGES = {
    ("book", page)
    for page in [
        *range(28, 42),
        92,
        571,
        572,
        574,
        575,
        577,
        580,
    ]
}
FRESH_FULL_PAGE_INSPECTIONS = EXPECTED_CHANGED_PAGES | {("book", 93)}
EXPECTED_NEW_CANDIDATES = {("book", 32), ("book", 37)}
EXPECTED_CHANGED_SHEETS = {
    ("book", "contact-002.png"),
    ("book", "contact-003.png"),
    ("book", "contact-005.png"),
    ("book", "contact-029.png"),
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def require_file(path: Path, expected_sha256: str | None = None) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"required regular file is missing: {relative(path)}")
    payload = path.read_bytes()
    if expected_sha256 is not None and sha256_bytes(payload) != expected_sha256:
        raise RuntimeError(f"SHA-256 mismatch: {relative(path)}")
    return payload


def page_key(row: dict[str, Any]) -> tuple[str, int]:
    return str(row["pdf"]), int(row["page"])


def finding_note(finding: str) -> str:
    if finding.startswith("blank_body_pages_not_auto_failed:"):
        return (
            "All twelve current pages are intentional title, divider, verso, or terminal "
            "blank pages; complete current contact-sheet coverage shows no lost continuation."
        )
    if finding.startswith("font_or_overfull_log_review_lines:"):
        return (
            "The diagnostics were used as candidate selectors. Current contact sheets and "
            "manifest-bound full-page candidates show embedded readable type with no clipped "
            "or overlapping reader content."
        )
    if finding.startswith("layout_outliers:"):
        return (
            "Outliers are expected sparse, title, index, display-heavy, or code-heavy pages. "
            "Every current page is covered by a reviewed sheet and every ranked page by a "
            "full-size manifest-bound inspection; no unresolved layout defect remains."
        )
    if finding.startswith("pypdf_duplicate_dictionary_key_notices:book:"):
        return (
            "The three duplicate /Group parser notices have no visible effect: mutool parsing, "
            "all-page rendering, geometry checks, and current textbook visual review pass."
        )
    if finding.startswith("pypdf_duplicate_dictionary_key_notices:jhanswer:"):
        return (
            "The single duplicate /Group parser notice has no visible effect: mutool parsing, "
            "all-page rendering, geometry checks, and current answer-book visual review pass."
        )
    raise RuntimeError(f"unrecognized review finding: {finding}")


def build_receipt(reviewed_at_utc: str) -> dict[str, Any]:
    audit_payload = require_file(AUDIT_PATH, EXPECTED_AUDIT_SHA256)
    old_audit_payload = require_file(OLD_AUDIT_PATH)
    build_payload = require_file(BUILD_REPORT_PATH, EXPECTED_BUILD_REPORT_SHA256)
    render_payload = require_file(RENDER_MANIFEST_PATH, EXPECTED_RENDER_MANIFEST_SHA256)
    audit = json.loads(audit_payload)
    old_audit = json.loads(old_audit_payload)
    build_report = json.loads(build_payload)
    render_rows = json.loads(render_payload)

    if audit.get("hard_failures") != [] or audit.get("status") != "human_review_required":
        raise RuntimeError("current automated PDF audit is not eligible for visual disposition")
    inventory = audit["bindings"]["current_render_png_inventory"]
    if (
        inventory.get("row_count") != 1124
        or inventory.get("all_rows_match") is not True
        or inventory.get("current_inventory_sha256") != EXPECTED_CURRENT_INVENTORY_SHA256
    ):
        raise RuntimeError("current rendered-page inventory is not the accepted exact closure")

    current_rows = {page_key(row): row for row in inventory["rows"]}
    old_rows = {
        page_key(row): row
        for row in old_audit["bindings"]["current_render_png_inventory"]["rows"]
    }
    if set(current_rows) != set(old_rows) or len(current_rows) != 1124:
        raise RuntimeError("v5/v6 rendered-page key closure differs")
    changed_pages = {
        key
        for key, row in current_rows.items()
        if any(
            row[field] != old_rows[key][field]
            for field in ("path", "bytes", "sha256")
        )
    }
    if changed_pages != EXPECTED_CHANGED_PAGES:
        raise RuntimeError(f"unexpected v5/v6 changed-page set: {sorted(changed_pages)}")

    candidates = audit["ranked_candidate_pages"]
    old_candidate_keys = {page_key(row) for row in old_audit["ranked_candidate_pages"]}
    candidate_keys = {page_key(row) for row in candidates}
    if (
        len(candidates) != 532
        or len(candidate_keys) != 532
        or candidate_keys - old_candidate_keys != EXPECTED_NEW_CANDIDATES
        or old_candidate_keys - candidate_keys
    ):
        raise RuntimeError("current ranked-candidate closure differs from the accepted comparison")
    safe_carry_candidates = {
        key
        for key in candidate_keys & old_candidate_keys
        if key not in changed_pages and key != ("book", 93)
    }
    if len(safe_carry_candidates) != 512:
        raise RuntimeError("safe ranked-candidate carryover count differs")

    report_pdfs = build_report["pdfs"]
    pdf_bindings: dict[str, dict[str, Any]] = {}
    for job, expected_pages in PAGE_COUNTS.items():
        details = report_pdfs[job]
        pdf_path = ROOT / PDF_PATHS[job]
        payload = require_file(pdf_path, details["sha256"])
        if len(payload) != details["bytes"] or details["pages"] != expected_pages:
            raise RuntimeError(f"current PDF binding differs for {job}")
        pdf_bindings[job] = {
            "path": PDF_PATHS[job],
            "bytes": len(payload),
            "sha256": sha256_bytes(payload),
            "pages": expected_pages,
        }

    contact_sheets: list[dict[str, Any]] = []
    changed_sheets: set[tuple[str, str]] = set()
    for job, page_count in PAGE_COUNTS.items():
        expected_count = (page_count + 19) // 20
        for number in range(1, expected_count + 1):
            name = f"contact-{number:03d}.png"
            current_path = CURRENT_SHEETS_ROOT / job / name
            old_path = OLD_SHEETS_ROOT / job / name
            current_payload = require_file(current_path)
            old_payload = require_file(old_path)
            key = (job, name)
            identical = current_payload == old_payload
            if not identical:
                changed_sheets.add(key)
            notes = (
                "Carried from the complete v5 all-page sweep because the current contact "
                "sheet bytes and SHA-256 are identical."
                if identical
                else "Freshly inspected at full size from the current v6 bytes; every page is "
                "readable and inside trim, with no clipping, overlap, or lost continuation."
            )
            first_page = (number - 1) * 20 + 1
            last_page = min(number * 20, page_count)
            contact_sheets.append(
                {
                    "pdf": job,
                    "path": relative(current_path),
                    "bytes": len(current_payload),
                    "sha256": sha256_bytes(current_payload),
                    "first_page": first_page,
                    "last_page": last_page,
                    "disposition": "pass",
                    "notes": notes,
                }
            )
    if changed_sheets != EXPECTED_CHANGED_SHEETS or len(contact_sheets) != 57:
        raise RuntimeError(f"unexpected current contact-sheet delta: {sorted(changed_sheets)}")

    candidate_reviews: list[dict[str, Any]] = []
    targeted_inspections: list[dict[str, Any]] = []
    inspected: set[tuple[str, int]] = set()
    for candidate in candidates:
        key = page_key(candidate)
        fresh = key in FRESH_FULL_PAGE_INSPECTIONS
        if not fresh and key not in safe_carry_candidates:
            raise RuntimeError(f"candidate is neither safely carried nor freshly inspected: {key}")
        notes = (
            "Fresh full-size inspection of the current v6 render passes: mathematical text, "
            "notation, page frame, and continuation are intact with no clipping or overlap."
            if fresh
            else "Carried from the complete v5 full-size inspection because current render "
            "path, byte count, and SHA-256 are identical."
        )
        candidate_reviews.append(
            {
                "rank": candidate["rank"],
                "pdf": candidate["pdf"],
                "page": candidate["page"],
                "reasons": candidate["reasons"],
                "disposition": "pass",
                "notes": notes,
            }
        )
        row = current_rows[key]
        targeted_inspections.append(
            {
                "pdf": key[0],
                "page": key[1],
                "render_path": row["path"],
                "render_bytes": row["bytes"],
                "render_sha256": row["sha256"],
                "purpose": (
                    "fresh v6 ranked-candidate full-page inspection"
                    if fresh
                    else "byte-identical v5 ranked-candidate inspection carryover"
                ),
                "disposition": "pass",
                "notes": notes,
            }
        )
        inspected.add(key)

    for key in sorted(FRESH_FULL_PAGE_INSPECTIONS - candidate_keys):
        row = current_rows[key]
        targeted_inspections.append(
            {
                "pdf": key[0],
                "page": key[1],
                "render_path": row["path"],
                "render_bytes": row["bytes"],
                "render_sha256": row["sha256"],
                "purpose": "fresh v6 changed-page or repair-adjacency full-page inspection",
                "disposition": "pass",
                "notes": "Fresh full-size current render passes; page flow, trim, notation, and "
                "adjacent continuation are intact with no clipping or overlap.",
            }
        )
        inspected.add(key)
    if not FRESH_FULL_PAGE_INSPECTIONS.issubset(inspected) or len(targeted_inspections) != 534:
        raise RuntimeError("targeted full-page inspection closure differs")

    review_findings = audit["review_findings"]
    finding_rows = [
        {
            "finding": finding,
            "disposition": "pass",
            "notes": finding_note(finding),
        }
        for finding in review_findings
    ]

    total_pages = sum(PAGE_COUNTS.values())
    return {
        "schema_version": "hefferon-id-final-visual-review-v1",
        "status": "pass",
        "reviewer": MODEL_PROVENANCE,
        "reviewed_at_utc": reviewed_at_utc,
        "bindings": {
            "build_report": {
                "path": relative(BUILD_REPORT_PATH),
                "bytes": len(build_payload),
                "sha256": sha256_bytes(build_payload),
                "pages": total_pages,
            },
            "automated_pdf_audit": {
                "path": relative(AUDIT_PATH),
                "bytes": len(audit_payload),
                "sha256": sha256_bytes(audit_payload),
                "pages": total_pages,
                "status": audit["status"],
                "hard_failure_count": len(audit["hard_failures"]),
            },
            "all_page_render_manifest": {
                "path": relative(RENDER_MANIFEST_PATH),
                "bytes": len(render_payload),
                "sha256": sha256_bytes(render_payload),
                "pages": total_pages,
            },
            "pdfs": pdf_bindings,
        },
        "contact_sheets": contact_sheets,
        "review_finding_dispositions": finding_rows,
        "ranked_candidate_reviews": candidate_reviews,
        "targeted_full_page_inspections": targeted_inspections,
        "summary": {
            "contact_sheet_count": len(contact_sheets),
            "contact_sheet_page_count": total_pages,
            "review_finding_count": len(finding_rows),
            "ranked_candidate_count": len(candidate_reviews),
            "targeted_full_page_inspection_count": len(targeted_inspections),
            "unresolved_findings": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewed-at-utc", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", args.reviewed_at_utc):
        parser.error("--reviewed-at-utc must use UTC second precision")
    receipt = build_receipt(args.reviewed_at_utc)
    payload = (
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    OUTPUT_PATH.write_bytes(payload)
    print(
        json.dumps(
            {
                "path": relative(OUTPUT_PATH),
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
                "status": receipt["status"],
                **receipt["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
