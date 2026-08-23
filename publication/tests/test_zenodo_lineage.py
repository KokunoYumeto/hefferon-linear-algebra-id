from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path
from unittest import mock


DRIVER = Path(__file__).resolve().parents[1] / "publish_release.py"
SPEC = importlib.util.spec_from_file_location("hefferon_publish_release_lineage", DRIVER)
assert SPEC and SPEC.loader
pub = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pub)


class ZenodoConceptLineageTests(unittest.TestCase):
    def plan(self):
        return copy.deepcopy(pub.load_plan())

    @staticmethod
    def binding():
        return {"fingerprint": "f" * 64}

    def row(
        self,
        plan,
        *,
        record_id: int,
        deposition_id: int | None = None,
        conceptrecid: int,
        fingerprint: str,
        version: str,
        state: str = "done",
        latest_id: int | None = None,
        latest_draft_id: int | None = None,
    ):
        doi = f"10.5281/zenodo.{record_id}"
        metadata = pub.zenodo_metadata(plan, doi, fingerprint)
        metadata["version"] = version
        metadata["prereserve_doi"] = {"doi": doi, "recid": record_id}
        links = {
            "latest": f"https://zenodo.org/api/records/{latest_id or record_id}",
        }
        if latest_draft_id is not None:
            links["latest_draft"] = (
                f"https://zenodo.org/api/deposit/depositions/{latest_draft_id}"
            )
        if state != "done":
            links["bucket"] = "https://zenodo.org/api/files/bucket"
        return {
            "id": deposition_id or record_id,
            "record_id": record_id,
            "doi": doi,
            "conceptrecid": conceptrecid,
            "conceptdoi": f"10.5281/zenodo.{conceptrecid}",
            "state": state,
            "submitted": state == "done",
            "metadata": metadata,
            "links": links,
            "files": [],
        }

    def test_existing_concept_creates_newversion_through_latest_record_only(self):
        plan = self.plan()
        binding = self.binding()
        prior = self.row(
            plan,
            record_id=100,
            deposition_id=1100,
            conceptrecid=90,
            fingerprint="e" * 64,
            version="2026.08.01",
            latest_draft_id=1101,
        )
        draft = self.row(
            plan,
            record_id=101,
            deposition_id=1101,
            conceptrecid=90,
            fingerprint="e" * 64,
            version="2026.08.01",
            state="unsubmitted",
            latest_id=100,
        )
        updated = copy.deepcopy(draft)
        updated["metadata"] = pub.zenodo_metadata(
            plan, "10.5281/zenodo.101", binding["fingerprint"]
        )
        updated["metadata"]["prereserve_doi"] = {
            "doi": "10.5281/zenodo.101",
            "recid": 101,
        }
        lineage = {
            "status": "existing",
            "conceptrecid": 90,
            "concept_doi": "10.5281/zenodo.90",
            "latest_deposition_id": 1100,
            "latest_record_id": 100,
            "latest_record_doi": "10.5281/zenodo.100",
            "latest_deposition": prior,
            "open_draft_ids": [],
            "open_drafts": [],
        }
        calls = []

        def request(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "POST" and endpoint.endswith("/actions/newversion"):
                return 201, {}, prior
            if method == "GET" and endpoint.endswith("/1101"):
                return 200, {}, draft
            if method == "PUT" and endpoint.endswith("/1101"):
                return 200, {}, updated
            raise AssertionError((method, endpoint, kwargs))

        client = mock.Mock()
        client.request.side_effect = request
        state = {"blob_cache": {}}
        with mock.patch.object(pub, "exact_zenodo_depositions", return_value=[]), mock.patch.object(
            pub, "zenodo_title_version_guard", return_value=None
        ), mock.patch.object(
            pub, "discover_zenodo_lineage", return_value=lineage
        ), mock.patch.object(pub, "save_state"):
            deposition, doi = pub.reserve_zenodo(client, plan, binding, state)
        self.assertEqual(deposition["id"], 1101)
        self.assertEqual(doi, "10.5281/zenodo.101")
        self.assertEqual(state["zenodo_conceptrecid"], 90)
        self.assertEqual(state["zenodo_lineage_latest_deposition_id"], 1100)
        self.assertEqual(state["zenodo_lineage_latest_record_id"], 100)
        self.assertEqual(state["zenodo_newversion_phase"], "done")
        self.assertIn(
            ("POST", "/deposit/depositions/1100/actions/newversion"),
            [(method, endpoint) for method, endpoint, _kwargs in calls],
        )
        self.assertNotIn(
            ("POST", "/deposit/depositions"),
            [(method, endpoint) for method, endpoint, _kwargs in calls],
        )

    def test_no_concept_allows_one_fresh_deposition_create(self):
        plan = self.plan()
        binding = self.binding()
        created = self.row(
            plan,
            record_id=201,
            conceptrecid=190,
            fingerprint=binding["fingerprint"],
            version=plan["release"]["version"],
            state="unsubmitted",
        )
        updated = copy.deepcopy(created)
        calls = []

        def request(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "POST" and endpoint == "/deposit/depositions":
                return 201, {}, created
            if method == "PUT" and endpoint.endswith("/201"):
                return 200, {}, updated
            raise AssertionError((method, endpoint, kwargs))

        client = mock.Mock()
        client.request.side_effect = request
        state = {"blob_cache": {}}
        with mock.patch.object(pub, "exact_zenodo_depositions", return_value=[]), mock.patch.object(
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
            deposition, doi = pub.reserve_zenodo(client, plan, binding, state)
        self.assertEqual(deposition["id"], 201)
        self.assertEqual(doi, "10.5281/zenodo.201")
        self.assertEqual(state["zenodo_conceptrecid"], 190)
        self.assertEqual(state["zenodo_create_phase"], "done")
        self.assertEqual(
            [(method, endpoint) for method, endpoint, _kwargs in calls if method == "POST"],
            [("POST", "/deposit/depositions")],
        )

    def test_ambiguous_same_work_concepts_fail_closed(self):
        plan = self.plan()
        first = self.row(
            plan,
            record_id=301,
            conceptrecid=290,
            fingerprint="a" * 64,
            version="2026.01.01",
        )
        second = self.row(
            plan,
            record_id=401,
            conceptrecid=390,
            fingerprint="b" * 64,
            version="2026.02.02",
        )
        with mock.patch.object(
            pub, "zenodo_paginated", return_value=[first, second]
        ), mock.patch.object(pub, "zenodo_public_paginated", return_value=[]):
            with self.assertRaisesRegex(pub.PublicationError, "ambiguous existing same-work"):
                pub.discover_zenodo_lineage(mock.Mock(), plan, self.binding())

    def test_one_concept_keeps_deposition_and_public_record_ids_distinct(self):
        plan = self.plan()
        authenticated = self.row(
            plan,
            record_id=450,
            deposition_id=1450,
            conceptrecid=440,
            fingerprint="a" * 64,
            version="2026.01.01",
        )
        authenticated["links"]["latest"] = (
            "https://zenodo.org/api/deposit/depositions/1450"
        )
        public = copy.deepcopy(authenticated)
        public["id"] = 450
        public.pop("record_id")
        public["links"]["latest"] = "https://zenodo.org/api/records/450"
        with mock.patch.object(
            pub, "zenodo_paginated", return_value=[authenticated]
        ), mock.patch.object(pub, "zenodo_public_paginated", return_value=[public]):
            lineage = pub.discover_zenodo_lineage(
                mock.Mock(), plan, self.binding()
            )
        self.assertEqual(lineage["conceptrecid"], 440)
        self.assertEqual(lineage["latest_deposition_id"], 1450)
        self.assertEqual(lineage["latest_record_id"], 450)

    def test_same_work_title_variant_is_still_bound_to_existing_concept(self):
        plan = self.plan()
        authenticated = self.row(
            plan,
            record_id=455,
            deposition_id=1455,
            conceptrecid=445,
            fingerprint="a" * 64,
            version="checkpoint-1",
        )
        authenticated["metadata"]["title"] = (
            "Hefferon Linear Algebra — checkpoint Bahasa Indonesia"
        )
        public = copy.deepcopy(authenticated)
        public["id"] = 455
        public.pop("record_id")
        with mock.patch.object(
            pub, "zenodo_paginated", return_value=[authenticated]
        ), mock.patch.object(pub, "zenodo_public_paginated", return_value=[public]):
            lineage = pub.discover_zenodo_lineage(
                mock.Mock(), plan, self.binding()
            )
        self.assertEqual(lineage["conceptrecid"], 445)
        self.assertEqual(lineage["latest_deposition_id"], 1455)

    def test_same_work_target_version_with_different_identity_fails_closed(self):
        plan = self.plan()
        prior = self.row(
            plan,
            record_id=456,
            deposition_id=1456,
            conceptrecid=445,
            fingerprint="e" * 64,
            version=plan["release"]["version"],
        )
        prior["metadata"]["title"] = "Linear Algebra — Indonesian checkpoint"
        with mock.patch.object(pub, "zenodo_paginated", return_value=[prior]), mock.patch.object(
            pub, "zenodo_public_paginated", return_value=[]
        ):
            with self.assertRaisesRegex(pub.PublicationError, "target version"):
                pub.discover_zenodo_lineage(
                    mock.Mock(), plan, self.binding()
                )

    def test_public_same_work_concept_not_in_account_fails_closed(self):
        plan = self.plan()
        public = self.row(
            plan,
            record_id=470,
            conceptrecid=460,
            fingerprint="a" * 64,
            version="2026.01.01",
        )
        with mock.patch.object(pub, "zenodo_paginated", return_value=[]), mock.patch.object(
            pub, "zenodo_public_paginated", return_value=[public]
        ):
            with self.assertRaisesRegex(pub.PublicationError, "not present in authenticated"):
                pub.discover_zenodo_lineage(mock.Mock(), plan, self.binding())

    def test_title_version_guard_reconciles_record_id_not_deposition_id(self):
        plan = self.plan()
        binding = self.binding()
        authenticated = self.row(
            plan,
            record_id=480,
            deposition_id=1480,
            conceptrecid=470,
            fingerprint=binding["fingerprint"],
            version=plan["release"]["version"],
            state="unsubmitted",
        )
        public = copy.deepcopy(authenticated)
        public["id"] = 480
        public.pop("record_id")
        with mock.patch.object(
            pub, "zenodo_paginated", return_value=[authenticated]
        ), mock.patch.object(pub, "zenodo_public_paginated", return_value=[public]):
            self.assertIs(
                pub.zenodo_title_version_guard(mock.Mock(), plan, binding),
                authenticated,
            )

    def test_stored_lineage_mismatch_fails_before_any_create_action(self):
        plan = self.plan()
        wrong_parent = self.row(
            plan,
            record_id=500,
            deposition_id=1500,
            conceptrecid=491,
            fingerprint="e" * 64,
            version="2026.08.01",
        )
        state = {
            "blob_cache": {},
            "zenodo_deposition_id": 1501,
            "zenodo_conceptrecid": 490,
            "zenodo_concept_doi": "10.5281/zenodo.490",
            "zenodo_lineage_latest_deposition_id": 1500,
            "zenodo_lineage_latest_record_id": 500,
            "zenodo_lineage_latest_record_doi": "10.5281/zenodo.500",
        }
        client = mock.Mock()
        client.request.return_value = (200, {}, wrong_parent)
        with self.assertRaisesRegex(pub.PublicationError, "concept lineage differs on resume"):
            pub.reserve_zenodo(client, plan, self.binding(), state)
        self.assertFalse(
            any(call.args[0] == "POST" for call in client.request.call_args_list)
        )

    def test_lost_newversion_response_recovers_latest_draft_without_repost(self):
        plan = self.plan()
        prior = self.row(
            plan,
            record_id=600,
            deposition_id=1600,
            conceptrecid=590,
            fingerprint="e" * 64,
            version="2026.08.01",
            latest_draft_id=1601,
        )
        draft = self.row(
            plan,
            record_id=601,
            deposition_id=1601,
            conceptrecid=590,
            fingerprint="e" * 64,
            version="2026.08.01",
            state="unsubmitted",
            latest_id=600,
        )
        state = {
            "blob_cache": {},
            "zenodo_conceptrecid": 590,
            "zenodo_concept_doi": "10.5281/zenodo.590",
            "zenodo_lineage_latest_deposition_id": 1600,
            "zenodo_lineage_latest_record_id": 600,
            "zenodo_lineage_latest_record_doi": "10.5281/zenodo.600",
            "zenodo_newversion_phase": "requested",
        }
        client = mock.Mock()
        client.request.side_effect = [(200, {}, prior), (200, {}, draft)]
        with mock.patch.object(pub, "save_state"):
            recovered = pub.request_zenodo_newversion(client, plan, state)
        self.assertEqual(recovered["id"], 1601)
        self.assertEqual(state["zenodo_newversion_phase"], "done")
        self.assertFalse(
            any(call.args[0] == "POST" for call in client.request.call_args_list)
        )

    def test_exact_matching_deposition_resumes_without_any_create_action(self):
        plan = self.plan()
        binding = self.binding()
        exact = self.row(
            plan,
            record_id=801,
            deposition_id=1801,
            conceptrecid=790,
            fingerprint=binding["fingerprint"],
            version=plan["release"]["version"],
            state="unsubmitted",
        )
        client = mock.Mock()
        client.request.return_value = (200, {}, exact)
        state = {"blob_cache": {}}
        with mock.patch.object(
            pub, "exact_zenodo_depositions", return_value=[exact]
        ), mock.patch.object(
            pub,
            "discover_zenodo_lineage",
            return_value={
                "status": "unpublished-concept",
                "conceptrecid": 790,
                "concept_doi": "10.5281/zenodo.790",
                "open_draft_ids": [801],
            },
        ), mock.patch.object(pub, "save_state"):
            resumed, doi = pub.reserve_zenodo(client, plan, binding, state)
        self.assertEqual(resumed["id"], 1801)
        self.assertEqual(doi, "10.5281/zenodo.801")
        self.assertFalse(
            any(call.args[0] == "POST" for call in client.request.call_args_list)
        )

    def test_newversion_response_must_be_original_resource_with_latest_draft_link(self):
        plan = self.plan()
        draft = self.row(
            plan,
            record_id=701,
            deposition_id=1701,
            conceptrecid=690,
            fingerprint="e" * 64,
            version="2026.08.01",
            state="unsubmitted",
        )
        state = {
            "zenodo_conceptrecid": 690,
            "zenodo_concept_doi": "10.5281/zenodo.690",
            "zenodo_lineage_latest_deposition_id": 1700,
            "zenodo_lineage_latest_record_id": 700,
            "zenodo_lineage_latest_record_doi": "10.5281/zenodo.700",
        }
        with self.assertRaisesRegex(pub.PublicationError, "original resource"):
            pub.zenodo_latest_draft_from_response(
                mock.Mock(), draft, plan, state
            )

    def test_zenodo_preflight_lineage_discovery_has_zero_github_calls(self):
        plan = self.plan()
        binding = self.binding()
        zenodo = mock.Mock()
        with mock.patch.object(pub, "zenodo_client", return_value=zenodo), mock.patch.object(
            pub, "exact_zenodo_depositions", return_value=[]
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
        ), mock.patch.object(pub, "load_state", return_value={"blob_cache": {}}), mock.patch.object(
            pub, "anonymous_json", return_value={"hits": {"hits": []}}
        ), mock.patch.object(
            pub, "github_client", side_effect=AssertionError("wrong channel")
        ):
            result = pub.zenodo_remote_preflight(plan, binding)
        self.assertEqual(result["lineage"]["status"], "absent")
        self.assertEqual(result["matching_authenticated_deposition_ids"], [])


if __name__ == "__main__":
    unittest.main()
