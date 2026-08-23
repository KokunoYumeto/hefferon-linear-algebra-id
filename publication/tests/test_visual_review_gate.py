from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


DRIVER = Path(__file__).resolve().parents[1] / "publish_release.py"
SPEC = importlib.util.spec_from_file_location("hefferon_publish_visual_gate", DRIVER)
assert SPEC and SPEC.loader
pub = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pub)


class VisualReviewGateTests(unittest.TestCase):
    def plan(self):
        return copy.deepcopy(pub.load_plan())

    @staticmethod
    def write_json(path: Path, value):
        payload = pub.canonical_bytes(value, pretty=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return payload

    def automated_fixture(self, root: Path, plan: dict):
        page_counts = {"book": 2, "jhanswer": 1, "lab": 1}
        component_jobs = {
            "textbook": "book",
            "worked-answers": "jhanswer",
            "sage-lab": "lab",
        }
        sources = {
            component_jobs[item["component"]]: item["source"]
            for item in plan["reader_pdfs"]
        }
        report_pdfs = {}
        for job, relative in sources.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((f"fixture-{job}-pdf").encode("ascii"))
            report_pdfs[job] = {
                "path": str(path.resolve()),
                "bytes": path.stat().st_size,
                "sha256": pub.sha256_file(path),
                "pages": page_counts[job],
            }

        report = {
            "status": "success",
            "source": {"tree_sha256": "1" * 64},
            "qa_summary": {
                "undefined_reference_lines": 0,
                "generated_english_label_hits": 0,
                "runtime_placeholder_lines": 0,
            },
            "reproducibility": {"matched": True, "schema": "fixture"},
            "pdfs": report_pdfs,
        }
        build_relative = plan["qa"]["build_report"]
        build_payload = self.write_json(root / build_relative, report)

        render_rows = []
        for job in ("book", "jhanswer", "lab"):
            width = len(str(page_counts[job]))
            for page in range(1, page_counts[job] + 1):
                raw = f"render-{job}-{page}".encode("ascii")
                render_rows.append(
                    {
                        "pdf": job,
                        "page": page,
                        "path": (
                            f"tmp/pdfs/hefferon_id/{job}/"
                            f"page-{page:0{width}d}.png"
                        ),
                        "bytes": len(raw),
                        "sha256": pub.sha256_bytes(raw),
                        "width": 612,
                        "height": 792,
                        "ink_fraction": 0.1,
                        "mean_luminance": 240.0,
                        "fully_white": False,
                    }
                )
        render_relative = plan["qa"]["all_page_render_manifest"]
        render_payload = self.write_json(root / render_relative, render_rows)
        all_page_renders = {
            "path": render_relative,
            "count": len(render_rows),
            "bytes_rendered": sum(row["bytes"] for row in render_rows),
            "manifest_bytes": len(render_payload),
            "manifest_sha256": pub.sha256_bytes(render_payload),
            "pdf_page_counts": page_counts,
        }

        inventory_rows = [
            {
                "pdf": row["pdf"],
                "page": row["page"],
                "path": row["path"],
                "bytes": row["bytes"],
                "sha256": row["sha256"],
            }
            for row in render_rows
        ]
        candidates = [
            {
                "pdf": "book",
                "page": 2,
                "score": 2.5,
                "automatic_failure": False,
                "reasons": ["layout_outlier:right_edge"],
                "disposition": "human_visual_review_required",
                "rank": 1,
            },
            {
                "pdf": "lab",
                "page": 1,
                "score": 1.5,
                "automatic_failure": False,
                "reasons": ["semantic_spot_check:python_random_output"],
                "disposition": "human_visual_review_required",
                "rank": 2,
            },
        ]
        review_findings = ["layout_outliers:1"]
        audit = {
            "schema_version": "hefferon-id-final-pdf-qa-v1",
            "status": "human_review_required",
            "scope": {"output": plan["qa"]["final_pdf_qa"]},
            "bindings": {
                "build_report": {
                    "path": build_relative,
                    "bytes": len(build_payload),
                    "sha256": pub.sha256_bytes(build_payload),
                    "status": report["status"],
                    "source_tree_sha256": report["source"]["tree_sha256"],
                    "qa_summary": copy.deepcopy(report["qa_summary"]),
                    "reproducibility": copy.deepcopy(report["reproducibility"]),
                },
                "all_page_render_manifest": {
                    "path": render_relative,
                    "bytes": len(render_payload),
                    "sha256": pub.sha256_bytes(render_payload),
                },
                "pdfs": {
                    job: {
                        "path": sources[job],
                        "bytes": report_pdfs[job]["bytes"],
                        "sha256": report_pdfs[job]["sha256"],
                        "pages": report_pdfs[job]["pages"],
                        "build_report_bytes_match": True,
                        "build_report_sha256_match": True,
                        "build_report_pages_match": True,
                    }
                    for job in ("book", "jhanswer", "lab")
                },
                "current_render_png_inventory": {
                    "row_count": len(inventory_rows),
                    "all_rows_match": True,
                    "current_inventory_sha256": pub.sha256_bytes(
                        pub.canonical_bytes(inventory_rows)
                    ),
                    "rows": inventory_rows,
                },
            },
            "ranked_candidate_pages": candidates,
            "hard_failures": [],
            "review_findings": review_findings,
            "summary": {
                "pdf_count": 3,
                "pdf_pages": sum(page_counts.values()),
                "render_png_count": len(render_rows),
                "all_pdf_bytes_match_build_report": True,
                "all_pdf_page_counts_match_build_report": True,
                "all_render_pngs_match_manifest": True,
                "all_page_geometry_valid": True,
                "all_fonts_embedded": True,
                "hard_log_diagnostic_count": 0,
                "ranked_candidate_page_count": len(candidates),
                "hard_failure_count": 0,
                "review_finding_count": len(review_findings),
            },
        }
        audit_relative = plan["qa"]["final_pdf_qa"]
        audit_payload = self.write_json(root / audit_relative, audit)
        return {
            "report": report,
            "report_pdfs": report_pdfs,
            "all_page_renders": all_page_renders,
            "render_rows": render_rows,
            "audit": audit,
            "audit_payload": audit_payload,
            "build_payload": build_payload,
            "render_payload": render_payload,
            "sources": sources,
            "page_counts": page_counts,
        }

    def visual_fixture(self, root: Path, plan: dict):
        fixture = self.automated_fixture(root, plan)
        final_pdf_qa = pub.validate_final_pdf_qa(
            plan,
            root,
            fixture["report"],
            fixture["report_pdfs"],
            fixture["all_page_renders"],
        )
        total_pages = sum(fixture["page_counts"].values())
        sheets = []
        for job in ("book", "jhanswer", "lab"):
            relative = f"qa/visual_review/{job}-contact-sheet.png"
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"contact-sheet-{job}".encode("ascii"))
            sheets.append(
                {
                    "pdf": job,
                    "path": relative,
                    "bytes": path.stat().st_size,
                    "sha256": pub.sha256_file(path),
                    "first_page": 1,
                    "last_page": fixture["page_counts"][job],
                    "disposition": "pass",
                    "notes": "All thumbnails inspected for clipping, centering, and blank-page anomalies.",
                }
            )

        candidate_reviews = [
            {
                "rank": row["rank"],
                "pdf": row["pdf"],
                "page": row["page"],
                "reasons": copy.deepcopy(row["reasons"]),
                "disposition": "pass",
                "notes": "Full-size render inspected; page is legible and the flagged condition is intentional.",
            }
            for row in fixture["audit"]["ranked_candidate_pages"]
        ]
        render_lookup = {
            (row["pdf"], row["page"]): row for row in fixture["render_rows"]
        }
        target_keys = {
            (row["pdf"], row["page"])
            for row in fixture["audit"]["ranked_candidate_pages"]
        }
        target_keys.update({("book", 1), ("jhanswer", 1), ("lab", 1)})
        inspections = []
        for job, page in sorted(target_keys, key=lambda key: (("book", "jhanswer", "lab").index(key[0]), key[1])):
            source = render_lookup[(job, page)]
            inspections.append(
                {
                    "pdf": job,
                    "page": page,
                    "render_path": source["path"],
                    "render_bytes": source["bytes"],
                    "render_sha256": source["sha256"],
                    "purpose": "ranked candidate or representative full-size visual check",
                    "disposition": "pass",
                    "notes": "Inspected at full-page resolution; no clipping or readability defect remains.",
                }
            )

        visual = {
            "schema_version": "hefferon-id-final-visual-review-v1",
            "status": "pass",
            "reviewer": "Codex on the user's request",
            "reviewed_at_utc": "2026-08-22T01:02:03Z",
            "bindings": {
                "build_report": {
                    "path": plan["qa"]["build_report"],
                    "bytes": len(fixture["build_payload"]),
                    "sha256": pub.sha256_bytes(fixture["build_payload"]),
                    "pages": total_pages,
                },
                "automated_pdf_audit": {
                    "path": plan["qa"]["final_pdf_qa"],
                    "bytes": len(fixture["audit_payload"]),
                    "sha256": pub.sha256_bytes(fixture["audit_payload"]),
                    "pages": total_pages,
                    "status": final_pdf_qa["status"],
                    "hard_failure_count": 0,
                },
                "all_page_render_manifest": {
                    "path": plan["qa"]["all_page_render_manifest"],
                    "bytes": len(fixture["render_payload"]),
                    "sha256": pub.sha256_bytes(fixture["render_payload"]),
                    "pages": total_pages,
                },
                "pdfs": {
                    job: {
                        "path": fixture["sources"][job],
                        "bytes": fixture["report_pdfs"][job]["bytes"],
                        "sha256": fixture["report_pdfs"][job]["sha256"],
                        "pages": fixture["report_pdfs"][job]["pages"],
                    }
                    for job in ("book", "jhanswer", "lab")
                },
            },
            "contact_sheets": sheets,
            "review_finding_dispositions": [
                {
                    "finding": finding,
                    "disposition": "pass",
                    "notes": "The related pages and logs were inspected and no release-blocking defect remains.",
                }
                for finding in fixture["audit"]["review_findings"]
            ],
            "ranked_candidate_reviews": candidate_reviews,
            "targeted_full_page_inspections": inspections,
            "summary": {
                "contact_sheet_count": len(sheets),
                "contact_sheet_page_count": total_pages,
                "review_finding_count": len(fixture["audit"]["review_findings"]),
                "ranked_candidate_count": len(candidate_reviews),
                "targeted_full_page_inspection_count": len(inspections),
                "unresolved_findings": 0,
            },
        }
        visual_relative = plan["qa"]["final_visual_review"]
        self.write_json(root / visual_relative, visual)
        fixture["final_pdf_qa"] = final_pdf_qa
        fixture["visual"] = visual
        fixture["visual_path"] = root / visual_relative
        return fixture

    def test_plan_requires_visual_gate_paths_and_true_switches(self):
        plan = self.plan()
        switches = (
            "require_final_pdf_qa_zero_hard_failures",
            "require_final_visual_review_pass",
            "require_complete_visual_review_coverage",
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "plan.json"
            for key in switches:
                mutated = copy.deepcopy(plan)
                mutated["qa"][key] = False
                self.write_json(path, mutated)
                with mock.patch.object(pub, "PLAN_PATH", path):
                    with self.assertRaisesRegex(pub.PublicationError, "must remain true"):
                        pub.load_plan()
            for key in ("final_pdf_qa", "final_visual_review"):
                mutated = copy.deepcopy(plan)
                mutated["qa"][key] = "../escape.json"
                self.write_json(path, mutated)
                with mock.patch.object(pub, "PLAN_PATH", path):
                    with self.assertRaisesRegex(pub.PublicationError, "unsafe relative path"):
                        pub.load_plan()

    def test_generated_final_pdf_qa_exact_fixture_passes(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = self.automated_fixture(root, plan)
            result = pub.validate_final_pdf_qa(
                plan,
                root,
                fixture["report"],
                fixture["report_pdfs"],
                fixture["all_page_renders"],
            )
        self.assertEqual(result["hard_failure_count"], 0)
        self.assertEqual(result["ranked_candidate_count"], 2)

    def test_generated_final_pdf_qa_stale_build_binding_fails_closed(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = self.automated_fixture(root, plan)
            fixture["audit"]["bindings"]["build_report"]["sha256"] = "0" * 64
            self.write_json(root / plan["qa"]["final_pdf_qa"], fixture["audit"])
            with self.assertRaisesRegex(pub.PublicationError, "build-report binding differs"):
                pub.validate_final_pdf_qa(
                    plan,
                    root,
                    fixture["report"],
                    fixture["report_pdfs"],
                    fixture["all_page_renders"],
                )

    def test_generated_final_pdf_qa_hard_failure_fails_closed(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = self.automated_fixture(root, plan)
            fixture["audit"]["hard_failures"] = ["font_embedding_failure:book"]
            self.write_json(root / plan["qa"]["final_pdf_qa"], fixture["audit"])
            with self.assertRaisesRegex(pub.PublicationError, "automated hard failures"):
                pub.validate_final_pdf_qa(
                    plan,
                    root,
                    fixture["report"],
                    fixture["report_pdfs"],
                    fixture["all_page_renders"],
                )

    def test_final_visual_review_exact_fixture_passes(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = self.visual_fixture(root, plan)
            result = pub.validate_final_visual_review(
                plan,
                root,
                fixture["report_pdfs"],
                fixture["all_page_renders"],
                fixture["final_pdf_qa"],
            )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["ranked_candidate_count"], 2)

    def test_final_visual_review_must_cover_every_ranked_candidate_once(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = self.visual_fixture(root, plan)
            fixture["visual"]["ranked_candidate_reviews"].pop()
            self.write_json(fixture["visual_path"], fixture["visual"])
            with self.assertRaisesRegex(pub.PublicationError, "candidate review count differs"):
                pub.validate_final_visual_review(
                    plan,
                    root,
                    fixture["report_pdfs"],
                    fixture["all_page_renders"],
                    fixture["final_pdf_qa"],
                )

    def test_final_visual_review_requires_exact_contact_sheet_page_coverage(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = self.visual_fixture(root, plan)
            fixture["visual"]["contact_sheets"][0]["last_page"] = 1
            self.write_json(fixture["visual_path"], fixture["visual"])
            with self.assertRaisesRegex(pub.PublicationError, "page coverage is not exact"):
                pub.validate_final_visual_review(
                    plan,
                    root,
                    fixture["report_pdfs"],
                    fixture["all_page_renders"],
                    fixture["final_pdf_qa"],
                )

    def test_final_visual_review_requires_candidate_full_page_inspection(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = self.visual_fixture(root, plan)
            inspections = fixture["visual"]["targeted_full_page_inspections"]
            fixture["visual"]["targeted_full_page_inspections"] = [
                row for row in inspections if (row["pdf"], row["page"]) != ("book", 2)
            ]
            fixture["visual"]["summary"]["targeted_full_page_inspection_count"] -= 1
            self.write_json(fixture["visual_path"], fixture["visual"])
            with self.assertRaisesRegex(pub.PublicationError, "not every ranked candidate"):
                pub.validate_final_visual_review(
                    plan,
                    root,
                    fixture["report_pdfs"],
                    fixture["all_page_renders"],
                    fixture["final_pdf_qa"],
                )

    def test_final_visual_review_stale_audit_binding_fails_closed(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = self.visual_fixture(root, plan)
            fixture["visual"]["bindings"]["automated_pdf_audit"]["sha256"] = "0" * 64
            self.write_json(fixture["visual_path"], fixture["visual"])
            with self.assertRaisesRegex(pub.PublicationError, "byte/SHA/page binding differs"):
                pub.validate_final_visual_review(
                    plan,
                    root,
                    fixture["report_pdfs"],
                    fixture["all_page_renders"],
                    fixture["final_pdf_qa"],
                )


if __name__ == "__main__":
    unittest.main()
