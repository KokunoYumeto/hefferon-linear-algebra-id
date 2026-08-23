from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


DRIVER = Path(__file__).resolve().parents[1] / "publish_figshare.py"
SPEC = importlib.util.spec_from_file_location("hefferon_publish_figshare_tests", DRIVER)
assert SPEC and SPEC.loader
fig = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fig)


FINGERPRINT = "f" * 64
OTHER_FINGERPRINT = "e" * 64


class FakeResponse:
    def __init__(self, status_code: int, location: str | None = None) -> None:
        self.status_code = status_code
        self.headers = {} if location is None else {"Location": location}

    def json(self):
        return {}


def context() -> dict:
    return {
        "fingerprint": FINGERPRINT,
        "doi": "10.5281/zenodo.123",
        "zenodo_url": "https://doi.org/10.5281/zenodo.123",
        "record_url": "https://zenodo.org/records/123",
        "final": Path("frozen-final"),
        "inventory": {"binding": {"fingerprint": FINGERPRINT}},
    }


def exact_license() -> dict:
    return {
        "value": 25,
        "name": "Creative Commons Attribution-ShareAlike 2.5 Generic",
        "url": fig.EXACT_LICENSE_URL,
    }


def cc0_license() -> dict:
    return {
        "value": 1,
        "name": "Creative Commons CC0 1.0 Universal",
        "url": fig.CC0_LICENSE_URL,
    }


def payload(name: str = "01_HEFFERON_LINEAR_ALGEBRA_ID_TEXTBOOK.pdf", data: bytes = b"reader") -> dict:
    return {
        "name": name,
        "path": str(Path("frozen-final") / name),
        "bytes": len(data),
        "md5": hashlib.md5(data, usedforsecurity=False).hexdigest(),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


class PreflightClient:
    """Small authenticated API double; every unplanned call fails the test."""

    def __init__(
        self,
        *,
        licenses: list[dict] | None = None,
        articles: list[dict] | None = None,
        details: dict[int, dict] | None = None,
        project_id: int = fig.PROJECT_ID,
        collection_id: int = fig.COLLECTION_ID,
    ) -> None:
        self.licenses = licenses if licenses is not None else [exact_license(), cc0_license()]
        self.articles = articles or []
        self.details = details or {}
        self.project_id = project_id
        self.collection_id = collection_id
        self.calls: list[tuple[str, str]] = []

    def json(self, method: str, path: str, **_kwargs):
        self.calls.append((method, path))
        if method != "GET":
            raise AssertionError(f"unexpected JSON mutation: {method} {path}")
        if path == f"/account/projects/{fig.PROJECT_ID}":
            return {"id": self.project_id, "title": "Open translations"}
        if path == f"/account/collections/{fig.COLLECTION_ID}":
            return {
                "id": self.collection_id,
                "title": "Indonesian Open Mathematics Editions",
                "doi": "10.6084/m9.figshare.c.8668413",
            }
        if path == "/account/licenses":
            return self.licenses
        if path.startswith(f"/account/projects/{fig.PROJECT_ID}/articles?"):
            return self.articles
        for article_id, details in self.details.items():
            if path.startswith(
                f"/account/projects/{fig.PROJECT_ID}/articles/{article_id}/files?"
            ):
                return details.get("files", [])
            if path in {
                f"/account/projects/{fig.PROJECT_ID}/articles/{article_id}",
                f"/account/articles/{article_id}",
            }:
                return details
        raise AssertionError(f"unexpected authenticated JSON call: {method} {path}")

    def request(self, *_args, **_kwargs):
        raise AssertionError("preflight attempted a remote mutation")


class StatefulClient:
    """In-memory Figshare transaction double for publish/recovery tests."""

    def __init__(
        self,
        licenses: list[dict],
        *,
        lose_first_create: bool = False,
        lose_first_article_publish: bool = False,
        lose_first_collection_add: bool = False,
        lose_first_collection_publish: bool = False,
    ) -> None:
        self.licenses = licenses
        self.articles: dict[int, dict] = {}
        self.collection_members: set[int] = set()
        self.collection_published = False
        self.next_id = 41
        self.lose_first_create = lose_first_create
        self.lose_first_article_publish = lose_first_article_publish
        self.lose_first_collection_add = lose_first_collection_add
        self.lose_first_collection_publish = lose_first_collection_publish
        self.create_attempts = 0
        self.article_publish_attempts = 0
        self.collection_add_attempts = 0
        self.collection_publish_attempts = 0
        self.calls: list[tuple[str, str, dict | None]] = []

    def _summary_rows(self) -> list[dict]:
        return [
            {"id": value["id"], "title": value["title"]}
            for value in self.articles.values()
        ]

    def json(self, method: str, path: str, **_kwargs):
        self.calls.append((method, path, None))
        if method != "GET":
            raise AssertionError(f"unexpected JSON mutation: {method} {path}")
        if path == f"/account/projects/{fig.PROJECT_ID}":
            return {"id": fig.PROJECT_ID, "title": "Open translations"}
        if path == f"/account/collections/{fig.COLLECTION_ID}":
            return {
                "id": fig.COLLECTION_ID,
                "title": "Indonesian Open Mathematics Editions",
                "doi": "10.6084/m9.figshare.c.8668413",
            }
        if path == "/account/licenses":
            return self.licenses
        if path.startswith(f"/account/projects/{fig.PROJECT_ID}/articles?"):
            return self._summary_rows()
        if path.startswith(f"/account/collections/{fig.COLLECTION_ID}/articles?"):
            return [
                {"id": article_id, "title": self.articles[article_id]["title"]}
                for article_id in sorted(self.collection_members)
            ]
        for article_id, article in self.articles.items():
            if path.startswith(
                f"/account/projects/{fig.PROJECT_ID}/articles/{article_id}/files?"
            ):
                return article["files"]
            if path in {
                f"/account/projects/{fig.PROJECT_ID}/articles/{article_id}",
                f"/account/articles/{article_id}",
            }:
                return article
            if path.startswith(f"/account/articles/{article_id}/files?"):
                return article["files"]
        raise AssertionError(f"unexpected authenticated JSON call: {method} {path}")

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        expected=(200,),
        retry=True,
    ):
        del expected, retry
        self.calls.append((method, path, json_body))
        if method == "POST" and path == f"/account/projects/{fig.PROJECT_ID}/articles":
            self.create_attempts += 1
            article_id = self.next_id
            self.next_id += 1
            self.articles[article_id] = {
                "id": article_id,
                **(json_body or {}),
                "files": [],
                "published_date": None,
            }
            if self.lose_first_create and self.create_attempts == 1:
                raise fig.FigshareError("simulated lost create response")
            return FakeResponse(201, f"https://api.figshare.com/v2/account/articles/{article_id}")
        if method == "PUT" and path.startswith("/account/articles/"):
            article_id = int(path.rsplit("/", 1)[1])
            self.articles[article_id].update(json_body or {})
            return FakeResponse(205)
        if method == "DELETE" and "/files/" in path:
            article_id, file_id = [int(value) for value in path.split("/")[3::2]]
            self.articles[article_id]["files"] = [
                row for row in self.articles[article_id]["files"] if row["id"] != file_id
            ]
            return FakeResponse(204)
        if method == "POST" and path.endswith("/files"):
            article_id = int(path.split("/")[3])
            if json_body and "link" in json_body:
                self.articles[article_id]["files"].append(
                    {
                        "id": 901,
                        "name": "Zenodo link",
                        "size": 0,
                        "is_link_only": True,
                        "download_url": json_body["link"],
                    }
                )
            return FakeResponse(201, f"https://api.figshare.com/v2/account/articles/{article_id}/files/901")
        if method == "POST" and path.endswith("/publish") and "/articles/" in path:
            article_id = int(path.split("/")[3])
            self.article_publish_attempts += 1
            self.articles[article_id]["published_date"] = "2026-08-22T00:00:00Z"
            if self.lose_first_article_publish and self.article_publish_attempts == 1:
                raise fig.FigshareError("simulated lost article publish response")
            return FakeResponse(201, f"https://api.figshare.com/v2/articles/{article_id}")
        if method == "POST" and path == f"/account/collections/{fig.COLLECTION_ID}/articles":
            self.collection_add_attempts += 1
            self.collection_members.update((json_body or {}).get("articles", []))
            if self.lose_first_collection_add and self.collection_add_attempts == 1:
                raise fig.FigshareError("simulated lost collection add response")
            return FakeResponse(201)
        if method == "POST" and path == f"/account/collections/{fig.COLLECTION_ID}/publish":
            self.collection_publish_attempts += 1
            self.collection_published = True
            if self.lose_first_collection_publish and self.collection_publish_attempts == 1:
                raise fig.FigshareError("simulated lost collection publish response")
            return FakeResponse(201)
        raise AssertionError(f"unexpected authenticated mutation: {method} {path}")

    def add_uploaded_file(self, article_id: int, row: dict) -> None:
        file_id = 1000 + len(self.articles[article_id]["files"])
        self.articles[article_id]["files"].append(
            {
                "id": file_id,
                "name": row["name"],
                "size": row["bytes"],
                "computed_md5": row["md5"],
                "status": "AVAILABLE",
            }
        )


class FigshareOfflineTests(unittest.TestCase):
    def test_01_driver_has_no_github_import_or_endpoint(self):
        source = DRIVER.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name.casefold() for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module.casefold())
        self.assertFalse(any("github" in value for value in imported))
        self.assertNotIn("api.github.com", source.casefold())
        self.assertNotIn("github.com", source.casefold())

    def test_02_preflight_uses_exact_project_and_collection_without_mutation(self):
        client = PreflightClient()
        first = payload()
        with mock.patch.object(fig, "zenodo_context", return_value=context()), mock.patch.object(
            fig, "exact_local_payload", return_value=[first]
        ), mock.patch.object(fig, "project_byte_inventory", return_value=0):
            result = fig.preflight(client)
        self.assertEqual(result["project"]["id"], 280296)
        self.assertEqual(result["collection"]["id"], 8668413)
        self.assertEqual(result["mutations"], 0)
        self.assertIn(("GET", "/account/projects/280296"), client.calls)
        self.assertIn(("GET", "/account/collections/8668413"), client.calls)

    def test_03_wrong_project_or_collection_identity_fails_closed(self):
        with mock.patch.object(fig, "zenodo_context", return_value=context()):
            with self.assertRaisesRegex(fig.FigshareError, "project identity differs"):
                fig.preflight(PreflightClient(project_id=1))
            with self.assertRaisesRegex(fig.FigshareError, "collection identity differs"):
                fig.preflight(PreflightClient(collection_id=1))

    def test_04_duplicate_exact_title_items_fail_closed(self):
        details = {
            11: {"id": 11, "title": fig.TITLE, "description": "foreign", "files": []},
            12: {"id": 12, "title": fig.TITLE, "description": "foreign", "files": []},
        }
        client = PreflightClient(
            articles=[
                {"id": 11, "title": fig.TITLE},
                {"id": 12, "title": fig.TITLE},
            ],
            details=details,
        )
        with mock.patch.object(fig, "zenodo_context", return_value=context()):
            with self.assertRaisesRegex(fig.FigshareError, "multiple|ambiguous|marker"):
                fig.preflight(client)

    def test_05_exact_title_with_foreign_transaction_marker_fails_closed(self):
        article = {
            "id": 11,
            "title": fig.TITLE,
            "description": f"Hefferon transaction: {OTHER_FINGERPRINT}",
            "files": [],
        }
        client = PreflightClient(
            articles=[{"id": 11, "title": fig.TITLE}], details={11: article}
        )
        with mock.patch.object(fig, "zenodo_context", return_value=context()):
            with self.assertRaisesRegex(fig.FigshareError, "marker|identity|owned|collision"):
                fig.preflight(client)

    def test_06_exact_license_selects_full_payload(self):
        client = PreflightClient(licenses=[cc0_license(), exact_license()])
        first = payload()
        with mock.patch.object(fig, "zenodo_context", return_value=context()), mock.patch.object(
            fig, "exact_local_payload", return_value=[first]
        ), mock.patch.object(fig, "project_byte_inventory", return_value=0):
            result = fig.preflight(client)
        self.assertEqual(result["branch"], "full")
        self.assertEqual(result["license"]["id"], 25)
        self.assertEqual(result["payload"][0]["name"], first["name"])
        self.assertEqual(result["payload_bytes"], first["bytes"])

    def test_07_missing_exact_license_uses_cc0_metadata_only(self):
        client = PreflightClient(licenses=[cc0_license()])
        with mock.patch.object(fig, "zenodo_context", return_value=context()), mock.patch.object(
            fig, "exact_local_payload", side_effect=AssertionError("must not stage licensed bytes")
        ), mock.patch.object(fig, "project_byte_inventory", return_value=0):
            result = fig.preflight(client)
        self.assertEqual(result["branch"], "metadata-link")
        self.assertEqual(result["license"]["id"], 1)
        self.assertEqual(result["payload"], [])
        self.assertEqual(result["payload_bytes"], 0)
        desired = fig.metadata(context(), result["branch"], result["license"]["id"])
        self.assertEqual(desired["defined_type"], "online resource")
        self.assertIn(context()["zenodo_url"], desired["references"])
        self.assertIn("Tidak ada PDF", desired["description"])

    def test_08_frozen_plan_is_reader_first_and_excludes_provenance_bundle(self):
        plan = fig.load_json(fig.PLAN_PATH)
        readers = plan["reader_pdfs"]
        self.assertEqual(readers[0]["component"], "textbook")
        self.assertTrue(readers[0]["release_name"].startswith("01_"))
        self.assertTrue(readers[0]["release_name"].casefold().endswith(".pdf"))
        included_bundles = [
            row["kind"]
            for row in plan["bundles"]
            if row["kind"] in {"editable-source", "modular-backend"}
        ]
        self.assertEqual(included_bundles, ["editable-source", "modular-backend"])

    def test_09_exact_payload_preserves_pdf_first_order_and_enforces_item_cap(self):
        plan = {
            "reader_pdfs": [
                {"component": "textbook", "release_name": "01_reader.pdf"},
                {"component": "worked-answers", "release_name": "02_answers.pdf"},
            ],
            "bundles": [
                {"kind": "editable-source", "release_name": "source.zip"},
                {"kind": "modular-backend", "release_name": "backend.zip"},
                {"kind": "provenance-qa", "release_name": "provenance.zip"},
            ],
            "release_assets": {
                "readme": "README.md",
                "manifest": "manifest.json",
                "checksums": "SHA256SUMS",
            },
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            final = root / "final"
            assets = final / "release-assets"
            assets.mkdir(parents=True)
            names = [
                "01_reader.pdf",
                "02_answers.pdf",
                "source.zip",
                "backend.zip",
                "README.md",
                "manifest.json",
                "SHA256SUMS",
            ]
            for name in names:
                (assets / name).write_bytes(name.encode("utf-8"))
            license_path = final / "snapshot" / "LICENSE"
            license_path.parent.mkdir(parents=True)
            license_path.write_bytes(b"CC BY-SA 2.5")
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            with mock.patch.object(fig, "PLAN_PATH", plan_path):
                rows = fig.exact_local_payload({"final": final})
                self.assertEqual(rows[0]["name"], "01_reader.pdf")
                self.assertNotIn("provenance.zip", [row["name"] for row in rows])
                total = sum(row["bytes"] for row in rows)
                with mock.patch.object(fig, "MAX_ITEM_BYTES", total - 1):
                    with self.assertRaisesRegex(fig.FigshareError, "500,000,000-byte cap"):
                        fig.exact_local_payload({"final": final})

    def test_10_project_cap_is_strictly_below_twenty_billion(self):
        client = PreflightClient()
        first = payload(data=b"xx")
        with mock.patch.object(fig, "zenodo_context", return_value=context()), mock.patch.object(
            fig, "exact_local_payload", return_value=[first]
        ), mock.patch.object(
            fig, "project_byte_inventory", return_value=fig.MAX_PROJECT_BYTES - 1
        ):
            with self.assertRaisesRegex(fig.FigshareError, "below 20,000,000,000"):
                fig.preflight(client)

    def test_11_new_full_item_uploads_pdf_first_publishes_and_joins_collection(self):
        client = StatefulClient([exact_license(), cc0_license()])
        first = payload()
        second = payload("02_HEFFERON_LINEAR_ALGEBRA_ID_WORKED_ANSWERS.pdf", b"answers")

        def uploaded(_client, article_id, row):
            client.add_uploaded_file(article_id, row)

        with mock.patch.object(fig, "zenodo_context", return_value=context()), mock.patch.object(
            fig, "exact_local_payload", return_value=[first, second]
        ), mock.patch.object(fig, "upload_file", side_effect=uploaded) as upload, mock.patch.object(
            fig, "public_article", return_value=None
        ), mock.patch.object(
            fig, "public_collection_contains", return_value=False
        ), mock.patch.object(fig, "atomic_json"
        ):
            result = fig.publish(client)
        self.assertEqual(client.create_attempts, 1)
        self.assertEqual(client.article_publish_attempts, 1)
        self.assertEqual([call.args[2]["name"] for call in upload.call_args_list], [first["name"], second["name"]])
        self.assertIn(result["article_id"], client.collection_members)
        self.assertTrue(client.collection_published)
        self.assertEqual(result["branch"], "full")

    def test_12_lost_create_response_recovers_same_item_without_duplicate(self):
        client = StatefulClient([cc0_license()], lose_first_create=True)
        with mock.patch.object(fig, "zenodo_context", return_value=context()), mock.patch.object(
            fig, "public_article", return_value=None
        ), mock.patch.object(
            fig, "public_collection_contains", return_value=False
        ), mock.patch.object(fig, "atomic_json"
        ):
            with self.assertRaisesRegex(fig.FigshareError, "lost create response"):
                fig.publish(client)
            result = fig.publish(client)
        self.assertEqual(client.create_attempts, 1)
        self.assertEqual(len(client.articles), 1)
        self.assertEqual(client.article_publish_attempts, 1)
        self.assertIn(result["article_id"], client.collection_members)
        self.assertTrue(client.collection_published)

    def test_13_collection_membership_is_idempotent(self):
        client = StatefulClient([cc0_license()])
        client.articles[41] = {"id": 41, "title": fig.TITLE, "files": []}
        with mock.patch.object(fig, "public_collection_contains", return_value=True):
            first = fig.ensure_collection(client, 41)
            second = fig.ensure_collection(client, 41)
        self.assertEqual(first, (True, True))
        self.assertEqual(second, (False, False))
        add_calls = [
            call for call in client.calls
            if call[:2] == ("POST", f"/account/collections/{fig.COLLECTION_ID}/articles")
        ]
        self.assertEqual(len(add_calls), 1)

    def test_14_full_anonymous_readback_verifies_order_size_hash_and_membership(self):
        first_bytes = b"reader"
        second_bytes = b"backend"
        expected = [payload(data=first_bytes), payload("backend.zip", second_bytes)]
        state = {
            "transaction_fingerprint": FINGERPRINT,
            "article_id": 41,
            "branch": "full",
            "license": {"id": 25, "url": fig.EXACT_LICENSE_URL},
            "payload": [
                {key: row[key] for key in ("name", "bytes", "md5", "sha256")}
                for row in expected
            ],
        }
        article = {
            "id": 41,
            "title": fig.TITLE,
            "description": f"{fig.WORK_MARKER}\n{fig.transaction_marker(FINGERPRINT)}",
            "references": [context()["zenodo_url"]],
            "license": {"id": 25, "url": fig.EXACT_LICENSE_URL},
            "doi": "10.6084/m9.figshare.123",
            "url_public_html": "https://figshare.com/articles/online_resource/123",
            "files": [
                {
                    "name": row["name"],
                    "size": row["bytes"],
                    "download_url": f"https://ndownloader.figshare.com/files/{index}",
                }
                for index, row in enumerate(expected, start=1)
            ],
        }

        def anonymous(path):
            if path == "/articles/41":
                return article
            if path == f"/projects/{fig.PROJECT_ID}/articles?page_size=1000":
                return [{"id": 41}]
            if path == f"/collections/{fig.COLLECTION_ID}/articles?page_size=1000":
                return [{"id": 41}]
            raise AssertionError(f"unexpected anonymous endpoint: {path}")

        with mock.patch.object(fig, "zenodo_context", return_value=context()), mock.patch.object(
            fig, "load_json", return_value=state
        ), mock.patch.object(fig, "anonymous_json", side_effect=anonymous), mock.patch.object(
            fig,
            "download_sha256",
            side_effect=[
                (len(first_bytes), hashlib.sha256(first_bytes).hexdigest()),
                (len(second_bytes), hashlib.sha256(second_bytes).hexdigest()),
            ],
        ) as downloads, mock.patch.object(fig, "resolve_doi", return_value="https://figshare.com/articles/dataset/123"), mock.patch.object(fig, "atomic_json"):
            receipt = fig.verify()
        self.assertTrue(receipt["anonymous_readback"])
        self.assertEqual(receipt["files"], [
            {"name": row["name"], "bytes": row["bytes"], "sha256": row["sha256"]}
            for row in expected
        ])
        self.assertEqual(downloads.call_count, 2)
        self.assertLess(receipt["project_public_bytes"], fig.MAX_PROJECT_BYTES)

    def test_15_anonymous_readback_rejects_size_before_download(self):
        row = payload()
        state = {
            "transaction_fingerprint": FINGERPRINT,
            "article_id": 41,
            "branch": "full",
            "license": {"id": 25, "url": fig.EXACT_LICENSE_URL},
            "payload": [{key: row[key] for key in ("name", "bytes", "md5", "sha256")}],
        }
        article = {
            "id": 41,
            "title": fig.TITLE,
            "description": f"{fig.WORK_MARKER}\n{fig.transaction_marker(FINGERPRINT)}",
            "references": [context()["zenodo_url"]],
            "license": {"id": 25},
            "files": [{"name": row["name"], "size": row["bytes"] + 1}],
        }
        with mock.patch.object(fig, "zenodo_context", return_value=context()), mock.patch.object(
            fig, "load_json", return_value=state
        ), mock.patch.object(fig, "anonymous_json", return_value=article), mock.patch.object(
            fig, "download_sha256"
        ) as download:
            with self.assertRaisesRegex(fig.FigshareError, "file size differs"):
                fig.verify()
        download.assert_not_called()

    def test_16_stable_work_marker_allows_one_prior_release_lineage(self):
        article = {
            "id": 11,
            "title": fig.TITLE,
            "description": f"{fig.WORK_MARKER}\n{fig.transaction_marker(OTHER_FINGERPRINT)}",
            "files": [],
        }
        client = PreflightClient(
            articles=[{"id": 11, "title": fig.TITLE}], details={11: article}
        )
        with mock.patch.object(fig, "zenodo_context", return_value=context()), mock.patch.object(
            fig, "project_byte_inventory", return_value=0
        ), mock.patch.object(fig, "exact_local_payload", return_value=[payload()]):
            result = fig.preflight(client)
        self.assertEqual(result["existing_article_id"], 11)
        self.assertFalse(result["exact_existing_transaction"])

    def test_17_public_current_transaction_is_idempotent(self):
        first = payload()
        public = {
            "id": 41,
            **fig.metadata(context(), "full", 25),
            "files": [
                {
                    "id": 91,
                    "name": first["name"],
                    "size": first["bytes"],
                    "computed_md5": first["md5"],
                }
            ],
            "license": {"id": 25},
        }
        check = {
            "branch": "full",
            "license": {"id": 25, "name": "CC BY-SA 2.5", "url": fig.EXACT_LICENSE_URL},
            "existing_article_id": 41,
            "payload": [{key: first[key] for key in ("name", "bytes", "md5", "sha256")}],
            "payload_bytes": first["bytes"],
        }
        client = StatefulClient([exact_license()])
        with mock.patch.object(fig, "zenodo_context", return_value=context()), mock.patch.object(
            fig, "preflight", return_value=check
        ), mock.patch.object(fig, "exact_local_payload", return_value=[first]), mock.patch.object(
            fig, "public_article", return_value=public
        ), mock.patch.object(fig, "ensure_collection", return_value=(False, False)), mock.patch.object(
            fig, "atomic_json"
        ):
            result = fig.publish(client)
        self.assertTrue(result["already_public_current"])
        self.assertFalse(result["mutated"])
        self.assertEqual(client.calls, [])

    def test_18_lost_article_publish_response_recovers_without_republishing(self):
        client = StatefulClient([cc0_license()], lose_first_article_publish=True)

        def visible(article_id):
            article = client.articles.get(article_id)
            return article if article and article.get("published_date") else None

        with mock.patch.object(fig, "zenodo_context", return_value=context()), mock.patch.object(
            fig, "public_article", side_effect=visible
        ), mock.patch.object(
            fig,
            "public_collection_contains",
            side_effect=lambda article_id: article_id in client.collection_members
            and client.collection_published,
        ), mock.patch.object(fig.time, "sleep"), mock.patch.object(fig, "atomic_json"):
            with self.assertRaisesRegex(fig.FigshareError, "lost article publish response"):
                fig.publish(client)
            result = fig.publish(client)
        self.assertEqual(len(client.articles), 1)
        self.assertEqual(client.article_publish_attempts, 1)
        self.assertTrue(result["already_public_current"])

    def test_19_lost_collection_publish_response_recovers_without_new_version(self):
        client = StatefulClient([cc0_license()], lose_first_collection_publish=True)

        def visible(article_id):
            article = client.articles.get(article_id)
            return article if article and article.get("published_date") else None

        with mock.patch.object(fig, "zenodo_context", return_value=context()), mock.patch.object(
            fig, "public_article", side_effect=visible
        ), mock.patch.object(
            fig,
            "public_collection_contains",
            side_effect=lambda article_id: article_id in client.collection_members
            and client.collection_published,
        ), mock.patch.object(fig, "atomic_json"):
            with self.assertRaisesRegex(fig.FigshareError, "lost collection publish response"):
                fig.publish(client)
            result = fig.publish(client)
        self.assertEqual(client.article_publish_attempts, 1)
        self.assertEqual(client.collection_publish_attempts, 1)
        self.assertTrue(result["already_public_current"])

    def test_20_defined_types_are_portable_figshare_v2_values(self):
        self.assertEqual(fig.metadata(context(), fig.FULL_BRANCH, 25)["defined_type"], "fileset")
        self.assertEqual(
            fig.metadata(context(), fig.METADATA_BRANCH, 1)["defined_type"],
            "online resource",
        )
        with self.assertRaisesRegex(fig.FigshareError, "unknown Figshare publication branch"):
            fig.metadata(context(), "unknown", 1)

    def test_21_two_owned_work_markers_fail_closed(self):
        rows = [
            {
                "id": article_id,
                "title": fig.TITLE,
                "description": fig.WORK_MARKER,
                "files": [],
            }
            for article_id in (11, 12)
        ]
        with self.assertRaisesRegex(fig.FigshareError, "multiple Figshare items"):
            fig.discover_owned_article(rows, FINGERPRINT)

    def test_22_incomplete_remote_file_is_never_treated_as_current(self):
        row = payload()
        remote = {
            "name": row["name"],
            "size": row["bytes"],
            "supplied_md5": row["md5"],
            "status": "PENDING",
        }
        self.assertFalse(fig.full_file_inventory_matches([remote], [row]))

    def test_23_verify_rejects_branch_license_mismatch_before_public_readback(self):
        state = {
            "transaction_fingerprint": FINGERPRINT,
            "article_id": 41,
            "branch": fig.FULL_BRANCH,
            "license": {"id": 1, "url": fig.CC0_LICENSE_URL},
            "payload": [],
        }
        with mock.patch.object(fig, "zenodo_context", return_value=context()), mock.patch.object(
            fig, "load_json", return_value=state
        ), mock.patch.object(fig, "anonymous_json") as anonymous:
            with self.assertRaisesRegex(fig.FigshareError, "license does not match"):
                fig.verify()
        anonymous.assert_not_called()

    def test_24_download_rechecks_final_redirect_origin(self):
        class DownloadResponse:
            status_code = 200
            url = "https://figshare.com.evil.example/stolen"

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def raise_for_status(self):
                return None

            def iter_content(self, _size):
                return iter((b"reader",))

        with mock.patch.object(fig.requests, "get", return_value=DownloadResponse()):
            with self.assertRaisesRegex(fig.FigshareError, "redirected outside"):
                fig.download_sha256(
                    "https://ndownloader.figshare.com/files/1",
                    len(b"reader"),
                )

    def test_25_license_label_without_canonical_url_cannot_authorize_bytes(self):
        unlabeled_url = exact_license()
        del unlabeled_url["url"]
        client = PreflightClient(licenses=[unlabeled_url, cc0_license()])
        with mock.patch.object(fig, "zenodo_context", return_value=context()), mock.patch.object(
            fig, "exact_local_payload", side_effect=AssertionError("must not stage licensed bytes")
        ), mock.patch.object(fig, "project_byte_inventory", return_value=0):
            result = fig.preflight(client)
        self.assertEqual(result["branch"], fig.METADATA_BRANCH)
        self.assertEqual(result["license"]["url"], fig.CC0_LICENSE_URL)

    def test_26_lost_collection_add_response_recovers_without_duplicate_add(self):
        client = StatefulClient([cc0_license()], lose_first_collection_add=True)

        def visible(article_id):
            article = client.articles.get(article_id)
            return article if article and article.get("published_date") else None

        with mock.patch.object(fig, "zenodo_context", return_value=context()), mock.patch.object(
            fig, "public_article", side_effect=visible
        ), mock.patch.object(
            fig,
            "public_collection_contains",
            side_effect=lambda article_id: article_id in client.collection_members
            and client.collection_published,
        ), mock.patch.object(fig.time, "sleep"), mock.patch.object(fig, "atomic_json"):
            with self.assertRaisesRegex(fig.FigshareError, "lost collection add response"):
                fig.publish(client)
            result = fig.publish(client)
        self.assertEqual(client.collection_add_attempts, 1)
        self.assertEqual(client.collection_publish_attempts, 1)
        self.assertTrue(result["already_public_current"])

    def test_27_metadata_only_anonymous_readback_has_zero_files_and_exact_link(self):
        state = {
            "transaction_fingerprint": FINGERPRINT,
            "article_id": 41,
            "branch": fig.METADATA_BRANCH,
            "license": {"id": 1, "url": fig.CC0_LICENSE_URL},
            "payload": [],
        }
        article = {
            "id": 41,
            "title": fig.TITLE,
            "description": f"{fig.WORK_MARKER}\n{fig.transaction_marker(FINGERPRINT)}",
            "references": [context()["zenodo_url"]],
            "license": {"id": 1},
            "doi": "10.6084/m9.figshare.123.v1",
            "url_public_html": "https://figshare.com/articles/online_resource/123",
            "files": [],
        }

        def anonymous(path):
            if path == "/articles/41":
                return article
            if path == f"/projects/{fig.PROJECT_ID}/articles?page_size=1000":
                return [{"id": 41}]
            if path == f"/collections/{fig.COLLECTION_ID}/articles?page_size=1000":
                return [{"id": 41}]
            raise AssertionError(f"unexpected anonymous endpoint: {path}")

        with mock.patch.object(fig, "zenodo_context", return_value=context()), mock.patch.object(
            fig, "load_json", return_value=state
        ), mock.patch.object(fig, "anonymous_json", side_effect=anonymous), mock.patch.object(
            fig, "download_sha256"
        ) as download, mock.patch.object(
            fig, "resolve_doi", return_value="https://figshare.com/articles/online_resource/123"
        ), mock.patch.object(fig, "atomic_json"):
            receipt = fig.verify()
        download.assert_not_called()
        self.assertEqual(receipt["branch"], fig.METADATA_BRANCH)
        self.assertEqual(receipt["files"], [])


if __name__ == "__main__":
    unittest.main()
