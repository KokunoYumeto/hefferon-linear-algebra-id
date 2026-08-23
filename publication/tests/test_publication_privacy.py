from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


PUBLICATION = Path(__file__).resolve().parents[1]
PROJECT = PUBLICATION.parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pub = load_module("hefferon_publish_release_privacy_tests", PUBLICATION / "publish_release.py")
fig = load_module("hefferon_publish_figshare_privacy_tests", PUBLICATION / "publish_figshare.py")


class PublicationPrivacyTests(unittest.TestCase):
    def plan(self):
        return copy.deepcopy(pub.load_plan())

    def test_exact_model_provenance_reaches_every_public_metadata_surface(self):
        plan = self.plan()
        exact = pub.EXPECTED_MODEL_PROVENANCE
        self.assertEqual(plan["release"]["model_provenance"], exact)
        self.assertIn(exact, (PROJECT / "README.md").read_text(encoding="utf-8"))
        self.assertIn(exact, (PROJECT / "NOTICE.id-ID.md").read_text(encoding="utf-8"))
        fingerprint = "f" * 64
        doi = "10.5281/zenodo.1"
        self.assertIn(exact, pub.zenodo_metadata(plan, doi, fingerprint)["description"])
        self.assertIn(
            exact,
            pub.release_readme(
                plan,
                doi,
                fingerprint,
                [],
                {"source_tree_sha256": "a" * 64},
            ).decode("utf-8"),
        )
        self.assertIn(exact, pub.pages_html(plan, doi, fingerprint).decode("utf-8"))
        context = {
            "fingerprint": fingerprint,
            "zenodo_url": f"https://doi.org/{doi}",
        }
        self.assertIn(exact, fig.metadata(context, fig.FULL_BRANCH, 25)["description"])
        self.assertIn(exact, fig.metadata(context, fig.METADATA_BRANCH, 1)["description"])

    def test_release_manifest_contains_exact_model_provenance_and_all_zips_are_safe(self):
        plan = self.plan()
        fingerprint = "f" * 64
        doi = "10.5281/zenodo.1"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / "snapshot"
            assets = root / "assets"
            (snapshot / "publication").mkdir(parents=True)
            (snapshot / "LICENSE").write_text("license\n", encoding="utf-8")
            (snapshot / "NOTICE.id-ID.md").write_text("notice\n", encoding="utf-8")
            pdf_rows = []
            for index, item in enumerate(plan["reader_pdfs"], start=1):
                payload = f"pdf-{index}\n".encode("utf-8")
                path = snapshot / item["source"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
                pdf_rows.append(
                    {
                        "component": item["component"],
                        "pages": index,
                        "bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )
            safe_flags = []

            def fake_zip(destination, _sources, _root, *, public_safe=False):
                safe_flags.append(public_safe)
                payload = (destination.name + "\n").encode("utf-8")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(payload)
                return {
                    "path": destination.name,
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "entry_count": 0,
                    "uncompressed_bytes": 0,
                    "entries_sha256": hashlib.sha256(b"[]\n").hexdigest(),
                }

            readiness = {
                "pdfs": pdf_rows,
                "source_tree_sha256": "a" * 64,
                "build_report_sha256": "b" * 64,
                "backend": {"status": "pass"},
            }
            with mock.patch.object(pub, "expand_includes", return_value=[]), mock.patch.object(
                pub, "staged_baseline_relative", return_value="tmp/baseline.json"
            ), mock.patch.object(pub, "deterministic_zip", side_effect=fake_zip):
                pub.build_release_payloads(
                    plan,
                    snapshot,
                    assets,
                    doi,
                    {"fingerprint": fingerprint},
                    readiness,
                )
            manifest = json.loads(
                (snapshot / "publication" / plan["release_assets"]["manifest"]).read_text(
                    encoding="utf-8"
                )
            )
        self.assertEqual(safe_flags, [True, True, True])
        self.assertEqual(manifest["model_provenance"], pub.EXPECTED_MODEL_PROVENANCE)

    def test_public_zip_sanitizes_home_path_without_writing_private_input(self):
        private_home = str(Path.home())
        private_identifier = Path.home().name
        payload = f'{{"path": "{private_home}\\evidence.json"}}\n'.encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "evidence.json"
            destination = root / "evidence.zip"
            with mock.patch.object(Path, "read_bytes", return_value=payload):
                pub.deterministic_zip(destination, [source], root, public_safe=True)
            with zipfile.ZipFile(destination, "r") as archive:
                public_payload = archive.read("evidence.json").decode("utf-8")
        self.assertIn("%USERPROFILE%", public_payload)
        self.assertNotIn(private_identifier.casefold(), public_payload.casefold())

    def test_public_payload_and_repository_snapshot_reject_bare_identifier(self):
        private = Path.home().name
        payload = f"private-account={private}".encode("utf-8")
        with self.assertRaises(pub.PublicationError):
            pub.public_safe_payload(payload)
        utf16_payload = f"private-account={private}".encode("utf-16-le")
        with self.assertRaises(pub.PublicationError):
            pub.public_safe_payload(utf16_payload)
        with mock.patch.object(Path, "read_bytes", return_value=payload):
            with self.assertRaises(pub.PublicationError):
                pub.assert_public_safe_file(Path("public.bin"))
            with self.assertRaises(fig.FigshareError):
                fig.assert_public_safe_file(Path("public.bin"))

    def test_public_log_payload_redacts_wrapped_bare_identifier(self):
        private = Path.home().name
        payload = f"wrapped-path-suffix/{private}/build.log\n".encode("utf-8")
        redacted = pub.public_safe_payload(payload, redact_bare_identifier=True)
        self.assertNotIn(private.casefold().encode("utf-8"), redacted.lower())
        self.assertIn(b"%USER%", redacted)

    def test_plan_rejects_local_identifier_and_github_target_is_fixed(self):
        plan = self.plan()
        self.assertEqual(
            (
                plan["github"]["owner"],
                plan["github"]["repository"],
                plan["github"]["default_branch"],
            ),
            (
                pub.EXPECTED_GITHUB_OWNER,
                pub.EXPECTED_GITHUB_REPOSITORY,
                pub.EXPECTED_GITHUB_DEFAULT_BRANCH,
            ),
        )
        with self.assertRaises(pub.PublicationError):
            pub.reject_local_user_identifier({"description": Path.home().name})

    def test_private_credential_path_expansion_is_absolute_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            expected = Path(directory) / "credential.md"
            with mock.patch.dict(os.environ, {"HEFFERON_PRIVATE_ROOT": directory}, clear=False):
                actual = pub.resolve_private_credential_path(
                    r"%HEFFERON_PRIVATE_ROOT%\credential.md", "github"
                )
            self.assertEqual(actual, expected)
        with self.assertRaises(pub.PublicationError):
            pub.resolve_private_credential_path("relative/credential.md", "github")
        with self.assertRaises(pub.PublicationError):
            pub.resolve_private_credential_path(
                r"%HEFFERON_UNSET_PRIVATE_ROOT%\credential.md", "github"
            )


if __name__ == "__main__":
    unittest.main()
