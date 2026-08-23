from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock


DRIVER = Path(__file__).resolve().parents[1] / "publish_release.py"
SPEC = importlib.util.spec_from_file_location("hefferon_publish_release_channels", DRIVER)
assert SPEC and SPEC.loader
pub = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pub)


class PublicationChannelIsolationTests(unittest.TestCase):
    def plan(self):
        return copy.deepcopy(pub.load_plan())

    @staticmethod
    def binding():
        return {"fingerprint": "f" * 64}

    def test_repository_neutral_metadata_and_payloads_claim_no_github_release(self):
        plan = self.plan()
        doi = "10.5281/zenodo.1"
        description = pub.release_description(plan, doi, "f" * 64)
        metadata = pub.zenodo_metadata(plan, doi, "f" * 64)
        readme = pub.release_readme(
            plan,
            doi,
            "f" * 64,
            [],
            {"source_tree_sha256": "a" * 64},
        ).decode("utf-8")
        page = pub.pages_html(plan, doi, "f" * 64).decode("utf-8")
        self.assertNotIn("github.com", description.casefold())
        self.assertNotIn("github.com", readme.casefold())
        self.assertNotIn("github.com", page.casefold())
        self.assertEqual(
            metadata["related_identifiers"],
            [
                {
                    "identifier": plan["authority"]["source_commit_url"],
                    "relation": "isDerivedFrom",
                    "resource_type": "software",
                }
            ],
        )
        self.assertIn(f"https://doi.org/{doi}", description)
        self.assertIn(f"https://doi.org/{doi}", readme)
        self.assertIn(f"https://doi.org/{doi}", page)

    def test_zenodo_only_publish_never_touches_github_and_leaves_it_pending(self):
        plan = self.plan()
        binding = self.binding()
        state = {"blob_cache": {}}
        final = Path("frozen-final")
        manifest = {
            "inventory_sha256": "a" * 64,
            "artifact_set_sha256": "b" * 64,
        }
        deposition = {"id": 11}
        public_record = {"id": 12}
        readback = {"combined_release_complete": False}
        forbidden = pub.PublicationError("GitHub must remain isolated")
        with mock.patch.object(pub, "load_state", return_value=state), mock.patch.object(
            pub, "prepare_base_stage", return_value=(Path("base"), {})
        ), mock.patch.object(pub, "zenodo_client", return_value=mock.Mock()), mock.patch.object(
            pub,
            "reserve_zenodo",
            return_value=(deposition, "10.5281/zenodo.12"),
        ), mock.patch.object(
            pub, "prepare_final_stage", return_value=(final, manifest)
        ), mock.patch.object(pub, "verify_inventory"), mock.patch.object(
            pub, "publish_zenodo", return_value=public_record
        ), mock.patch.object(
            pub, "zenodo_anonymous_readback", return_value=readback
        ), mock.patch.object(
            pub, "github_client", side_effect=forbidden
        ), mock.patch.object(
            pub, "verify_public_github", side_effect=forbidden
        ):
            state.update(
                {
                    "zenodo_record_id": 12,
                    "zenodo_doi": "10.5281/zenodo.12",
                }
            )
            result = pub.publish_zenodo_only(plan, binding)
        self.assertEqual(result["status"], "zenodo-published-github-pending")
        self.assertEqual(result["github"], {"status": "pending"})
        self.assertFalse(result["combined_release_complete"])
        self.assertNotIn("complete", state)

    def test_github_only_publish_reuses_frozen_assets_and_never_touches_zenodo(self):
        plan = self.plan()
        binding = self.binding()
        state = {
            "blob_cache": {},
            "zenodo_doi": "10.5281/zenodo.12",
            "zenodo_published": True,
        }
        final = Path("one-frozen-final")
        manifest = {
            "inventory_sha256": "a" * 64,
            "artifact_set_sha256": "b" * 64,
            "artifacts": [{"path": f"asset-{index}"} for index in range(9)],
        }
        github = mock.Mock()
        release = {"id": 7, "html_url": "https://github.com/o/r", "draft": False}
        authentication = {"login": plan["github"]["owner"]}
        forbidden = pub.PublicationError("Zenodo must remain isolated")
        with mock.patch.object(pub, "load_state", return_value=state), mock.patch.object(
            pub, "frozen_final_release", return_value=(final, manifest)
        ) as frozen, mock.patch.object(
            pub, "require_verified_zenodo_receipt_for_github"
        ) as receipt_gate, mock.patch.object(
            pub, "github_client", return_value=(github, authentication)
        ), mock.patch.object(pub, "ensure_github_repository"), mock.patch.object(
            pub, "publish_repository_snapshot", return_value={"status": "published"}
        ), mock.patch.object(
            pub, "ensure_github_release", return_value=release
        ) as release_call, mock.patch.object(
            pub, "ensure_pages", return_value={"status": "built"}
        ), mock.patch.object(
            pub, "github_anonymous_readback", return_value={"combined_release_complete": False}
        ) as readback_call, mock.patch.object(
            pub, "prepare_base_stage"
        ) as base_stage, mock.patch.object(
            pub, "prepare_final_stage"
        ) as final_stage, mock.patch.object(
            pub, "zenodo_client", side_effect=forbidden
        ), mock.patch.object(
            pub, "verify_public_zenodo", side_effect=forbidden
        ):
            result = pub.publish_github_only(plan, binding)
        frozen.assert_called_once_with(plan, binding, state)
        receipt_gate.assert_called_once_with(plan, binding, state, final, manifest)
        release_call.assert_called_once_with(github, plan, state, final, manifest, binding)
        readback_call.assert_called_once_with(plan, binding, state, final, manifest)
        base_stage.assert_not_called()
        final_stage.assert_not_called()
        self.assertEqual(result["artifact_set_sha256"], manifest["artifact_set_sha256"])
        self.assertFalse(result["combined_release_complete"])
        self.assertNotIn("complete", state)

    def test_github_only_publish_fails_before_github_when_zenodo_is_not_verified(self):
        plan = self.plan()
        binding = self.binding()
        state = {"blob_cache": {}, "zenodo_doi": "10.5281/zenodo.12"}
        final = Path("one-frozen-final")
        manifest = {
            "inventory_sha256": "a" * 64,
            "artifact_set_sha256": "b" * 64,
            "artifacts": [],
        }
        with mock.patch.object(pub, "load_state", return_value=state), mock.patch.object(
            pub, "frozen_final_release", return_value=(final, manifest)
        ), mock.patch.object(pub, "github_client") as github:
            with self.assertRaisesRegex(
                pub.PublicationError, "completed Zenodo publication"
            ):
                pub.publish_github_only(plan, binding)
        github.assert_not_called()

    def test_github_receipt_gate_binds_exact_zenodo_record_and_asset_bytes(self):
        plan = self.plan()
        binding = self.binding()
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            assets = final / "release-assets"
            assets.mkdir(parents=True)
            asset_path = assets / "reader.pdf"
            asset_path.write_bytes(b"reader")
            artifact = {
                "path": asset_path.name,
                "bytes": asset_path.stat().st_size,
                "sha256": pub.sha256_file(asset_path),
            }
            manifest = {
                "inventory_sha256": "a" * 64,
                "artifact_set_sha256": "b" * 64,
                "artifacts": [artifact],
            }
            state = {
                "zenodo_published": True,
                "zenodo_doi": "10.5281/zenodo.12",
                "zenodo_record_id": 12,
            }
            receipt = {
                "schema_version": "hefferon-id-public-readback-zenodo-v1",
                "publication_target": "zenodo",
                "transaction_fingerprint": binding["fingerprint"],
                "release_tag": plan["release"]["tag"],
                "final_inventory_sha256": manifest["inventory_sha256"],
                "artifact_set_sha256": manifest["artifact_set_sha256"],
                "github": {"status": "pending"},
                "zenodo": {
                    "record_id": 12,
                    "doi": state["zenodo_doi"],
                    "assets": [
                        {
                            "name": artifact["path"],
                            "bytes": artifact["bytes"],
                            "sha256": artifact["sha256"],
                        }
                    ],
                },
                "all_zenodo_release_bytes_verified": True,
                "complete_metadata_and_doi_verified": True,
                "combined_release_complete": False,
            }
            receipt_path = Path(td) / "public-readback.zenodo.json"
            pub.save_json(receipt_path, receipt)
            state["zenodo_anonymous_readback_sha256"] = pub.sha256_file(receipt_path)
            with mock.patch.object(pub, "ZENODO_READBACK_PATH", receipt_path):
                self.assertEqual(
                    pub.require_verified_zenodo_receipt_for_github(
                        plan, binding, state, final, manifest
                    ),
                    receipt,
                )

    def test_zenodo_receipt_is_separate_and_does_not_set_complete(self):
        plan = self.plan()
        binding = self.binding()
        state = {"blob_cache": {}, "zenodo_doi": "10.5281/zenodo.1"}
        manifest = {
            "inventory_sha256": "a" * 64,
            "artifact_set_sha256": "b" * 64,
        }
        with mock.patch.object(pub, "pin_final_release_state"), mock.patch.object(
            pub, "verify_public_zenodo", return_value={"assets": list(range(9))}
        ), mock.patch.object(pub, "verify_inventory"), mock.patch.object(
            pub, "save_json"
        ) as write, mock.patch.object(pub, "sha256_file", return_value="c" * 64), mock.patch.object(
            pub, "save_state"
        ):
            result = pub.zenodo_anonymous_readback(
                plan, binding, state, Path("final"), manifest
            )
        write.assert_called_once_with(pub.ZENODO_READBACK_PATH, result)
        self.assertEqual(state["zenodo_anonymous_readback_sha256"], "c" * 64)
        self.assertNotIn("complete", state)
        self.assertEqual(result["github"], {"status": "pending"})
        self.assertFalse(result["combined_release_complete"])

    def test_combined_receipt_alone_sets_complete(self):
        plan = self.plan()
        binding = self.binding()
        state = {"blob_cache": {}}
        manifest = {
            "inventory_sha256": "a" * 64,
            "artifact_set_sha256": "b" * 64,
        }
        with mock.patch.object(
            pub, "github_anonymous_readback", return_value={"github": {"assets": []}}
        ), mock.patch.object(
            pub, "zenodo_anonymous_readback", return_value={"zenodo": {"assets": []}}
        ), mock.patch.object(pub, "save_json"), mock.patch.object(
            pub, "sha256_file", return_value="c" * 64
        ), mock.patch.object(pub, "save_state"):
            result = pub.anonymous_readback(
                plan, binding, state, Path("final"), manifest
            )
        self.assertTrue(result["combined_release_complete"])
        self.assertTrue(state["complete"])
        self.assertEqual(state["anonymous_readback_sha256"], "c" * 64)

    def test_public_zenodo_readback_downloads_all_nine_exact_assets(self):
        plan = self.plan()
        binding = self.binding()
        doi = "10.5281/zenodo.1"
        state = {"zenodo_record_id": 1, "zenodo_doi": doi}
        names = [item["release_name"] for item in plan["reader_pdfs"]]
        names += [item["release_name"] for item in plan["bundles"]]
        names += [
            plan["release_assets"]["readme"],
            plan["release_assets"]["manifest"],
            plan["release_assets"]["checksums"],
        ]
        self.assertEqual(len(names), plan["release_assets"]["expected_count"])
        with tempfile.TemporaryDirectory() as td:
            final = Path(td)
            assets = final / "release-assets"
            assets.mkdir()
            artifacts = []
            files = []
            expected_by_url = {}
            for index, name in enumerate(names):
                payload = f"exact-asset-{index}".encode("ascii")
                path = assets / name
                path.write_bytes(payload)
                digest = hashlib.sha256(payload).hexdigest()
                artifacts.append(
                    {"path": name, "bytes": len(payload), "sha256": digest}
                )
                url = f"https://zenodo.org/records/1/files/{urllib.parse.quote(name, safe='')}"
                expected_by_url[url] = (len(payload), digest, url)
                files.append(
                    {
                        "key": name,
                        "size": len(payload),
                        "checksum": "md5:"
                        + hashlib.md5(payload, usedforsecurity=False).hexdigest(),
                        "links": {"content": url},
                    }
                )
            record = {
                "id": 1,
                "doi": doi,
                "metadata": {},
                "files": files,
            }

            def stream(url, **_kwargs):
                if url == f"https://doi.org/{doi}":
                    return 1, "0" * 64, "https://zenodo.org/records/1"
                return expected_by_url[url]

            with mock.patch.object(pub, "poll_zenodo_public", return_value=record), mock.patch.object(
                pub, "assert_zenodo_metadata"
            ), mock.patch.object(pub, "normalize_zenodo_metadata", return_value={}), mock.patch.object(
                pub, "stream_sha256", side_effect=stream
            ) as download:
                result = pub.verify_public_zenodo(
                    plan, binding, state, final, {"artifacts": artifacts}
                )
        self.assertEqual(len(result["assets"]), 9)
        self.assertEqual(
            {item["name"]: item["sha256"] for item in result["assets"]},
            {item["path"]: item["sha256"] for item in artifacts},
        )
        self.assertEqual(download.call_count, 10)

    def test_same_title_version_different_fingerprint_blocks_creation(self):
        plan = self.plan()
        binding = self.binding()
        other_metadata = pub.zenodo_metadata(plan, None, "e" * 64)
        collision = {"id": 9, "metadata": other_metadata}
        with mock.patch.object(pub, "zenodo_paginated", return_value=[collision]), mock.patch.object(
            pub, "zenodo_public_paginated", return_value=[]
        ):
            with self.assertRaisesRegex(pub.PublicationError, "different transaction marker"):
                pub.zenodo_title_version_guard(mock.Mock(), plan, binding)

    def test_exact_title_version_and_fingerprint_is_reusable(self):
        plan = self.plan()
        binding = self.binding()
        metadata = pub.zenodo_metadata(plan, None, binding["fingerprint"])
        deposition = {"id": 9, "metadata": metadata}
        public_record = {"id": 9, "metadata": metadata}
        with mock.patch.object(pub, "zenodo_paginated", return_value=[deposition]), mock.patch.object(
            pub, "zenodo_public_paginated", return_value=[public_record]
        ):
            self.assertIs(
                pub.zenodo_title_version_guard(mock.Mock(), plan, binding), deposition
            )

    def test_cli_routes_zenodo_preflight_without_github(self):
        plan = self.plan()
        binding = {
            "plan_sha256": "a" * 64,
            "driver_sha256": "b" * 64,
            "fingerprint": "f" * 64,
        }
        with mock.patch.object(pub.sys, "argv", ["publish_release.py", "zenodo-preflight"]), mock.patch.object(
            pub, "load_plan", return_value=plan
        ), mock.patch.object(pub, "transaction_binding", return_value=binding), mock.patch.object(
            pub, "sha256_file_stable", side_effect=["a" * 64, "b" * 64]
        ), mock.patch.object(pub, "load_json", return_value=plan), mock.patch.object(
            pub, "local_preflight", return_value={"ready": True}
        ), mock.patch.object(
            pub, "zenodo_remote_preflight", return_value={"records": []}
        ) as zenodo, mock.patch.object(
            pub, "github_remote_preflight", side_effect=AssertionError("wrong channel")
        ), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(pub.main(), 0)
        zenodo.assert_called_once_with(plan, binding)

    def test_cli_routes_github_publish_without_zenodo(self):
        plan = self.plan()
        binding = {
            "plan_sha256": "a" * 64,
            "driver_sha256": "b" * 64,
            "fingerprint": "f" * 64,
        }
        lock = mock.MagicMock()
        lock.return_value.__enter__.return_value = None
        with mock.patch.object(pub.sys, "argv", ["publish_release.py", "github-publish"]), mock.patch.object(
            pub, "load_plan", return_value=plan
        ), mock.patch.object(pub, "transaction_binding", return_value=binding), mock.patch.object(
            pub, "sha256_file_stable", side_effect=["a" * 64, "b" * 64]
        ), mock.patch.object(pub, "load_json", return_value=plan), mock.patch.object(
            pub, "TransactionLock", lock
        ), mock.patch.object(
            pub, "publish_github_only", return_value={"status": "github"}
        ) as github, mock.patch.object(
            pub, "publish_zenodo_only", side_effect=AssertionError("wrong channel")
        ), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(pub.main(), 0)
        github.assert_called_once_with(plan, binding)


if __name__ == "__main__":
    unittest.main()
