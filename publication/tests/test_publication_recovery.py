from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


DRIVER = Path(__file__).resolve().parents[1] / "publish_release.py"
SPEC = importlib.util.spec_from_file_location("hefferon_publish_release_recovery", DRIVER)
assert SPEC and SPEC.loader
pub = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pub)


class PublicationRecoveryTests(unittest.TestCase):
    def plan(self):
        return copy.deepcopy(pub.load_plan())

    def repository(self, plan, repository_id=1):
        owner = plan["github"]["owner"]
        repo = plan["github"]["repository"]
        return {
            "id": repository_id,
            "private": False,
            "full_name": f"{owner}/{repo}",
            "html_url": f"https://github.com/{owner}/{repo}",
            "owner": {"login": owner},
            **pub.expected_repository_settings(plan, branch_exists=False),
        }

    def release(self, plan, release_id=7, draft=True):
        owner = plan["github"]["owner"]
        repo = plan["github"]["repository"]
        return {
            "id": release_id,
            "draft": draft,
            "upload_url": (
                f"https://uploads.github.com/repos/{owner}/{repo}/"
                f"releases/{release_id}/assets{{?name,label}}"
            ),
            "html_url": pub.github_release_url(plan),
        }

    def final_with_readme(self, plan, root):
        final = Path(root)
        readme = (
            final
            / "snapshot"
            / "publication"
            / plan["release_assets"]["readme"]
        )
        readme.parent.mkdir(parents=True, exist_ok=True)
        readme.write_text("bounded release body", encoding="utf-8")
        (final / "release-assets").mkdir(exist_ok=True)
        return final

    def test_19_final_snapshot_must_match_every_frozen_base_byte(self):
        with tempfile.TemporaryDirectory() as td:
            snapshot = Path(td) / "snapshot"
            snapshot.mkdir()
            (snapshot / "a").write_bytes(b"evil")
            good = b"good"
            manifest = {
                "files": [
                    {
                        "path": "snapshot/a",
                        "bytes": len(good),
                        "sha256": hashlib.sha256(good).hexdigest(),
                        "git_blob_sha": "a" * 40,
                    }
                ]
            }
            with self.assertRaises(pub.PublicationError):
                pub.verify_snapshot_copy(manifest, snapshot)

    def test_20_repository_creation_lost_response_recovers_exact_created_repo(self):
        plan = self.plan()
        repository = self.repository(plan)
        client = mock.Mock()
        client.request.side_effect = pub.PublicationError("response lost")
        state = {"blob_cache": {}}
        with mock.patch.object(
            pub,
            "github_optional",
            side_effect=[
                (404, None),
                (200, repository),
                (404, None),
                (404, None),
                (404, None),
            ],
        ), mock.patch.object(
            pub, "reconcile_repository_settings", return_value=repository
        ), mock.patch.object(pub, "save_state"), mock.patch.object(pub.time, "sleep"):
            result = pub.ensure_github_repository(client, plan, state)
        self.assertEqual(result["id"], 1)
        self.assertEqual(state["github_repository_id"], 1)

    def test_20b_lost_create_response_never_binds_a_racing_nonempty_repo(self):
        plan = self.plan()
        repository = self.repository(plan)
        client = mock.Mock()
        client.request.side_effect = pub.PublicationError("response lost")
        state = {"blob_cache": {}}
        with mock.patch.object(
            pub,
            "github_optional",
            side_effect=[
                (404, None),
                (200, repository),
                (200, [{"ref": "refs/heads/main"}]),
                (200, []),
                (200, []),
            ],
        ), mock.patch.object(pub, "reconcile_repository_settings") as reconcile:
            with self.assertRaisesRegex(pub.PublicationError, "has refs/content"):
                pub.ensure_github_repository(client, plan, state)
        reconcile.assert_not_called()
        self.assertNotIn("github_repository_id", state)

    def test_21_branch_ref_lost_response_recovers_exact_commit_and_tree(self):
        plan = self.plan()
        entry = {
            "bytes": 1,
            "sha256": "a" * 64,
            "sha": "1" * 40,
            "mode": "100644",
            "local_path": Path("a"),
        }
        state = {
            "github_repository_id": 1,
            "blob_cache": {
                "a": {"bytes": 1, "sha256": "a" * 64, "remote_sha": "1" * 40}
            },
        }
        client = mock.Mock()
        client.request.side_effect = [
            (201, {}, {"sha": "b" * 40}),
            (201, {}, {"sha": "c" * 40}),
            pub.PublicationError("ref response lost"),
        ]
        verified = {
            "commit_sha": "c" * 40,
            "tree_sha": "b" * 40,
            "repository_snapshot_sha256": "d" * 64,
        }
        with mock.patch.object(pub, "verify_inventory"), mock.patch.object(
            pub, "repository_entries", return_value={"a": entry}
        ), mock.patch.object(
            pub, "remote_branch_state", side_effect=[None, None]
        ), mock.patch.object(
            pub,
            "poll_remote_branch_state",
            return_value=("c" * 40, "b" * 40, {}),
        ) as poll, mock.patch.object(
            pub, "verify_remote_repository", return_value=verified
        ), mock.patch.object(
            pub, "reconcile_repository_settings", return_value={"id": 1}
        ), mock.patch.object(pub, "save_state"), mock.patch.object(pub.time, "sleep"):
            result = pub.publish_repository_snapshot(
                client, plan, state, Path("unused"), {"fingerprint": "f"}
            )
        self.assertEqual(result["commit_sha"], "c" * 40)
        self.assertGreaterEqual(poll.call_count, 2)
        self.assertNotIn("github_pending_commit_sha", state)

    def test_22_tag_ref_lost_response_recovers_exact_target(self):
        plan = self.plan()
        state = {"github_commit_sha": "c" * 40, "blob_cache": {}}
        client = mock.Mock()
        client.request.side_effect = [
            (201, {}, {"sha": "d" * 40}),
            pub.PublicationError("tag-ref response lost"),
        ]
        with mock.patch.object(
            pub, "resolve_tag", side_effect=[None, "c" * 40]
        ), mock.patch.object(pub, "save_state"), mock.patch.object(pub.time, "sleep"):
            target = pub.ensure_tag(client, plan, state)
        self.assertEqual(target, "c" * 40)
        self.assertNotIn("github_pending_tag_object_sha", state)

    def test_23_release_creation_lost_response_recovers_one_draft(self):
        plan = self.plan()
        state = {"github_commit_sha": "c" * 40, "blob_cache": {}}
        release = self.release(plan)
        client = mock.Mock()
        client.request.side_effect = pub.PublicationError("release response lost")
        transitions = []
        with tempfile.TemporaryDirectory() as td:
            final = self.final_with_readme(plan, td)
            with mock.patch.object(pub, "verify_inventory"), mock.patch.object(
                pub, "artifact_map", return_value={}
            ), mock.patch.object(pub, "ensure_tag", return_value="c" * 40), mock.patch.object(
                pub, "find_release", side_effect=[None, release]
            ), mock.patch.object(
                pub,
                "reconcile_release_metadata",
                side_effect=lambda _c, _p, _f, item, _sha, draft: transitions.append(draft)
                or {**item, "draft": draft},
            ), mock.patch.object(pub, "release_assets", return_value=[]), mock.patch.object(
                pub, "repository_entries", return_value={}
            ), mock.patch.object(pub, "verify_remote_repository"), mock.patch.object(
                pub, "resolve_tag", return_value="c" * 40
            ), mock.patch.object(
                pub, "github_optional", return_value=(200, {"id": 7})
            ), mock.patch.object(pub, "save_state"), mock.patch.object(pub.time, "sleep"):
                result = pub.ensure_github_release(
                    client, plan, state, final, {"artifacts": []}, {"fingerprint": "f"}
                )
        self.assertFalse(result["draft"])
        self.assertEqual(transitions, [True, False])

    def test_24_asset_upload_lost_response_recovers_uploaded_asset(self):
        plan = self.plan()
        state = {"github_commit_sha": "c" * 40, "blob_cache": {}}
        release = self.release(plan)
        expected = {"path": "a.bin", "bytes": 1, "sha256": "a" * 64}
        asset = {"id": 8, "name": "a.bin", "size": 1}
        client = mock.Mock()
        client.upload_release_asset.side_effect = pub.PublicationError("asset response lost")
        with tempfile.TemporaryDirectory() as td:
            final = self.final_with_readme(plan, td)
            (final / "release-assets" / "a.bin").write_bytes(b"x")
            with mock.patch.object(pub, "verify_inventory"), mock.patch.object(
                pub, "artifact_map", return_value={"a.bin": expected}
            ), mock.patch.object(pub, "ensure_tag", return_value="c" * 40), mock.patch.object(
                pub, "find_release", return_value=release
            ), mock.patch.object(
                pub,
                "reconcile_release_metadata",
                side_effect=lambda _c, _p, _f, item, _sha, draft: {**item, "draft": draft},
            ), mock.patch.object(
                pub, "release_assets", side_effect=[[], [asset], [asset]]
            ), mock.patch.object(pub, "verify_github_asset_bytes"), mock.patch.object(
                pub, "repository_entries", return_value={}
            ), mock.patch.object(pub, "verify_remote_repository"), mock.patch.object(
                pub, "resolve_tag", return_value="c" * 40
            ), mock.patch.object(
                pub, "github_optional", return_value=(200, {"id": 7})
            ), mock.patch.object(pub, "save_state"), mock.patch.object(pub.time, "sleep"):
                result = pub.ensure_github_release(
                    client, plan, state, final, {"artifacts": []}, {"fingerprint": "f"}
                )
        self.assertFalse(result["draft"])
        client.upload_release_asset.assert_called_once()

    def test_25_release_patch_lost_response_recovers_exact_metadata(self):
        plan = self.plan()
        client = mock.Mock()
        client.request.side_effect = pub.PublicationError("patch response lost")
        with tempfile.TemporaryDirectory() as td:
            final = self.final_with_readme(plan, td)
            recovered = {
                "id": 7,
                **pub.expected_release_metadata(plan, final, "c" * 40, draft=False),
            }
            with mock.patch.object(pub, "resolve_tag", return_value="c" * 40), mock.patch.object(
                pub, "poll_release_state", return_value=recovered
            ):
                result = pub.reconcile_release_metadata(
                    client, plan, final, {"id": 7}, "c" * 40, draft=False
                )
        self.assertEqual(result, recovered)

    def test_26_pages_create_and_https_lost_responses_use_exact_readback(self):
        plan = self.plan()
        source = {"branch": plan["github"]["default_branch"], "path": "/docs"}
        pages_http = {"source": source, "https_enforced": False}
        pages_https = {"source": source, "https_enforced": True}
        client = mock.Mock()
        client.request.side_effect = [
            pub.PublicationError("create response lost"),
            pub.PublicationError("setting response lost"),
        ]
        with mock.patch.object(pub, "github_optional", return_value=(404, None)), mock.patch.object(
            pub, "poll_github_optional", side_effect=[pages_http, pages_https]
        ), mock.patch.object(pub.time, "sleep"):
            result = pub.ensure_pages(client, plan)
        self.assertTrue(result["https_enforced"])

    def test_27_zenodo_create_lost_response_recovers_exact_fingerprint(self):
        plan = self.plan()
        binding = {"fingerprint": "f" * 64}
        doi = "10.5281/zenodo.1"
        initial_metadata = pub.zenodo_metadata(plan, None, binding["fingerprint"])
        initial_metadata["prereserve_doi"] = {"doi": doi, "recid": 1}
        initial = {
            "id": 11,
            "doi": doi,
            "record_id": 1,
            "conceptrecid": 1,
            "conceptdoi": "10.5281/zenodo.1",
            "state": "unsubmitted",
            "metadata": initial_metadata,
        }
        final = {
            **initial,
            "metadata": pub.zenodo_metadata(plan, doi, binding["fingerprint"]),
        }
        client = mock.Mock()
        client.request.side_effect = [
            pub.PublicationError("create response lost"),
            (200, {}, final),
        ]
        state = {"blob_cache": {}}
        with mock.patch.object(
            pub, "exact_zenodo_depositions", side_effect=[[], [initial]]
        ), mock.patch.object(
            pub, "zenodo_title_version_guard", return_value=None
        ), mock.patch.object(
            pub,
            "discover_zenodo_lineage",
            return_value={
                "status": "absent",
                "authenticated_record_count": 0,
                "public_record_count": 0,
                "open_draft_ids": [],
            },
        ), mock.patch.object(pub, "save_state"), mock.patch.object(pub.time, "sleep"):
            deposition, recovered_doi = pub.reserve_zenodo(
                client, plan, binding, state
            )
        self.assertEqual(deposition["id"], 11)
        self.assertEqual(recovered_doi, doi)

    def test_28_zenodo_upload_lost_response_recovers_exact_remote_md5(self):
        plan = self.plan()
        binding = {"fingerprint": "f" * 64}
        with tempfile.TemporaryDirectory() as td:
            local = Path(td) / "a.bin"
            local.write_bytes(b"right")
            checksum = hashlib.md5(b"right", usedforsecurity=False).hexdigest()
            expected = {
                "path": "a.bin",
                "local_path": str(local),
                "bytes": 5,
                "sha256": pub.sha256_file(local),
            }
            deposition = {
                "id": 11,
                "state": "unsubmitted",
                "links": {"bucket": "https://zenodo.org/api/files/bucket"},
                "files": [],
            }
            recovered = {
                **deposition,
                "files": [
                    {
                        "filename": "a.bin",
                        "filesize": 5,
                        "checksum": "md5:" + checksum,
                    }
                ],
            }
            client = mock.Mock(origins={pub.origin(pub.ZENODO_ORIGIN)})
            client.upload.side_effect = pub.PublicationError("upload response lost")
            with mock.patch.object(pub, "zenodo_artifacts", return_value={"a.bin": expected}), mock.patch.object(
                pub, "poll_deposition", return_value=recovered
            ), mock.patch.object(pub, "refresh_deposition", return_value=recovered):
                result = pub.upload_zenodo_draft(
                    client, plan, binding, deposition, Path(td), {"artifacts": []}
                )
        self.assertEqual(result, recovered)
        client.upload.assert_called_once()

    def test_29_zenodo_publish_lost_response_polls_done_without_second_action(self):
        plan = self.plan()
        binding = {"fingerprint": "f" * 64}
        doi = "10.5281/zenodo.1"
        metadata = pub.zenodo_metadata(plan, doi, binding["fingerprint"])
        draft = {
            "id": 11,
            "doi": doi,
            "record_id": 1,
            "state": "unsubmitted",
            "metadata": metadata,
        }
        done = {**draft, "state": "done"}
        client = mock.Mock()
        client.request.side_effect = pub.PublicationError("publish response lost")
        state = {"zenodo_doi": doi, "blob_cache": {}}
        with mock.patch.object(pub, "zenodo_artifacts", return_value={}), mock.patch.object(
            pub, "upload_zenodo_draft", return_value=draft
        ), mock.patch.object(pub, "verify_inventory"), mock.patch.object(
            pub, "refresh_deposition", return_value=draft
        ), mock.patch.object(pub, "verify_zenodo_files_authenticated", return_value=[]), mock.patch.object(
            pub, "poll_deposition", return_value=done
        ), mock.patch.object(pub, "poll_zenodo_public", return_value={"id": 1}), mock.patch.object(
            pub, "save_state"
        ):
            result = pub.publish_zenodo(
                client,
                plan,
                binding,
                state,
                draft,
                Path("unused"),
                {"artifacts": []},
            )
        self.assertEqual(result["id"], 1)
        self.assertEqual(client.request.call_count, 1)
        self.assertEqual(state["zenodo_publish_phase"], "done")

    def test_30_allowed_origin_is_rechecked_after_anonymous_redirect(self):
        response = mock.MagicMock()
        response.status = 200
        response.headers = {}
        response.read.return_value = b"{}"
        response.geturl.return_value = "https://evil.invalid/capture"
        opener = mock.MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with mock.patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaises(pub.PublicationError):
                pub.http_bytes(
                    "GET",
                    "https://api.github.com/user",
                    allowed_origins={pub.origin(pub.GITHUB_API_ORIGIN)},
                )

    def test_31_bad_draft_asset_delete_lost_response_recovers_absence(self):
        plan = self.plan()
        state = {"github_commit_sha": "c" * 40, "blob_cache": {}}
        release = self.release(plan)
        expected = {"path": "a.bin", "bytes": 1, "sha256": "a" * 64}
        old_asset = {"id": 8, "name": "a.bin", "size": 1}
        new_asset = {"id": 9, "name": "a.bin", "size": 1}
        client = mock.Mock()
        client.request.side_effect = pub.PublicationError("delete response lost")
        client.upload_release_asset.return_value = new_asset
        with tempfile.TemporaryDirectory() as td:
            final = self.final_with_readme(plan, td)
            (final / "release-assets" / "a.bin").write_bytes(b"x")
            with mock.patch.object(pub, "verify_inventory"), mock.patch.object(
                pub, "artifact_map", return_value={"a.bin": expected}
            ), mock.patch.object(pub, "ensure_tag", return_value="c" * 40), mock.patch.object(
                pub, "find_release", return_value=release
            ), mock.patch.object(
                pub,
                "reconcile_release_metadata",
                side_effect=lambda _c, _p, _f, item, _sha, draft: {**item, "draft": draft},
            ), mock.patch.object(
                pub, "release_assets", side_effect=[[old_asset], [], [new_asset]]
            ), mock.patch.object(
                pub,
                "verify_github_asset_bytes",
                side_effect=[pub.PublicationError("wrong bytes"), None, None],
            ), mock.patch.object(pub, "repository_entries", return_value={}), mock.patch.object(
                pub, "verify_remote_repository"
            ), mock.patch.object(pub, "resolve_tag", return_value="c" * 40), mock.patch.object(
                pub, "github_optional", return_value=(200, {"id": 7})
            ), mock.patch.object(pub, "save_state"), mock.patch.object(pub.time, "sleep"):
                result = pub.ensure_github_release(
                    client, plan, state, final, {"artifacts": []}, {"fingerprint": "f"}
                )
        self.assertFalse(result["draft"])
        client.upload_release_asset.assert_called_once()

    def test_32_anonymous_readback_retries_both_eventually_consistent_services(self):
        plan = self.plan()
        state = {"blob_cache": {}, "zenodo_doi": "10.5281/zenodo.1"}
        github = {"release_id": 7}
        zenodo = {"record_id": 11}
        with mock.patch.object(pub, "verify_inventory"), mock.patch.object(
            pub, "validate_final_manifest"
        ), mock.patch.object(pub, "pin_inventory"), mock.patch.object(
            pub, "pin_state_sha256"
        ), mock.patch.object(
            pub,
            "verify_public_github",
            side_effect=[pub.PublicationError("not visible"), github],
        ) as github_check, mock.patch.object(
            pub,
            "verify_public_zenodo",
            side_effect=[pub.PublicationError("not visible"), zenodo],
        ) as zenodo_check, mock.patch.object(pub, "save_json"), mock.patch.object(
            pub, "sha256_file", return_value="a" * 64
        ), mock.patch.object(pub, "save_state"), mock.patch.object(pub.time, "sleep"):
            result = pub.anonymous_readback(
                plan,
                {"fingerprint": "f" * 64},
                state,
                Path("unused"),
                {"inventory_sha256": "b" * 64, "artifact_set_sha256": "c" * 64},
            )
        self.assertTrue(result["all_release_bytes_verified"])
        self.assertEqual(github_check.call_count, 2)
        self.assertEqual(zenodo_check.call_count, 2)

    def test_33_casefold_duplicate_artifact_names_are_rejected(self):
        plan = self.plan()
        plan["reader_pdfs"][1]["release_name"] = plan["reader_pdfs"][0][
            "release_name"
        ].lower()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "plan.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            with mock.patch.object(pub, "PLAN_PATH", path):
                with self.assertRaises(pub.PublicationError):
                    pub.load_plan()

    def test_34_already_pinned_inventory_cannot_be_rebound(self):
        state = {"base_inventory_sha256": "a" * 64}
        with self.assertRaises(pub.PublicationError):
            pub.pin_inventory(
                state,
                "base_inventory_sha256",
                {"inventory_sha256": "b" * 64},
                Path("unused"),
            )

    def test_35_pages_wrong_hash_never_falls_through_as_success(self):
        with tempfile.TemporaryDirectory() as td:
            local = Path(td) / "index.html"
            local.write_bytes(b"right")
            with mock.patch.object(
                pub,
                "stream_sha256",
                return_value=(5, hashlib.sha256(b"wrong").hexdigest(), "https://example.com/index.html"),
            ) as readback, mock.patch.object(pub.time, "sleep"):
                with self.assertRaisesRegex(pub.PublicationError, "did not become byte-consistent"):
                    pub.poll_exact_public_file(
                        "https://example.com/index.html",
                        local,
                        allowed_origins={pub.origin("https://example.com")},
                        attempts=3,
                    )
            self.assertEqual(readback.call_count, 3)

    def test_36_persisted_zenodo_publish_request_never_reposts_while_ambiguous(self):
        plan = self.plan()
        binding = {"fingerprint": "f" * 64}
        doi = "10.5281/zenodo.1"
        draft = {
            "id": 11,
            "doi": doi,
            "record_id": 1,
            "state": "unsubmitted",
            "metadata": pub.zenodo_metadata(plan, doi, binding["fingerprint"]),
        }
        client = mock.Mock()
        state = {
            "zenodo_doi": doi,
            "zenodo_publish_phase": "requested",
            "blob_cache": {},
        }
        with mock.patch.object(pub, "zenodo_artifacts", return_value={}), mock.patch.object(
            pub, "poll_deposition", return_value=None
        ):
            with self.assertRaisesRegex(pub.PublicationError, "refusing a duplicate"):
                pub.publish_zenodo(
                    client, plan, binding, state, draft, Path("unused"), {"artifacts": []}
                )
        client.request.assert_not_called()

    def test_37_persisted_zenodo_publish_request_recovers_done_without_repost(self):
        plan = self.plan()
        binding = {"fingerprint": "f" * 64}
        doi = "10.5281/zenodo.1"
        draft = {
            "id": 11,
            "doi": doi,
            "record_id": 1,
            "state": "unsubmitted",
            "metadata": pub.zenodo_metadata(plan, doi, binding["fingerprint"]),
        }
        done = {**draft, "state": "done"}
        client = mock.Mock()
        state = {
            "zenodo_doi": doi,
            "zenodo_publish_phase": "requested",
            "blob_cache": {},
        }
        with mock.patch.object(pub, "zenodo_artifacts", return_value={}), mock.patch.object(
            pub, "poll_deposition", return_value=done
        ), mock.patch.object(pub, "upload_zenodo_draft", return_value=done), mock.patch.object(
            pub, "verify_inventory"
        ), mock.patch.object(pub, "refresh_deposition", return_value=done), mock.patch.object(
            pub, "verify_zenodo_files_authenticated", return_value=[]
        ), mock.patch.object(pub, "poll_zenodo_public", return_value={"id": 1}), mock.patch.object(
            pub, "save_state"
        ):
            result = pub.publish_zenodo(
                client, plan, binding, state, draft, Path("unused"), {"artifacts": []}
            )
        self.assertEqual(result["id"], 1)
        client.request.assert_not_called()
        self.assertEqual(state["zenodo_publish_phase"], "done")

    def test_38_final_artifact_closure_rejects_renamed_asset_even_with_new_digest(self):
        plan = self.plan()
        artifacts = []
        for item in plan["reader_pdfs"]:
            artifacts.append(
                {
                    "kind": "reader-pdf",
                    "path": item["release_name"],
                    "component": item["component"],
                    "bytes": 1,
                    "sha256": "a" * 64,
                    "pages": 1,
                }
            )
        for item in plan["bundles"]:
            artifacts.append(
                {
                    "kind": item["kind"],
                    "path": item["release_name"],
                    "bytes": 1,
                    "sha256": "b" * 64,
                    "entry_count": 1,
                    "uncompressed_bytes": 1,
                    "entries_sha256": "c" * 64,
                }
            )
        artifacts.extend(
            [
                {"kind": "release-readme", "path": plan["release_assets"]["readme"], "bytes": 1, "sha256": "d" * 64},
                {"kind": "release-manifest", "path": plan["release_assets"]["manifest"], "bytes": 1, "sha256": "e" * 64},
                {"kind": "checksums", "path": plan["release_assets"]["checksums"], "bytes": 1, "sha256": "f" * 64},
            ]
        )
        artifacts[0]["path"] = "RENAMED.pdf"
        manifest = {
            "stage": "final",
            "doi": "10.5281/zenodo.1",
            "artifacts": artifacts,
            "artifact_set_sha256": pub.sha256_bytes(pub.canonical_bytes(artifacts)),
        }
        with self.assertRaisesRegex(pub.PublicationError, "name/kind/order closure"):
            pub.validate_final_manifest(plan, manifest, "10.5281/zenodo.1")

    def test_39_full_manifest_metadata_is_pinned_not_only_file_rows(self):
        binding = {"fingerprint": "f" * 64}
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td)
            target = stage / "snapshot" / "unit"
            target.parent.mkdir()
            target.write_bytes(b"fixed")
            rows = pub.inventory_rows(stage, omit={"inventory.json"})
            manifest = {
                "schema_version": "hefferon-id-immutable-inventory-v1",
                "stage": "base",
                "binding": binding,
                "inventory_sha256": pub.inventory_digest(rows),
                "file_count": len(rows),
                "files": rows,
                "readiness": {"gate": "original"},
            }
            pub.save_json(stage / "inventory.json", manifest)
            state = {}
            verified = pub.verify_inventory(stage, binding)
            pub.pin_inventory(state, "base_inventory_sha256", verified, stage)
            manifest["readiness"] = {"gate": "tampered"}
            pub.save_json(stage / "inventory.json", manifest)
            verified = pub.verify_inventory(stage, binding)
            with self.assertRaisesRegex(pub.PublicationError, "already-pinned manifest"):
                pub.pin_inventory(state, "base_inventory_sha256", verified, stage)

    def test_40_staging_input_digest_changes_on_same_size_source_mutation(self):
        plan = {
            "staging_inputs": ["source"],
            "qa": {"build_report": "report.json"},
            "repository_snapshot": {"exclude_names": [], "exclude_suffixes": []},
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            source.mkdir()
            unit = source / "unit.tex"
            unit.write_bytes(b"good")
            _rows, before = pub.staging_input_inventory(
                plan, root, require_complete=False
            )
            unit.write_bytes(b"evil")
            _rows, after = pub.staging_input_inventory(
                plan, root, require_complete=False
            )
        self.assertNotEqual(before, after)

    def test_41_existing_base_refuses_live_input_drift_before_reuse(self):
        plan = self.plan()
        binding = {"fingerprint": "f" * 64, "input_inventory_sha256": "a" * 64}
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / binding["fingerprint"] / "base"
            base.mkdir(parents=True)
            manifest = {
                "stage": "base",
                "readiness": {},
                "inventory_sha256": "b" * 64,
            }
            with mock.patch.object(pub, "TRANSACTIONS", Path(td)), mock.patch.object(
                pub, "verify_inventory", return_value=manifest
            ), mock.patch.object(
                pub, "staging_input_inventory", return_value=([], "c" * 64)
            ), mock.patch.object(pub, "strict_readiness") as readiness:
                with self.assertRaisesRegex(pub.PublicationError, "live staging inputs differ"):
                    pub.prepare_base_stage(plan, binding, {},)
            readiness.assert_not_called()

    def test_42_current_source_tree_must_match_build_report(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_root = root / plan["qa"]["source_root"]
            source_root.mkdir(parents=True)
            (source_root / "unit.tex").write_text("current", encoding="utf-8")
            rows, current_tree = pub.canonical_source_tree(source_root)
            source_manifest = root / plan["qa"]["staged_source_manifest"]
            source_manifest.parent.mkdir(parents=True)
            source_manifest.write_text(
                json.dumps({"tree_sha256": current_tree, "files": rows}),
                encoding="utf-8",
            )
            report_path = root / plan["qa"]["build_report"]
            report_path.write_text(
                json.dumps(
                    {
                        "status": "success",
                        "source": {
                            "unchanged_during_build": True,
                            "tree_sha256": "a" * 64,
                            "file_count": len(rows),
                            "live_end_file_count": len(rows),
                            "live_end_tree_sha256": "a" * 64,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(pub.PublicationError, "current translated source tree"):
                pub.strict_readiness(plan, root)

    def test_43_exclusions_are_relative_to_snapshot_not_transaction_ancestors(self):
        plan = {
            "staging_inputs": ["source"],
            "qa": {"build_report": "report.json"},
            "repository_snapshot": {
                "exclude_names": [".transactions"],
                "exclude_suffixes": [],
            },
        }
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td)
            live = parent / "live"
            staged = parent / ".transactions" / "fingerprint" / "base.tmp" / "snapshot"
            for root in (live, staged):
                unit = root / "source" / "unit.tex"
                unit.parent.mkdir(parents=True)
                unit.write_bytes(b"same")
            live_rows, live_digest = pub.staging_input_inventory(
                plan, live, require_complete=False
            )
            staged_rows, staged_digest = pub.staging_input_inventory(
                plan, staged, require_complete=False
            )
        self.assertEqual(live_rows, staged_rows)
        self.assertEqual(live_digest, staged_digest)

    def test_44_legacy_public_zenodo_shape_without_pids_is_fully_verified(self):
        plan = self.plan()
        doi = "10.5281/zenodo.1"
        binding = {"fingerprint": "f" * 64}
        state = {"zenodo_record_id": 1, "zenodo_doi": doi}
        record = {
            "id": 1,
            "doi": doi,
            "doi_url": f"https://doi.org/{doi}",
            "metadata": {},
            "files": [],
        }
        with mock.patch.object(pub, "poll_zenodo_public", return_value=record), mock.patch.object(
            pub, "assert_zenodo_metadata"
        ), mock.patch.object(pub, "artifact_map", return_value={}), mock.patch.object(
            pub, "normalize_zenodo_metadata", return_value={}
        ), mock.patch.object(
            pub,
            "stream_sha256",
            return_value=(1, "a" * 64, "https://zenodo.org/records/1"),
        ):
            result = pub.verify_public_zenodo(
                plan, binding, state, Path("unused"), {"artifacts": []}
            )
        self.assertEqual(result["doi"], doi)

    def test_45_public_zenodo_doi_shapes_must_agree(self):
        with self.assertRaisesRegex(pub.PublicationError, "DOI identities disagree"):
            pub.public_record_doi(
                {
                    "doi": "10.5281/zenodo.1",
                    "pids": {
                        "doi": {"identifier": "10.5281/zenodo.2"}
                    },
                }
            )

    def test_46_ambiguous_zenodo_create_phase_never_posts_again(self):
        plan = self.plan()
        binding = {"fingerprint": "f" * 64}
        state = {"blob_cache": {}}
        client = mock.Mock()
        client.request.side_effect = pub.PublicationError("create response lost")
        with mock.patch.object(pub, "exact_zenodo_depositions", return_value=[]), mock.patch.object(
            pub, "poll_exact_zenodo_deposition", return_value=None
        ), mock.patch.object(
            pub, "zenodo_title_version_guard", return_value=None
        ), mock.patch.object(
            pub,
            "discover_zenodo_lineage",
            return_value={
                "status": "absent",
                "authenticated_record_count": 0,
                "public_record_count": 0,
                "open_draft_ids": [],
            },
        ), mock.patch.object(pub, "save_state"):
            with self.assertRaises(pub.PublicationError):
                pub.reserve_zenodo(client, plan, binding, state)
            self.assertEqual(state["zenodo_create_phase"], "requested")
            with self.assertRaisesRegex(pub.PublicationError, "refusing a duplicate create"):
                pub.reserve_zenodo(client, plan, binding, state)
        self.assertEqual(client.request.call_count, 1)

    def test_47_exact_marker_collision_with_identity_drift_fails_closed(self):
        plan = self.plan()
        binding = {"fingerprint": "f" * 64}
        doi = "10.5281/zenodo.1"
        metadata = pub.zenodo_metadata(plan, doi, binding["fingerprint"])
        metadata["title"] = "drifted title"
        candidate = {
            "id": 11,
            "doi": doi,
            "metadata": metadata,
        }
        with mock.patch.object(pub, "zenodo_paginated", return_value=[candidate]):
            with self.assertRaisesRegex(pub.PublicationError, "title/version identity differs"):
                pub.exact_zenodo_depositions(mock.Mock(), plan, binding)

    def test_48_manifest_must_still_match_verified_object_when_pinned(self):
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td)
            current = {"inventory_sha256": "a" * 64, "marker": "changed"}
            passed = {"inventory_sha256": "a" * 64, "marker": "verified"}
            pub.save_json(stage / "inventory.json", current)
            state = {}
            with self.assertRaisesRegex(pub.PublicationError, "between verification and pinning"):
                pub.pin_inventory(state, "base_inventory_sha256", passed, stage)
            self.assertEqual(state, {})


if __name__ == "__main__":
    unittest.main()
