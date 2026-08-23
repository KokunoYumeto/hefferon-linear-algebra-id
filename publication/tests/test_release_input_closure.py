from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PUBLICATION_DRIVER = Path(__file__).resolve().parents[1] / "publish_release.py"
PUBLICATION_SPEC = importlib.util.spec_from_file_location(
    "hefferon_publish_release_input_closure", PUBLICATION_DRIVER
)
assert PUBLICATION_SPEC and PUBLICATION_SPEC.loader
pub = importlib.util.module_from_spec(PUBLICATION_SPEC)
PUBLICATION_SPEC.loader.exec_module(pub)

BUILD_DRIVER = Path(__file__).resolve().parents[2] / "tools" / "build_hefferon_id.py"
BUILD_SPEC = importlib.util.spec_from_file_location(
    "hefferon_build_driver_input_closure", BUILD_DRIVER
)
assert BUILD_SPEC and BUILD_SPEC.loader
builder = importlib.util.module_from_spec(BUILD_SPEC)
BUILD_SPEC.loader.exec_module(builder)

FIXTURE_MODULE_PATH = Path(__file__).with_name("test_publish_release.py")
FIXTURE_SPEC = importlib.util.spec_from_file_location(
    "hefferon_publication_existing_fixtures", FIXTURE_MODULE_PATH
)
assert FIXTURE_SPEC and FIXTURE_SPEC.loader
fixtures = importlib.util.module_from_spec(FIXTURE_SPEC)
FIXTURE_SPEC.loader.exec_module(fixtures)


class ReleaseInputClosureTests(unittest.TestCase):
    @staticmethod
    def _write_json(path: Path, value: object) -> bytes:
        payload = pub.canonical_bytes(value, pretty=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return payload

    @staticmethod
    def _canonical_tree(root: Path) -> tuple[list[dict[str, object]], str]:
        rows = []
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            payload = path.read_bytes()
            rows.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
        canonical = json.dumps(
            rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return rows, hashlib.sha256(canonical).hexdigest()

    def _matched_build_fixture(
        self, root: Path, plan: dict[str, object]
    ) -> tuple[dict[str, object], dict[str, Path]]:
        source_root = root / plan["qa"]["source_root"]
        source_root.mkdir(parents=True)
        (source_root / "unit.tex").write_text("unit\n", encoding="utf-8")
        source_rows, source_tree = pub.canonical_source_tree(source_root)
        self._write_json(
            root / plan["qa"]["staged_source_manifest"],
            {"tree_sha256": source_tree, "files": source_rows},
        )

        report = fixtures.PublicationDriverTests.build_fingerprint_report()
        report["status"] = plan["qa"]["required_status"]
        report["source"] = {
            "unchanged_during_build": True,
            "tree_sha256": source_tree,
            "file_count": len(source_rows),
            "live_end_file_count": len(source_rows),
            "live_end_tree_sha256": source_tree,
        }
        report["qa_summary"] = {
            "undefined_reference_lines": 0,
            "generated_english_label_hits": 0,
            "runtime_placeholder_lines": 0,
        }
        report["cross_pdf_link_audit"] = {"all_pair_actions_resolved": True}

        tool_payloads = {
            "builder": ("tools/build_hefferon_id.py", b"builder fixture\n"),
            "lab_graphics_extractor": (
                "tools/extract_lab_graphics_from_authority_pdf.py",
                b"lab extractor fixture\n",
            ),
            "book_graphics_recoverer": (
                "tools/recover_book_asy_graphics.py",
                b"book recoverer fixture\n",
            ),
            "lab_sagetex_runner": (
                "tools/run_lab_sagetex_wsl.py",
                b"Sage runner fixture\n",
            ),
            "pythontex_startup": (
                "tools/pythontex_startup/sitecustomize.py",
                b"PythonTeX startup fixture\n",
            ),
        }
        live_tools: dict[str, Path] = {}
        report["build_tools"] = {}
        for name, (relative, payload) in tool_payloads.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            live_tools[name] = path
            report["build_tools"][name] = {
                "path": str(path.resolve()),
                "bytes": len(payload),
                "sha256": pub.sha256_bytes(payload),
            }

        closure = root / "tools" / "pdftex-font-closure"
        shutil.copytree(builder.PDFTEX_FONT_CLOSURE, closure)
        closure_rows, closure_tree = self._canonical_tree(closure)
        closure_bytes = sum(int(row["bytes"]) for row in closure_rows)
        report["pdftex_font_dependencies"] = {}
        dependency_bytes = 0
        dependency_paths: list[Path] = []
        staged_buckets = {
            ".map": "fonts/map/hefferon-id",
            ".enc": "fonts/enc/hefferon-id",
            ".pfb": "fonts/type1/hefferon-id",
            ".pfa": "fonts/type1/hefferon-id",
        }
        for name, expected_bytes, expected_sha256 in builder.PDFTEX_FONT_DEPENDENCIES:
            suffix = Path(name).suffix.lower()
            dependency = closure / builder.PDFTEX_FONT_BUCKETS[suffix] / name
            self.assertEqual(dependency.stat().st_size, expected_bytes)
            self.assertEqual(pub.sha256_file(dependency), expected_sha256)
            dependency_paths.append(dependency)
            dependency_bytes += expected_bytes
            report["pdftex_font_dependencies"][name] = {
                "source_path": str(dependency.resolve()),
                "source_project_path": dependency.relative_to(root).as_posix(),
                "staged_path": str(
                    (
                        root
                        / "build"
                        / "hefferon_id"
                        / "texmf"
                        / staged_buckets[suffix]
                        / name
                    ).resolve()
                ),
                "bytes": expected_bytes,
                "sha256": expected_sha256,
            }
        report["pdftex_font_dependencies_end_verification"] = {
            "dependency_count": len(dependency_paths),
            "bytes": dependency_bytes,
            "all_verified": True,
        }
        report["pdftex_font_closure"] = {
            "path": str(closure.resolve()),
            "file_count": len(closure_rows),
            "bytes": closure_bytes,
            "tree_sha256": closure_tree,
            "sha256sums_bytes": (closure / "SHA256SUMS").stat().st_size,
            "sha256sums_sha256": pub.sha256_file(closure / "SHA256SUMS"),
            "third_party_notices_bytes": (
                closure / "THIRD_PARTY_NOTICES.json"
            ).stat().st_size,
            "third_party_notices_sha256": pub.sha256_file(
                closure / "THIRD_PARTY_NOTICES.json"
            ),
            "readme_bytes": (closure / "README.md").stat().st_size,
            "readme_sha256": pub.sha256_file(closure / "README.md"),
        }
        report["pdftex_font_closure_end_verification"] = {
            "file_count": len(closure_rows),
            "bytes": closure_bytes,
            "tree_sha256": closure_tree,
            "all_verified": True,
        }

        authority_paths = {
            "book": root / "authority" / "official" / "book.pdf",
            "lab": root / "authority" / "official" / "lab.pdf",
        }
        for name, path in authority_paths.items():
            payload = f"authority {name}\n".encode("ascii")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            report[f"authority_{name}_pdf"] = {
                "path": str(path.resolve()),
                "sha256": pub.sha256_bytes(payload),
            }

        report_key_by_component = {
            "textbook": "book",
            "worked-answers": "jhanswer",
            "sage-lab": "lab",
        }
        for item in plan["reader_pdfs"]:
            path = root / item["source"]
            payload = f"reader {item['component']}\n".encode("ascii")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            report["pdfs"][report_key_by_component[item["component"]]] = {
                "pages": 1,
                "bytes": len(payload),
                "sha256": pub.sha256_bytes(payload),
            }

        metapost_keys = (
            "schema_version",
            "random_seed",
            "source_date_epoch",
            "asset_count",
            "bytes",
            "canonical_sha256",
            "files",
        )
        self._write_json(
            root / plan["qa"]["metapost_asset_manifest"],
            {key: report["metapost_assets"][key] for key in metapost_keys},
        )
        input_keys = (
            "schema_version",
            "all_map_encoding_font_program_inputs_private",
            "jobs",
            "controlled_input_count",
            "metric_input_count",
            "controlled_inputs",
            "metric_inputs",
            "canonical_sha256",
        )
        self._write_json(
            root / plan["qa"]["pdftex_input_audit"],
            {key: report["pdftex_input_audit"][key] for key in input_keys},
        )

        fingerprint = pub.reconstruct_build_fingerprint(report)
        report["reproducibility"] = fixtures.PublicationDriverTests.reproducibility_record(
            fingerprint
        )
        self._write_json(root / plan["qa"]["build_report"], report)
        live_tools["font_closure_payload"] = dependency_paths[0]
        return report, live_tools

    @staticmethod
    def _readiness_patches():
        return (
            mock.patch.object(
                pub, "validate_all_page_render_manifest", return_value={"status": "pass"}
            ),
            mock.patch.object(pub, "validate_final_pdf_qa", return_value={"status": "pass"}),
            mock.patch.object(
                pub, "validate_final_visual_review", return_value={"status": "pass"}
            ),
            mock.patch.object(pub, "validate_cross_pdf_sidecar", return_value={"status": "pass"}),
            mock.patch.object(pub, "validate_lab_sagetex_sidecar", return_value={"status": "pass"}),
            mock.patch.object(pub, "run_backend_validator", return_value={"status": "pass"}),
        )

    def _strict_readiness(self, plan: dict[str, object], root: Path) -> dict[str, object]:
        patches = self._readiness_patches()
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        return pub.strict_readiness(plan, root)

    def test_preflight_and_package_reject_live_build_tool_byte_drift(self):
        plan = copy.deepcopy(pub.load_plan())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _report, live = self._matched_build_fixture(root, plan)
            self.assertEqual(self._strict_readiness(plan, root)["source_tree_sha256"], pub.canonical_source_tree(root / plan["qa"]["source_root"])[1])

            tool = live["builder"]
            original = tool.read_bytes()
            tool.write_bytes(bytes([original[0] ^ 1]) + original[1:])
            with self.assertRaisesRegex(
                pub.PublicationError, r"(?i)(build.?tool|tooling|builder)"
            ):
                self._strict_readiness(plan, root)

    def test_preflight_and_package_reject_live_font_closure_byte_drift(self):
        plan = copy.deepcopy(pub.load_plan())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _report, live = self._matched_build_fixture(root, plan)
            self._strict_readiness(plan, root)

            payload = live["font_closure_payload"]
            original = payload.read_bytes()
            payload.write_bytes(bytes([original[0] ^ 1]) + original[1:])
            with self.assertRaisesRegex(
                pub.PublicationError, r"(?i)(font.?closure|pdftex)"
            ):
                self._strict_readiness(plan, root)

    def test_authority_pdf_build_inputs_are_preserved_in_every_offline_route(self):
        plan = copy.deepcopy(pub.load_plan())
        authority_inputs = {
            builder.AUTHORITY_BOOK_PDF.relative_to(builder.PROJECT_ROOT).as_posix(),
            builder.AUTHORITY_LAB_PDF.relative_to(builder.PROJECT_ROOT).as_posix(),
        }
        self.assertEqual(
            authority_inputs,
            {"authority/official/book.pdf", "authority/official/lab.pdf"},
        )
        editable = next(
            item for item in plan["bundles"] if item["kind"] == "editable-source"
        )
        routes = {
            "offline staging snapshot": set(plan["staging_inputs"]),
            "editable-source release ZIP": set(editable["include"]),
            "GitHub repository snapshot": set(plan["repository_snapshot"]["include"]),
        }
        for route, included in routes.items():
            with self.subTest(route=route):
                self.assertTrue(
                    authority_inputs.issubset(included),
                    f"{route} omits exact builder authority inputs: "
                    f"{sorted(authority_inputs - included)}",
                )


if __name__ == "__main__":
    unittest.main()
