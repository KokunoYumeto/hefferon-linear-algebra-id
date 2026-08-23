from __future__ import annotations

import copy
import io
import importlib.util
import json
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock


DRIVER = Path(__file__).resolve().parents[1] / "publish_release.py"
SPEC = importlib.util.spec_from_file_location("hefferon_publish_release", DRIVER)
assert SPEC and SPEC.loader
pub = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pub)


class PublicationDriverTests(unittest.TestCase):
    def plan(self):
        return copy.deepcopy(pub.load_plan())

    @staticmethod
    def write_json_fixture(path, value):
        payload = (
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return payload

    def cross_pdf_fixture(self, root, plan, *, answers=3):
        counts = {
            "book_to_jhanswer": answers,
            "jhanswer_to_book": answers,
            "unresolved_pair_actions": 0,
            "goto_remote_actions": 2 * answers,
        }
        audit = {
            "all_pair_actions_resolved": True,
            "counts": counts,
            "unresolved_pair_actions": [],
            "actions": [{"ordinal": index} for index in range(2 * answers)],
        }
        relative = plan["qa"]["cross_pdf_link_audit"]
        path = root / relative
        payload = self.write_json_fixture(path, audit)
        report = {
            "generated_answer_stream": {"all_answers": answers},
            "cross_pdf_link_audit": {
                "path": relative,
                "bytes": len(payload),
                "sha256": pub.sha256_bytes(payload),
                "counts": copy.deepcopy(counts),
                "all_pair_actions_resolved": True,
            },
        }
        return path, audit, report

    def lab_sagetex_fixture(self, root, plan):
        graphics_manifest_sha = "a" * 64
        outputs = {
            "sout": {
                "path": "staging/lab.sagetex.sout",
                "bytes": 11,
                "sha256": "1" * 64,
            },
            "scmd": {
                "path": "staging/lab.sagetex.scmd",
                "bytes": 12,
                "sha256": "2" * 64,
                "line_count": 1237,
            },
            "command_label_count": 148,
            "command_label_first": 0,
            "command_label_last": 147,
            "command_source_listing_count": 1018,
            "maximum_listed_source_line": 1236,
            "source_md5": "3" * 32,
        }
        figures = {
            "target_count": 64,
            "changed_from_authority_count": 63,
            "unchanged_from_authority_paths": ["asy/ellipsoid1.pdf"],
            "authority_manifest": {"sha256": graphics_manifest_sha},
            "final_state": "all_64_pinned_authority_figures_restored_and_rehashed",
        }
        sage_stable = {
            "schema_version": "hefferon-id-sagetex-stable-fingerprint-v1",
            "wsl_distro": "Ubuntu-22.04",
            "sage_version": "SageMath version 9.5, Release Date: 2022-01-30",
            "sagetex_distribution_version": "3.6.1",
            "sagetex_module_version": "2021/10/16 v3.6",
            "random_seed": 20260821,
            "source_date_epoch": "1633046400",
            "generated_sage_script_sha256": "4" * 64,
            "compatibility_sage_script_sha256": "5" * 64,
            "runner_sha256": "6" * 64,
            "pytxcode_sha256": "7" * 64,
            "sout_sha256": outputs["sout"]["sha256"],
            "scmd_sha256": outputs["scmd"]["sha256"],
            "source_md5": outputs["source_md5"],
            "command_label_count": 148,
            "command_source_listing_count": 1018,
            "authority_graphics_manifest_sha256": graphics_manifest_sha,
            "sage_changed_figure_count": 63,
            "sage_changed_paths_sha256": "8" * 64,
            "final_figure_source": "pinned_authority_pdf_forms_restored_after_execution",
        }
        pythontex_stable = {
            "schema_version": "hefferon-id-pythontex-stable-fingerprint-v1",
            "version": "PythonTeX 0.19",
            "random_seed": 20260821,
            "pythonhashseed": 0,
            "source_date_epoch": "1633046400",
            "startup_sha256": "9" * 64,
            "macros_sha256": "b" * 64,
            "pygments_sha256": "c" * 64,
        }
        sidecar = {
            "schema_version": "hefferon-id-sagetex-runtime-v1",
            "status": "pass",
            "outputs": outputs,
            "figure_execution": figures,
            "stable_fingerprint": sage_stable,
        }
        relative = plan["qa"]["lab_sagetex_runtime_manifest"]
        path = root / relative
        payload = self.write_json_fixture(path, sidecar)
        runtime_stable = copy.deepcopy(sage_stable)
        runtime_stable["pythontex"] = copy.deepcopy(pythontex_stable)
        runtime = {
            "schema_version": sidecar["schema_version"],
            "status": "pass",
            "outputs": copy.deepcopy(outputs),
            "figure_execution": copy.deepcopy(figures),
            "stable_fingerprint": runtime_stable,
            "pythontex": {
                "status": "pass",
                "success_line": "PythonTeX:  lab - 0 error(s), 0 warning(s)",
                "outputs": {
                    "macros": {"sha256": pythontex_stable["macros_sha256"]},
                    "pygments": {"sha256": pythontex_stable["pygments_sha256"]},
                },
                "stable_fingerprint": copy.deepcopy(pythontex_stable),
            },
            "post_execution_authority_graphics": {
                "count": 64,
                "manifest_sha256": graphics_manifest_sha,
            },
            "manifest_artifact": {
                "path": relative,
                "bytes": len(payload),
                "sha256": pub.sha256_bytes(payload),
            },
        }
        report = {
            "lab_sagetex": runtime,
            "lab_graphics": {"manifest_sha256": graphics_manifest_sha},
        }
        return path, sidecar, report

    def rebind_sidecar(self, path, value, binding):
        payload = self.write_json_fixture(path, value)
        binding["bytes"] = len(payload)
        binding["sha256"] = pub.sha256_bytes(payload)

    @staticmethod
    def build_fingerprint_report():
        metapost_files = [
            {
                "source": "fixture.mp",
                "figure": index + 1,
                "path": f"fixture.{index + 1}",
                "bytes": 1,
                "sha256": "f" * 64,
            }
            for index in range(307)
        ]
        metapost_canonical = pub.sha256_bytes(
            json.dumps(
                metapost_files,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        metapost_core = {
            "schema_version": "hefferon-id-metapost-assets-v1",
            "random_seed": 1,
            "source_date_epoch": "1633046400",
            "asset_count": 307,
            "bytes": 307,
            "canonical_sha256": metapost_canonical,
            "files": metapost_files,
        }
        metapost_payload = pub.canonical_bytes(metapost_core, pretty=True)
        convergence = {}
        for job, comparison_pass in (("book", 7), ("jhanswer", 4)):
            rows = [{"path": f"{job}.pdf", "bytes": 1, "sha256": "0" * 64}]
            state_sha = pub.sha256_bytes(
                json.dumps(
                    rows,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            convergence[job] = {
                "schema_version": "hefferon-id-tex-convergence-v1",
                "job": job,
                "comparison_pass": comparison_pass,
                "matched": True,
                "state": {
                    "schema_version": "hefferon-id-tex-convergence-state-v1",
                    "job": job,
                    "file_count": 1,
                    "bytes": 1,
                    "canonical_sha256": state_sha,
                    "files": rows,
                },
            }
            if job == "book":
                index_rows = [
                    {"path": "book.idx", "bytes": 1, "sha256": "1" * 64},
                    {"path": "book.ind", "bytes": 1, "sha256": "2" * 64},
                ]
                index_sha = pub.sha256_bytes(
                    json.dumps(
                        index_rows,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
                convergence[job]["index_fixed_point"] = {
                    "schema_version": "hefferon-id-book-index-fixed-point-v1",
                    "refreshed_after_tex_pass": 5,
                    "verified_after_tex_pass": 6,
                    "matched": True,
                    "state": {
                        "schema_version": "hefferon-id-book-index-state-v1",
                        "file_count": 2,
                        "bytes": 2,
                        "canonical_sha256": index_sha,
                        "files": index_rows,
                    },
                }
        font_dependency_names = sorted(pub.EXPECTED_PDFTEX_FONT_DEPENDENCY_NAMES)
        font_dependencies = {
            name: {"bytes": 1, "sha256": "a" * 64}
            for name in font_dependency_names
        }
        font_dependencies[font_dependency_names[0]]["bytes"] += (
            pub.EXPECTED_PDFTEX_FONT_DEPENDENCY_BYTES - len(font_dependency_names)
        )
        input_audit_stable = {
            "schema_version": "hefferon-id-pdftex-input-audit-v1",
            "all_map_encoding_font_program_inputs_private": True,
            "jobs": ["book", "jhanswer"],
            "controlled_input_count": 1,
            "metric_input_count": 1,
            "controlled_inputs": [
                {
                    "job": "book",
                    "name": "fixture.map",
                    "suffix": ".map",
                    "bytes": 1,
                    "sha256": "1" * 64,
                    "closure_path": "fonts/map/hefferon-id/fixture.map",
                }
            ],
            "metric_inputs": [
                {
                    "job": "book",
                    "name": "fixture.tfm",
                    "suffix": ".tfm",
                    "bytes": 1,
                    "sha256": "2" * 64,
                }
            ],
        }
        input_audit_canonical = pub.sha256_bytes(
            json.dumps(
                input_audit_stable,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        input_audit_file = {
            **input_audit_stable,
            "canonical_sha256": input_audit_canonical,
        }
        input_audit_payload = pub.canonical_bytes(input_audit_file, pretty=True)
        return {
            "source": {"tree_sha256": "1" * 64},
            "authority_book_pdf": {"path": "C:/fixture/book.pdf", "sha256": "a" * 64},
            "authority_lab_pdf": {"path": "C:/fixture/lab.pdf", "sha256": "b" * 64},
            "book_graphics": {"manifest_sha256": "2" * 64},
            "lab_graphics": {"manifest_sha256": "3" * 64},
            "missing_lab_asset": {"manifest_sha256": "4" * 64},
            "lab_sagetex": {
                "stable_fingerprint": {
                    "schema_version": "hefferon-id-sagetex-stable-fingerprint-v1",
                    "random_seed": 20260821,
                }
            },
            "metapost_assets": {
                **metapost_core,
                "manifest_path": "build/hefferon_id/metapost_asset_manifest.json",
                "manifest_bytes": len(metapost_payload),
                "manifest_sha256": pub.sha256_bytes(metapost_payload),
            },
            "metapost_assets_end_verification": {
                "asset_count": 307,
                "bytes": 307,
                "canonical_sha256": metapost_canonical,
                "all_verified": True,
            },
            "generated_answer_stream": {
                "path": "C:/fixture/bookans.tex",
                "bytes": 1,
                "sha256": "3" * 64,
                "all_answers": 133,
                "topic_count": 1,
                "topic_answers": 133,
                "expected_native_topic_answers": 131,
                "expected_indonesian_edition_supplied_topic_answers": 2,
                "expected_topic_answers": 133,
                "topic_answer_entries": [
                    {"topic_ordinal": index + 1} for index in range(133)
                ],
            },
            "tex_convergence": convergence,
            "pdftex_input_audit": {
                **input_audit_file,
                "path": "build/hefferon_id/pdftex_input_audit.json",
                "bytes": len(input_audit_payload),
                "sha256": pub.sha256_bytes(input_audit_payload),
            },
            "build_tools": {
                name: {"sha256": "5" * 64}
                for name in pub.EXPECTED_BUILD_TOOL_PATHS
            },
            "tool_versions": {
                "python": "Python 3.13",
                "xelatex": "XeTeX test fixture",
            },
            "pdftex_font_dependencies": font_dependencies,
            "pdftex_font_dependencies_end_verification": {
                "dependency_count": len(font_dependencies),
                "bytes": pub.EXPECTED_PDFTEX_FONT_DEPENDENCY_BYTES,
                "all_verified": True,
            },
            "pdftex_font_closure": {
                "path": "C:/fixture/pdftex-font-closure",
                "file_count": pub.EXPECTED_PDFTEX_FONT_CLOSURE_FILE_COUNT,
                "bytes": pub.EXPECTED_PDFTEX_FONT_CLOSURE_BYTES,
                "tree_sha256": pub.EXPECTED_PDFTEX_FONT_CLOSURE_TREE_SHA256,
                "sha256sums_bytes": 2700,
                "sha256sums_sha256": "c" * 64,
                "third_party_notices_bytes": 8000,
                "third_party_notices_sha256": "d" * 64,
                "readme_bytes": 4000,
                "readme_sha256": "e" * 64,
            },
            "pdftex_font_closure_end_verification": {
                "file_count": pub.EXPECTED_PDFTEX_FONT_CLOSURE_FILE_COUNT,
                "bytes": pub.EXPECTED_PDFTEX_FONT_CLOSURE_BYTES,
                "tree_sha256": pub.EXPECTED_PDFTEX_FONT_CLOSURE_TREE_SHA256,
                "all_verified": True,
            },
            "pdfs": {
                "book": {"pages": 578, "bytes": 1001, "sha256": "7" * 64},
                "jhanswer": {"pages": 433, "bytes": 1002, "sha256": "8" * 64},
                "lab": {"pages": 109, "bytes": 1003, "sha256": "9" * 64},
            },
        }

    @staticmethod
    def reproducibility_record(fingerprint):
        payload = (
            json.dumps(
                fingerprint, ensure_ascii=False, sort_keys=True, indent=2
            )
            + "\n"
        ).encode("utf-8")
        digest = pub.sha256_bytes(payload)
        return {
            "matched": True,
            "sha256": digest,
            "current_sha256": digest,
            "baseline": copy.deepcopy(fingerprint),
            "current": copy.deepcopy(fingerprint),
        }

    def test_01_zenodo_same_size_wrong_md5_blocks_publish_boundary(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "a.bin"
            path.write_bytes(b"right")
            expected = {
                "a.bin": {
                    "path": "a.bin",
                    "local_path": str(path),
                    "bytes": 5,
                    "sha256": pub.sha256_file(path),
                }
            }
            deposition = {
                "files": [
                    {
                        "filename": "a.bin",
                        "filesize": 5,
                        "checksum": "md5:" + "0" * 32,
                        "links": {"download": "https://zenodo.org/api/files/a"},
                    }
                ]
            }
            client = mock.Mock(origins={pub.origin(pub.ZENODO_ORIGIN)})
            with self.assertRaises(pub.PublicationError):
                pub.verify_zenodo_files_authenticated(client, deposition, expected)
            client.content_sha256.assert_not_called()

    def test_02_github_release_is_draft_until_exact_assets_verified(self):
        plan = self.plan()
        state = {
            "github_repository_id": 1,
            "github_commit_sha": "c" * 40,
            "blob_cache": {},
        }
        binding = {"fingerprint": "f" * 64}
        calls = []
        fake_release = {
            "id": 7,
            "draft": True,
            "upload_url": (
                f"https://uploads.github.com/repos/{plan['github']['owner']}/"
                f"{plan['github']['repository']}/releases/7/assets{{?name}}"
            ),
            "html_url": "https://github.com/o/r/releases/tag/v",
        }

        class Client:
            def request(self, method, endpoint, **kwargs):
                calls.append((method, endpoint, kwargs.get("body")))
                if method == "POST" and endpoint.endswith("/releases"):
                    self.assert_draft(kwargs["body"])
                    return 201, {}, fake_release
                return 200, {}, {"id": 7}

            @staticmethod
            def assert_draft(body):
                if body.get("draft") is not True:
                    raise AssertionError("release was not created as draft")

            def upload_release_asset(self, _url, _path):
                return {"id": 1, "name": "a", "size": 1}

        release_assets_calls = iter([[], [{"id": 1, "name": "a", "size": 1}]])
        draft_transitions = []
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            pub, "verify_inventory"
        ), mock.patch.object(pub, "artifact_map", return_value={"a": {"path": "a", "bytes": 1, "sha256": "a" * 64}}), mock.patch.object(
            pub, "ensure_tag", return_value="c" * 40
        ), mock.patch.object(pub, "find_release", return_value=None), mock.patch.object(
            pub,
            "reconcile_release_metadata",
            side_effect=lambda _c, _p, _f, release, _sha, draft: draft_transitions.append(draft) or {**release, "draft": draft},
        ), mock.patch.object(
            pub, "release_assets", side_effect=lambda *_args: next(release_assets_calls)
        ), mock.patch.object(pub, "verify_github_asset_bytes"), mock.patch.object(
            pub, "repository_entries", return_value={}
        ), mock.patch.object(pub, "verify_remote_repository"), mock.patch.object(
            pub, "resolve_tag", return_value="c" * 40
        ), mock.patch.object(pub, "github_optional", return_value=(200, {"id": 7})), mock.patch.object(
            pub, "save_state"
        ):
            final = Path(td)
            (final / "release-assets").mkdir()
            (final / "release-assets" / "a").write_bytes(b"x")
            release_readme = (
                final
                / "snapshot"
                / "publication"
                / plan["release_assets"]["readme"]
            )
            release_readme.parent.mkdir(parents=True)
            release_readme.write_text("release body", encoding="utf-8")
            result = pub.ensure_github_release(Client(), plan, state, final, {"artifacts": []}, binding)
        self.assertFalse(result["draft"])
        self.assertEqual(draft_transitions, [True, False])

    def test_03_authenticated_cross_origin_redirect_is_rejected(self):
        handler = pub.SafeRedirectHandler()
        request = urllib.request.Request(
            "https://api.github.com/a", headers={"Authorization": "Bearer secret"}
        )
        with self.assertRaises(pub.PublicationError):
            handler.redirect_request(
                request, None, 302, "Found", {}, "https://evil.invalid/capture"
            )

    def test_04_inventory_detects_same_size_post_validation_mutation(self):
        binding = {"fingerprint": "f"}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "snapshot" / "x"
            target.parent.mkdir()
            target.write_bytes(b"good")
            rows = pub.inventory_rows(root, omit={"inventory.json"})
            pub.save_json(
                root / "inventory.json",
                {
                    "schema_version": "hefferon-id-immutable-inventory-v1",
                    "stage": "base",
                    "binding": binding,
                    "inventory_sha256": pub.inventory_digest(rows),
                    "file_count": len(rows),
                    "files": rows,
                    "readiness": {},
                },
            )
            pub.verify_inventory(root, binding)
            target.write_bytes(b"evil")
            with self.assertRaises(pub.PublicationError):
                pub.verify_inventory(root, binding)

    def test_05_pdf_report_entry_bytes_sha_and_pages_are_mandatory(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_root = root / plan["qa"]["source_root"]
            source_root.mkdir(parents=True)
            (source_root / "unit.tex").write_text("unit", encoding="utf-8")
            source_rows, source_tree = pub.canonical_source_tree(source_root)
            source_manifest = root / plan["qa"]["staged_source_manifest"]
            source_manifest.parent.mkdir(parents=True)
            source_manifest.write_text(
                json.dumps({"tree_sha256": source_tree, "files": source_rows}),
                encoding="utf-8",
            )
            report = {
                "status": "success",
                "source": {
                    "unchanged_during_build": True,
                    "tree_sha256": source_tree,
                    "file_count": len(source_rows),
                    "live_end_file_count": len(source_rows),
                    "live_end_tree_sha256": source_tree,
                },
                "reproducibility": {
                    "matched": True,
                    "sha256": "a" * 64,
                    "current_sha256": "a" * 64,
                    "baseline": {
                        "schema_version": "hefferon-id-build-reproducibility-v4"
                    },
                    "current": {
                        "schema_version": "hefferon-id-build-reproducibility-v4"
                    },
                },
                "qa_summary": {
                    "undefined_reference_lines": 0,
                    "generated_english_label_hits": 0,
                    "runtime_placeholder_lines": 0,
                },
                "cross_pdf_link_audit": {"all_pair_actions_resolved": True},
                "pdfs": {},
            }
            path = root / plan["qa"]["build_report"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report), encoding="utf-8")
            with mock.patch.object(
                pub, "validate_build_reproducibility"
            ), mock.patch.object(
                pub, "run_backend_validator", return_value={"status": "pass"}
            ):
                with self.assertRaisesRegex(pub.PublicationError, r"pdfs\.book"):
                    pub.strict_readiness(plan, root)

    def test_06_full_repository_tree_blob_mismatch_is_rejected(self):
        plan = self.plan()

        class Client:
            def request(self, _method, endpoint, **_kwargs):
                if "/git/ref/heads/" in endpoint:
                    return 200, {}, {
                        "ref": f"refs/heads/{plan['github']['default_branch']}",
                        "object": {"sha": "c" * 40, "type": "commit"},
                    }
                if "/git/commits/" in endpoint:
                    return 200, {}, {"sha": "c" * 40, "tree": {"sha": "b" * 40}}
                return 200, {}, {
                    "sha": "b" * 40,
                    "truncated": False,
                    "tree": [{"path": "x", "type": "blob", "mode": "100644", "sha": "d" * 40, "size": 1}],
                }

        with self.assertRaisesRegex(pub.PublicationError, "tree/blob identity differs"):
            pub.verify_remote_repository(
                Client(),
                plan,
                {"x": {"sha": "e" * 40, "mode": "100644", "bytes": 1, "sha256": "a" * 64}},
                "c" * 40,
            )

    def test_07_transaction_state_must_match_exact_fingerprint_binding(self):
        binding = {"fingerprint": "right"}
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "schema_version": "hefferon-id-publication-transaction-v2",
                        "binding": {"fingerprint": "wrong"},
                        "transaction_fingerprint": "wrong",
                        "blob_cache": {},
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(pub, "STATE_PATH", state_path):
                with self.assertRaises(pub.PublicationError):
                    pub.load_state(binding)

    def test_08_nonempty_unbound_repository_is_not_adopted_even_if_size_zero(self):
        plan = self.plan()
        repo = {
            "id": 1,
            "private": False,
            "full_name": f"{plan['github']['owner']}/{plan['github']['repository']}",
            "size": 0,
        }
        state = {"blob_cache": {}}
        with mock.patch.object(
            pub,
            "github_optional",
            side_effect=[
                (200, repo),
                (200, [{"ref": "refs/heads/main"}]),
                (200, []),
                (200, []),
            ],
        ):
            with self.assertRaises(pub.PublicationError):
                pub.ensure_github_repository(mock.Mock(), plan, state)

    def test_09_release_metadata_mismatch_after_patch_is_rejected(self):
        plan = self.plan()
        release = {"id": 4}
        client = mock.Mock()
        client.request.return_value = (200, {}, {"id": 4, "name": "wrong"})
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            pub, "resolve_tag", return_value="c" * 40
        ):
            final = Path(td)
            body = final / "snapshot" / "publication" / plan["release_assets"]["readme"]
            body.parent.mkdir(parents=True)
            body.write_text("body", encoding="utf-8")
            with self.assertRaises(pub.PublicationError):
                pub.reconcile_release_metadata(client, plan, final, release, "c" * 40, draft=True)

    def test_10_complete_zenodo_metadata_comparison_rejects_missing_field(self):
        plan = self.plan()
        fingerprint = "f" * 64
        metadata = pub.zenodo_metadata(plan, "10.5281/zenodo.1", fingerprint)
        del metadata["related_identifiers"]
        with self.assertRaises(pub.PublicationError):
            pub.assert_zenodo_metadata(
                metadata, plan, "10.5281/zenodo.1", fingerprint, public=False
            )

    def test_11_urlerror_is_normalized_after_bounded_retries(self):
        opener = mock.Mock()
        opener.open.side_effect = urllib.error.URLError("offline")
        with mock.patch("urllib.request.build_opener", return_value=opener), mock.patch.object(pub.time, "sleep"):
            with self.assertRaises(pub.PublicationError):
                pub.http_bytes("GET", "https://example.com/x", retryable=True)
        self.assertEqual(opener.open.call_count, 5)

    def test_12_exclusive_lock_rejects_concurrent_transaction(self):
        with tempfile.TemporaryDirectory() as td:
            lock_path = Path(td) / "lock"
            with pub.TransactionLock(lock_path):
                with self.assertRaises(pub.PublicationError):
                    with pub.TransactionLock(lock_path):
                        pass

    def test_13_public_plan_rejects_embedded_credentials(self):
        plan = self.plan()
        plan["credentials"] = {"github": "private/path"}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "plan.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            with mock.patch.object(pub, "PLAN_PATH", path):
                with self.assertRaises(pub.PublicationError):
                    pub.load_plan()

    def test_publication_plan_cannot_redirect_the_single_purpose_github_target(self):
        baseline = self.plan()
        mutations = (
            ("owner", "AnotherOwner"),
            ("repository", "another-repository"),
            ("default_branch", "release"),
        )
        for key, value in mutations:
            with self.subTest(key=key):
                plan = copy.deepcopy(baseline)
                plan["github"][key] = value
                with tempfile.TemporaryDirectory() as td:
                    path = Path(td) / "plan.json"
                    path.write_text(json.dumps(plan), encoding="utf-8")
                    with mock.patch.object(pub, "PLAN_PATH", path):
                        with self.assertRaisesRegex(
                            pub.PublicationError,
                            "GitHub target must remain exactly",
                        ):
                            pub.load_plan()

    def test_14_traversal_duplicate_and_wrong_json_types_are_rejected(self):
        with self.assertRaises(pub.PublicationError):
            pub.validate_basename("../asset.pdf", "test")
        with self.assertRaises(pub.PublicationError):
            pub.decode_bounded_json(b"[]", dict, "test")

    def test_15_default_branch_reconciles_on_already_current_resume(self):
        plan = self.plan()
        state = {
            "github_repository_id": 1,
            "github_commit_sha": "c" * 40,
            "blob_cache": {},
        }
        verified = {
            "commit_sha": "c" * 40,
            "tree_sha": "b" * 40,
            "repository_snapshot_sha256": "a" * 64,
        }
        with mock.patch.object(pub, "verify_inventory"), mock.patch.object(
            pub, "repository_entries", return_value={"x": {}}
        ), mock.patch.object(pub, "remote_branch_state", return_value=("c" * 40, "b" * 40, {})), mock.patch.object(
            pub, "verify_remote_repository", return_value=verified
        ), mock.patch.object(pub, "save_state"), mock.patch.object(
            pub, "reconcile_repository_settings", return_value={"id": 1}
        ) as reconcile:
            result = pub.publish_repository_snapshot(
                mock.Mock(), plan, state, Path("unused"), {"fingerprint": "f"}
            )
        self.assertEqual(result["status"], "already-current")
        reconcile.assert_called_once_with(mock.ANY, plan, branch_exists=True)

    def test_16_blob_cache_skips_completed_blob_and_uploads_only_missing(self):
        plan = self.plan()
        first = {"bytes": 1, "sha256": "a" * 64, "sha": "1" * 40, "mode": "100644", "local_path": Path("a")}
        second = {"bytes": 1, "sha256": "b" * 64, "sha": "2" * 40, "mode": "100644", "local_path": Path("b")}
        state = {
            "github_repository_id": 1,
            "blob_cache": {
                "a": {"bytes": 1, "sha256": "a" * 64, "remote_sha": "1" * 40}
            }
        }
        client = mock.Mock()
        client.upload_blob.return_value = {"sha": "2" * 40}
        client.request.side_effect = [
            (201, {}, {"sha": "b" * 40}),
            (201, {}, {"sha": "c" * 40}),
            (201, {}, {"ref": "heads/main"}),
        ]
        with mock.patch.object(pub, "verify_inventory"), mock.patch.object(
            pub, "repository_entries", return_value={"a": first, "b": second}
        ), mock.patch.object(pub, "remote_branch_state", side_effect=[None, None]), mock.patch.object(
            pub, "save_state"
        ), mock.patch.object(
            pub,
            "poll_remote_branch_state",
            return_value=("c" * 40, "b" * 40, {}),
        ), mock.patch.object(
            pub, "reconcile_repository_settings", return_value={"id": 1}
        ), mock.patch.object(
            pub,
            "verify_remote_repository",
            return_value={"commit_sha": "c" * 40, "tree_sha": "b" * 40, "repository_snapshot_sha256": "a" * 64},
        ), mock.patch.object(pub.time, "sleep"):
            pub.publish_repository_snapshot(
                client, plan, state, Path("unused"), {"fingerprint": "f"}
            )
        client.upload_blob.assert_called_once_with(pub.repo_base(plan) + "/git/blobs", Path("b"))

    def test_17_upstream_repository_related_resource_is_software(self):
        metadata = pub.zenodo_metadata(self.plan(), "10.5281/zenodo.1", "f" * 64)
        self.assertEqual(metadata["related_identifiers"][0]["resource_type"], "software")

    def test_18_github_pagination_reaches_older_pages(self):
        client = mock.Mock()
        first = [{"id": index} for index in range(100)]
        client.request.side_effect = [(200, {}, first), (200, {}, [{"id": 100}])]
        rows = pub.github_paginated(client, "/releases")
        self.assertEqual(len(rows), 101)
        self.assertEqual(client.request.call_count, 2)

    def test_19_anonymous_zenodo_pagination_respects_public_page_cap(self):
        first = [{"id": index} for index in range(pub.ZENODO_PUBLIC_PAGE_SIZE)]
        second = [{"id": pub.ZENODO_PUBLIC_PAGE_SIZE}]
        with mock.patch.object(
            pub,
            "anonymous_json",
            side_effect=[{"hits": {"hits": first}}, {"hits": {"hits": second}}],
        ) as anonymous:
            rows = pub.zenodo_public_paginated("fixture")
        self.assertEqual(len(rows), pub.ZENODO_PUBLIC_PAGE_SIZE + 1)
        self.assertEqual(anonymous.call_count, 2)
        for call in anonymous.call_args_list:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(call.args[0]).query)
            self.assertEqual(query["size"], [str(pub.ZENODO_PUBLIC_PAGE_SIZE)])

    def test_staging_preserves_lexical_paths_through_reparse_resolution(self):
        # A Windows junction can resolve a lexical `doc/samples` path to a
        # different physical target.  The snapshot must retain the inventory
        # path while still validating the resolved source boundary.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "doc" / "samples" / "fixture.txt"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"fixture")
            snapshot = root / "snapshot"
            resolved = root / "physical" / "fixture.txt"
            resolved.parent.mkdir(parents=True)
            resolved.write_bytes(b"fixture")
            with mock.patch.object(pub, "ensure_under", return_value=resolved):
                relative = pub.validate_relative_name(
                    "doc/samples/fixture.txt", "staging input"
                )
                checked = pub.ensure_under(root / relative, root)
            self.assertEqual(relative, "doc/samples/fixture.txt")
            self.assertEqual(checked, resolved)
            self.assertNotEqual(
                pub.lexical_relative(checked, root), relative
            )

    def test_recovery_rejects_wrong_zenodo_fingerprint(self):
        plan = self.plan()
        deposition = {
            "id": 1,
            "doi": "10.5281/zenodo.1",
            "metadata": pub.zenodo_metadata(plan, "10.5281/zenodo.1", "x" * 64),
        }
        with self.assertRaises(pub.PublicationError):
            pub.validate_deposition_identity(
                deposition,
                plan,
                {"fingerprint": "y" * 64},
                require_final_metadata=False,
            )

    def test_authenticated_asset_without_optional_digest_is_still_downloaded(self):
        client = mock.Mock()
        client.authenticated_asset_sha256.return_value = (3, "a" * 64)
        pub.verify_github_asset_bytes(
            client,
            self.plan(),
            {"id": 8, "name": "a", "size": 3},
            {"path": "a", "bytes": 3, "sha256": "a" * 64},
        )
        client.authenticated_asset_sha256.assert_called_once()

    def test_api_supplied_upload_origin_is_exact(self):
        with self.assertRaises(pub.PublicationError):
            pub.validate_origin(
                "https://uploads.github.com.evil.invalid/x",
                {pub.origin(pub.GITHUB_UPLOAD_ORIGIN)},
            )

    def test_atomic_write_uses_unique_temp_and_leaves_exact_target_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "state.json"
            pub.atomic_write(target, b"one")
            pub.atomic_write(target, b"two")
            self.assertEqual(target.read_bytes(), b"two")
            self.assertEqual([path.name for path in root.iterdir()], ["state.json"])

    def test_rate_limited_github_403_is_retried_with_server_delay(self):
        url = "https://api.github.com/user"
        limited = urllib.error.HTTPError(
            url,
            403,
            "rate limited",
            {"Retry-After": "0", "X-RateLimit-Remaining": "0"},
            io.BytesIO(b'{"message":"API rate limit exceeded"}'),
        )
        response = mock.MagicMock()
        response.status = 200
        response.headers = {"Content-Length": "2"}
        response.read.return_value = b"{}"
        response.geturl.return_value = url
        response.__enter__.return_value = response
        opener = mock.MagicMock()
        opener.open.side_effect = [limited, response]
        with mock.patch("urllib.request.build_opener", return_value=opener), mock.patch.object(
            pub.time, "sleep"
        ) as sleeper:
            status, _headers, payload, final_url = pub.http_bytes(
                "GET",
                url,
                retryable=True,
                allowed_origins={pub.origin(pub.GITHUB_API_ORIGIN)},
            )
        self.assertEqual((status, payload, final_url), (200, b"{}", url))
        self.assertEqual(opener.open.call_count, 2)
        sleeper.assert_called_once_with(0.0)

    def test_all_page_render_manifest_is_bound_to_every_pdf_page(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            relative = plan["qa"]["all_page_render_manifest"]
            path = root / relative
            path.parent.mkdir(parents=True)
            page_counts = {"book": 2, "jhanswer": 1, "lab": 1}
            rows = []
            report_pdfs = {}
            for job, pages in page_counts.items():
                job_rows = []
                width = len(str(pages))
                for page in range(1, pages + 1):
                    row = {
                        "pdf": job,
                        "page": page,
                        "path": f"tmp/pdfs/hefferon_id/{job}/page-{page:0{width}d}.png",
                        "bytes": 100 + page,
                        "sha256": f"{page:064x}",
                        "width": 612,
                        "height": 792,
                        "ink_fraction": 0.1,
                        "mean_luminance": 240.0,
                        "fully_white": False,
                    }
                    rows.append(row)
                    job_rows.append(row)
                canonical = json.dumps(
                    job_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
                report_pdfs[job] = {
                    "pages": pages,
                    "all_page_renders": {
                        "count": pages,
                        "bytes": sum(row["bytes"] for row in job_rows),
                        "canonical_sha256": pub.sha256_bytes(canonical),
                    },
                }
            payload = (json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
                "utf-8"
            )
            path.write_bytes(payload)
            report = {
                "all_page_render_manifest": {
                    "path": str(path),
                    "count": len(rows),
                    "bytes_rendered": sum(row["bytes"] for row in rows),
                    "manifest_bytes": len(payload),
                    "manifest_sha256": pub.sha256_bytes(payload),
                }
            }
            result = pub.validate_all_page_render_manifest(
                plan, root, report, report_pdfs
            )
            self.assertEqual(result["count"], 4)
            self.assertEqual(result["pdf_page_counts"], page_counts)

    def test_malformed_all_page_render_manifest_cannot_pass_readiness_gate(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / plan["qa"]["all_page_render_manifest"]
            path.parent.mkdir(parents=True)
            path.write_text('{"status":"failed","rendered_pages":0}', encoding="utf-8")
            with self.assertRaisesRegex(pub.PublicationError, "expected list"):
                pub.validate_all_page_render_manifest(plan, root, {}, {})

    def test_sidecar_qa_plan_fields_are_mandatory_and_cannot_be_disabled(self):
        plan = self.plan()
        required_switches = (
            "require_sidecar_byte_bindings",
            "require_lab_sagetex_closure",
            "require_build_fingerprint_v4",
        )
        required_paths = (
            "cross_pdf_link_audit",
            "lab_sagetex_runtime_manifest",
            "metapost_asset_manifest",
            "pdftex_input_audit",
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "publication-plan.json"
            for key in required_switches:
                with self.subTest(switch=key):
                    mutated = copy.deepcopy(plan)
                    mutated["qa"][key] = False
                    self.write_json_fixture(path, mutated)
                    with mock.patch.object(pub, "PLAN_PATH", path):
                        with self.assertRaisesRegex(pub.PublicationError, "must remain true"):
                            pub.load_plan()
            for key in required_paths:
                with self.subTest(path=key):
                    mutated = copy.deepcopy(plan)
                    mutated["qa"][key] = "../escaped.json"
                    self.write_json_fixture(path, mutated)
                    with mock.patch.object(pub, "PLAN_PATH", path):
                        with self.assertRaisesRegex(pub.PublicationError, "unsafe relative path"):
                            pub.load_plan()

    def test_cross_pdf_sidecar_valid_fixture_passes(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _path, _audit, report = self.cross_pdf_fixture(root, plan)
            result = pub.validate_cross_pdf_sidecar(plan, root, report)
        self.assertEqual(result["answer_links_each_direction"], 3)
        self.assertTrue(result["all_pair_actions_resolved"])

    def test_cross_pdf_sidecar_stale_sha_fails_closed(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _path, _audit, report = self.cross_pdf_fixture(root, plan)
            report["cross_pdf_link_audit"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(pub.PublicationError, "SHA-256 differs"):
                pub.validate_cross_pdf_sidecar(plan, root, report)

    def test_cross_pdf_sidecar_self_consistent_wrong_count_fails_closed(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path, audit, report = self.cross_pdf_fixture(root, plan)
            audit["counts"]["goto_remote_actions"] = 5
            report["cross_pdf_link_audit"]["counts"] = copy.deepcopy(audit["counts"])
            self.rebind_sidecar(
                path, audit, report["cross_pdf_link_audit"]
            )
            with self.assertRaisesRegex(pub.PublicationError, "action closure differs"):
                pub.validate_cross_pdf_sidecar(plan, root, report)

    def test_lab_sagetex_sidecar_valid_fixture_passes(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _path, _sidecar, report = self.lab_sagetex_fixture(root, plan)
            result = pub.validate_lab_sagetex_sidecar(plan, root, report)
        self.assertEqual(result["command_labels"], 148)
        self.assertEqual(result["sage_changed_figures"], 63)
        self.assertTrue(result["pythontex_zero_errors_warnings"])

    def test_lab_sagetex_sidecar_stale_sha_fails_closed(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _path, _sidecar, report = self.lab_sagetex_fixture(root, plan)
            report["lab_sagetex"]["manifest_artifact"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(pub.PublicationError, "SHA-256 differs"):
                pub.validate_lab_sagetex_sidecar(plan, root, report)

    def test_lab_sagetex_self_consistent_wrong_output_count_fails_closed(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path, sidecar, report = self.lab_sagetex_fixture(root, plan)
            sidecar["outputs"]["command_label_count"] = 149
            report["lab_sagetex"]["outputs"] = copy.deepcopy(sidecar["outputs"])
            self.rebind_sidecar(
                path, sidecar, report["lab_sagetex"]["manifest_artifact"]
            )
            with self.assertRaisesRegex(pub.PublicationError, "command-output closure differs"):
                pub.validate_lab_sagetex_sidecar(plan, root, report)

    def test_lab_sagetex_report_runtime_drift_fails_closed(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _path, _sidecar, report = self.lab_sagetex_fixture(root, plan)
            report["lab_sagetex"]["outputs"]["maximum_listed_source_line"] = 1235
            with self.assertRaisesRegex(pub.PublicationError, "report outputs differ"):
                pub.validate_lab_sagetex_sidecar(plan, root, report)

    def test_lab_sagetex_self_consistent_sage_control_mutation_fails_closed(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path, sidecar, report = self.lab_sagetex_fixture(root, plan)
            sidecar["stable_fingerprint"]["random_seed"] = 0
            report["lab_sagetex"]["stable_fingerprint"]["random_seed"] = 0
            self.rebind_sidecar(
                path, sidecar, report["lab_sagetex"]["manifest_artifact"]
            )
            with self.assertRaisesRegex(pub.PublicationError, "SageTeX stable fingerprint"):
                pub.validate_lab_sagetex_sidecar(plan, root, report)

    def test_lab_sagetex_self_consistent_pythontex_control_mutation_fails_closed(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _path, _sidecar, report = self.lab_sagetex_fixture(root, plan)
            pythontex = report["lab_sagetex"]["pythontex"]["stable_fingerprint"]
            report_stable = report["lab_sagetex"]["stable_fingerprint"]["pythontex"]
            pythontex["pythonhashseed"] = 1
            report_stable["pythonhashseed"] = 1
            with self.assertRaisesRegex(pub.PublicationError, "PythonTeX deterministic"):
                pub.validate_lab_sagetex_sidecar(plan, root, report)

    def test_build_fingerprint_v3_is_recomputed_from_live_report_fields(self):
        report = self.build_fingerprint_report()
        fingerprint = pub.reconstruct_build_fingerprint(report)
        self.assertEqual(
            set(fingerprint["pdftex_font_closure"]),
            {
                "file_count",
                "bytes",
                "tree_sha256",
                "sha256sums_bytes",
                "sha256sums_sha256",
                "third_party_notices_bytes",
                "third_party_notices_sha256",
                "readme_bytes",
                "readme_sha256",
            },
        )
        self.assertEqual(
            set(fingerprint["pdftex_font_closure_end_verification"]),
            {"file_count", "bytes", "tree_sha256", "all_verified"},
        )
        self.assertNotIn("path", fingerprint["pdftex_font_closure"])
        reproducibility = self.reproducibility_record(fingerprint)
        pub.validate_build_reproducibility(report, reproducibility)

        mutated = copy.deepcopy(reproducibility)
        mutated["baseline"]["lab_sagetex_stable_fingerprint"]["random_seed"] = 0
        mutated["current"] = copy.deepcopy(mutated["baseline"])
        payload = (
            json.dumps(
                mutated["current"], ensure_ascii=False, sort_keys=True, indent=2
            )
            + "\n"
        ).encode("utf-8")
        mutated["sha256"] = pub.sha256_bytes(payload)
        mutated["current_sha256"] = pub.sha256_bytes(payload)
        with self.assertRaisesRegex(pub.PublicationError, "live build-report fields"):
            pub.validate_build_reproducibility(report, mutated)

    def test_metapost_manifest_binding_accepts_windows_crlf_sidecar(self):
        report = self.build_fingerprint_report()
        core = {
            key: report["metapost_assets"][key]
            for key in (
                "schema_version",
                "random_seed",
                "source_date_epoch",
                "asset_count",
                "bytes",
                "canonical_sha256",
                "files",
            )
        }
        payload = pub.canonical_bytes(core, pretty=True).replace(b"\n", b"\r\n")
        report["metapost_assets"]["manifest_bytes"] = len(payload)
        report["metapost_assets"]["manifest_sha256"] = pub.sha256_bytes(payload)
        fingerprint = pub.reconstruct_build_fingerprint(report)
        self.assertEqual(
            fingerprint["metapost_assets"]["manifest_bytes"], len(payload)
        )

    def test_pdftex_input_audit_binding_accepts_windows_crlf_sidecar(self):
        report = self.build_fingerprint_report()
        stable = {
            key: report["pdftex_input_audit"][key]
            for key in (
                "schema_version",
                "all_map_encoding_font_program_inputs_private",
                "jobs",
                "controlled_input_count",
                "metric_input_count",
                "controlled_inputs",
                "metric_inputs",
            )
        }
        canonical = pub.sha256_bytes(
            json.dumps(
                stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        )
        payload = pub.canonical_bytes(
            {**stable, "canonical_sha256": canonical}, pretty=True
        ).replace(b"\n", b"\r\n")
        report["pdftex_input_audit"]["bytes"] = len(payload)
        report["pdftex_input_audit"]["sha256"] = pub.sha256_bytes(payload)
        fingerprint = pub.reconstruct_build_fingerprint(report)
        self.assertEqual(
            fingerprint["pdftex_input_audit"]["bytes"], len(payload)
        )

    def test_v4_reproducibility_sidecars_are_read_back_byte_exactly(self):
        plan = self.plan()
        report = self.build_fingerprint_report()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            metapost_core = {
                key: report["metapost_assets"][key]
                for key in (
                    "schema_version",
                    "random_seed",
                    "source_date_epoch",
                    "asset_count",
                    "bytes",
                    "canonical_sha256",
                    "files",
                )
            }
            input_core = {
                key: report["pdftex_input_audit"][key]
                for key in (
                    "schema_version",
                    "all_map_encoding_font_program_inputs_private",
                    "jobs",
                    "controlled_input_count",
                    "metric_input_count",
                    "controlled_inputs",
                    "metric_inputs",
                    "canonical_sha256",
                )
            }
            self.write_json_fixture(
                root / plan["qa"]["metapost_asset_manifest"], metapost_core
            )
            self.write_json_fixture(
                root / plan["qa"]["pdftex_input_audit"], input_core
            )
            result = pub.validate_v4_reproducibility_sidecars(plan, root, report)
            self.assertEqual(result["metapost"]["asset_count"], 307)
            self.assertTrue(result["pdftex_input_audit"]["all_private"])
            self.write_json_fixture(
                root / plan["qa"]["metapost_asset_manifest"], {"tampered": True}
            )
            with self.assertRaisesRegex(pub.PublicationError, "MetaPost sidecar differs"):
                pub.validate_v4_reproducibility_sidecars(plan, root, report)

    def test_build_fingerprint_v3_rejects_invalid_font_closure_fields(self):
        invalid_cases = (
            ("non-integer byte count", ("pdftex_font_closure", "bytes"), True),
            ("invalid digest", ("pdftex_font_closure", "tree_sha256"), "G" * 64),
            (
                "extra path-neutral field",
                ("pdftex_font_closure", "unexpected"),
                "value",
            ),
        )
        for label, (section, key), value in invalid_cases:
            with self.subTest(label=label):
                report = self.build_fingerprint_report()
                report[section][key] = value
                with self.assertRaises(pub.PublicationError):
                    pub.reconstruct_build_fingerprint(report)

    def test_build_fingerprint_v3_requires_verified_matching_font_closure_end(self):
        invalid_cases = (
            ("not verified", "all_verified", False),
            ("file count mismatch", "file_count", 31),
            ("byte count mismatch", "bytes", 1669979),
            ("tree mismatch", "tree_sha256", "f" * 64),
        )
        for label, key, value in invalid_cases:
            with self.subTest(label=label):
                report = self.build_fingerprint_report()
                report["pdftex_font_closure_end_verification"][key] = value
                with self.assertRaisesRegex(
                    pub.PublicationError,
                    "font closure end verification is inconsistent",
                ):
                    pub.reconstruct_build_fingerprint(report)

    def test_build_fingerprint_v3_rejects_stale_canonical_sha(self):
        report = self.build_fingerprint_report()
        fingerprint = pub.reconstruct_build_fingerprint(report)
        reproducibility = self.reproducibility_record(fingerprint)
        reproducibility["current_sha256"] = "0" * 64
        with self.assertRaisesRegex(pub.PublicationError, "canonical SHA-256"):
            pub.validate_build_reproducibility(report, reproducibility)


if __name__ == "__main__":
    unittest.main()
