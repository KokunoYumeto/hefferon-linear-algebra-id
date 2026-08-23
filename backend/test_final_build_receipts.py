"""Focused fail-closed tests for the final-build live receipt gate."""

from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter


MODULE_PATH = Path(__file__).with_name("validate_backend.py")
SPEC = importlib.util.spec_from_file_location("hefferon_validate_backend", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class FinalBuildReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.report_path = self.root / "build_report.json"
        self.link_path = self.root / "cross_pdf_link_audit.json"
        self.runtime_path = self.root / "lab_sagetex_runtime_manifest.json"
        self.pdf_root = self.root / "output" / "pdf"
        self.pdf_root.mkdir(parents=True)
        self.old_paths = (
            validator.BUILD_REPORT_PATH,
            validator.BUILD_PDF_ROOT,
            validator.CROSS_PDF_LINK_AUDIT_PATH,
            validator.LAB_SAGETEX_RUNTIME_MANIFEST_PATH,
        )
        validator.BUILD_REPORT_PATH = self.report_path
        validator.BUILD_PDF_ROOT = self.pdf_root
        validator.CROSS_PDF_LINK_AUDIT_PATH = self.link_path
        validator.LAB_SAGETEX_RUNTIME_MANIFEST_PATH = self.runtime_path

        self.link = {
            "actions": [{"ordinal": ordinal} for ordinal in range(2064)],
            "all_pair_actions_resolved": True,
            "counts": {
                "book_to_jhanswer": 1032,
                "goto_remote_actions": 2064,
                "jhanswer_to_book": 1032,
                "unresolved_pair_actions": 0,
            },
            "unresolved_pair_actions": [],
        }
        pythontex_fingerprint = {"seed": 20260821}
        self.runtime = {
            "figure_execution": {
                "changed_from_authority_count": 63,
                "final_state": "all_64_pinned_authority_figures_restored_and_rehashed",
                "target_count": 64,
                "unchanged_from_authority_paths": ["asy/ellipsoid1.pdf"],
            },
            "outputs": {
                "command_label_count": 148,
                "command_label_first": 0,
                "command_label_last": 147,
                "command_source_listing_count": 1018,
                "maximum_listed_source_line": 1236,
                "scmd": {"line_count": 1237},
            },
            "schema_version": "hefferon-id-sagetex-runtime-v1",
            "stable_fingerprint": {"sage": "pinned"},
            "status": "pass",
        }
        self.report = {
            "lab_graphics": {"manifest_sha256": "a" * 64},
            "lab_sagetex": {
                "figure_execution": copy.deepcopy(self.runtime["figure_execution"]),
                "outputs": copy.deepcopy(self.runtime["outputs"]),
                "post_execution_authority_graphics": {
                    "count": 64,
                    "manifest_sha256": "a" * 64,
                },
                "pythontex": {
                    "stable_fingerprint": pythontex_fingerprint,
                    "status": "pass",
                    "success_line": "PythonTeX:  lab - 0 error(s), 0 warning(s)",
                },
                "schema_version": "hefferon-id-sagetex-runtime-v1",
                "stable_fingerprint": {
                    "pythontex": pythontex_fingerprint,
                    "sage": "pinned",
                },
                "status": "pass",
            },
            "qa_summary": {
                "generated_english_label_hits": 0,
                "runtime_placeholder_lines": 0,
                "undefined_reference_lines": 0,
            },
            "pdfs": {},
            "status": "success",
        }
        self.witness = {
            "pdfs": {},
            "qa_summary": copy.deepcopy(self.report["qa_summary"]),
            "runtime_placeholder_lines": 0,
        }
        self.reader_artifacts: list[dict] = []
        self.bind_link()
        self.bind_runtime()
        self.bind_pdfs()
        self.bind_report()

    def tearDown(self) -> None:
        (
            validator.BUILD_REPORT_PATH,
            validator.BUILD_PDF_ROOT,
            validator.CROSS_PDF_LINK_AUDIT_PATH,
            validator.LAB_SAGETEX_RUNTIME_MANIFEST_PATH,
        ) = self.old_paths
        self.temporary.cleanup()

    @staticmethod
    def write_json(path: Path, value: dict) -> bytes:
        payload = (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")
        path.write_bytes(payload)
        return payload

    def bind_link(self) -> None:
        payload = self.write_json(self.link_path, self.link)
        digest = validator.sha256(payload)
        self.report["cross_pdf_link_audit"] = {
            "all_pair_actions_resolved": True,
            "bytes": len(payload),
            "counts": copy.deepcopy(self.link["counts"]),
            "path": "build/hefferon_id/cross_pdf_link_audit.json",
            "sha256": digest,
        }
        self.witness["cross_pdf_link_audit"] = {
            "all_pair_actions_resolved": True,
            "answer_links_each_direction": self.link["counts"]["book_to_jhanswer"],
            "bytes": len(payload),
            "goto_remote_actions": self.link["counts"]["goto_remote_actions"],
            "locator": "build/hefferon_id/cross_pdf_link_audit.json",
            "sha256": digest,
            "unresolved_pair_actions": self.link["counts"]["unresolved_pair_actions"],
        }

    def bind_runtime(self) -> None:
        payload = self.write_json(self.runtime_path, self.runtime)
        digest = validator.sha256(payload)
        self.report["lab_sagetex"]["manifest_artifact"] = {
            "bytes": len(payload),
            "path": "build/hefferon_id/lab_sagetex_runtime_manifest.json",
            "sha256": digest,
        }
        outputs = self.runtime["outputs"]
        figures = self.runtime["figure_execution"]
        self.witness["lab_sagetex_runtime"] = {
            "authority_figures_restored": 64,
            "bytes": len(payload),
            "command_labels": outputs["command_label_count"],
            "command_source_listings": outputs["command_source_listing_count"],
            "locator": "build/hefferon_id/lab_sagetex_runtime_manifest.json",
            "maximum_listed_source_line": outputs["maximum_listed_source_line"],
            "pythontex_zero_errors_warnings": True,
            "sage_changed_figures": figures["changed_from_authority_count"],
            "scmd_lines": outputs["scmd"]["line_count"],
            "sha256": digest,
        }

    def bind_report(self) -> None:
        payload = self.write_json(self.report_path, self.report)
        self.witness["build_report_sha256"] = validator.sha256(payload)

    def bind_pdfs(self) -> None:
        page_counts = {"book": 2, "jhanswer": 3, "lab": 1}
        for artifact_id, (component, job, filename) in validator.FINAL_PDF_SPECS.items():
            path = self.pdf_root / filename
            writer = PdfWriter()
            for _ in range(page_counts[job]):
                writer.add_blank_page(width=612, height=792)
            with path.open("wb") as stream:
                writer.write(stream)
            payload = path.read_bytes()
            digest = validator.sha256(payload)
            locator = f"build/hefferon_id/output/pdf/{filename}"
            self.report["pdfs"][job] = {
                "bytes": len(payload),
                "pages": page_counts[job],
                "path": locator,
                "sha256": digest,
            }
            self.witness["pdfs"][component] = {
                "bytes": len(payload),
                "page_count": page_counts[job],
                "sha256": digest,
                "target_locator": locator,
            }
            self.reader_artifacts.append(
                {
                    "bytes": len(payload),
                    "id": artifact_id,
                    "page_count": page_counts[job],
                    "sha256": digest,
                    "target_locator": locator,
                }
            )

    def validate(self) -> None:
        validator.validate_final_build_live_receipts(
            self.witness, self.reader_artifacts
        )

    def test_valid_receipts_pass(self) -> None:
        self.validate()

    def test_stale_cross_pdf_sidecar_fails(self) -> None:
        self.link_path.write_bytes(self.link_path.read_bytes() + b" ")
        with self.assertRaisesRegex(RuntimeError, "cross-PDF link witness"):
            self.validate()

    def test_stale_sagetex_sidecar_fails(self) -> None:
        self.runtime_path.write_bytes(self.runtime_path.read_bytes() + b" ")
        with self.assertRaisesRegex(RuntimeError, "SageTeX runtime witness"):
            self.validate()

    def test_live_runtime_placeholder_fails_even_when_report_is_rebound(self) -> None:
        self.report["qa_summary"]["runtime_placeholder_lines"] = 1
        self.witness["qa_summary"] = copy.deepcopy(self.report["qa_summary"])
        self.bind_report()
        with self.assertRaisesRegex(RuntimeError, "runtime closure"):
            self.validate()

    def test_wrong_link_counts_fail_even_when_all_hashes_are_rebound(self) -> None:
        self.link["counts"]["book_to_jhanswer"] = 1031
        self.bind_link()
        self.bind_report()
        with self.assertRaisesRegex(RuntimeError, "answer-link closure"):
            self.validate()

    def test_boolean_zero_link_count_is_not_accepted_as_integer_zero(self) -> None:
        self.link["counts"]["unresolved_pair_actions"] = False
        self.bind_link()
        self.bind_report()
        with self.assertRaisesRegex(RuntimeError, "answer-link closure"):
            self.validate()

    def test_wrong_runtime_counts_fail_even_when_all_hashes_are_rebound(self) -> None:
        self.runtime["outputs"]["command_label_count"] = 147
        self.report["lab_sagetex"]["outputs"] = copy.deepcopy(self.runtime["outputs"])
        self.bind_runtime()
        self.bind_report()
        with self.assertRaisesRegex(RuntimeError, "runtime fails exact"):
            self.validate()

    def test_malformed_cross_pdf_sha_and_bytes_fail(self) -> None:
        self.witness["cross_pdf_link_audit"]["sha256"] = "z" * 64
        self.witness["cross_pdf_link_audit"]["bytes"] = True
        with self.assertRaisesRegex(RuntimeError, "stale or malformed"):
            self.validate()

    def test_malformed_runtime_sha_and_bytes_fail(self) -> None:
        self.witness["lab_sagetex_runtime"]["sha256"] = "A" * 64
        self.witness["lab_sagetex_runtime"]["bytes"] = "not-an-integer"
        with self.assertRaisesRegex(RuntimeError, "stale or malformed"):
            self.validate()

    def test_each_stale_live_pdf_fails(self) -> None:
        for filename in ("book.pdf", "jhanswer.pdf", "lab.pdf"):
            with self.subTest(filename=filename):
                path = self.pdf_root / filename
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                with self.assertRaisesRegex(RuntimeError, "PDF receipt"):
                    self.validate()
                path.write_bytes(original)

    def test_wrong_build_report_pdf_path_fails(self) -> None:
        self.report["pdfs"]["book"]["path"] = (
            "build/hefferon_id/output/pdf/not-book.pdf"
        )
        self.bind_report()
        with self.assertRaisesRegex(RuntimeError, "build report PDF receipt"):
            self.validate()

    def test_wrong_pdf_page_count_fails_even_when_receipts_agree(self) -> None:
        artifact_id = (
            "r005.hefferon-linear-algebra.artifact.textbook-pdf.locale.id-id"
        )
        artifact = next(
            item for item in self.reader_artifacts if item["id"] == artifact_id
        )
        artifact["page_count"] = 99
        self.report["pdfs"]["book"]["pages"] = 99
        self.witness["pdfs"]["main-textbook"]["page_count"] = 99
        self.bind_report()
        with self.assertRaisesRegex(RuntimeError, "PDF receipt"):
            self.validate()

    def test_malformed_pdf_sha_and_bytes_fail(self) -> None:
        artifact = self.reader_artifacts[0]
        artifact["sha256"] = "not-a-sha256"
        artifact["bytes"] = True
        with self.assertRaisesRegex(RuntimeError, "PDF receipt"):
            self.validate()


if __name__ == "__main__":
    unittest.main()
