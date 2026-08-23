#!/usr/bin/env python3
"""Safely package, publish, and verify the Hefferon id-ID release.

The driver never invokes Git. Preflight commands are read-only. Mutating and
verification commands hold one process lock and operate from a hashed,
immutable transaction staging tree. GitHub and Zenodo can be published and
verified together or as isolated channels; interrupted transactions resume
from their persisted, byte-bound state.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import html
import http.client
import json
import mimetypes
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Sequence


PROJECT = Path(__file__).resolve().parents[1]
PUBLICATION = PROJECT / "publication"
PLAN_PATH = PUBLICATION / "publication-plan.json"
RUNTIME_PATH = PUBLICATION / ".runtime.json"
STATE_PATH = PUBLICATION / "transaction-state.json"
LOCK_PATH = PUBLICATION / ".publication.lock"
TRANSACTIONS = PUBLICATION / ".transactions"
READBACK_PATH = PUBLICATION / "public-readback.json"
ZENODO_READBACK_PATH = PUBLICATION / "public-readback.zenodo.json"
GITHUB_READBACK_PATH = PUBLICATION / "public-readback.github.json"
USER_AGENT = "Codex-R005-Hefferon-id-publication/2"
GITHUB_API_ORIGIN = "https://api.github.com"
GITHUB_UPLOAD_ORIGIN = "https://uploads.github.com"
GITHUB_WEB_ORIGIN = "https://github.com"
GITHUB_RAW_ORIGIN = "https://raw.githubusercontent.com"
ZENODO_ORIGIN = "https://zenodo.org"
EXPECTED_GITHUB_OWNER = "KokunoYumeto"
EXPECTED_GITHUB_REPOSITORY = "hefferon-linear-algebra-id"
EXPECTED_GITHUB_DEFAULT_BRANCH = "main"
EXPECTED_MODEL_PROVENANCE = "OpenAI Codex gpt-5.6-sol, Ultra."
MAX_JSON_RESPONSE = 32 * 1024 * 1024
MAX_ERROR_RESPONSE = 256 * 1024
MAX_BLOB_BYTES = 100 * 1024 * 1024
MAX_UNBOUNDED_DOWNLOAD = 64 * 1024 * 1024
MAX_CREDENTIAL_FILE = 1024 * 1024
MAX_PAGES = 100
ZENODO_PUBLIC_PAGE_SIZE = 25
FIXED_ZIP_TIME = (2026, 8, 21, 0, 0, 0)
TRANSIENT_HTTP = {408, 425, 429, 500, 502, 503, 504}
EXPECTED_SAGE_VERSION = "SageMath version 9.5, Release Date: 2022-01-30"
EXPECTED_SAGETEX_DISTRIBUTION_VERSION = "3.6.1"
EXPECTED_SAGETEX_MODULE_VERSION = "2021/10/16 v3.6"
EXPECTED_RANDOM_SEED = 20260821
EXPECTED_SOURCE_DATE_EPOCH = "1633046400"
EXPECTED_NATIVE_TOPIC_ANSWERS = 131
EXPECTED_INDONESIAN_EDITION_SUPPLIED_TOPIC_ANSWERS = 2
EXPECTED_TOPIC_ANSWERS = 133
EXPECTED_BUILD_TOOL_PATHS = {
    "builder": "tools/build_hefferon_id.py",
    "lab_graphics_extractor": "tools/extract_lab_graphics_from_authority_pdf.py",
    "book_graphics_recoverer": "tools/recover_book_asy_graphics.py",
    "lab_sagetex_runner": "tools/run_lab_sagetex_wsl.py",
    "pythontex_startup": "tools/pythontex_startup/sitecustomize.py",
}
EXPECTED_AUTHORITY_BUILD_INPUTS = {
    "authority_book_pdf": "authority/official/book.pdf",
    "authority_lab_pdf": "authority/official/lab.pdf",
}
EXPECTED_PDFTEX_FONT_DEPENDENCY_NAMES = {
    "8r.enc",
    "bera.map",
    "BrushScriptX-Italic.pfa",
    "cm-super-t1.enc",
    "cm-super-t1.map",
    "cm-super-ts1.enc",
    "cm-super-ts1.map",
    "cmex10.pfb",
    "cmmi10.pfb",
    "cmmi5.pfb",
    "cmmi7.pfb",
    "cmr10.pfb",
    "cmsy10.pfb",
    "cmsy5.pfb",
    "cmsy7.pfb",
    "euex10.pfb",
    "eufm10.pfb",
    "eufm5.pfb",
    "eufm7.pfb",
    "eurb10.pfb",
    "eurm10.pfb",
    "eurm5.pfb",
    "eurm7.pfb",
    "eusm10.pfb",
    "eusm7.pfb",
    "fvmr8a.pfb",
    "fvsb8a.pfb",
    "fvsr8a.pfb",
    "hefferon-standard.map",
    "lcircle1.pfb",
    "line10.pfb",
    "linew10.pfb",
    "msam10.pfb",
    "msam7.pfb",
    "msbm10.pfb",
    "msbm7.pfb",
    "pbsi.map",
    "rsfs10.pfb",
    "sfocc10.pfb",
    "sform10.pfb",
    "sform5.pfb",
    "sform6.pfb",
    "sform7.pfb",
    "sform8.pfb",
    "sform9.pfb",
    "sfosl10.pfb",
    "sfoti10.pfb",
    "sfssdc10.pfb",
    "ugq.map",
    "ugqb8a.pfb",
    "uhvr8a.pfb",
}
EXPECTED_PDFTEX_FONT_DEPENDENCY_BYTES = 2_289_616
EXPECTED_PDFTEX_FONT_CLOSURE_FILE_COUNT = 73
EXPECTED_PDFTEX_FONT_CLOSURE_BYTES = 10_325_900
EXPECTED_PDFTEX_FONT_CLOSURE_TREE_SHA256 = (
    "542e2566a14b473654387a8a263cc1d49392e35db7058880d56f95cc6059ce56"
)


class PublicationError(RuntimeError):
    """A bounded, secret-safe publication failure."""


def canonical_bytes(value: Any, *, pretty: bool = False) -> bytes:
    options = {"ensure_ascii": False, "sort_keys": True}
    if pretty:
        text = json.dumps(value, indent=2, **options)
    else:
        text = json.dumps(value, separators=(",", ":"), **options)
    return (text + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_file_stable(path: Path) -> str:
    before = path.stat()
    digest = sha256_file(path)
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise PublicationError(f"file changed while hashing: {path}")
    return digest


def md5_file(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_blob_sha_file(path: Path) -> str:
    digest = hashlib.sha1(usedforsecurity=False)
    digest.update(b"blob " + str(path.stat().st_size).encode("ascii") + b"\0")
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_json(path: Path, *, expected: type = dict) -> Any:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise PublicationError(f"cannot read {path}: {exc}") from None
    if len(payload) > MAX_JSON_RESPONSE:
        raise PublicationError(f"JSON file exceeds bounded size: {path}")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicationError(f"invalid JSON in {path}: {exc}") from None
    if not isinstance(value, expected):
        raise PublicationError(f"JSON type mismatch in {path}: expected {expected.__name__}")
    return value


def save_json(path: Path, value: Any) -> None:
    atomic_write(path, canonical_bytes(value, pretty=True))


def expect_dict(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PublicationError(f"{context} is not a JSON object")
    return value


def expect_list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise PublicationError(f"{context} is not a JSON array")
    return value


def require_string(mapping: dict[str, Any], key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise PublicationError(f"{context}.{key} is missing or not a nonempty string")
    return value


def require_integer(mapping: dict[str, Any], key: str, context: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise PublicationError(f"{context}.{key} is missing or not an integer")
    return value


def require_boolean(mapping: dict[str, Any], key: str, context: str) -> bool:
    value = mapping.get(key)
    if not isinstance(value, bool):
        raise PublicationError(f"{context}.{key} is missing or not a boolean")
    return value


def require_sha(value: Any, context: str, *, algorithm: str = "sha256") -> str:
    lengths = {"sha1": 40, "sha256": 64, "md5": 32}
    length = lengths[algorithm]
    if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        raise PublicationError(f"{context} is not a lowercase {algorithm} digest")
    return value


def require_exact_keys(
    mapping: dict[str, Any], required: set[str], context: str, *, optional: set[str] | None = None
) -> None:
    optional = optional or set()
    missing = required - set(mapping)
    extras = set(mapping) - required - optional
    if missing or extras:
        raise PublicationError(
            f"{context} key closure differs; missing={sorted(missing)}, extra={sorted(extras)}"
        )


def ensure_under(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and not resolved.is_relative_to(root_resolved):
        raise PublicationError(f"path escapes bounded root {root}: {path}")
    return resolved


def lexical_relative(path: Path, root: Path) -> str:
    try:
        return path.absolute().relative_to(root.absolute()).as_posix()
    except ValueError:
        raise PublicationError(f"path is outside bounded root: {path}") from None


def validate_relative_name(value: str, context: str) -> str:
    candidate = Path(value)
    if (
        not value
        or candidate.is_absolute()
        or bool(candidate.drive)
        or ".." in candidate.parts
        or value.startswith(("/", "\\"))
        or "\x00" in value
    ):
        raise PublicationError(f"unsafe relative path in {context}: {value!r}")
    return candidate.as_posix()


def validate_basename(value: str, context: str) -> str:
    if (
        Path(value).name != value
        or value in {"", ".", ".."}
        or "/" in value
        or "\\" in value
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", value)
    ):
        raise PublicationError(f"unsafe artifact basename in {context}: {value!r}")
    return value


class TransactionLock:
    """Cross-process exclusive lock held for every local/remote mutation."""

    def __init__(self, path: Path = LOCK_PATH):
        self.path = path
        self.stream: BinaryIO | None = None

    def __enter__(self) -> "TransactionLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+b")
        self.stream.seek(0, os.SEEK_END)
        if self.stream.tell() == 0:
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            self.stream = None
            raise PublicationError("another publication transaction holds the lock") from None
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        if self.stream is None:
            return
        self.stream.seek(0)
        if os.name == "nt":
            import msvcrt

            with contextlib.suppress(OSError):
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            with contextlib.suppress(OSError):
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        self.stream.close()
        self.stream = None


def reject_public_credentials(value: Any, context: str = "plan") -> None:
    """Reject private material even if a future schema field is added accidentally."""
    github_secret = re.compile(r"(?:github_pat_[A-Za-z0-9_]{20,}|gh[opusr]_[A-Za-z0-9]{20,})")
    bearer_secret = re.compile(r"(?i)\b(?:authorization\s*:\s*)?bearer\s+[A-Za-z0-9._~-]{16,}")
    forbidden_keys = {
        "credential",
        "credentials",
        "credential_file",
        "github_credential_file",
        "zenodo_credential_file",
        "secret",
        "secrets",
        "token",
        "access_token",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise PublicationError(f"{context} contains a non-string JSON key")
            if key.lower() in forbidden_keys:
                raise PublicationError(f"public publication plan contains private field {context}.{key}")
            reject_public_credentials(child, f"{context}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_public_credentials(child, f"{context}[{index}]")
    elif isinstance(value, str) and (github_secret.search(value) or bearer_secret.search(value)):
        raise PublicationError(f"public publication plan contains credential-like material at {context}")


def reject_local_user_identifier(value: Any, context: str = "public value") -> None:
    """Reject the local account identifier without ever including it in diagnostics."""

    identifier = Path.home().name
    if not identifier:
        return
    if isinstance(value, dict):
        for key, child in value.items():
            reject_local_user_identifier(key, f"{context}.key")
            reject_local_user_identifier(child, f"{context}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_local_user_identifier(child, f"{context}[{index}]")
    elif isinstance(value, str) and identifier.casefold() in value.casefold():
        raise PublicationError(f"{context} contains the local user identifier")


def require_string_list(value: Any, context: str, *, unique: bool = False) -> list[str]:
    items = expect_list(value, context)
    result: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, str) or not item:
            raise PublicationError(f"{context}[{index}] is not a nonempty string")
        result.append(item)
    if unique and len(result) != len(set(result)):
        raise PublicationError(f"{context} contains duplicate values")
    return result


def load_plan() -> dict[str, Any]:
    plan = load_json(PLAN_PATH)
    if plan.get("schema_version") != "hefferon-id-publication-plan-v1":
        raise PublicationError("unsupported publication plan schema")
    reject_public_credentials(plan)
    reject_local_user_identifier(plan, "public publication plan")
    require_exact_keys(
        plan,
        {
            "schema_version",
            "release",
            "authority",
            "rights",
            "github",
            "zenodo",
            "runtime",
            "qa",
            "reader_pdfs",
            "bundles",
            "repository_snapshot",
            "release_assets",
            "staging_inputs",
        },
        "plan",
    )
    release = expect_dict(plan["release"], "plan.release")
    require_exact_keys(
        release,
        {"version", "tag", "publication_date", "title", "short_title", "model_provenance"},
        "plan.release",
    )
    for key in ("version", "tag", "publication_date", "title", "short_title", "model_provenance"):
        require_string(release, key, "plan.release")
    if release["model_provenance"] != EXPECTED_MODEL_PROVENANCE:
        raise PublicationError("release model provenance differs from the required exact identity")
    if release["tag"] != "v" + release["version"]:
        raise PublicationError("release tag is not exactly v + version")
    if not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", release["version"]):
        raise PublicationError("release version is not YYYY.MM.DD")
    if release["publication_date"] != release["version"].replace(".", "-"):
        raise PublicationError("release date is not bound to the version")

    authority = expect_dict(plan["authority"], "plan.authority")
    require_exact_keys(
        authority,
        {
            "author",
            "work",
            "homepage",
            "repository",
            "source_commit",
            "source_tree",
            "source_commit_url",
        },
        "plan.authority",
    )
    for key in ("author", "work", "homepage", "repository", "source_commit_url"):
        require_string(authority, key, "plan.authority")
    require_sha(authority.get("source_commit"), "plan.authority.source_commit", algorithm="sha1")
    require_sha(authority.get("source_tree"), "plan.authority.source_tree", algorithm="sha1")
    for key in ("homepage", "repository", "source_commit_url"):
        origin(authority[key])

    rights = expect_dict(plan["rights"], "plan.rights")
    require_exact_keys(
        rights,
        {
            "selected_license_id",
            "selected_license_name",
            "selected_license_url",
            "route",
            "attribution_file",
        },
        "plan.rights",
    )
    for key in rights:
        require_string(rights, key, "plan.rights")
    origin(rights["selected_license_url"])
    validate_relative_name(rights["attribution_file"], "rights.attribution_file")

    github = expect_dict(plan["github"], "plan.github")
    require_exact_keys(
        github,
        {
            "owner",
            "repository",
            "description",
            "default_branch",
            "pages_path",
            "topics",
        },
        "plan.github",
    )
    for key in ("owner", "repository", "description", "default_branch", "pages_path"):
        require_string(github, key, "plan.github")
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", github["owner"]):
        raise PublicationError("GitHub owner is not a safe account name")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", github["repository"]):
        raise PublicationError("GitHub repository is not a safe repository name")
    if (
        github["owner"] != EXPECTED_GITHUB_OWNER
        or github["repository"] != EXPECTED_GITHUB_REPOSITORY
        or github["default_branch"] != EXPECTED_GITHUB_DEFAULT_BRANCH
    ):
        raise PublicationError(
            "GitHub target must remain exactly "
            f"{EXPECTED_GITHUB_OWNER}/{EXPECTED_GITHUB_REPOSITORY}:"
            f"{EXPECTED_GITHUB_DEFAULT_BRANCH}"
        )
    if github["pages_path"] != "/docs":
        raise PublicationError("GitHub Pages path must remain /docs")
    topics = require_string_list(github["topics"], "plan.github.topics", unique=True)
    if topics != sorted(topics) or any(not re.fullmatch(r"[a-z0-9-]{1,50}", item) for item in topics):
        raise PublicationError("GitHub topics must be unique, lowercase, and sorted")

    zenodo = expect_dict(plan["zenodo"], "plan.zenodo")
    require_exact_keys(
        zenodo,
        {
            "upload_type",
            "publication_type",
            "language",
            "creator",
            "access_right",
            "keywords",
        },
        "plan.zenodo",
    )
    for key in ("upload_type", "publication_type", "language", "creator", "access_right"):
        require_string(zenodo, key, "plan.zenodo")
    require_string_list(zenodo["keywords"], "plan.zenodo.keywords", unique=True)

    runtime = expect_dict(plan["runtime"], "plan.runtime")
    require_exact_keys(
        runtime,
        {"github_token_environment", "zenodo_token_environment", "excluded_local_configuration"},
        "plan.runtime",
    )
    for key in runtime:
        require_string(runtime, key, "plan.runtime")
    for key in ("github_token_environment", "zenodo_token_environment"):
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", runtime[key]):
            raise PublicationError(f"plan.runtime.{key} is not a safe environment name")
    if runtime["excluded_local_configuration"] != "publication/.runtime.json":
        raise PublicationError("private runtime path must remain publication/.runtime.json")

    qa = expect_dict(plan["qa"], "plan.qa")
    require_exact_keys(
        qa,
        {
            "source_root",
            "build_report",
            "staged_source_manifest",
            "all_page_render_manifest",
            "cross_pdf_link_audit",
            "lab_sagetex_runtime_manifest",
            "metapost_asset_manifest",
            "pdftex_input_audit",
            "final_pdf_qa",
            "final_visual_review",
            "backend_validator",
            "required_status",
            "require_reproducibility_match",
            "require_source_unchanged",
            "require_zero_undefined_references",
            "require_zero_generated_english_labels",
            "require_zero_runtime_placeholders",
            "require_resolved_cross_pdf_links",
            "require_sidecar_byte_bindings",
            "require_lab_sagetex_closure",
            "require_build_fingerprint_v4",
            "require_final_pdf_qa_zero_hard_failures",
            "require_final_visual_review_pass",
            "require_complete_visual_review_coverage",
            "require_backend_final_build",
        },
        "plan.qa",
    )
    for key in (
        "source_root",
        "build_report",
        "staged_source_manifest",
        "all_page_render_manifest",
        "cross_pdf_link_audit",
        "lab_sagetex_runtime_manifest",
        "metapost_asset_manifest",
        "pdftex_input_audit",
        "final_pdf_qa",
        "final_visual_review",
        "backend_validator",
    ):
        validate_relative_name(require_string(qa, key, "plan.qa"), f"qa.{key}")
    require_string(qa, "required_status", "plan.qa")
    for key in (
        "require_reproducibility_match",
        "require_source_unchanged",
        "require_zero_undefined_references",
        "require_zero_generated_english_labels",
        "require_zero_runtime_placeholders",
        "require_resolved_cross_pdf_links",
        "require_sidecar_byte_bindings",
        "require_lab_sagetex_closure",
        "require_build_fingerprint_v4",
        "require_final_pdf_qa_zero_hard_failures",
        "require_final_visual_review_pass",
        "require_complete_visual_review_coverage",
        "require_backend_final_build",
    ):
        if require_boolean(qa, key, "plan.qa") is not True:
            raise PublicationError(f"plan.qa.{key} must remain true")

    artifact_names: list[str] = []
    components: list[str] = []
    reader_sources: list[str] = []
    for index, item_value in enumerate(expect_list(plan.get("reader_pdfs"), "reader_pdfs")):
        item = expect_dict(item_value, f"reader_pdfs[{index}]")
        require_exact_keys(item, {"component", "source", "release_name"}, f"reader_pdfs[{index}]")
        components.append(require_string(item, "component", "reader_pdf"))
        reader_sources.append(
            validate_relative_name(require_string(item, "source", "reader_pdf"), "reader_pdf.source")
        )
        artifact_names.append(
            validate_basename(require_string(item, "release_name", "reader_pdf"), "reader_pdf")
        )
    if components != ["textbook", "worked-answers", "sage-lab"]:
        raise PublicationError("reader PDF component/order closure is not exact")
    if len(reader_sources) != len(set(reader_sources)):
        raise PublicationError("reader PDF sources are not unique")
    bundle_kinds: list[str] = []
    bundle_includes: dict[str, set[str]] = {}
    for index, item_value in enumerate(expect_list(plan.get("bundles"), "bundles")):
        item = expect_dict(item_value, f"bundles[{index}]")
        require_exact_keys(item, {"kind", "release_name", "include"}, f"bundles[{index}]")
        bundle_kind = require_string(item, "kind", "bundle")
        bundle_kinds.append(bundle_kind)
        artifact_names.append(
            validate_basename(require_string(item, "release_name", "bundle"), "bundle")
        )
        included_values = require_string_list(
            item.get("include"), "bundle.include", unique=True
        )
        bundle_includes[bundle_kind] = set(included_values)
        for included in included_values:
            validate_relative_name(included, "bundle.include")
    if bundle_kinds != ["editable-source", "modular-backend", "provenance-qa"]:
        raise PublicationError("bundle kind/order closure is not exact")
    required_authority_inputs = set(EXPECTED_AUTHORITY_BUILD_INPUTS.values())
    if not required_authority_inputs.issubset(bundle_includes["editable-source"]):
        raise PublicationError(
            "editable-source bundle omits required offline authority PDFs"
        )
    release_assets = expect_dict(plan.get("release_assets"), "release_assets")
    require_exact_keys(
        release_assets,
        {"directory", "readme", "manifest", "checksums", "expected_count"},
        "release_assets",
    )
    validate_relative_name(require_string(release_assets, "directory", "release_assets"), "release_assets.directory")
    for key in ("readme", "manifest", "checksums"):
        artifact_names.append(validate_basename(require_string(release_assets, key, "release_assets"), key))
    if len(artifact_names) != len({name.casefold() for name in artifact_names}):
        raise PublicationError("release artifact basenames are not unique")
    if len(artifact_names) != require_integer(release_assets, "expected_count", "release_assets"):
        raise PublicationError("release artifact count does not match the plan")
    repository_snapshot = expect_dict(plan["repository_snapshot"], "repository_snapshot")
    require_exact_keys(
        repository_snapshot, {"include", "exclude_names", "exclude_suffixes"}, "repository_snapshot"
    )
    repository_includes = require_string_list(
        repository_snapshot["include"], "repository_snapshot.include", unique=True
    )
    for value in repository_includes:
        validate_relative_name(value, "repository_snapshot.include")
    if not required_authority_inputs.issubset(set(repository_includes)):
        raise PublicationError(
            "repository snapshot omits required offline authority PDFs"
        )
    exclude_names = require_string_list(
        repository_snapshot["exclude_names"], "repository_snapshot.exclude_names", unique=True
    )
    private_names = {
        ".publication.lock",
        ".runtime.json",
        ".transactions",
        "public-readback.json",
        "transaction-state.json",
    }
    if not private_names.issubset(set(exclude_names)):
        raise PublicationError("repository snapshot does not exclude every private runtime/state path")
    require_string_list(repository_snapshot["exclude_suffixes"], "repository_snapshot.exclude_suffixes", unique=True)
    staging_inputs = require_string_list(
        plan.get("staging_inputs"), "staging_inputs", unique=True
    )
    for value in staging_inputs:
        validate_relative_name(value, "staging_inputs")
    if not required_authority_inputs.issubset(set(staging_inputs)):
        raise PublicationError("staging inputs omit required offline authority PDFs")
    return plan


def transaction_binding(plan: dict[str, Any]) -> dict[str, str]:
    _input_rows, input_digest = staging_input_inventory(
        plan, PROJECT, require_complete=False
    )
    core = {
        "plan_sha256": sha256_file_stable(PLAN_PATH),
        "driver_sha256": sha256_file_stable(Path(__file__).resolve()),
        "input_inventory_sha256": input_digest,
        "owner": plan["github"]["owner"],
        "repository": plan["github"]["repository"],
        "tag": plan["release"]["tag"],
        "version": plan["release"]["version"],
        "source_commit": plan["authority"]["source_commit"],
        "source_tree": plan["authority"]["source_tree"],
    }
    return {**core, "fingerprint": sha256_bytes(canonical_bytes(core))}


def new_state(binding: dict[str, str]) -> dict[str, Any]:
    return {
        "schema_version": "hefferon-id-publication-transaction-v2",
        "binding": binding,
        "transaction_fingerprint": binding["fingerprint"],
        "blob_cache": {},
    }


def validate_state_fields(state: dict[str, Any]) -> None:
    allowed = {
        "schema_version",
        "binding",
        "transaction_fingerprint",
        "blob_cache",
        "base_inventory_sha256",
        "base_manifest_sha256",
        "final_inventory_sha256",
        "final_manifest_sha256",
        "artifact_set_sha256",
        "github_repository_id",
        "github_pending_commit_sha",
        "github_pending_tree_sha",
        "github_commit_sha",
        "github_tree_sha",
        "repository_snapshot_sha256",
        "github_pending_tag_object_sha",
        "github_tag_commit_sha",
        "github_release_id",
        "github_release_url",
        "github_release_public",
        "zenodo_deposition_id",
        "zenodo_doi",
        "zenodo_record_id",
        "zenodo_conceptrecid",
        "zenodo_concept_doi",
        "zenodo_lineage_latest_deposition_id",
        "zenodo_lineage_latest_record_id",
        "zenodo_lineage_latest_record_doi",
        "zenodo_create_phase",
        "zenodo_newversion_phase",
        "zenodo_publish_phase",
        "zenodo_published",
        "zenodo_prepublish_authenticated_files",
        "zenodo_anonymous_readback_sha256",
        "github_anonymous_readback_sha256",
        "anonymous_readback_sha256",
        "complete",
    }
    extras = set(state) - allowed
    if extras:
        raise PublicationError(f"transaction state contains unsupported fields: {sorted(extras)}")
    if state.get("schema_version") != "hefferon-id-publication-transaction-v2":
        raise PublicationError("transaction state schema marker differs")
    binding = expect_dict(state.get("binding"), "transaction state.binding")
    binding_keys = {
        "plan_sha256",
        "driver_sha256",
        "input_inventory_sha256",
        "owner",
        "repository",
        "tag",
        "version",
        "source_commit",
        "source_tree",
        "fingerprint",
    }
    require_exact_keys(binding, binding_keys, "transaction state.binding")
    for key in ("plan_sha256", "driver_sha256", "input_inventory_sha256", "fingerprint"):
        require_sha(binding.get(key), f"transaction state.binding.{key}")
    for key in ("source_commit", "source_tree"):
        require_sha(binding.get(key), f"transaction state.binding.{key}", algorithm="sha1")
    for key in ("owner", "repository", "tag", "version"):
        require_string(binding, key, "transaction state.binding")
    fingerprint = require_sha(
        state.get("transaction_fingerprint"), "state.transaction_fingerprint"
    )
    if binding.get("fingerprint") != fingerprint:
        raise PublicationError("transaction state fingerprint and binding differ")
    binding_core = {key: value for key, value in binding.items() if key != "fingerprint"}
    if sha256_bytes(canonical_bytes(binding_core)) != fingerprint:
        raise PublicationError("transaction state binding fingerprint does not recompute")
    cache = expect_dict(state.get("blob_cache"), "transaction blob cache")
    for relative, item_value in cache.items():
        if not isinstance(relative, str):
            raise PublicationError("transaction blob cache has a non-string key")
        validate_relative_name(relative, "blob cache")
        item = expect_dict(item_value, f"blob cache {relative}")
        require_exact_keys(item, {"bytes", "sha256", "remote_sha"}, f"blob cache {relative}")
        if require_integer(item, "bytes", "blob cache") < 0:
            raise PublicationError("blob cache has a negative byte count")
        require_sha(item.get("sha256"), "blob cache.sha256")
        require_sha(item.get("remote_sha"), "blob cache.remote_sha", algorithm="sha1")
    for key in (
        "base_inventory_sha256",
        "base_manifest_sha256",
        "final_inventory_sha256",
        "final_manifest_sha256",
        "artifact_set_sha256",
        "repository_snapshot_sha256",
        "zenodo_anonymous_readback_sha256",
        "github_anonymous_readback_sha256",
        "anonymous_readback_sha256",
    ):
        if key in state:
            require_sha(state[key], f"state.{key}")
    for key in (
        "github_pending_commit_sha",
        "github_pending_tree_sha",
        "github_commit_sha",
        "github_tree_sha",
        "github_pending_tag_object_sha",
        "github_tag_commit_sha",
    ):
        if key in state:
            require_sha(state[key], f"state.{key}", algorithm="sha1")
    for key in (
        "github_repository_id",
        "github_release_id",
        "zenodo_deposition_id",
        "zenodo_record_id",
        "zenodo_conceptrecid",
        "zenodo_lineage_latest_deposition_id",
        "zenodo_lineage_latest_record_id",
    ):
        if key in state and (
            not isinstance(state[key], int) or isinstance(state[key], bool) or state[key] <= 0
        ):
            raise PublicationError(f"state.{key} is not a positive integer")
    for key in ("github_release_public", "zenodo_published", "complete"):
        if key in state and not isinstance(state[key], bool):
            raise PublicationError(f"state.{key} is not a boolean")
    if "zenodo_doi" in state and not re.fullmatch(
        r"10\.5281/zenodo\.\d+", str(state["zenodo_doi"])
    ):
        raise PublicationError("state.zenodo_doi is malformed")
    lineage_keys = {
        "zenodo_conceptrecid",
        "zenodo_concept_doi",
        "zenodo_lineage_latest_deposition_id",
        "zenodo_lineage_latest_record_id",
        "zenodo_lineage_latest_record_doi",
    }
    present_lineage_keys = lineage_keys.intersection(state)
    if present_lineage_keys and present_lineage_keys != lineage_keys:
        raise PublicationError("Zenodo lineage state is only partially pinned")
    if present_lineage_keys:
        conceptrecid = state["zenodo_conceptrecid"]
        concept_doi = state["zenodo_concept_doi"]
        latest_id = state["zenodo_lineage_latest_record_id"]
        latest_doi = state["zenodo_lineage_latest_record_doi"]
        if concept_doi != f"10.5281/zenodo.{conceptrecid}":
            raise PublicationError("state Zenodo concept DOI/record identity differs")
        if latest_doi != f"10.5281/zenodo.{latest_id}":
            raise PublicationError("state Zenodo latest-record DOI/identity differs")
    if "zenodo_publish_phase" in state and state["zenodo_publish_phase"] not in {
        "requested",
        "done",
    }:
        raise PublicationError("state.zenodo_publish_phase is malformed")
    if "zenodo_create_phase" in state and state["zenodo_create_phase"] not in {
        "requested",
        "done",
    }:
        raise PublicationError("state.zenodo_create_phase is malformed")
    if "zenodo_newversion_phase" in state and state["zenodo_newversion_phase"] not in {
        "requested",
        "done",
    }:
        raise PublicationError("state.zenodo_newversion_phase is malformed")
    if "zenodo_newversion_phase" in state and not present_lineage_keys:
        raise PublicationError("Zenodo new-version phase lacks a pinned lineage")
    if "github_release_url" in state:
        validate_origin(state["github_release_url"], {origin(GITHUB_WEB_ORIGIN)})
    if "zenodo_prepublish_authenticated_files" in state:
        for index, value in enumerate(
            expect_list(
                state["zenodo_prepublish_authenticated_files"],
                "state.zenodo_prepublish_authenticated_files",
            )
        ):
            item = expect_dict(value, f"state prepublish file[{index}]")
            require_exact_keys(item, {"name", "bytes", "sha256"}, "state prepublish file")
            validate_basename(require_string(item, "name", "state prepublish file"), "state prepublish file")
            if require_integer(item, "bytes", "state prepublish file") < 0:
                raise PublicationError("state prepublish file has a negative byte count")
            require_sha(item.get("sha256"), "state prepublish file.sha256")


def load_state(binding: dict[str, str]) -> dict[str, Any]:
    if not STATE_PATH.exists():
        return new_state(binding)
    state = load_json(STATE_PATH)
    if state.get("schema_version") != "hefferon-id-publication-transaction-v2":
        raise PublicationError("transaction state has an unsupported or test-only schema")
    if state.get("binding") != binding or state.get("transaction_fingerprint") != binding["fingerprint"]:
        raise PublicationError("transaction state is not bound to this exact plan/driver/release")
    if not isinstance(state.get("blob_cache"), dict):
        raise PublicationError("transaction blob cache is malformed")
    validate_state_fields(state)
    return state


def save_state(state: dict[str, Any]) -> None:
    validate_state_fields(state)
    save_json(STATE_PATH, state)


def origin(url: str) -> tuple[str, str, int]:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise PublicationError(f"URL is not a plain HTTPS origin: {url!r}")
    return parsed.scheme, parsed.hostname.lower(), parsed.port or 443


def validate_origin(url: str, allowed: set[tuple[str, str, int]]) -> None:
    if origin(url) not in allowed:
        raise PublicationError(f"URL origin is outside the exact allowlist: {url!r}")


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never forward Authorization across an origin boundary."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        newurl = urllib.parse.urljoin(req.full_url, newurl)
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise PublicationError("redirect attempted to leave HTTPS")
        all_headers = {**getattr(req, "unredirected_hdrs", {}), **req.headers}
        has_auth = any(key.lower() == "authorization" for key in all_headers)
        if has_auth and origin(req.full_url) != origin(newurl):
            raise PublicationError("authenticated cross-origin redirect rejected")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def bounded_read(response: Any, limit: int = MAX_JSON_RESPONSE) -> bytes:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise PublicationError("HTTP response limit is malformed")
    declared = response.headers.get("Content-Length")
    if declared:
        try:
            declared_size = int(declared)
        except (TypeError, ValueError):
            raise PublicationError("HTTP Content-Length is malformed") from None
        if declared_size < 0 or declared_size > limit:
            raise PublicationError("HTTP response exceeds bounded size")
    payload = response.read(limit + 1)
    if len(payload) > limit:
        raise PublicationError("HTTP response exceeds bounded size")
    return payload


def safe_error_detail(payload: bytes) -> str:
    try:
        value = json.loads(payload.decode("utf-8"))
        if isinstance(value, dict):
            return str(value.get("message") or value.get("errors") or "")[:500]
    except Exception:
        pass
    return payload.decode("utf-8", "replace")[:500]


def backoff_seconds(
    attempt: int,
    retry_after: str | None = None,
    rate_limit_reset: str | None = None,
) -> float:
    if retry_after:
        with contextlib.suppress(ValueError):
            return min(60.0, max(0.0, float(retry_after)))
    if rate_limit_reset:
        with contextlib.suppress(ValueError):
            return min(60.0, max(0.0, float(rate_limit_reset) - time.time() + 1.0))
    return min(12.0, 0.75 * (2**attempt))


def retryable_http_status(
    status: int, headers: dict[str, str], payload: bytes = b""
) -> bool:
    if status in TRANSIENT_HTTP:
        return True
    if status != 403:
        return False
    message = payload[:MAX_ERROR_RESPONSE].lower()
    return bool(
        headers.get("retry-after")
        or headers.get("x-ratelimit-remaining") == "0"
        or b"rate limit" in message
        or b"secondary rate" in message
    )


def http_bytes(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    expected: Sequence[int] = (200,),
    allowed_origins: set[tuple[str, str, int]] | None = None,
    retryable: bool = False,
    max_response: int = MAX_JSON_RESPONSE,
    timeout: int = 120,
    follow_redirects: bool = True,
) -> tuple[int, dict[str, str], bytes, str]:
    if allowed_origins is not None:
        validate_origin(url, allowed_origins)
    request_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    opener = urllib.request.build_opener(
        SafeRedirectHandler() if follow_redirects else NoRedirectHandler()
    )
    attempts = 5 if retryable else 1
    for attempt in range(attempts):
        request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
        try:
            with opener.open(request, timeout=timeout) as response:
                status = response.status
                payload = bounded_read(response, max_response)
                response_headers = {
                    key.lower(): value for key, value in response.headers.items()
                }
                final_url = response.geturl()
                if allowed_origins is not None:
                    validate_origin(final_url, allowed_origins)
        except urllib.error.HTTPError as exc:
            status = exc.code
            response_headers = {
                key.lower(): value for key, value in exc.headers.items()
            }
            payload = exc.read(MAX_ERROR_RESPONSE + 1)[:MAX_ERROR_RESPONSE]
            final_url = exc.geturl()
            if allowed_origins is not None:
                validate_origin(final_url, allowed_origins)
            if retryable_http_status(status, response_headers, payload) and attempt + 1 < attempts:
                time.sleep(
                    backoff_seconds(
                        attempt,
                        response_headers.get("retry-after"),
                        response_headers.get("x-ratelimit-reset"),
                    )
                )
                continue
            if status in expected:
                return status, response_headers, payload, final_url
            safe_url = urllib.parse.urlsplit(url)._replace(query="").geturl()
            raise PublicationError(
                f"HTTP {status} for {method} {safe_url}: {safe_error_detail(payload)}"
            ) from None
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
            if attempt + 1 < attempts:
                time.sleep(backoff_seconds(attempt))
                continue
            safe_url = urllib.parse.urlsplit(url)._replace(query="").geturl()
            raise PublicationError(f"network failure for {method} {safe_url}: {exc}") from None
        if status not in expected:
            safe_url = urllib.parse.urlsplit(url)._replace(query="").geturl()
            raise PublicationError(f"unexpected HTTP {status} for {method} {safe_url}")
        return status, response_headers, payload, final_url
    raise PublicationError("unreachable HTTP retry state")


def decode_bounded_json(payload: bytes, expected_type: type, context: str) -> Any:
    try:
        value = json.loads(payload.decode("utf-8")) if payload else None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicationError(f"invalid JSON response for {context}: {exc}") from None
    if not isinstance(value, expected_type):
        raise PublicationError(
            f"JSON response type mismatch for {context}: expected {expected_type.__name__}"
        )
    return value


def stream_request(
    method: str,
    url: str,
    source: Path,
    *,
    headers: dict[str, str],
    allowed_origins: set[tuple[str, str, int]],
    expected: Sequence[int],
    retryable: bool,
    max_response: int = MAX_JSON_RESPONSE,
) -> tuple[int, dict[str, str], bytes]:
    validate_origin(url, allowed_origins)
    parsed = urllib.parse.urlsplit(url)
    path_and_query = parsed.path or "/"
    if parsed.query:
        path_and_query += "?" + parsed.query
    attempts = 4 if retryable else 1
    for attempt in range(attempts):
        before = source.stat()
        connection = http.client.HTTPSConnection(
            parsed.hostname, parsed.port or 443, timeout=900, context=ssl.create_default_context()
        )
        try:
            connection.putrequest(method, path_and_query)
            complete_headers = {
                "User-Agent": USER_AGENT,
                "Content-Length": str(source.stat().st_size),
                **headers,
            }
            for key, value in complete_headers.items():
                connection.putheader(key, value)
            connection.endheaders()
            with source.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    connection.send(block)
            response = connection.getresponse()
            status = response.status
            response_headers = {
                key.lower(): value for key, value in response.getheaders()
            }
            payload = bounded_read(response, max_response)
        except (TimeoutError, socket.timeout, OSError, http.client.HTTPException) as exc:
            if attempt + 1 < attempts:
                time.sleep(backoff_seconds(attempt))
                continue
            raise PublicationError(f"streaming upload failed for {source.name}: {exc}") from None
        finally:
            connection.close()
        after = source.stat()
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
            raise PublicationError(f"streaming upload source changed: {source.name}")
        if retryable_http_status(status, response_headers, payload) and attempt + 1 < attempts:
            time.sleep(
                backoff_seconds(
                    attempt,
                    response_headers.get("retry-after"),
                    response_headers.get("x-ratelimit-reset"),
                )
            )
            continue
        if 300 <= status < 400:
            raise PublicationError("authenticated streaming upload redirect rejected")
        if status not in expected:
            raise PublicationError(
                f"streaming upload HTTP {status} for {source.name}: {safe_error_detail(payload)}"
            )
        return status, response_headers, payload
    raise PublicationError("unreachable streaming retry state")


def stream_sha256(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    allowed_origins: set[tuple[str, str, int]] | None = None,
    expected_bytes: int | None = None,
    retryable: bool = True,
    follow_redirects: bool = True,
    timeout: int = 300,
    max_bytes: int = MAX_UNBOUNDED_DOWNLOAD,
) -> tuple[int, str, str]:
    if allowed_origins is not None:
        validate_origin(url, allowed_origins)
    opener = urllib.request.build_opener(
        SafeRedirectHandler() if follow_redirects else NoRedirectHandler()
    )
    attempts = 5 if retryable else 1
    for attempt in range(attempts):
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, **(headers or {})}, method="GET"
        )
        try:
            with opener.open(request, timeout=timeout) as response:
                if response.status != 200:
                    raise PublicationError(f"download returned HTTP {response.status}")
                final_url = response.geturl()
                if allowed_origins is not None:
                    validate_origin(final_url, allowed_origins)
                declared = response.headers.get("Content-Length")
                effective_limit = expected_bytes if expected_bytes is not None else max_bytes
                if not isinstance(effective_limit, int) or isinstance(effective_limit, bool) or effective_limit < 0:
                    raise PublicationError("download byte limit is malformed")
                if declared:
                    try:
                        declared_size = int(declared)
                    except (TypeError, ValueError):
                        raise PublicationError("download Content-Length is malformed") from None
                    if declared_size < 0 or declared_size > effective_limit:
                        raise PublicationError("download Content-Length exceeds its bound")
                    if expected_bytes is not None and declared_size != expected_bytes:
                        raise PublicationError("download Content-Length differs from inventory")
                digest = hashlib.sha256()
                size = 0
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    size += len(block)
                    if size > effective_limit:
                        raise PublicationError("download exceeds its bounded byte count")
                    digest.update(block)
                if expected_bytes is not None and size != expected_bytes:
                    raise PublicationError("download byte count differs from inventory")
                return size, digest.hexdigest(), final_url
        except PublicationError:
            raise
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
            status = exc.code if isinstance(exc, urllib.error.HTTPError) else None
            error_headers = (
                {key.lower(): value for key, value in exc.headers.items()}
                if isinstance(exc, urllib.error.HTTPError)
                else {}
            )
            error_payload = (
                exc.read(MAX_ERROR_RESPONSE + 1)[:MAX_ERROR_RESPONSE]
                if isinstance(exc, urllib.error.HTTPError)
                else b""
            )
            if isinstance(exc, urllib.error.HTTPError) and allowed_origins is not None:
                validate_origin(exc.geturl(), allowed_origins)
            if attempt + 1 < attempts and (
                status is None
                or status == 404
                or retryable_http_status(status, error_headers, error_payload)
            ):
                time.sleep(
                    backoff_seconds(
                        attempt,
                        error_headers.get("retry-after"),
                        error_headers.get("x-ratelimit-reset"),
                    )
                )
                continue
            raise PublicationError(f"download failed for {url}: {exc}") from None
    raise PublicationError("unreachable download retry state")


def runtime_configuration(plan: dict[str, Any]) -> dict[str, Any]:
    runtime = expect_dict(plan.get("runtime"), "plan.runtime")
    path_value = require_string(runtime, "excluded_local_configuration", "runtime")
    if validate_relative_name(path_value, "runtime configuration") != "publication/.runtime.json":
        raise PublicationError("runtime configuration must remain the excluded publication/.runtime.json")
    runtime_path = ensure_under(PROJECT / path_value, PROJECT)
    if not runtime_path.is_file():
        return {}
    runtime = load_json(runtime_path)
    require_exact_keys(
        runtime,
        set(),
        "private runtime",
        optional={"github_credential_file", "zenodo_credential_file"},
    )
    for key, value in runtime.items():
        if not isinstance(value, str) or not value:
            raise PublicationError(f"private runtime {key} is malformed")
    return runtime


def credential_candidates(plan: dict[str, Any], kind: str) -> list[str]:
    runtime_plan = expect_dict(plan.get("runtime"), "plan.runtime")
    environment_key = require_string(
        runtime_plan, f"{kind}_token_environment", f"runtime.{kind}"
    )
    found: list[str] = []
    environment_value = os.environ.get(environment_key)
    if environment_value:
        found.append(environment_value.strip())
    runtime = runtime_configuration(plan)
    credential_path = runtime.get(f"{kind}_credential_file")
    if credential_path is not None:
        if not isinstance(credential_path, str) or not credential_path:
            raise PublicationError(f"private runtime {kind} credential path is malformed")
        path = resolve_private_credential_path(credential_path, kind)
        if not path.is_file():
            raise PublicationError(f"private runtime {kind} credential file is missing")
        resolved_credential = path.resolve()
        project_resolved = PROJECT.resolve()
        if resolved_credential == project_resolved or resolved_credential.is_relative_to(
            project_resolved
        ):
            raise PublicationError(
                f"private runtime {kind} credential file must remain outside the public project"
            )
        if path.stat().st_size > MAX_CREDENTIAL_FILE:
            raise PublicationError(f"private runtime {kind} credential file exceeds 1 MiB")
        text = path.read_text(encoding="utf-8")
        patterns = (
            (r"github_pat_[A-Za-z0-9_]{50,255}", r"ghp_[A-Za-z0-9]{30,255}")
            if kind == "github"
            else (r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{40,}(?![A-Za-z0-9_-])",)
        )
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                value = match.group(0)
                if value not in found:
                    found.append(value)
    found = [value for value in found if value]
    if kind == "github":
        found = [
            value
            for value in found
            if re.fullmatch(r"(?:github_pat_[A-Za-z0-9_]{50,255}|ghp_[A-Za-z0-9]{30,255})", value)
        ]
    else:
        found = [value for value in found if re.fullmatch(r"[A-Za-z0-9_-]{40,512}", value)]
    if not found:
        raise PublicationError(f"no {kind} credential candidate was supplied")
    return found


def resolve_private_credential_path(value: str, kind: str) -> Path:
    """Expand a private credential path while rejecting ambiguous path syntax."""

    if not value or "\x00" in value:
        raise PublicationError(f"private runtime {kind} credential path is malformed")
    expanded = os.path.expanduser(os.path.expandvars(value))
    if (
        re.search(r"%[^%]+%", expanded)
        or re.search(r"\$(?:[A-Za-z_][A-Za-z0-9_]*|\{[^}]+\})", expanded)
        or re.match(r"^~(?:[/\\]|$)", expanded)
    ):
        raise PublicationError(
            f"private runtime {kind} credential path contains an unresolved expansion"
        )
    path = Path(expanded)
    if not path.is_absolute():
        raise PublicationError(f"private runtime {kind} credential path must be absolute")
    return path


class GitHubClient:
    api_origins = {origin(GITHUB_API_ORIGIN)}
    upload_origins = {origin(GITHUB_UPLOAD_ORIGIN)}

    def __init__(self, token: str):
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        body: Any | None = None,
        expected_type: type | None = dict,
        expected: Sequence[int] = (200,),
        retryable: bool | None = None,
    ) -> tuple[int, dict[str, str], Any]:
        if not endpoint.startswith("/"):
            raise PublicationError("GitHub endpoint must be origin-relative")
        url = GITHUB_API_ORIGIN + endpoint
        payload = None if body is None else canonical_bytes(body)
        headers = dict(self.headers)
        if body is not None:
            headers["Content-Type"] = "application/json"
        if retryable is None:
            retryable = method in {"GET", "HEAD", "PUT", "PATCH", "DELETE"}
        status, response_headers, response_payload, _url = http_bytes(
            method,
            url,
            headers=headers,
            body=payload,
            expected=expected,
            allowed_origins=self.api_origins,
            retryable=retryable,
        )
        if expected_type is None:
            value = None
        else:
            value = decode_bounded_json(response_payload, expected_type, endpoint)
        return status, response_headers, value

    def upload_release_asset(self, upload_url: str, path: Path) -> dict[str, Any]:
        validate_origin(upload_url, self.upload_origins)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        _status, _headers, payload = stream_request(
            "POST",
            upload_url,
            path,
            headers={**self.headers, "Content-Type": content_type},
            allowed_origins=self.upload_origins,
            expected=(201,),
            retryable=False,
        )
        return expect_dict(decode_bounded_json(payload, dict, "GitHub asset upload"), "asset upload")

    def upload_blob(self, endpoint: str, path: Path) -> dict[str, Any]:
        if path.stat().st_size > MAX_BLOB_BYTES:
            raise PublicationError(f"GitHub blob exceeds 100 MiB: {path.name}")
        temp_root = TRANSACTIONS / ".request-bodies"
        temp_root.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix="blob-", suffix=".json", dir=temp_root)
        body_path = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as target, path.open("rb") as source:
                target.write(b'{"content":"')
                while True:
                    block = source.read(3 * 1024 * 1024)
                    if not block:
                        break
                    target.write(base64.b64encode(block))
                target.write(b'","encoding":"base64"}\n')
            _status, _headers, payload = stream_request(
                "POST",
                GITHUB_API_ORIGIN + endpoint,
                body_path,
                headers={**self.headers, "Content-Type": "application/json"},
                allowed_origins=self.api_origins,
                expected=(201,),
                retryable=True,
            )
            return expect_dict(decode_bounded_json(payload, dict, "GitHub blob"), "blob")
        finally:
            with contextlib.suppress(FileNotFoundError):
                body_path.unlink()

    def authenticated_asset_sha256(
        self, owner: str, repo: str, asset_id: int, expected_bytes: int
    ) -> tuple[int, str]:
        endpoint = f"/repos/{owner}/{repo}/releases/assets/{asset_id}"
        url = GITHUB_API_ORIGIN + endpoint
        validate_origin(url, self.api_origins)
        opener = urllib.request.build_opener(NoRedirectHandler())
        for attempt in range(5):
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    **self.headers,
                    "Accept": "application/octet-stream",
                },
                method="GET",
            )
            try:
                response = opener.open(request, timeout=300)
            except urllib.error.HTTPError as exc:
                if exc.code == 302:
                    location = exc.headers.get("Location")
                    if not location:
                        raise PublicationError("GitHub asset redirect omitted Location") from None
                    location = urllib.parse.urljoin(url, location)
                    origin(location)
                    size, digest, _final_url = stream_sha256(
                        location,
                        expected_bytes=expected_bytes,
                        retryable=True,
                        follow_redirects=True,
                    )
                    return size, digest
                error_headers = {
                    key.lower(): value for key, value in exc.headers.items()
                }
                if retryable_http_status(exc.code, error_headers) and attempt < 4:
                    time.sleep(
                        backoff_seconds(
                            attempt,
                            error_headers.get("retry-after"),
                            error_headers.get("x-ratelimit-reset"),
                        )
                    )
                    continue
                raise PublicationError(f"GitHub asset download HTTP {exc.code}") from None
            except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
                if attempt < 4:
                    time.sleep(backoff_seconds(attempt))
                    continue
                raise PublicationError(f"GitHub asset download failed: {exc}") from None
            with response:
                if response.status != 200:
                    raise PublicationError(f"GitHub asset download HTTP {response.status}")
                declared = response.headers.get("Content-Length")
                if declared:
                    try:
                        declared_size = int(declared)
                    except (TypeError, ValueError):
                        raise PublicationError("GitHub asset Content-Length is malformed") from None
                    if declared_size != expected_bytes:
                        raise PublicationError("GitHub asset Content-Length differs")
                digest = hashlib.sha256()
                size = 0
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    size += len(block)
                    if size > expected_bytes:
                        raise PublicationError("GitHub asset exceeds expected bytes")
                    digest.update(block)
                if size != expected_bytes:
                    raise PublicationError("GitHub asset byte count differs")
                return size, digest.hexdigest()
        raise PublicationError("unreachable GitHub asset retry state")


class ZenodoClient:
    origins = {origin(ZENODO_ORIGIN)}

    def __init__(self, token: str):
        self.headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def request(
        self,
        method: str,
        endpoint_or_url: str,
        *,
        body: Any | None = None,
        expected_type: type | None = dict,
        expected: Sequence[int] = (200,),
        retryable: bool | None = None,
    ) -> tuple[int, dict[str, str], Any]:
        url = (
            endpoint_or_url
            if endpoint_or_url.startswith("https://")
            else ZENODO_ORIGIN + "/api" + endpoint_or_url
        )
        validate_origin(url, self.origins)
        payload = None if body is None else canonical_bytes(body)
        headers = dict(self.headers)
        if body is not None:
            headers["Content-Type"] = "application/json"
        if retryable is None:
            retryable = method in {"GET", "HEAD", "PUT", "PATCH", "DELETE"}
        status, response_headers, response_payload, _url = http_bytes(
            method,
            url,
            headers=headers,
            body=payload,
            expected=expected,
            allowed_origins=self.origins,
            retryable=retryable,
            timeout=300,
        )
        value = (
            None
            if expected_type is None
            else decode_bounded_json(response_payload, expected_type, endpoint_or_url)
        )
        return status, response_headers, value

    def upload(self, bucket_url: str, path: Path) -> dict[str, Any]:
        validate_origin(bucket_url, self.origins)
        _status, _headers, payload = stream_request(
            "PUT",
            bucket_url,
            path,
            headers={**self.headers, "Content-Type": "application/octet-stream"},
            allowed_origins=self.origins,
            expected=(200, 201),
            retryable=True,
        )
        return expect_dict(decode_bounded_json(payload, dict, "Zenodo upload"), "upload")

    def content_sha256(self, url: str, expected_bytes: int) -> tuple[int, str]:
        size, digest, _final = stream_sha256(
            url,
            headers=self.headers,
            allowed_origins=self.origins,
            expected_bytes=expected_bytes,
            retryable=True,
        )
        return size, digest


def github_client(plan: dict[str, Any]) -> tuple[GitHubClient, dict[str, Any]]:
    owner = plan["github"]["owner"]
    candidates = credential_candidates(plan, "github")
    candidates.sort(key=lambda value: not value.startswith("ghp_"))
    for token in candidates:
        client = GitHubClient(token)
        try:
            _status, headers, value = client.request("GET", "/user")
        except PublicationError:
            continue
        user = expect_dict(value, "GitHub user")
        if user.get("login") == owner:
            return client, {
                "login": owner,
                "token_kind": "classic" if token.startswith("ghp_") else "fine-grained",
                "oauth_scopes_present": bool(headers.get("x-oauth-scopes")),
            }
    raise PublicationError("no GitHub token candidate authenticates as the configured owner")


def zenodo_client(plan: dict[str, Any]) -> ZenodoClient:
    for token in credential_candidates(plan, "zenodo"):
        client = ZenodoClient(token)
        try:
            _status, _headers, value = client.request(
                "GET", "/deposit/depositions?size=1&page=1", expected_type=list
            )
            expect_list(value, "Zenodo authentication probe")
            return client
        except PublicationError:
            continue
    raise PublicationError("no Zenodo token candidate authenticates successfully")


def github_optional(
    client: GitHubClient, endpoint: str, *, expected_type: type = dict
) -> tuple[int, Any | None]:
    try:
        status, _headers, value = client.request(
            "GET", endpoint, expected_type=expected_type
        )
        return status, value
    except PublicationError as exc:
        if str(exc).startswith("HTTP 404 ") or str(exc).startswith("HTTP 409 "):
            return 404, None
        raise


def github_paginated(client: GitHubClient, endpoint: str) -> list[dict[str, Any]]:
    separator = "&" if "?" in endpoint else "?"
    rows: list[dict[str, Any]] = []
    for page in range(1, MAX_PAGES + 1):
        page_endpoint = f"{endpoint}{separator}per_page=100&page={page}"
        _status, _headers, value = client.request(
            "GET", page_endpoint, expected_type=list
        )
        batch = expect_list(value, page_endpoint)
        for index, row in enumerate(batch):
            rows.append(expect_dict(row, f"{page_endpoint}[{index}]"))
        if len(batch) < 100:
            return rows
    raise PublicationError("GitHub pagination exceeded the bounded page limit")


def poll_github_optional(
    client: Any,
    endpoint: str,
    *,
    expected_type: type = dict,
    attempts: int = 8,
) -> Any | None:
    for attempt in range(attempts):
        _status, value = github_optional(client, endpoint, expected_type=expected_type)
        if value is not None:
            return value
        if attempt + 1 < attempts:
            time.sleep(backoff_seconds(min(attempt, 4)))
    return None


def zenodo_paginated(client: ZenodoClient, query: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    encoded = urllib.parse.quote(query)
    for page in range(1, MAX_PAGES + 1):
        endpoint = (
            f"/deposit/depositions?q={encoded}&size=100&page={page}&sort=mostrecent"
        )
        _status, _headers, value = client.request("GET", endpoint, expected_type=list)
        batch = expect_list(value, endpoint)
        for index, row in enumerate(batch):
            rows.append(expect_dict(row, f"{endpoint}[{index}]"))
        if len(batch) < 100:
            return rows
    raise PublicationError("Zenodo pagination exceeded the bounded page limit")


def anonymous_json(url: str, expected_type: type = dict) -> Any:
    _status, _headers, payload, _final = http_bytes(
        "GET", url, headers={"Accept": "application/json"}, expected=(200,), retryable=True
    )
    return decode_bounded_json(payload, expected_type, url)


def zenodo_public_paginated(query: str) -> list[dict[str, Any]]:
    """Return a bounded anonymous Zenodo record search without credentials."""

    rows: list[dict[str, Any]] = []
    for page in range(1, MAX_PAGES + 1):
        parameters = urllib.parse.urlencode(
            {
                "q": query,
                "size": ZENODO_PUBLIC_PAGE_SIZE,
                "page": page,
                "sort": "mostrecent",
            }
        )
        value = expect_dict(
            anonymous_json(f"{ZENODO_ORIGIN}/api/records?{parameters}"),
            "Zenodo public search",
        )
        hits = expect_dict(value.get("hits"), "Zenodo public hits")
        batch = expect_list(hits.get("hits"), "Zenodo public hit rows")
        for index, row in enumerate(batch):
            rows.append(expect_dict(row, f"Zenodo public hit[{index}]"))
        if len(batch) < ZENODO_PUBLIC_PAGE_SIZE:
            return rows
    raise PublicationError("Zenodo public pagination exceeded the bounded page limit")


def github_remote_preflight(plan: dict[str, Any]) -> dict[str, Any]:
    github, authentication = github_client(plan)
    owner = plan["github"]["owner"]
    repo = plan["github"]["repository"]
    tag = plan["release"]["tag"]
    base = f"/repos/{owner}/{repo}"
    repo_status, repository = github_optional(github, base)
    releases: list[dict[str, Any]] = []
    exact_release: dict[str, Any] | None = None
    pages_status = 404
    pages = None
    if repository is not None:
        releases = github_paginated(github, base + "/releases")
        matches = [item for item in releases if item.get("tag_name") == tag]
        if len(matches) > 1:
            raise PublicationError("multiple GitHub releases use the exact target tag")
        exact_release = matches[0] if matches else None
        pages_status, pages = github_optional(github, base + "/pages")
    return {
        "authenticated_login": authentication["login"],
        "token_kind": authentication["token_kind"],
        "repository_status": repo_status,
        "repository": repository,
        "release_count": len(releases),
        "exact_tag_release": exact_release,
        "pages_status": pages_status,
        "pages": pages,
    }


def zenodo_remote_preflight(
    plan: dict[str, Any], binding: dict[str, str]
) -> dict[str, Any]:
    """Inspect only Zenodo state; this function has no GitHub dependency."""

    zenodo = zenodo_client(plan)
    exact_deposits = exact_zenodo_depositions(zenodo, plan, binding)
    guarded = zenodo_title_version_guard(zenodo, plan, binding)
    lineage = discover_zenodo_lineage(zenodo, plan, binding)
    state = load_state(binding)
    pinned = validate_pinned_zenodo_lineage(zenodo, plan, state)
    if "zenodo_conceptrecid" in state and lineage.get("status") == "absent":
        raise PublicationError("stored Zenodo lineage disappeared during preflight")
    if "zenodo_conceptrecid" in state and lineage.get("conceptrecid") not in {
        None,
        state["zenodo_conceptrecid"],
    }:
        raise PublicationError("stored and discovered Zenodo concepts differ during preflight")
    exact_ids = {
        zenodo_record_identity(row, "exact Zenodo deposition")[0]
        for row in exact_deposits
    }
    unexplained_open = set(lineage.get("open_draft_ids", [])) - exact_ids
    resumable_newversion = (
        state.get("zenodo_newversion_phase") in {"requested", "done"}
        and state.get("zenodo_conceptrecid") == lineage.get("conceptrecid")
    )
    if unexplained_open and not resumable_newversion:
        raise PublicationError(
            "the intended Zenodo concept has an unrelated open draft; refusing a new version"
        )
    public_query = urllib.parse.urlencode(
        {"q": f'metadata.description:"{binding["fingerprint"]}"', "size": 25}
    )
    public = expect_dict(
        anonymous_json(f"{ZENODO_ORIGIN}/api/records?{public_query}"),
        "Zenodo public search",
    )
    hits = expect_dict(public.get("hits"), "Zenodo hits")
    return {
        "matching_authenticated_deposition_ids": sorted(exact_ids),
        "matching_public_records": expect_list(hits.get("hits"), "Zenodo public hits"),
        "same_title_version_authenticated_id": (
            guarded.get("id") if guarded is not None else None
        ),
        "lineage": zenodo_lineage_summary(lineage),
        "stored_lineage_validated": pinned is not None,
        "newversion_resume_pending": bool(unexplained_open and resumable_newversion),
    }


def remote_preflight(plan: dict[str, Any], binding: dict[str, str]) -> dict[str, Any]:
    return {
        "github": github_remote_preflight(plan),
        "zenodo": zenodo_remote_preflight(plan, binding),
        "transaction_fingerprint": binding["fingerprint"],
    }


def excluded(path: Path, plan: dict[str, Any], root: Path) -> bool:
    settings = expect_dict(plan["repository_snapshot"], "repository_snapshot")
    names = expect_list(settings.get("exclude_names"), "exclude_names")
    suffixes = expect_list(settings.get("exclude_suffixes"), "exclude_suffixes")
    relative_parts = Path(lexical_relative(path, root)).parts
    return any(part in names for part in relative_parts) or any(
        path.name.endswith(str(suffix)) for suffix in suffixes
    )


def expand_includes(root: Path, includes: Iterable[str], plan: dict[str, Any]) -> list[Path]:
    files: dict[str, Path] = {}
    for relative_value in includes:
        relative = validate_relative_name(relative_value, "include")
        target = root / relative
        ensure_under(target, root)
        if not target.exists():
            raise PublicationError(f"required bounded path is missing: {relative}")
        if target.is_symlink():
            raise PublicationError(f"symbolic link rejected from staged include: {relative}")
        candidates: Iterable[Path] = [target] if target.is_file() else target.rglob("*")
        for candidate in candidates:
            if not candidate.is_file() or excluded(candidate, plan, root):
                continue
            if candidate.is_symlink():
                raise PublicationError(f"symbolic links are not allowed in staged closure: {candidate}")
            ensure_under(candidate, root)
            key = lexical_relative(candidate, root)
            files[key] = candidate
    return [files[key] for key in sorted(files)]


def copy_stable(source: Path, destination: Path) -> dict[str, Any]:
    if source.is_symlink() or destination.is_symlink():
        raise PublicationError(f"symbolic link rejected during stable copy: {source}")
    before = source.stat()
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with source.open("rb") as input_stream, destination.open("wb") as output_stream:
        while True:
            block = input_stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
            output_stream.write(block)
        output_stream.flush()
        os.fsync(output_stream.fileno())
    after = source.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or destination.stat().st_size != before.st_size
    ):
        raise PublicationError(f"live input changed while staging: {source}")
    destination_digest = sha256_file(destination)
    if destination_digest != digest.hexdigest():
        raise PublicationError(f"staged copy hash mismatch: {source}")
    return {
        "bytes": destination.stat().st_size,
        "sha256": destination_digest,
        "git_blob_sha": git_blob_sha_file(destination),
    }


def inventory_rows(root: Path, *, omit: set[str] | None = None) -> list[dict[str, Any]]:
    omitted = omit or set()
    rows: list[dict[str, Any]] = []
    all_entries = list(root.rglob("*"))
    for entry in all_entries:
        if entry.is_symlink():
            raise PublicationError(f"symbolic link rejected from immutable inventory: {entry}")
    for path in sorted((item for item in all_entries if item.is_file()), key=lambda p: lexical_relative(p, root)):
        if path.is_symlink():
            raise PublicationError(f"symbolic link rejected from immutable inventory: {path}")
        ensure_under(path, root)
        relative = lexical_relative(path, root)
        if relative in omitted:
            continue
        rows.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "git_blob_sha": git_blob_sha_file(path),
            }
        )
    return rows


def inventory_digest(rows: list[dict[str, Any]]) -> str:
    return sha256_bytes(canonical_bytes(rows))


def verify_inventory(stage: Path, binding: dict[str, str]) -> dict[str, Any]:
    manifest_path = stage / "inventory.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise PublicationError("immutable inventory manifest is missing or linked")
    manifest = load_json(manifest_path)
    if manifest.get("schema_version") != "hefferon-id-immutable-inventory-v1":
        raise PublicationError("immutable inventory schema mismatch")
    if manifest.get("binding") != binding:
        raise PublicationError("immutable inventory binding mismatch")
    stage_name = manifest.get("stage")
    base_keys = {
        "schema_version",
        "stage",
        "binding",
        "inventory_sha256",
        "file_count",
        "files",
        "readiness",
    }
    if stage_name == "base":
        require_exact_keys(manifest, base_keys, "base immutable inventory")
    elif stage_name == "final":
        require_exact_keys(
            manifest,
            base_keys | {"doi", "artifacts", "artifact_set_sha256"},
            "final immutable inventory",
        )
    else:
        raise PublicationError("immutable inventory stage marker is invalid")
    expect_dict(manifest.get("readiness"), "inventory.readiness")
    rows = expect_list(manifest.get("files"), "inventory.files")
    if require_integer(manifest, "file_count", "inventory") != len(rows):
        raise PublicationError("immutable inventory file count differs")
    normalized: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, value in enumerate(rows):
        row = expect_dict(value, f"inventory.files[{index}]")
        require_exact_keys(
            row,
            {"path", "bytes", "sha256", "git_blob_sha"},
            f"inventory.files[{index}]",
        )
        relative = validate_relative_name(require_string(row, "path", "inventory row"), "inventory row")
        if relative in names:
            raise PublicationError("immutable inventory contains duplicate paths")
        names.add(relative)
        path = ensure_under(stage / relative, stage)
        if not path.is_file():
            raise PublicationError(f"immutable inventory file is missing: {relative}")
        expected_bytes = require_integer(row, "bytes", "inventory row")
        if expected_bytes < 0:
            raise PublicationError("immutable inventory byte count is negative")
        expected_sha = require_sha(row.get("sha256"), "inventory row.sha256")
        expected_git = require_sha(
            row.get("git_blob_sha"), "inventory row.git_blob_sha", algorithm="sha1"
        )
        if path.is_symlink():
            raise PublicationError(f"immutable inventory contains a symbolic link: {relative}")
        if (
            path.stat().st_size != expected_bytes
            or sha256_file(path) != expected_sha
            or git_blob_sha_file(path) != expected_git
        ):
            raise PublicationError(f"immutable inventory byte drift: {relative}")
        normalized.append(
            {
                "path": relative,
                "bytes": expected_bytes,
                "sha256": expected_sha,
                "git_blob_sha": expected_git,
            }
        )
    stage_entries = list(stage.rglob("*"))
    if any(path.is_symlink() for path in stage_entries):
        raise PublicationError("immutable inventory closure contains a symbolic link")
    actual = {
        lexical_relative(path, stage)
        for path in stage_entries
        if path.is_file() and lexical_relative(path, stage) != "inventory.json"
    }
    if actual != names:
        missing = sorted(names - actual)[:5]
        extra = sorted(actual - names)[:5]
        raise PublicationError(f"immutable inventory closure drift; missing={missing}, extra={extra}")
    digest = inventory_digest(normalized)
    if manifest.get("inventory_sha256") != digest:
        raise PublicationError("immutable inventory digest mismatch")
    return manifest


def verify_snapshot_copy(base_manifest: dict[str, Any], snapshot: Path) -> None:
    expected: dict[str, tuple[int, str, str]] = {}
    for value in expect_list(base_manifest.get("files"), "base inventory.files"):
        row = expect_dict(value, "base inventory row")
        relative = require_string(row, "path", "base inventory row")
        if not relative.startswith("snapshot/"):
            raise PublicationError("base inventory contains a file outside snapshot/")
        inner = validate_relative_name(relative.removeprefix("snapshot/"), "base snapshot path")
        if inner in expected:
            raise PublicationError("base snapshot inventory contains duplicate paths")
        expected[inner] = (
            require_integer(row, "bytes", "base inventory row"),
            require_sha(row.get("sha256"), "base inventory row.sha256"),
            require_sha(row.get("git_blob_sha"), "base inventory row.git_blob_sha", algorithm="sha1"),
        )
    actual_paths = inventory_rows(snapshot)
    actual = {
        row["path"]: (row["bytes"], row["sha256"], row["git_blob_sha"])
        for row in actual_paths
    }
    if actual != expected:
        raise PublicationError("copied final snapshot differs from the frozen base inventory")


def pin_inventory(
    state: dict[str, Any],
    key: str,
    manifest: dict[str, Any],
    stage: Path,
) -> None:
    digest = require_sha(manifest.get("inventory_sha256"), f"{key} inventory SHA-256")
    prior = state.get(key)
    if prior is not None and prior != digest:
        raise PublicationError(f"{key} differs from the transaction's already-pinned inventory")
    manifest_keys = {
        "base_inventory_sha256": "base_manifest_sha256",
        "final_inventory_sha256": "final_manifest_sha256",
    }
    try:
        manifest_key = manifest_keys[key]
    except KeyError:
        raise PublicationError(f"unsupported immutable inventory pin: {key}") from None
    manifest_path = stage / "inventory.json"
    manifest_digest = sha256_file_stable(manifest_path)
    current_manifest = load_json(manifest_path)
    if current_manifest != manifest or sha256_file_stable(manifest_path) != manifest_digest:
        raise PublicationError("immutable inventory manifest changed between verification and pinning")
    prior_manifest = state.get(manifest_key)
    if prior_manifest is not None and prior_manifest != manifest_digest:
        raise PublicationError(
            f"{manifest_key} differs from the transaction's already-pinned manifest"
        )
    state[key] = digest
    state[manifest_key] = manifest_digest


def pin_state_sha256(state: dict[str, Any], key: str, value: Any) -> None:
    digest = require_sha(value, f"state pin {key}")
    prior = state.get(key)
    if prior is not None and prior != digest:
        raise PublicationError(f"{key} differs from the transaction's already-pinned value")
    state[key] = digest


def validate_final_manifest(plan: dict[str, Any], manifest: dict[str, Any], doi: str) -> None:
    if manifest.get("stage") != "final" or manifest.get("doi") != doi:
        raise PublicationError("final immutable inventory stage/DOI binding differs")
    artifacts = expect_list(manifest.get("artifacts"), "final inventory.artifacts")
    if len(artifacts) != require_integer(
        expect_dict(plan["release_assets"], "release_assets"),
        "expected_count",
        "release_assets",
    ):
        raise PublicationError("final immutable artifact count differs from the plan")
    expected_rows: list[dict[str, str]] = []
    for item in plan["reader_pdfs"]:
        expected_rows.append(
            {
                "path": item["release_name"],
                "kind": "reader-pdf",
                "component": item["component"],
            }
        )
    for item in plan["bundles"]:
        expected_rows.append({"path": item["release_name"], "kind": item["kind"]})
    expected_rows.extend(
        [
            {"path": plan["release_assets"]["readme"], "kind": "release-readme"},
            {"path": plan["release_assets"]["manifest"], "kind": "release-manifest"},
            {"path": plan["release_assets"]["checksums"], "kind": "checksums"},
        ]
    )
    names: list[str] = []
    for index, (value, expected_row) in enumerate(zip(artifacts, expected_rows, strict=True)):
        item = expect_dict(value, f"final inventory.artifacts[{index}]")
        common_keys = {"kind", "path", "bytes", "sha256"}
        if expected_row["kind"] == "reader-pdf":
            exact_keys = common_keys | {"component", "pages"}
        elif expected_row["kind"] in {
            "editable-source",
            "modular-backend",
            "provenance-qa",
        }:
            exact_keys = common_keys | {
                "entry_count",
                "uncompressed_bytes",
                "entries_sha256",
            }
        else:
            exact_keys = common_keys
        require_exact_keys(item, exact_keys, f"final inventory.artifacts[{index}]")
        name = validate_basename(require_string(item, "path", "artifact"), "artifact")
        names.append(name)
        if name != expected_row["path"] or item.get("kind") != expected_row["kind"]:
            raise PublicationError("final immutable artifact name/kind/order closure differs")
        if "component" in expected_row and item.get("component") != expected_row["component"]:
            raise PublicationError("final immutable reader-PDF component closure differs")
        if require_integer(item, "bytes", "artifact") <= 0:
            raise PublicationError("final immutable artifact has a nonpositive byte count")
        require_sha(item.get("sha256"), "artifact.sha256")
        if expected_row["kind"] == "reader-pdf" and require_integer(
            item, "pages", "artifact"
        ) <= 0:
            raise PublicationError("final immutable reader PDF has no pages")
        if "entry_count" in item:
            if require_integer(item, "entry_count", "artifact") <= 0:
                raise PublicationError("final immutable ZIP has no entries")
            if require_integer(item, "uncompressed_bytes", "artifact") <= 0:
                raise PublicationError("final immutable ZIP has no uncompressed bytes")
            require_sha(item.get("entries_sha256"), "artifact.entries_sha256")
    if len(names) != len({name.casefold() for name in names}):
        raise PublicationError("final immutable artifact names are not unique")
    expected_digest = sha256_bytes(canonical_bytes(artifacts))
    if manifest.get("artifact_set_sha256") != expected_digest:
        raise PublicationError("final immutable artifact-set digest differs")


def run_backend_validator(plan: dict[str, Any], root: Path) -> dict[str, Any]:
    validator = ensure_under(root / plan["qa"]["backend_validator"], root)
    if not validator.is_file():
        raise PublicationError("backend final validator is missing")
    try:
        completed = subprocess.run(
            [sys.executable, "-B", str(validator), "--require-final-build"],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=900,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PublicationError(f"backend final validator could not complete: {exc}") from None
    if len(completed.stdout.encode("utf-8")) > MAX_JSON_RESPONSE:
        raise PublicationError("backend final validator output exceeds the bounded JSON limit")
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()[-2500:]
        raise PublicationError(f"backend final validator failed: {detail}")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise PublicationError(f"backend validator returned invalid JSON: {exc}") from None
    result = expect_dict(result, "backend validator")
    if result.get("status") != "pass" or result.get("final_build_required") is not True:
        raise PublicationError("backend final validator did not close the final-build gate")
    return result


def canonical_source_tree(root: Path) -> tuple[list[dict[str, Any]], str]:
    if not root.is_dir() or root.is_symlink():
        raise PublicationError("canonical translated source root is missing or linked")
    entries = list(root.rglob("*"))
    if any(entry.is_symlink() for entry in entries):
        raise PublicationError("canonical translated source contains a symbolic link")
    rows: list[dict[str, Any]] = []
    # Match tools/build_hefferon_id.py's Path ordering exactly. On Windows this
    # is case-normalized and differs from a case-sensitive relative-string sort
    # when metadata files such as README.md share a tree with directories.
    for path in sorted(entry for entry in entries if entry.is_file()):
        ensure_under(path, root)
        rows.append(
            {
                "path": lexical_relative(path, root),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    payload = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return rows, sha256_bytes(payload)


def validate_live_build_inputs(root: Path, report: dict[str, Any]) -> dict[str, Any]:
    """Rehash every repository input needed to reproduce the matched build."""
    report_tools = expect_dict(report.get("build_tools"), "build_report.build_tools")
    if set(report_tools) != set(EXPECTED_BUILD_TOOL_PATHS):
        raise PublicationError("build-report tool path closure differs")
    tool_receipts: dict[str, dict[str, Any]] = {}
    for name, relative in EXPECTED_BUILD_TOOL_PATHS.items():
        context = f"build_report.build_tools.{name}"
        details = expect_dict(report_tools.get(name), context)
        require_exact_keys(details, {"path", "bytes", "sha256"}, context)
        recorded_path = require_string(details, "path", context).replace("\\", "/")
        if not recorded_path.endswith("/" + relative):
            raise PublicationError(f"{context}.path does not identify {relative}")
        path = ensure_under(root / relative, root)
        if not path.is_file() or path.is_symlink():
            raise PublicationError(f"live build tool is missing or linked: {relative}")
        byte_count = require_integer(details, "bytes", context)
        expected_sha = require_sha(details.get("sha256"), f"{context}.sha256")
        if (
            byte_count != path.stat().st_size
            or expected_sha != sha256_file_stable(path)
        ):
            raise PublicationError(f"live build tool differs from matched build: {relative}")
        tool_receipts[name] = {
            "path": relative,
            "bytes": byte_count,
            "sha256": expected_sha,
        }

    authority_receipts: dict[str, dict[str, Any]] = {}
    for report_key, relative in EXPECTED_AUTHORITY_BUILD_INPUTS.items():
        context = f"build_report.{report_key}"
        details = expect_dict(report.get(report_key), context)
        require_exact_keys(details, {"path", "sha256"}, context)
        recorded_path = require_string(details, "path", context).replace("\\", "/")
        if not recorded_path.endswith("/" + relative):
            raise PublicationError(f"{context}.path does not identify {relative}")
        path = ensure_under(root / relative, root)
        if not path.is_file() or path.is_symlink():
            raise PublicationError(f"authority build input is missing or linked: {relative}")
        expected_sha = require_sha(details.get("sha256"), f"{context}.sha256")
        if sha256_file_stable(path) != expected_sha:
            raise PublicationError(
                f"authority build input differs from matched build: {relative}"
            )
        authority_receipts[report_key] = {
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": expected_sha,
        }

    closure_root = ensure_under(root / "tools/pdftex-font-closure", root)
    closure_rows, closure_tree = canonical_source_tree(closure_root)
    closure_bytes = sum(int(row["bytes"]) for row in closure_rows)
    if (
        len(closure_rows) != EXPECTED_PDFTEX_FONT_CLOSURE_FILE_COUNT
        or closure_bytes != EXPECTED_PDFTEX_FONT_CLOSURE_BYTES
        or closure_tree != EXPECTED_PDFTEX_FONT_CLOSURE_TREE_SHA256
    ):
        raise PublicationError("live pdfTeX font closure identity differs")
    closure_report = expect_dict(
        report.get("pdftex_font_closure"), "build_report.pdftex_font_closure"
    )
    if (
        require_integer(closure_report, "file_count", "pdftex_font_closure")
        != len(closure_rows)
        or require_integer(closure_report, "bytes", "pdftex_font_closure")
        != closure_bytes
        or require_sha(
            closure_report.get("tree_sha256"), "pdftex_font_closure.tree_sha256"
        )
        != closure_tree
    ):
        raise PublicationError("live pdfTeX font closure differs from matched build")
    for report_prefix, relative in (
        ("sha256sums", "SHA256SUMS"),
        ("third_party_notices", "THIRD_PARTY_NOTICES.json"),
        ("readme", "README.md"),
    ):
        path = closure_root / relative
        if (
            require_integer(
                closure_report,
                f"{report_prefix}_bytes",
                "pdftex_font_closure",
            )
            != path.stat().st_size
            or require_sha(
                closure_report.get(f"{report_prefix}_sha256"),
                f"pdftex_font_closure.{report_prefix}_sha256",
            )
            != sha256_file_stable(path)
        ):
            raise PublicationError(
                f"live pdfTeX font metadata differs from matched build: {relative}"
            )

    dependency_report = expect_dict(
        report.get("pdftex_font_dependencies"),
        "build_report.pdftex_font_dependencies",
    )
    if set(dependency_report) != EXPECTED_PDFTEX_FONT_DEPENDENCY_NAMES:
        raise PublicationError("matched-build pdfTeX font dependency names differ")
    dependency_receipts: dict[str, dict[str, Any]] = {}
    dependency_bytes = 0
    for name in sorted(EXPECTED_PDFTEX_FONT_DEPENDENCY_NAMES):
        suffix = Path(name).suffix.lower()
        if suffix == ".map":
            bucket = "maps"
        elif suffix == ".enc":
            bucket = "encodings"
        elif suffix in {".pfb", ".pfa"}:
            bucket = "type1"
        else:
            raise PublicationError(f"unsupported expected font dependency: {name}")
        relative = f"tools/pdftex-font-closure/{bucket}/{name}"
        path = ensure_under(root / relative, root)
        details = expect_dict(
            dependency_report.get(name),
            f"build_report.pdftex_font_dependencies.{name}",
        )
        require_exact_keys(
            details,
            {"source_path", "source_project_path", "staged_path", "bytes", "sha256"},
            f"build_report.pdftex_font_dependencies.{name}",
        )
        if details.get("source_project_path") != relative:
            raise PublicationError(f"font dependency project path differs: {name}")
        byte_count = require_integer(details, "bytes", f"font dependency {name}")
        expected_sha = require_sha(details.get("sha256"), f"font dependency {name}.sha256")
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != byte_count
            or sha256_file_stable(path) != expected_sha
        ):
            raise PublicationError(f"live font dependency differs from matched build: {name}")
        dependency_bytes += byte_count
        dependency_receipts[name] = {
            "path": relative,
            "bytes": byte_count,
            "sha256": expected_sha,
        }
    if dependency_bytes != EXPECTED_PDFTEX_FONT_DEPENDENCY_BYTES:
        raise PublicationError("live pdfTeX font dependency byte total differs")

    return {
        "build_tools": tool_receipts,
        "authority_inputs": authority_receipts,
        "pdftex_font_closure": {
            "file_count": len(closure_rows),
            "bytes": closure_bytes,
            "tree_sha256": closure_tree,
            "dependency_count": len(dependency_receipts),
            "dependency_bytes": dependency_bytes,
        },
    }


def validate_all_page_render_manifest(
    plan: dict[str, Any],
    root: Path,
    report: dict[str, Any],
    report_pdfs: dict[str, Any],
) -> dict[str, Any]:
    relative = plan["qa"]["all_page_render_manifest"]
    path = ensure_under(root / relative, root)
    payload = path.read_bytes()
    rows = load_json(path, expected=list)
    summary = expect_dict(
        report.get("all_page_render_manifest"),
        "build_report.all_page_render_manifest",
    )
    require_exact_keys(
        summary,
        {"path", "count", "bytes_rendered", "manifest_bytes", "manifest_sha256"},
        "build_report.all_page_render_manifest",
    )
    reported_path = require_string(
        summary, "path", "build_report.all_page_render_manifest"
    ).replace("\\", "/")
    if reported_path != relative and not reported_path.endswith("/" + relative):
        raise PublicationError("build-report render-manifest path is not the planned path")
    if require_integer(summary, "manifest_bytes", "all_page_render_manifest") != len(payload):
        raise PublicationError("all-page render-manifest byte count differs")
    if require_sha(
        summary.get("manifest_sha256"), "all_page_render_manifest.manifest_sha256"
    ) != sha256_bytes(payload):
        raise PublicationError("all-page render-manifest SHA-256 differs")
    if require_integer(summary, "count", "all_page_render_manifest") != len(rows):
        raise PublicationError("all-page render-manifest row count differs")

    expected_jobs = ("book", "jhanswer", "lab")
    grouped: dict[str, list[dict[str, Any]]] = {job: [] for job in expected_jobs}
    total_rendered_bytes = 0
    required_row_keys = {
        "pdf",
        "page",
        "path",
        "bytes",
        "sha256",
        "width",
        "height",
        "ink_fraction",
        "mean_luminance",
        "fully_white",
    }
    for index, row_value in enumerate(rows):
        row = expect_dict(row_value, f"all_page_render_manifest[{index}]")
        require_exact_keys(row, required_row_keys, f"all_page_render_manifest[{index}]")
        job = require_string(row, "pdf", f"render row {index}")
        if job not in grouped:
            raise PublicationError(f"render row {index} has an unknown PDF key")
        page = require_integer(row, "page", f"render row {index}")
        rendered_bytes = require_integer(row, "bytes", f"render row {index}")
        width = require_integer(row, "width", f"render row {index}")
        height = require_integer(row, "height", f"render row {index}")
        if page <= 0 or rendered_bytes < 64 or width <= 0 or height <= 0:
            raise PublicationError(f"render row {index} has invalid positive metrics")
        require_sha(row.get("sha256"), f"render row {index}.sha256")
        render_path = require_string(row, "path", f"render row {index}")
        validate_relative_name(render_path, f"render row {index}.path")
        ink = row.get("ink_fraction")
        luminance = row.get("mean_luminance")
        if (
            not isinstance(ink, (int, float))
            or isinstance(ink, bool)
            or not 0 <= ink <= 1
            or not isinstance(luminance, (int, float))
            or isinstance(luminance, bool)
            or not 10 <= luminance <= 255
        ):
            raise PublicationError(f"render row {index} has invalid image metrics")
        fully_white = require_boolean(row, "fully_white", f"render row {index}")
        if fully_white is not (ink == 0):
            raise PublicationError(f"render row {index} has inconsistent white-page metrics")
        grouped[job].append(row)
        total_rendered_bytes += rendered_bytes

    if require_integer(summary, "bytes_rendered", "all_page_render_manifest") != total_rendered_bytes:
        raise PublicationError("all-page rendered-byte total differs")

    expected_total_pages = 0
    for job in expected_jobs:
        details = expect_dict(report_pdfs.get(job), f"build_report.pdfs.{job}")
        pages = require_integer(details, "pages", f"build_report.pdfs.{job}")
        expected_total_pages += pages
        job_rows = grouped[job]
        if [row["page"] for row in job_rows] != list(range(1, pages + 1)):
            raise PublicationError(f"all-page render sequence is incomplete for {job}")
        page_width = len(str(pages))
        for row in job_rows:
            expected_path = (
                f"tmp/pdfs/hefferon_id/{job}/"
                f"page-{row['page']:0{page_width}d}.png"
            )
            if row["path"] != expected_path:
                raise PublicationError(f"all-page render path differs for {job} page {row['page']}")
        render_details = expect_dict(
            details.get("all_page_renders"), f"build_report.pdfs.{job}.all_page_renders"
        )
        if require_integer(render_details, "count", f"{job}.all_page_renders") != pages:
            raise PublicationError(f"build-report render count differs for {job}")
        if require_integer(render_details, "bytes", f"{job}.all_page_renders") != sum(
            int(row["bytes"]) for row in job_rows
        ):
            raise PublicationError(f"build-report rendered bytes differ for {job}")
        canonical = json.dumps(
            job_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if require_sha(
            render_details.get("canonical_sha256"),
            f"{job}.all_page_renders.canonical_sha256",
        ) != sha256_bytes(canonical):
            raise PublicationError(f"build-report render digest differs for {job}")

    if len(rows) != expected_total_pages:
        raise PublicationError("all-page render total differs from the three PDF page counts")
    return {
        "path": relative,
        "count": len(rows),
        "bytes_rendered": total_rendered_bytes,
        "manifest_bytes": len(payload),
        "manifest_sha256": sha256_bytes(payload),
        "pdf_page_counts": {job: len(grouped[job]) for job in expected_jobs},
    }


def load_qa_artifact(
    root: Path, relative: str, context: str
) -> tuple[Path, bytes, dict[str, Any]]:
    validate_relative_name(relative, context)
    path = ensure_under(root / relative, root)
    if not path.is_file() or path.is_symlink():
        raise PublicationError(f"{context} is missing, linked, or not a regular file")
    payload = path.read_bytes()
    if len(payload) > MAX_JSON_RESPONSE:
        raise PublicationError(f"{context} exceeds the bounded JSON limit")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicationError(f"invalid JSON in {context}: {exc}") from None
    return path, payload, expect_dict(value, context)


def validate_final_pdf_qa(
    plan: dict[str, Any],
    root: Path,
    report: dict[str, Any],
    report_pdfs: dict[str, Any],
    all_page_renders: dict[str, Any],
) -> dict[str, Any]:
    """Bind the generated audit to the exact build without pretending human review is done."""
    relative = plan["qa"]["final_pdf_qa"]
    _path, payload, audit = load_qa_artifact(root, relative, "final PDF QA report")
    if audit.get("schema_version") != "hefferon-id-final-pdf-qa-v1":
        raise PublicationError("unsupported final PDF QA schema")

    scope = expect_dict(audit.get("scope"), "final_pdf_qa.scope")
    if require_string(scope, "output", "final_pdf_qa.scope") != relative:
        raise PublicationError("final PDF QA output path differs from the plan")

    build_relative = plan["qa"]["build_report"]
    build_path = ensure_under(root / build_relative, root)
    build_payload = build_path.read_bytes()
    bindings = expect_dict(audit.get("bindings"), "final_pdf_qa.bindings")
    build_binding = expect_dict(
        bindings.get("build_report"), "final_pdf_qa.bindings.build_report"
    )
    require_exact_keys(
        build_binding,
        {
            "path",
            "bytes",
            "sha256",
            "status",
            "source_tree_sha256",
            "qa_summary",
            "reproducibility",
        },
        "final_pdf_qa.bindings.build_report",
    )
    if (
        require_string(build_binding, "path", "final_pdf_qa.build_report")
        != build_relative
        or require_integer(build_binding, "bytes", "final_pdf_qa.build_report")
        != len(build_payload)
        or require_sha(build_binding.get("sha256"), "final_pdf_qa.build_report.sha256")
        != sha256_bytes(build_payload)
        or build_binding.get("status") != report.get("status")
        or build_binding.get("source_tree_sha256")
        != expect_dict(report.get("source"), "build_report.source").get("tree_sha256")
        or build_binding.get("qa_summary") != report.get("qa_summary")
        or build_binding.get("reproducibility") != report.get("reproducibility")
    ):
        raise PublicationError("final PDF QA build-report binding differs")

    render_relative = plan["qa"]["all_page_render_manifest"]
    render_path = ensure_under(root / render_relative, root)
    render_payload = render_path.read_bytes()
    render_rows = load_json(render_path, expected=list)
    render_binding = expect_dict(
        bindings.get("all_page_render_manifest"),
        "final_pdf_qa.bindings.all_page_render_manifest",
    )
    require_exact_keys(
        render_binding,
        {"path", "bytes", "sha256"},
        "final_pdf_qa.bindings.all_page_render_manifest",
    )
    if (
        require_string(render_binding, "path", "final_pdf_qa.render_manifest")
        != render_relative
        or require_integer(render_binding, "bytes", "final_pdf_qa.render_manifest")
        != len(render_payload)
        or require_sha(render_binding.get("sha256"), "final_pdf_qa.render_manifest.sha256")
        != sha256_bytes(render_payload)
        or len(render_rows) != require_integer(all_page_renders, "count", "all_page_renders")
    ):
        raise PublicationError("final PDF QA render-manifest binding differs")

    job_to_source = {
        {"textbook": "book", "worked-answers": "jhanswer", "sage-lab": "lab"}[
            item["component"]
        ]: item["source"]
        for item in plan["reader_pdfs"]
    }
    audit_pdfs = expect_dict(bindings.get("pdfs"), "final_pdf_qa.bindings.pdfs")
    if set(audit_pdfs) != {"book", "jhanswer", "lab"}:
        raise PublicationError("final PDF QA PDF binding closure differs")
    page_counts: dict[str, int] = {}
    for job in ("book", "jhanswer", "lab"):
        context = f"final_pdf_qa.bindings.pdfs.{job}"
        binding = expect_dict(audit_pdfs.get(job), context)
        require_exact_keys(
            binding,
            {
                "path",
                "bytes",
                "sha256",
                "pages",
                "build_report_bytes_match",
                "build_report_sha256_match",
                "build_report_pages_match",
            },
            context,
        )
        details = expect_dict(report_pdfs.get(job), f"build_report.pdfs.{job}")
        pdf_path = ensure_under(root / job_to_source[job], root)
        expected_bytes = require_integer(details, "bytes", f"build_report.pdfs.{job}")
        expected_sha = require_sha(details.get("sha256"), f"build_report.pdfs.{job}.sha256")
        pages = require_integer(details, "pages", f"build_report.pdfs.{job}")
        page_counts[job] = pages
        if (
            binding.get("path") != job_to_source[job]
            or require_integer(binding, "bytes", context) != expected_bytes
            or require_sha(binding.get("sha256"), f"{context}.sha256") != expected_sha
            or require_integer(binding, "pages", context) != pages
            or binding.get("build_report_bytes_match") is not True
            or binding.get("build_report_sha256_match") is not True
            or binding.get("build_report_pages_match") is not True
            or not pdf_path.is_file()
            or pdf_path.is_symlink()
            or pdf_path.stat().st_size != expected_bytes
            or sha256_file(pdf_path) != expected_sha
        ):
            raise PublicationError(f"final PDF QA live PDF binding differs for {job}")

    order = {"book": 0, "jhanswer": 1, "lab": 2}
    expected_render_rows = sorted(
        [
            {
                "pdf": row["pdf"],
                "page": row["page"],
                "path": row["path"],
                "bytes": row["bytes"],
                "sha256": row["sha256"],
            }
            for row in render_rows
        ],
        key=lambda row: (order[row["pdf"]], row["page"]),
    )
    inventory = expect_dict(
        bindings.get("current_render_png_inventory"),
        "final_pdf_qa.bindings.current_render_png_inventory",
    )
    require_exact_keys(
        inventory,
        {"row_count", "all_rows_match", "current_inventory_sha256", "rows"},
        "final_pdf_qa.bindings.current_render_png_inventory",
    )
    if (
        require_integer(inventory, "row_count", "final_pdf_qa.render_inventory")
        != len(expected_render_rows)
        or inventory.get("all_rows_match") is not True
        or expect_list(inventory.get("rows"), "final_pdf_qa.render_inventory.rows")
        != expected_render_rows
        or require_sha(
            inventory.get("current_inventory_sha256"),
            "final_pdf_qa.render_inventory.current_inventory_sha256",
        )
        != sha256_bytes(canonical_bytes(expected_render_rows))
    ):
        raise PublicationError("final PDF QA rendered-page inventory differs")

    hard_failures = require_string_list(
        audit.get("hard_failures"), "final_pdf_qa.hard_failures", unique=True
    )
    review_findings = require_string_list(
        audit.get("review_findings"), "final_pdf_qa.review_findings", unique=True
    )
    if hard_failures:
        raise PublicationError("final PDF QA contains automated hard failures")

    candidates = expect_list(
        audit.get("ranked_candidate_pages"), "final_pdf_qa.ranked_candidate_pages"
    )
    candidate_keys: set[tuple[str, int]] = set()
    for index, candidate_value in enumerate(candidates, start=1):
        context = f"final_pdf_qa.ranked_candidate_pages[{index - 1}]"
        candidate = expect_dict(candidate_value, context)
        require_exact_keys(
            candidate,
            {"pdf", "page", "score", "automatic_failure", "reasons", "disposition", "rank"},
            context,
        )
        job = require_string(candidate, "pdf", context)
        page = require_integer(candidate, "page", context)
        rank = require_integer(candidate, "rank", context)
        reasons = require_string_list(candidate.get("reasons"), f"{context}.reasons", unique=True)
        score = candidate.get("score")
        if (
            job not in page_counts
            or page < 1
            or page > page_counts[job]
            or rank != index
            or not isinstance(score, (int, float))
            or isinstance(score, bool)
            or candidate.get("automatic_failure") is not False
            or candidate.get("disposition") != "human_visual_review_required"
            or reasons != sorted(reasons)
            or (job, page) in candidate_keys
        ):
            raise PublicationError(f"invalid or duplicate ranked PDF candidate at rank {index}")
        candidate_keys.add((job, page))

    summary = expect_dict(audit.get("summary"), "final_pdf_qa.summary")
    required_true = (
        "all_pdf_bytes_match_build_report",
        "all_pdf_page_counts_match_build_report",
        "all_render_pngs_match_manifest",
        "all_page_geometry_valid",
        "all_fonts_embedded",
    )
    if any(summary.get(key) is not True for key in required_true):
        raise PublicationError("final PDF QA contains a failed automated summary gate")
    total_pages = sum(page_counts.values())
    if (
        require_integer(summary, "pdf_count", "final_pdf_qa.summary") != 3
        or require_integer(summary, "pdf_pages", "final_pdf_qa.summary") != total_pages
        or require_integer(summary, "render_png_count", "final_pdf_qa.summary")
        != total_pages
        or require_integer(summary, "hard_failure_count", "final_pdf_qa.summary") != 0
        or require_integer(summary, "hard_log_diagnostic_count", "final_pdf_qa.summary") != 0
        or require_integer(summary, "ranked_candidate_page_count", "final_pdf_qa.summary")
        != len(candidates)
        or require_integer(summary, "review_finding_count", "final_pdf_qa.summary")
        != len(review_findings)
    ):
        raise PublicationError("final PDF QA summary count closure differs")
    expected_status = "human_review_required" if review_findings else "pass"
    if audit.get("status") != expected_status:
        raise PublicationError("final PDF QA status differs from its review findings")

    return {
        "path": relative,
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
        "status": expected_status,
        "pages": total_pages,
        "hard_failure_count": 0,
        "review_finding_count": len(review_findings),
        "ranked_candidate_count": len(candidates),
    }


def validate_final_visual_review(
    plan: dict[str, Any],
    root: Path,
    report_pdfs: dict[str, Any],
    all_page_renders: dict[str, Any],
    final_pdf_qa: dict[str, Any],
) -> dict[str, Any]:
    """Require a byte-bound, complete human disposition of every visual QA surface."""
    relative = plan["qa"]["final_visual_review"]
    _path, payload, review = load_qa_artifact(root, relative, "final visual review")
    require_exact_keys(
        review,
        {
            "schema_version",
            "status",
            "reviewer",
            "reviewed_at_utc",
            "bindings",
            "contact_sheets",
            "review_finding_dispositions",
            "ranked_candidate_reviews",
            "targeted_full_page_inspections",
            "summary",
        },
        "final_visual_review",
    )
    if review.get("schema_version") != "hefferon-id-final-visual-review-v1":
        raise PublicationError("unsupported final visual review schema")
    if review.get("status") != "pass":
        raise PublicationError("final visual review status is not pass")
    require_string(review, "reviewer", "final_visual_review")
    reviewed_at = require_string(review, "reviewed_at_utc", "final_visual_review")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", reviewed_at):
        raise PublicationError("final visual review timestamp is not UTC second precision")

    audit_relative = plan["qa"]["final_pdf_qa"]
    audit_path = ensure_under(root / audit_relative, root)
    audit_payload = audit_path.read_bytes()
    audit = load_json(audit_path)
    build_relative = plan["qa"]["build_report"]
    build_path = ensure_under(root / build_relative, root)
    build_payload = build_path.read_bytes()
    render_relative = plan["qa"]["all_page_render_manifest"]
    render_path = ensure_under(root / render_relative, root)
    render_payload = render_path.read_bytes()
    render_rows = load_json(render_path, expected=list)
    total_pages = sum(
        require_integer(expect_dict(report_pdfs[job], f"pdfs.{job}"), "pages", f"pdfs.{job}")
        for job in ("book", "jhanswer", "lab")
    )

    bindings = expect_dict(review.get("bindings"), "final_visual_review.bindings")
    require_exact_keys(
        bindings,
        {"build_report", "automated_pdf_audit", "all_page_render_manifest", "pdfs"},
        "final_visual_review.bindings",
    )
    expected_artifacts = {
        "build_report": (build_relative, build_payload),
        "automated_pdf_audit": (audit_relative, audit_payload),
        "all_page_render_manifest": (render_relative, render_payload),
    }
    for name, (expected_path, expected_payload) in expected_artifacts.items():
        context = f"final_visual_review.bindings.{name}"
        binding = expect_dict(bindings.get(name), context)
        required = {"path", "bytes", "sha256", "pages"}
        if name == "automated_pdf_audit":
            required |= {"status", "hard_failure_count"}
        require_exact_keys(binding, required, context)
        if (
            require_string(binding, "path", context) != expected_path
            or require_integer(binding, "bytes", context) != len(expected_payload)
            or require_sha(binding.get("sha256"), f"{context}.sha256")
            != sha256_bytes(expected_payload)
            or require_integer(binding, "pages", context) != total_pages
        ):
            raise PublicationError(f"{context} byte/SHA/page binding differs")
        if name == "automated_pdf_audit" and (
            binding.get("status") != final_pdf_qa["status"]
            or require_integer(binding, "hard_failure_count", context) != 0
        ):
            raise PublicationError("final visual review automated-audit binding differs")

    plan_sources = {
        {"textbook": "book", "worked-answers": "jhanswer", "sage-lab": "lab"}[
            item["component"]
        ]: item["source"]
        for item in plan["reader_pdfs"]
    }
    review_pdfs = expect_dict(bindings.get("pdfs"), "final_visual_review.bindings.pdfs")
    if set(review_pdfs) != {"book", "jhanswer", "lab"}:
        raise PublicationError("final visual review PDF binding closure differs")
    page_counts: dict[str, int] = {}
    for job in ("book", "jhanswer", "lab"):
        context = f"final_visual_review.bindings.pdfs.{job}"
        binding = expect_dict(review_pdfs.get(job), context)
        require_exact_keys(binding, {"path", "bytes", "sha256", "pages"}, context)
        details = expect_dict(report_pdfs.get(job), f"build_report.pdfs.{job}")
        pdf_path = ensure_under(root / plan_sources[job], root)
        pages = require_integer(details, "pages", f"build_report.pdfs.{job}")
        expected_bytes = require_integer(details, "bytes", f"build_report.pdfs.{job}")
        expected_sha = require_sha(details.get("sha256"), f"build_report.pdfs.{job}.sha256")
        page_counts[job] = pages
        if (
            binding.get("path") != plan_sources[job]
            or require_integer(binding, "bytes", context) != expected_bytes
            or require_sha(binding.get("sha256"), f"{context}.sha256") != expected_sha
            or require_integer(binding, "pages", context) != pages
            or not pdf_path.is_file()
            or pdf_path.is_symlink()
            or pdf_path.stat().st_size != expected_bytes
            or sha256_file(pdf_path) != expected_sha
        ):
            raise PublicationError(f"final visual review PDF binding differs for {job}")

    contact_sheets = expect_list(review.get("contact_sheets"), "final_visual_review.contact_sheets")
    covered: dict[str, list[int]] = {job: [] for job in page_counts}
    sheet_paths: set[str] = set()
    for index, row_value in enumerate(contact_sheets):
        context = f"final_visual_review.contact_sheets[{index}]"
        row = expect_dict(row_value, context)
        require_exact_keys(
            row,
            {"pdf", "path", "bytes", "sha256", "first_page", "last_page", "disposition", "notes"},
            context,
        )
        job = require_string(row, "pdf", context)
        sheet_relative = validate_relative_name(require_string(row, "path", context), context)
        first_page = require_integer(row, "first_page", context)
        last_page = require_integer(row, "last_page", context)
        notes = require_string(row, "notes", context)
        sheet_path = ensure_under(root / sheet_relative, root)
        if (
            job not in page_counts
            or not sheet_relative.startswith("qa/")
            or sheet_relative in sheet_paths
            or first_page < 1
            or last_page < first_page
            or last_page > page_counts[job]
            or row.get("disposition") != "pass"
            or not notes.strip()
            or not sheet_path.is_file()
            or sheet_path.is_symlink()
            or require_integer(row, "bytes", context) != sheet_path.stat().st_size
            or require_sha(row.get("sha256"), f"{context}.sha256") != sha256_file(sheet_path)
        ):
            raise PublicationError(f"invalid final visual review contact sheet {index}")
        sheet_paths.add(sheet_relative)
        covered[job].extend(range(first_page, last_page + 1))
    for job, pages in covered.items():
        if pages != list(range(1, page_counts[job] + 1)):
            raise PublicationError(f"contact-sheet page coverage is not exact for {job}")

    review_findings = require_string_list(
        audit.get("review_findings"), "final_pdf_qa.review_findings", unique=True
    )
    finding_rows = expect_list(
        review.get("review_finding_dispositions"),
        "final_visual_review.review_finding_dispositions",
    )
    if len(finding_rows) != len(review_findings):
        raise PublicationError("visual review finding disposition count differs")
    for index, (row_value, finding) in enumerate(zip(finding_rows, review_findings)):
        context = f"final_visual_review.review_finding_dispositions[{index}]"
        row = expect_dict(row_value, context)
        require_exact_keys(row, {"finding", "disposition", "notes"}, context)
        if (
            row.get("finding") != finding
            or row.get("disposition") != "pass"
            or not require_string(row, "notes", context).strip()
        ):
            raise PublicationError(f"visual review finding {index} lacks an exact pass disposition")

    candidates = expect_list(
        audit.get("ranked_candidate_pages"), "final_pdf_qa.ranked_candidate_pages"
    )
    candidate_reviews = expect_list(
        review.get("ranked_candidate_reviews"), "final_visual_review.ranked_candidate_reviews"
    )
    if len(candidate_reviews) != len(candidates):
        raise PublicationError("ranked visual candidate review count differs")
    candidate_keys: set[tuple[str, int]] = set()
    for index, (row_value, candidate_value) in enumerate(zip(candidate_reviews, candidates)):
        context = f"final_visual_review.ranked_candidate_reviews[{index}]"
        row = expect_dict(row_value, context)
        candidate = expect_dict(candidate_value, f"final_pdf_qa.candidate[{index}]")
        require_exact_keys(row, {"rank", "pdf", "page", "reasons", "disposition", "notes"}, context)
        key = (row.get("pdf"), row.get("page"))
        if (
            require_integer(row, "rank", context) != candidate.get("rank")
            or key != (candidate.get("pdf"), candidate.get("page"))
            or row.get("reasons") != candidate.get("reasons")
            or row.get("disposition") != "pass"
            or not require_string(row, "notes", context).strip()
            or key in candidate_keys
        ):
            raise PublicationError(f"ranked visual candidate {index} lacks an exact pass disposition")
        candidate_keys.add(key)

    manifest_lookup: dict[tuple[str, int], dict[str, Any]] = {}
    for row_value in render_rows:
        row = expect_dict(row_value, "all_page_render_manifest row")
        key = (row.get("pdf"), row.get("page"))
        if key in manifest_lookup:
            raise PublicationError("duplicate page in all-page render manifest")
        manifest_lookup[key] = row
    inspections = expect_list(
        review.get("targeted_full_page_inspections"),
        "final_visual_review.targeted_full_page_inspections",
    )
    inspected: set[tuple[str, int]] = set()
    for index, row_value in enumerate(inspections):
        context = f"final_visual_review.targeted_full_page_inspections[{index}]"
        row = expect_dict(row_value, context)
        require_exact_keys(
            row,
            {
                "pdf",
                "page",
                "render_path",
                "render_bytes",
                "render_sha256",
                "purpose",
                "disposition",
                "notes",
            },
            context,
        )
        key = (require_string(row, "pdf", context), require_integer(row, "page", context))
        manifest_row = manifest_lookup.get(key)
        if (
            manifest_row is None
            or key in inspected
            or row.get("render_path") != manifest_row.get("path")
            or require_integer(row, "render_bytes", context) != manifest_row.get("bytes")
            or require_sha(row.get("render_sha256"), f"{context}.render_sha256")
            != manifest_row.get("sha256")
            or row.get("disposition") != "pass"
            or not require_string(row, "purpose", context).strip()
            or not require_string(row, "notes", context).strip()
        ):
            raise PublicationError(f"invalid targeted full-page inspection {index}")
        inspected.add(key)
    if not candidate_keys.issubset(inspected):
        raise PublicationError("not every ranked candidate has one targeted full-page inspection")
    for job in page_counts:
        if not any(key[0] == job for key in inspected):
            raise PublicationError(f"no targeted full-page inspection recorded for {job}")

    summary = expect_dict(review.get("summary"), "final_visual_review.summary")
    require_exact_keys(
        summary,
        {
            "contact_sheet_count",
            "contact_sheet_page_count",
            "review_finding_count",
            "ranked_candidate_count",
            "targeted_full_page_inspection_count",
            "unresolved_findings",
        },
        "final_visual_review.summary",
    )
    if (
        require_integer(summary, "contact_sheet_count", "final_visual_review.summary")
        != len(contact_sheets)
        or require_integer(summary, "contact_sheet_page_count", "final_visual_review.summary")
        != total_pages
        or require_integer(summary, "review_finding_count", "final_visual_review.summary")
        != len(review_findings)
        or require_integer(summary, "ranked_candidate_count", "final_visual_review.summary")
        != len(candidates)
        or require_integer(
            summary, "targeted_full_page_inspection_count", "final_visual_review.summary"
        )
        != len(inspections)
        or require_integer(summary, "unresolved_findings", "final_visual_review.summary") != 0
    ):
        raise PublicationError("final visual review summary closure differs")

    return {
        "path": relative,
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
        "status": "pass",
        "pages": total_pages,
        "contact_sheet_count": len(contact_sheets),
        "review_finding_count": len(review_findings),
        "ranked_candidate_count": len(candidates),
        "targeted_full_page_inspection_count": len(inspections),
        "unresolved_findings": 0,
    }


def validate_cross_pdf_sidecar(
    plan: dict[str, Any], root: Path, report: dict[str, Any]
) -> dict[str, Any]:
    relative = plan["qa"]["cross_pdf_link_audit"]
    path = ensure_under(root / relative, root)
    payload = path.read_bytes()
    audit = load_json(path)
    binding = expect_dict(
        report.get("cross_pdf_link_audit"), "build_report.cross_pdf_link_audit"
    )
    require_exact_keys(
        binding,
        {"path", "bytes", "sha256", "counts", "all_pair_actions_resolved"},
        "build_report.cross_pdf_link_audit",
    )
    reported_path = require_string(
        binding, "path", "build_report.cross_pdf_link_audit"
    ).replace("\\", "/")
    if reported_path != relative and not reported_path.endswith("/" + relative):
        raise PublicationError("cross-PDF sidecar path is not the planned path")
    if require_integer(binding, "bytes", "cross_pdf_link_audit") != len(payload):
        raise PublicationError("cross-PDF sidecar byte count differs")
    if require_sha(binding.get("sha256"), "cross_pdf_link_audit.sha256") != sha256_bytes(
        payload
    ):
        raise PublicationError("cross-PDF sidecar SHA-256 differs")
    if binding.get("all_pair_actions_resolved") is not True:
        raise PublicationError("build-report cross-PDF resolution is not true")
    if audit.get("all_pair_actions_resolved") is not True:
        raise PublicationError("cross-PDF sidecar resolution is not true")
    counts = expect_dict(audit.get("counts"), "cross_pdf_link_audit.counts")
    if counts != binding.get("counts"):
        raise PublicationError("cross-PDF sidecar counts differ from the build report")
    expected_answers = require_integer(
        expect_dict(report.get("generated_answer_stream"), "generated_answer_stream"),
        "all_answers",
        "generated_answer_stream",
    )
    if (
        require_integer(counts, "book_to_jhanswer", "cross_pdf_link_audit.counts")
        != expected_answers
        or require_integer(counts, "jhanswer_to_book", "cross_pdf_link_audit.counts")
        != expected_answers
        or require_integer(counts, "unresolved_pair_actions", "cross_pdf_link_audit.counts")
        != 0
        or require_integer(counts, "goto_remote_actions", "cross_pdf_link_audit.counts")
        != 2 * expected_answers
    ):
        raise PublicationError("cross-PDF action closure differs from the answer stream")
    unresolved = expect_list(
        audit.get("unresolved_pair_actions"), "cross_pdf_link_audit.unresolved_pair_actions"
    )
    actions = expect_list(audit.get("actions"), "cross_pdf_link_audit.actions")
    if unresolved or len(actions) != 2 * expected_answers:
        raise PublicationError("cross-PDF sidecar action inventory is incomplete")
    return {
        "path": relative,
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
        "answer_links_each_direction": expected_answers,
        "all_pair_actions_resolved": True,
    }


def validate_lab_sagetex_sidecar(
    plan: dict[str, Any], root: Path, report: dict[str, Any]
) -> dict[str, Any]:
    relative = plan["qa"]["lab_sagetex_runtime_manifest"]
    path = ensure_under(root / relative, root)
    payload = path.read_bytes()
    sidecar = load_json(path)
    runtime = expect_dict(report.get("lab_sagetex"), "build_report.lab_sagetex")
    artifact = expect_dict(runtime.get("manifest_artifact"), "lab_sagetex.manifest_artifact")
    require_exact_keys(
        artifact, {"path", "bytes", "sha256"}, "lab_sagetex.manifest_artifact"
    )
    reported_path = require_string(
        artifact, "path", "lab_sagetex.manifest_artifact"
    ).replace("\\", "/")
    if reported_path != relative and not reported_path.endswith("/" + relative):
        raise PublicationError("SageTeX sidecar path is not the planned path")
    if require_integer(artifact, "bytes", "lab_sagetex.manifest_artifact") != len(payload):
        raise PublicationError("SageTeX sidecar byte count differs")
    if require_sha(artifact.get("sha256"), "lab_sagetex.manifest_artifact.sha256") != sha256_bytes(
        payload
    ):
        raise PublicationError("SageTeX sidecar SHA-256 differs")
    if (
        sidecar.get("schema_version") != "hefferon-id-sagetex-runtime-v1"
        or sidecar.get("status") != "pass"
        or runtime.get("schema_version") != sidecar.get("schema_version")
        or runtime.get("status") != "pass"
    ):
        raise PublicationError("SageTeX runtime schema/status closure differs")

    outputs = expect_dict(sidecar.get("outputs"), "lab_sagetex.outputs")
    if runtime.get("outputs") != outputs:
        raise PublicationError("SageTeX report outputs differ from the sidecar")
    if (
        require_integer(outputs, "command_label_count", "lab_sagetex.outputs") != 148
        or require_integer(outputs, "command_label_first", "lab_sagetex.outputs") != 0
        or require_integer(outputs, "command_label_last", "lab_sagetex.outputs") != 147
        or require_integer(outputs, "command_source_listing_count", "lab_sagetex.outputs")
        != 1018
        or require_integer(outputs, "maximum_listed_source_line", "lab_sagetex.outputs")
        != 1236
        or require_integer(
            expect_dict(outputs.get("scmd"), "lab_sagetex.outputs.scmd"),
            "line_count",
            "lab_sagetex.outputs.scmd",
        )
        != 1237
    ):
        raise PublicationError("SageTeX command-output closure differs")
    require_sha(outputs.get("source_md5"), "lab_sagetex.outputs.source_md5", algorithm="md5")

    figures = expect_dict(sidecar.get("figure_execution"), "lab_sagetex.figure_execution")
    if runtime.get("figure_execution") != figures:
        raise PublicationError("SageTeX report figure closure differs from the sidecar")
    if (
        require_integer(figures, "target_count", "lab_sagetex.figure_execution") != 64
        or require_integer(
            figures, "changed_from_authority_count", "lab_sagetex.figure_execution"
        )
        != 63
        or figures.get("unchanged_from_authority_paths") != ["asy/ellipsoid1.pdf"]
        or figures.get("final_state")
        != "all_64_pinned_authority_figures_restored_and_rehashed"
    ):
        raise PublicationError("SageTeX figure side-effect/restoration closure differs")

    sidecar_stable = expect_dict(
        sidecar.get("stable_fingerprint"), "lab_sagetex.stable_fingerprint"
    )
    validate_sagetex_stable_fingerprint(sidecar_stable, outputs, figures)
    report_stable = dict(
        expect_dict(runtime.get("stable_fingerprint"), "report.lab_sagetex.stable_fingerprint")
    )
    pythontex_stable = report_stable.pop("pythontex", None)
    if report_stable != sidecar_stable:
        raise PublicationError("SageTeX stable fingerprint differs from the sidecar")
    pythontex = expect_dict(runtime.get("pythontex"), "lab_sagetex.pythontex")
    pythontex_fingerprint = expect_dict(
        pythontex.get("stable_fingerprint"), "lab_sagetex.pythontex.stable_fingerprint"
    )
    validate_pythontex_stable_fingerprint(pythontex_fingerprint, pythontex)
    if (
        pythontex.get("status") != "pass"
        or pythontex.get("success_line") != "PythonTeX:  lab - 0 error(s), 0 warning(s)"
        or pythontex_fingerprint != pythontex_stable
    ):
        raise PublicationError("PythonTeX deterministic runtime closure differs")

    restored = expect_dict(
        runtime.get("post_execution_authority_graphics"),
        "lab_sagetex.post_execution_authority_graphics",
    )
    lab_graphics = expect_dict(report.get("lab_graphics"), "build_report.lab_graphics")
    if (
        require_integer(restored, "count", "post_execution_authority_graphics") != 64
        or restored.get("manifest_sha256") != lab_graphics.get("manifest_sha256")
    ):
        raise PublicationError("post-Sage authority-figure restoration differs")
    return {
        "path": relative,
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
        "command_labels": 148,
        "command_source_listings": 1018,
        "scmd_lines": 1237,
        "sage_changed_figures": 63,
        "authority_figures_restored": 64,
        "pythontex_zero_errors_warnings": True,
    }


def validate_sagetex_stable_fingerprint(
    stable: dict[str, Any], outputs: dict[str, Any], figures: dict[str, Any]
) -> None:
    require_exact_keys(
        stable,
        {
            "schema_version",
            "wsl_distro",
            "sage_version",
            "sagetex_distribution_version",
            "sagetex_module_version",
            "random_seed",
            "source_date_epoch",
            "generated_sage_script_sha256",
            "compatibility_sage_script_sha256",
            "runner_sha256",
            "pytxcode_sha256",
            "sout_sha256",
            "scmd_sha256",
            "source_md5",
            "command_label_count",
            "command_source_listing_count",
            "authority_graphics_manifest_sha256",
            "sage_changed_figure_count",
            "sage_changed_paths_sha256",
            "final_figure_source",
        },
        "lab_sagetex.stable_fingerprint",
    )
    if (
        stable.get("schema_version")
        != "hefferon-id-sagetex-stable-fingerprint-v1"
        or stable.get("wsl_distro") != "Ubuntu-22.04"
        or stable.get("sage_version") != EXPECTED_SAGE_VERSION
        or stable.get("sagetex_distribution_version")
        != EXPECTED_SAGETEX_DISTRIBUTION_VERSION
        or stable.get("sagetex_module_version") != EXPECTED_SAGETEX_MODULE_VERSION
        or require_integer(stable, "random_seed", "lab_sagetex.stable_fingerprint")
        != EXPECTED_RANDOM_SEED
        or stable.get("source_date_epoch") != EXPECTED_SOURCE_DATE_EPOCH
        or require_integer(
            stable, "command_label_count", "lab_sagetex.stable_fingerprint"
        )
        != 148
        or require_integer(
            stable,
            "command_source_listing_count",
            "lab_sagetex.stable_fingerprint",
        )
        != 1018
        or require_integer(
            stable, "sage_changed_figure_count", "lab_sagetex.stable_fingerprint"
        )
        != 63
        or stable.get("final_figure_source")
        != "pinned_authority_pdf_forms_restored_after_execution"
    ):
        raise PublicationError("SageTeX stable fingerprint controls differ")
    for key in (
        "generated_sage_script_sha256",
        "compatibility_sage_script_sha256",
        "runner_sha256",
        "pytxcode_sha256",
        "sout_sha256",
        "scmd_sha256",
        "authority_graphics_manifest_sha256",
        "sage_changed_paths_sha256",
    ):
        require_sha(stable.get(key), f"lab_sagetex.stable_fingerprint.{key}")
    require_sha(
        stable.get("source_md5"),
        "lab_sagetex.stable_fingerprint.source_md5",
        algorithm="md5",
    )
    sout = expect_dict(outputs.get("sout"), "lab_sagetex.outputs.sout")
    scmd = expect_dict(outputs.get("scmd"), "lab_sagetex.outputs.scmd")
    authority_manifest = expect_dict(
        figures.get("authority_manifest"), "lab_sagetex.figure_execution.authority_manifest"
    )
    if (
        stable["sout_sha256"]
        != require_sha(sout.get("sha256"), "lab_sagetex.outputs.sout.sha256")
        or stable["scmd_sha256"]
        != require_sha(scmd.get("sha256"), "lab_sagetex.outputs.scmd.sha256")
        or stable["source_md5"] != outputs.get("source_md5")
        or stable["authority_graphics_manifest_sha256"]
        != require_sha(
            authority_manifest.get("sha256"),
            "lab_sagetex.figure_execution.authority_manifest.sha256",
        )
    ):
        raise PublicationError("SageTeX stable fingerprint output bindings differ")


def validate_pythontex_stable_fingerprint(
    stable: dict[str, Any], pythontex: dict[str, Any]
) -> None:
    require_exact_keys(
        stable,
        {
            "schema_version",
            "version",
            "random_seed",
            "pythonhashseed",
            "source_date_epoch",
            "startup_sha256",
            "macros_sha256",
            "pygments_sha256",
        },
        "lab_sagetex.pythontex.stable_fingerprint",
    )
    if (
        stable.get("schema_version")
        != "hefferon-id-pythontex-stable-fingerprint-v1"
        or stable.get("version") != "PythonTeX 0.19"
        or require_integer(
            stable, "random_seed", "lab_sagetex.pythontex.stable_fingerprint"
        )
        != EXPECTED_RANDOM_SEED
        or require_integer(
            stable, "pythonhashseed", "lab_sagetex.pythontex.stable_fingerprint"
        )
        != 0
        or stable.get("source_date_epoch") != EXPECTED_SOURCE_DATE_EPOCH
    ):
        raise PublicationError("PythonTeX deterministic fingerprint controls differ")
    for key in ("startup_sha256", "macros_sha256", "pygments_sha256"):
        require_sha(stable.get(key), f"lab_sagetex.pythontex.stable_fingerprint.{key}")
    pythontex_outputs = expect_dict(
        pythontex.get("outputs"), "lab_sagetex.pythontex.outputs"
    )
    macros = expect_dict(
        pythontex_outputs.get("macros"), "lab_sagetex.pythontex.outputs.macros"
    )
    pygments = expect_dict(
        pythontex_outputs.get("pygments"), "lab_sagetex.pythontex.outputs.pygments"
    )
    if (
        stable["macros_sha256"]
        != require_sha(
            macros.get("sha256"), "lab_sagetex.pythontex.outputs.macros.sha256"
        )
        or stable["pygments_sha256"]
        != require_sha(
            pygments.get("sha256"),
            "lab_sagetex.pythontex.outputs.pygments.sha256",
        )
    ):
        raise PublicationError("PythonTeX deterministic output bindings differ")


def reconstruct_build_fingerprint(report: dict[str, Any]) -> dict[str, Any]:
    source = expect_dict(report.get("source"), "build_report.source")
    authority_book_pdf = expect_dict(
        report.get("authority_book_pdf"), "build_report.authority_book_pdf"
    )
    authority_lab_pdf = expect_dict(
        report.get("authority_lab_pdf"), "build_report.authority_lab_pdf"
    )
    for name, details in (
        ("book", authority_book_pdf),
        ("lab", authority_lab_pdf),
    ):
        require_exact_keys(
            details,
            {"path", "sha256"},
            f"build_report.authority_{name}_pdf",
        )
    book_graphics = expect_dict(
        report.get("book_graphics"), "build_report.book_graphics"
    )
    lab_graphics = expect_dict(
        report.get("lab_graphics"), "build_report.lab_graphics"
    )
    missing_lab_asset = expect_dict(
        report.get("missing_lab_asset"), "build_report.missing_lab_asset"
    )
    lab_sagetex = expect_dict(
        report.get("lab_sagetex"), "build_report.lab_sagetex"
    )
    metapost_report = expect_dict(
        report.get("metapost_assets"), "build_report.metapost_assets"
    )
    metapost_keys = {
        "schema_version",
        "random_seed",
        "source_date_epoch",
        "asset_count",
        "bytes",
        "canonical_sha256",
        "files",
        "manifest_bytes",
        "manifest_sha256",
    }
    require_exact_keys(
        metapost_report,
        metapost_keys,
        "build_report.metapost_assets",
        optional={"manifest_path"},
    )
    if (
        metapost_report.get("schema_version") != "hefferon-id-metapost-assets-v1"
        or require_integer(metapost_report, "random_seed", "metapost_assets") != 1
        or metapost_report.get("source_date_epoch") != "1633046400"
    ):
        raise PublicationError("MetaPost deterministic-control identity differs")
    metapost_files = expect_list(
        metapost_report.get("files"), "build_report.metapost_assets.files"
    )
    if (
        require_integer(metapost_report, "asset_count", "metapost_assets") != 307
        or len(metapost_files) != 307
    ):
        raise PublicationError("MetaPost asset count is not exactly 307")
    metapost_bytes = 0
    metapost_paths: set[str] = set()
    for index, value in enumerate(metapost_files):
        context = f"build_report.metapost_assets.files[{index}]"
        row = expect_dict(value, context)
        require_exact_keys(
            row, {"source", "figure", "path", "bytes", "sha256"}, context
        )
        path = require_string(row, "path", context)
        if path in metapost_paths or not re.fullmatch(r".+\.[0-9]+", path):
            raise PublicationError(f"{context}.path is duplicated or not numeric-suffixed")
        metapost_paths.add(path)
        if require_integer(row, "figure", context) <= 0:
            raise PublicationError(f"{context}.figure is not positive")
        byte_count = require_integer(row, "bytes", context)
        if byte_count <= 0:
            raise PublicationError(f"{context}.bytes is not positive")
        metapost_bytes += byte_count
        require_string(row, "source", context)
        require_sha(row.get("sha256"), f"{context}.sha256")
    if require_integer(metapost_report, "bytes", "metapost_assets") != metapost_bytes:
        raise PublicationError("MetaPost byte total differs from its file rows")
    metapost_canonical = sha256_bytes(
        json.dumps(
            metapost_files,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if (
        require_sha(
            metapost_report.get("canonical_sha256"),
            "build_report.metapost_assets.canonical_sha256",
        )
        != metapost_canonical
    ):
        raise PublicationError("MetaPost canonical SHA-256 differs")
    metapost = {key: metapost_report[key] for key in metapost_keys - {"manifest_bytes", "manifest_sha256"}}
    metapost["manifest_bytes"] = require_integer(
        metapost_report, "manifest_bytes", "metapost_assets"
    )
    metapost["manifest_sha256"] = require_sha(
        metapost_report.get("manifest_sha256"), "metapost_assets.manifest_sha256"
    )
    metapost_manifest_core = {
        key: metapost[key]
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
    metapost_manifest_payload = canonical_bytes(metapost_manifest_core, pretty=True)
    # The build runs on Windows as well as POSIX.  Python's text writer may
    # preserve the host newline convention in this JSON sidecar, so accept
    # the exact LF or CRLF serialization while keeping the semantic core
    # byte-bound and rejecting every other representation.
    metapost_manifest_payload_crlf = metapost_manifest_payload.replace(
        b"\n", b"\r\n"
    )
    valid_manifest_bindings = {
        (len(metapost_manifest_payload), sha256_bytes(metapost_manifest_payload)),
        (
            len(metapost_manifest_payload_crlf),
            sha256_bytes(metapost_manifest_payload_crlf),
        ),
    }
    if (
        metapost["manifest_bytes"], metapost["manifest_sha256"]
    ) not in valid_manifest_bindings:
        raise PublicationError("MetaPost manifest artifact binding differs")
    metapost_end_report = expect_dict(
        report.get("metapost_assets_end_verification"),
        "build_report.metapost_assets_end_verification",
    )
    require_exact_keys(
        metapost_end_report,
        {"asset_count", "bytes", "canonical_sha256", "all_verified"},
        "build_report.metapost_assets_end_verification",
    )
    if (
        metapost_end_report.get("all_verified") is not True
        or require_integer(metapost_end_report, "asset_count", "metapost_end") != 307
        or require_integer(metapost_end_report, "bytes", "metapost_end") != metapost_bytes
        or require_sha(metapost_end_report.get("canonical_sha256"), "metapost_end.sha256")
        != metapost_canonical
    ):
        raise PublicationError("MetaPost end verification differs")
    metapost_end = dict(metapost_end_report)

    answer_stream_report = expect_dict(
        report.get("generated_answer_stream"), "build_report.generated_answer_stream"
    )
    answer_stream_keys = {
        "bytes",
        "sha256",
        "all_answers",
        "topic_count",
        "topic_answers",
        "expected_native_topic_answers",
        "expected_indonesian_edition_supplied_topic_answers",
        "expected_topic_answers",
        "topic_answer_entries",
    }
    require_exact_keys(
        answer_stream_report,
        answer_stream_keys,
        "build_report.generated_answer_stream",
        optional={"path"},
    )
    for key in answer_stream_keys - {"sha256", "topic_answer_entries"}:
        if require_integer(answer_stream_report, key, "generated_answer_stream") < 0:
            raise PublicationError(f"generated_answer_stream.{key} is negative")
    if (
        answer_stream_report["bytes"] <= 0
        or answer_stream_report["all_answers"] <= 0
        or answer_stream_report["topic_count"] <= 0
        or answer_stream_report["expected_native_topic_answers"]
        != EXPECTED_NATIVE_TOPIC_ANSWERS
        or answer_stream_report[
            "expected_indonesian_edition_supplied_topic_answers"
        ]
        != EXPECTED_INDONESIAN_EDITION_SUPPLIED_TOPIC_ANSWERS
        or answer_stream_report["expected_topic_answers"]
        != EXPECTED_TOPIC_ANSWERS
        or answer_stream_report["expected_topic_answers"]
        != answer_stream_report["expected_native_topic_answers"]
        + answer_stream_report["expected_indonesian_edition_supplied_topic_answers"]
        or answer_stream_report["topic_answers"]
        != answer_stream_report["expected_topic_answers"]
    ):
        raise PublicationError("generated answer-stream semantic counts differ")
    require_sha(answer_stream_report.get("sha256"), "generated_answer_stream.sha256")
    topic_entries = expect_list(
        answer_stream_report.get("topic_answer_entries"),
        "generated_answer_stream.topic_answer_entries",
    )
    if len(topic_entries) != answer_stream_report["topic_answers"]:
        raise PublicationError("generated answer topic-entry count differs")
    answer_stream = {key: answer_stream_report[key] for key in answer_stream_keys}

    convergence_report = expect_dict(
        report.get("tex_convergence"), "build_report.tex_convergence"
    )
    if set(convergence_report) != {"book", "jhanswer"}:
        raise PublicationError("TeX convergence job closure differs")
    tex_convergence: dict[str, Any] = {}
    for job, expected_pass in (("book", 7), ("jhanswer", 4)):
        context = f"build_report.tex_convergence.{job}"
        details = expect_dict(convergence_report.get(job), context)
        required_keys = {
            "schema_version",
            "job",
            "comparison_pass",
            "matched",
            "state",
        }
        if job == "book":
            required_keys.add("index_fixed_point")
        require_exact_keys(
            details,
            required_keys,
            context,
        )
        if (
            details.get("schema_version") != "hefferon-id-tex-convergence-v1"
            or details.get("job") != job
            or details.get("matched") is not True
            or require_integer(details, "comparison_pass", context) != expected_pass
        ):
            raise PublicationError(f"{context} identity or match differs")
        state = expect_dict(details.get("state"), f"{context}.state")
        require_exact_keys(
            state,
            {"schema_version", "job", "file_count", "bytes", "canonical_sha256", "files"},
            f"{context}.state",
        )
        rows = expect_list(state.get("files"), f"{context}.state.files")
        if (
            state.get("schema_version") != "hefferon-id-tex-convergence-state-v1"
            or state.get("job") != job
            or require_integer(state, "file_count", f"{context}.state") != len(rows)
        ):
            raise PublicationError(f"{context}.state identity or count differs")
        byte_total = 0
        paths: set[str] = set()
        for index, value in enumerate(rows):
            row_context = f"{context}.state.files[{index}]"
            row = expect_dict(value, row_context)
            require_exact_keys(row, {"path", "bytes", "sha256"}, row_context)
            row_path = require_string(row, "path", row_context)
            if row_path in paths:
                raise PublicationError(f"{row_context}.path is duplicated")
            paths.add(row_path)
            row_bytes = require_integer(row, "bytes", row_context)
            if row_bytes <= 0:
                raise PublicationError(f"{row_context}.bytes is not positive")
            byte_total += row_bytes
            require_sha(row.get("sha256"), f"{row_context}.sha256")
        state_canonical = sha256_bytes(
            json.dumps(
                rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        )
        if (
            require_integer(state, "bytes", f"{context}.state") != byte_total
            or require_sha(state.get("canonical_sha256"), f"{context}.state.sha256")
            != state_canonical
        ):
            raise PublicationError(f"{context}.state byte/hash binding differs")
        if job == "book":
            index_fixed_point = expect_dict(
                details.get("index_fixed_point"), f"{context}.index_fixed_point"
            )
            require_exact_keys(
                index_fixed_point,
                {
                    "schema_version",
                    "refreshed_after_tex_pass",
                    "verified_after_tex_pass",
                    "matched",
                    "state",
                },
                f"{context}.index_fixed_point",
            )
            if (
                index_fixed_point.get("schema_version")
                != "hefferon-id-book-index-fixed-point-v1"
                or require_integer(
                    index_fixed_point,
                    "refreshed_after_tex_pass",
                    f"{context}.index_fixed_point",
                )
                != 5
                or require_integer(
                    index_fixed_point,
                    "verified_after_tex_pass",
                    f"{context}.index_fixed_point",
                )
                != 6
                or index_fixed_point.get("matched") is not True
            ):
                raise PublicationError("book index fixed-point control differs")
            index_state = expect_dict(
                index_fixed_point.get("state"),
                f"{context}.index_fixed_point.state",
            )
            require_exact_keys(
                index_state,
                {
                    "schema_version",
                    "file_count",
                    "bytes",
                    "canonical_sha256",
                    "files",
                },
                f"{context}.index_fixed_point.state",
            )
            index_rows = expect_list(
                index_state.get("files"),
                f"{context}.index_fixed_point.state.files",
            )
            if (
                index_state.get("schema_version")
                != "hefferon-id-book-index-state-v1"
                or require_integer(
                    index_state,
                    "file_count",
                    f"{context}.index_fixed_point.state",
                )
                != 2
                or len(index_rows) != 2
            ):
                raise PublicationError("book index fixed-point state closure differs")
            normalized_index_rows: list[dict[str, Any]] = []
            index_bytes = 0
            for row_index, expected_path in enumerate(("book.idx", "book.ind")):
                row_context = (
                    f"{context}.index_fixed_point.state.files[{row_index}]"
                )
                row = expect_dict(index_rows[row_index], row_context)
                require_exact_keys(row, {"path", "bytes", "sha256"}, row_context)
                if row.get("path") != expected_path:
                    raise PublicationError("book index fixed-point path/order differs")
                byte_count = require_integer(row, "bytes", row_context)
                if byte_count <= 0:
                    raise PublicationError("book index fixed-point file is empty")
                index_bytes += byte_count
                normalized_index_rows.append(
                    {
                        "path": expected_path,
                        "bytes": byte_count,
                        "sha256": require_sha(
                            row.get("sha256"), f"{row_context}.sha256"
                        ),
                    }
                )
            index_canonical = sha256_bytes(
                json.dumps(
                    normalized_index_rows,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            if (
                require_integer(
                    index_state,
                    "bytes",
                    f"{context}.index_fixed_point.state",
                )
                != index_bytes
                or require_sha(
                    index_state.get("canonical_sha256"),
                    f"{context}.index_fixed_point.state.canonical_sha256",
                )
                != index_canonical
            ):
                raise PublicationError("book index fixed-point byte/hash binding differs")
        tex_convergence[job] = details

    input_audit_report = expect_dict(
        report.get("pdftex_input_audit"), "build_report.pdftex_input_audit"
    )
    input_audit_keys = {
        "schema_version",
        "all_map_encoding_font_program_inputs_private",
        "jobs",
        "controlled_input_count",
        "metric_input_count",
        "controlled_inputs",
        "metric_inputs",
        "canonical_sha256",
        "bytes",
        "sha256",
    }
    require_exact_keys(
        input_audit_report,
        input_audit_keys,
        "build_report.pdftex_input_audit",
        optional={"path"},
    )
    controlled_inputs = expect_list(
        input_audit_report.get("controlled_inputs"), "pdftex_input_audit.controlled_inputs"
    )
    metric_inputs = expect_list(
        input_audit_report.get("metric_inputs"), "pdftex_input_audit.metric_inputs"
    )
    if (
        input_audit_report.get("schema_version") != "hefferon-id-pdftex-input-audit-v1"
        or input_audit_report.get("all_map_encoding_font_program_inputs_private") is not True
        or input_audit_report.get("jobs") != ["book", "jhanswer"]
        or require_integer(input_audit_report, "controlled_input_count", "pdftex_input_audit")
        != len(controlled_inputs)
        or require_integer(input_audit_report, "metric_input_count", "pdftex_input_audit")
        != len(metric_inputs)
    ):
        raise PublicationError("pdfTeX recorded-input audit identity or counts differ")
    for kind, rows, required_keys in (
        (
            "controlled",
            controlled_inputs,
            {"job", "name", "suffix", "bytes", "sha256", "closure_path"},
        ),
        ("metric", metric_inputs, {"job", "name", "suffix", "bytes", "sha256"}),
    ):
        for index, value in enumerate(rows):
            context = f"pdftex_input_audit.{kind}_inputs[{index}]"
            row = expect_dict(value, context)
            require_exact_keys(row, required_keys, context)
            if row.get("job") not in {"book", "jhanswer"}:
                raise PublicationError(f"{context}.job differs")
            require_string(row, "name", context)
            require_string(row, "suffix", context)
            if require_integer(row, "bytes", context) <= 0:
                raise PublicationError(f"{context}.bytes is not positive")
            require_sha(row.get("sha256"), f"{context}.sha256")
            if kind == "controlled":
                require_string(row, "closure_path", context)
    input_audit_stable = {
        key: input_audit_report[key]
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
    input_audit_canonical = sha256_bytes(
        json.dumps(
            input_audit_stable,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if (
        require_sha(input_audit_report.get("canonical_sha256"), "pdftex_input_audit.canonical")
        != input_audit_canonical
    ):
        raise PublicationError("pdfTeX input-audit canonical SHA-256 differs")
    input_audit_file = {
        **input_audit_stable,
        "canonical_sha256": input_audit_canonical,
    }
    input_audit_payload = canonical_bytes(input_audit_file, pretty=True)
    input_audit_payload_crlf = input_audit_payload.replace(b"\n", b"\r\n")
    valid_input_audit_bindings = {
        (len(input_audit_payload), sha256_bytes(input_audit_payload)),
        (len(input_audit_payload_crlf), sha256_bytes(input_audit_payload_crlf)),
    }
    if (
        require_integer(input_audit_report, "bytes", "pdftex_input_audit"),
        require_sha(input_audit_report.get("sha256"), "pdftex_input_audit.sha256"),
    ) not in valid_input_audit_bindings:
        raise PublicationError("pdfTeX input-audit artifact binding differs")
    pdftex_input_audit = {key: input_audit_report[key] for key in input_audit_keys}

    build_tools = expect_dict(report.get("build_tools"), "build_report.build_tools")
    tool_versions = expect_dict(
        report.get("tool_versions"), "build_report.tool_versions"
    )
    if set(build_tools) != set(EXPECTED_BUILD_TOOL_PATHS) or not tool_versions:
        raise PublicationError("build fingerprint tool closure is empty")
    build_tool_sha256: dict[str, str] = {}
    for name, value in sorted(build_tools.items()):
        if not isinstance(name, str) or not name:
            raise PublicationError("build-report tool name is invalid")
        details = expect_dict(value, f"build_report.build_tools.{name}")
        build_tool_sha256[name] = require_sha(
            details.get("sha256"), f"build_report.build_tools.{name}.sha256"
        )
    for name, value in tool_versions.items():
        if not isinstance(name, str) or not name or not isinstance(value, str) or not value:
            raise PublicationError("build-report tool-version closure is invalid")

    font_dependencies_report = expect_dict(
        report.get("pdftex_font_dependencies"),
        "build_report.pdftex_font_dependencies",
    )
    if not font_dependencies_report:
        raise PublicationError("build fingerprint pdfTeX font dependency closure is empty")
    font_dependencies: dict[str, dict[str, Any]] = {}
    font_dependency_bytes = 0
    for name, value in sorted(font_dependencies_report.items()):
        if not isinstance(name, str) or not name:
            raise PublicationError("build-report pdfTeX font dependency name is invalid")
        details = expect_dict(value, f"build_report.pdftex_font_dependencies.{name}")
        byte_count = require_integer(
            details,
            "bytes",
            f"build_report.pdftex_font_dependencies.{name}",
        )
        if byte_count <= 0:
            raise PublicationError(
                f"build-report pdfTeX font dependency byte count is invalid: {name}"
            )
        font_dependencies[name] = {
            "bytes": byte_count,
            "sha256": require_sha(
                details.get("sha256"),
                f"build_report.pdftex_font_dependencies.{name}.sha256",
            ),
        }
        font_dependency_bytes += byte_count
    if set(font_dependencies) != EXPECTED_PDFTEX_FONT_DEPENDENCY_NAMES:
        raise PublicationError("build-report pdfTeX font dependency names differ")
    if font_dependency_bytes != EXPECTED_PDFTEX_FONT_DEPENDENCY_BYTES:
        raise PublicationError("build-report pdfTeX font dependency bytes differ")
    font_end = expect_dict(
        report.get("pdftex_font_dependencies_end_verification"),
        "build_report.pdftex_font_dependencies_end_verification",
    )
    font_end_count = require_integer(
        font_end,
        "dependency_count",
        "build_report.pdftex_font_dependencies_end_verification",
    )
    font_end_bytes = require_integer(
        font_end,
        "bytes",
        "build_report.pdftex_font_dependencies_end_verification",
    )
    if (
        font_end.get("all_verified") is not True
        or font_end_count != len(font_dependencies)
        or font_end_bytes != font_dependency_bytes
    ):
        raise PublicationError("build-report pdfTeX font end verification is inconsistent")

    font_closure_report = expect_dict(
        report.get("pdftex_font_closure"),
        "build_report.pdftex_font_closure",
    )
    font_closure_keys = {
        "file_count",
        "bytes",
        "tree_sha256",
        "sha256sums_bytes",
        "sha256sums_sha256",
        "third_party_notices_bytes",
        "third_party_notices_sha256",
        "readme_bytes",
        "readme_sha256",
    }
    require_exact_keys(
        font_closure_report,
        font_closure_keys,
        "build_report.pdftex_font_closure",
        optional={"path"},
    )
    font_closure: dict[str, Any] = {}
    for key in (
        "file_count",
        "bytes",
        "sha256sums_bytes",
        "third_party_notices_bytes",
        "readme_bytes",
    ):
        value = require_integer(
            font_closure_report,
            key,
            "build_report.pdftex_font_closure",
        )
        if value <= 0:
            raise PublicationError(
                f"build_report.pdftex_font_closure.{key} is not positive"
            )
        font_closure[key] = value
    for key in (
        "tree_sha256",
        "sha256sums_sha256",
        "third_party_notices_sha256",
        "readme_sha256",
    ):
        font_closure[key] = require_sha(
            font_closure_report.get(key),
            f"build_report.pdftex_font_closure.{key}",
        )
    font_closure = {
        key: font_closure[key]
        for key in (
            "file_count",
            "bytes",
            "tree_sha256",
            "sha256sums_bytes",
            "sha256sums_sha256",
            "third_party_notices_bytes",
            "third_party_notices_sha256",
            "readme_bytes",
            "readme_sha256",
        )
    }
    if (
        font_closure["file_count"] != EXPECTED_PDFTEX_FONT_CLOSURE_FILE_COUNT
        or font_closure["bytes"] != EXPECTED_PDFTEX_FONT_CLOSURE_BYTES
        or font_closure["tree_sha256"]
        != EXPECTED_PDFTEX_FONT_CLOSURE_TREE_SHA256
    ):
        raise PublicationError("build-report pdfTeX font closure identity differs")

    font_closure_end_report = expect_dict(
        report.get("pdftex_font_closure_end_verification"),
        "build_report.pdftex_font_closure_end_verification",
    )
    require_exact_keys(
        font_closure_end_report,
        {"file_count", "bytes", "tree_sha256", "all_verified"},
        "build_report.pdftex_font_closure_end_verification",
    )
    font_closure_end_count = require_integer(
        font_closure_end_report,
        "file_count",
        "build_report.pdftex_font_closure_end_verification",
    )
    font_closure_end_bytes = require_integer(
        font_closure_end_report,
        "bytes",
        "build_report.pdftex_font_closure_end_verification",
    )
    font_closure_end_tree_sha256 = require_sha(
        font_closure_end_report.get("tree_sha256"),
        "build_report.pdftex_font_closure_end_verification.tree_sha256",
    )
    font_closure_end_all_verified = require_boolean(
        font_closure_end_report,
        "all_verified",
        "build_report.pdftex_font_closure_end_verification",
    )
    if (
        font_closure_end_all_verified is not True
        or font_closure_end_count != font_closure["file_count"]
        or font_closure_end_bytes != font_closure["bytes"]
        or font_closure_end_tree_sha256 != font_closure["tree_sha256"]
    ):
        raise PublicationError(
            "build-report pdfTeX font closure end verification is inconsistent"
        )
    font_closure_end = {
        "file_count": font_closure_end_count,
        "bytes": font_closure_end_bytes,
        "tree_sha256": font_closure_end_tree_sha256,
        "all_verified": True,
    }

    report_pdfs = expect_dict(report.get("pdfs"), "build_report.pdfs")
    if set(report_pdfs) != {"book", "jhanswer", "lab"}:
        raise PublicationError("build fingerprint PDF closure is not exactly book/jhanswer/lab")
    pdfs: dict[str, dict[str, Any]] = {}
    for name, value in sorted(report_pdfs.items()):
        details = expect_dict(value, f"build_report.pdfs.{name}")
        pages = require_integer(details, "pages", f"build_report.pdfs.{name}")
        byte_count = require_integer(details, "bytes", f"build_report.pdfs.{name}")
        if pages <= 0 or byte_count <= 0:
            raise PublicationError(f"build fingerprint PDF dimensions are invalid: {name}")
        pdfs[name] = {
            "pages": pages,
            "bytes": byte_count,
            "sha256": require_sha(
                details.get("sha256"), f"build_report.pdfs.{name}.sha256"
            ),
        }
    return {
        "schema_version": "hefferon-id-build-reproducibility-v4",
        "source_tree_sha256": require_sha(
            source.get("tree_sha256"), "build_report.source.tree_sha256"
        ),
        "authority_pdf_sha256": {
            "book": require_sha(
                authority_book_pdf.get("sha256"),
                "build_report.authority_book_pdf.sha256",
            ),
            "lab": require_sha(
                authority_lab_pdf.get("sha256"),
                "build_report.authority_lab_pdf.sha256",
            ),
        },
        "book_graphics_manifest_sha256": require_sha(
            book_graphics.get("manifest_sha256"),
            "build_report.book_graphics.manifest_sha256",
        ),
        "lab_graphics_manifest_sha256": require_sha(
            lab_graphics.get("manifest_sha256"),
            "build_report.lab_graphics.manifest_sha256",
        ),
        "missing_lab_asset_manifest_sha256": require_sha(
            missing_lab_asset.get("manifest_sha256"),
            "build_report.missing_lab_asset.manifest_sha256",
        ),
        "lab_sagetex_stable_fingerprint": expect_dict(
            lab_sagetex.get("stable_fingerprint"),
            "build_report.lab_sagetex.stable_fingerprint",
        ),
        "metapost_assets": metapost,
        "metapost_assets_end_verification": metapost_end,
        "generated_answer_stream": answer_stream,
        "tex_convergence": tex_convergence,
        "pdftex_input_audit": pdftex_input_audit,
        "build_tool_sha256": build_tool_sha256,
        "tool_versions": dict(tool_versions),
        "pdftex_font_dependencies": font_dependencies,
        "pdftex_font_dependencies_end_verification": {
            "dependency_count": font_end_count,
            "bytes": font_end_bytes,
            "all_verified": True,
        },
        "pdftex_font_closure": font_closure,
        "pdftex_font_closure_end_verification": font_closure_end,
        "pdfs": pdfs,
    }


def validate_build_reproducibility(
    report: dict[str, Any], reproducibility: dict[str, Any]
) -> dict[str, Any]:
    if reproducibility.get("matched") is not True:
        raise PublicationError("second-build reproducibility match is not true")
    current = expect_dict(
        reproducibility.get("current"), "build_report.reproducibility.current"
    )
    baseline = expect_dict(
        reproducibility.get("baseline"), "build_report.reproducibility.baseline"
    )
    reconstructed = reconstruct_build_fingerprint(report)
    if (
        current.get("schema_version") != "hefferon-id-build-reproducibility-v4"
        or baseline != current
    ):
        raise PublicationError("build reproducibility-v4 fingerprint closure differs")
    if current != reconstructed:
        raise PublicationError(
            "build reproducibility-v4 fingerprint differs from live build-report fields"
        )
    canonical_sha256 = sha256_bytes(canonical_bytes(current, pretty=True))
    if (
        require_sha(
            reproducibility.get("sha256"), "build_report.reproducibility.sha256"
        )
        != canonical_sha256
        or require_sha(
            reproducibility.get("current_sha256"),
            "build_report.reproducibility.current_sha256",
        )
        != canonical_sha256
    ):
        raise PublicationError("build reproducibility-v4 canonical SHA-256 differs")
    return reconstructed


def validate_v4_reproducibility_sidecars(
    plan: dict[str, Any], root: Path, report: dict[str, Any]
) -> dict[str, Any]:
    metapost_binding = expect_dict(
        report.get("metapost_assets"), "build_report.metapost_assets"
    )
    metapost_relative = plan["qa"]["metapost_asset_manifest"]
    metapost_path = ensure_under(root / metapost_relative, root)
    metapost_payload = metapost_path.read_bytes()
    metapost_sidecar = load_json(metapost_path)
    metapost_core = {
        key: metapost_binding[key]
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
    reported_metapost_path = require_string(
        metapost_binding, "manifest_path", "build_report.metapost_assets"
    ).replace("\\", "/")
    if (
        not reported_metapost_path.endswith("/" + metapost_relative)
        and reported_metapost_path != metapost_relative
    ):
        raise PublicationError("MetaPost sidecar path differs from the publication plan")
    if (
        metapost_sidecar != metapost_core
        or require_integer(metapost_binding, "manifest_bytes", "metapost_assets")
        != len(metapost_payload)
        or require_sha(metapost_binding.get("manifest_sha256"), "metapost_assets.sha256")
        != sha256_bytes(metapost_payload)
    ):
        raise PublicationError("MetaPost sidecar differs from its build-report binding")

    input_binding = expect_dict(
        report.get("pdftex_input_audit"), "build_report.pdftex_input_audit"
    )
    input_relative = plan["qa"]["pdftex_input_audit"]
    input_path = ensure_under(root / input_relative, root)
    input_payload = input_path.read_bytes()
    input_sidecar = load_json(input_path)
    input_core = {
        key: input_binding[key]
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
    reported_input_path = require_string(
        input_binding, "path", "build_report.pdftex_input_audit"
    ).replace("\\", "/")
    if (
        not reported_input_path.endswith("/" + input_relative)
        and reported_input_path != input_relative
    ):
        raise PublicationError("pdfTeX input-audit path differs from the publication plan")
    if (
        input_sidecar != input_core
        or require_integer(input_binding, "bytes", "pdftex_input_audit")
        != len(input_payload)
        or require_sha(input_binding.get("sha256"), "pdftex_input_audit.sha256")
        != sha256_bytes(input_payload)
    ):
        raise PublicationError("pdfTeX input-audit sidecar differs from its binding")
    return {
        "metapost": {
            "path": metapost_relative,
            "bytes": len(metapost_payload),
            "sha256": sha256_bytes(metapost_payload),
            "asset_count": metapost_core["asset_count"],
        },
        "pdftex_input_audit": {
            "path": input_relative,
            "bytes": len(input_payload),
            "sha256": sha256_bytes(input_payload),
            "all_private": True,
        },
    }


def strict_readiness(plan: dict[str, Any], root: Path) -> dict[str, Any]:
    report_path = ensure_under(root / plan["qa"]["build_report"], root)
    report = load_json(report_path)
    if report.get("status") != plan["qa"]["required_status"]:
        raise PublicationError(f"build status is not {plan['qa']['required_status']!r}")
    source = expect_dict(report.get("source"), "build_report.source")
    if source.get("unchanged_during_build") is not True:
        raise PublicationError("source-unchanged build gate is not true")
    source_tree = require_string(source, "tree_sha256", "build_report.source")
    require_sha(source_tree, "build_report.source.tree_sha256")
    source_root = ensure_under(root / plan["qa"]["source_root"], root)
    source_rows, live_source_tree = canonical_source_tree(source_root)
    if live_source_tree != source_tree:
        raise PublicationError("current translated source tree differs from the built tree")
    if require_integer(source, "file_count", "build_report.source") != len(source_rows):
        raise PublicationError("build-report source file count differs from current source")
    if require_integer(source, "live_end_file_count", "build_report.source") != len(
        source_rows
    ):
        raise PublicationError("build-report end source count differs from current source")
    if source.get("live_end_tree_sha256") != live_source_tree:
        raise PublicationError("build-report end source tree differs from current source")
    source_manifest_path = ensure_under(
        root / plan["qa"]["staged_source_manifest"], root
    )
    source_manifest = load_json(source_manifest_path)
    require_exact_keys(
        source_manifest, {"tree_sha256", "files"}, "staged source manifest"
    )
    manifest_tree = require_sha(
        source_manifest.get("tree_sha256"), "staged source manifest.tree_sha256"
    )
    manifest_rows = expect_list(source_manifest.get("files"), "staged source manifest.files")
    if manifest_tree != live_source_tree or manifest_rows != source_rows:
        raise PublicationError(
            "staged-source manifest does not exactly bind the current translated source"
        )
    reproducibility = expect_dict(report.get("reproducibility"), "build_report.reproducibility")
    validate_build_reproducibility(report, reproducibility)
    qa_summary = expect_dict(report.get("qa_summary"), "build_report.qa_summary")
    if require_integer(qa_summary, "undefined_reference_lines", "qa_summary") != 0:
        raise PublicationError("undefined-reference count is not zero")
    if require_integer(qa_summary, "generated_english_label_hits", "qa_summary") != 0:
        raise PublicationError("generated-English-label count is not zero")
    if require_integer(qa_summary, "runtime_placeholder_lines", "qa_summary") != 0:
        raise PublicationError("runtime-placeholder count is not zero")
    cross = expect_dict(report.get("cross_pdf_link_audit"), "cross_pdf_link_audit")
    if cross.get("all_pair_actions_resolved") is not True:
        raise PublicationError("cross-PDF link resolution is not true")
    report_pdfs = expect_dict(report.get("pdfs"), "build_report.pdfs")
    report_keys = {"textbook": "book", "worked-answers": "jhanswer", "sage-lab": "lab"}
    pdfs: list[dict[str, Any]] = []
    for item_value in plan["reader_pdfs"]:
        item = expect_dict(item_value, "reader_pdf")
        key = report_keys[item["component"]]
        details = expect_dict(report_pdfs.get(key), f"build_report.pdfs.{key}")
        expected_bytes = require_integer(details, "bytes", f"pdfs.{key}")
        expected_sha = require_string(details, "sha256", f"pdfs.{key}")
        pages = require_integer(details, "pages", f"pdfs.{key}")
        if expected_bytes <= 0 or pages <= 0 or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise PublicationError(f"invalid bytes/SHA/pages binding for PDF {key}")
        path = ensure_under(root / item["source"], root)
        if (
            not path.is_file()
            or path.stat().st_size != expected_bytes
            or sha256_file(path) != expected_sha
        ):
            raise PublicationError(f"PDF differs from mandatory report binding: {key}")
        pdfs.append(
            {
                "component": item["component"],
                "source": item["source"],
                "release_name": item["release_name"],
                "bytes": expected_bytes,
                "sha256": expected_sha,
                "pages": pages,
            }
        )
    if set(report_pdfs) != {"book", "jhanswer", "lab"}:
        raise PublicationError("build report PDF closure is not exactly book/jhanswer/lab")
    reproducibility_sidecars = validate_v4_reproducibility_sidecars(
        plan, root, report
    )
    all_page_renders = validate_all_page_render_manifest(
        plan, root, report, report_pdfs
    )
    final_pdf_qa = validate_final_pdf_qa(
        plan, root, report, report_pdfs, all_page_renders
    )
    final_visual_review = validate_final_visual_review(
        plan, root, report_pdfs, all_page_renders, final_pdf_qa
    )
    cross_pdf_sidecar = validate_cross_pdf_sidecar(plan, root, report)
    lab_sagetex_sidecar = validate_lab_sagetex_sidecar(plan, root, report)
    backend = run_backend_validator(plan, root)
    live_build_inputs = validate_live_build_inputs(root, report)
    return {
        "source_tree_sha256": source_tree,
        "build_report_sha256": sha256_file(report_path),
        "pdfs": pdfs,
        "all_page_renders": all_page_renders,
        "final_pdf_qa": final_pdf_qa,
        "final_visual_review": final_visual_review,
        "cross_pdf_sidecar": cross_pdf_sidecar,
        "lab_sagetex_sidecar": lab_sagetex_sidecar,
        "reproducibility_sidecars": reproducibility_sidecars,
        "live_build_inputs": live_build_inputs,
        "backend": backend,
    }


def baseline_relative(
    plan: dict[str, Any],
    root: Path = PROJECT,
    *,
    require_report: bool = True,
) -> str | None:
    report_path = ensure_under(root / plan["qa"]["build_report"], root)
    if not report_path.is_file():
        if require_report:
            raise PublicationError("build report needed to bind the reproducibility baseline is missing")
        return None
    report = load_json(report_path)
    reproducibility = expect_dict(report.get("reproducibility"), "reproducibility")
    value = require_string(reproducibility, "path", "reproducibility")
    path = Path(value)
    if path.is_absolute():
        relative: str | None = None
        for candidate_root in (PROJECT, root):
            try:
                relative = lexical_relative(ensure_under(path, candidate_root), candidate_root)
                break
            except PublicationError:
                continue
        if relative is None:
            raise PublicationError("recorded reproducibility baseline is outside the project")
    else:
        relative = validate_relative_name(value, "reproducibility baseline")
    staged_path = ensure_under(root / relative, root)
    if not staged_path.is_file() or staged_path.is_symlink():
        raise PublicationError("recorded reproducibility baseline is missing")
    return relative


def staging_input_inventory(
    plan: dict[str, Any], root: Path, *, require_complete: bool
) -> tuple[list[dict[str, Any]], str]:
    """Hash only the plan's bounded staging inputs and reproducibility witness.

    Missing configured inputs are represented in preflight bindings so a later
    completed build necessarily receives a new transaction fingerprint.  A
    package/publish stage requires the complete closure.
    """

    includes = list(require_string_list(plan.get("staging_inputs"), "staging_inputs", unique=True))
    baseline = baseline_relative(plan, root, require_report=require_complete)
    if baseline is not None and baseline not in includes:
        includes.append(baseline)
    files: dict[str, Path] = {}
    missing: set[str] = set()
    for relative_value in includes:
        relative = validate_relative_name(relative_value, "staging input")
        target = ensure_under(root / relative, root)
        if not target.exists():
            if require_complete:
                raise PublicationError(f"required bounded staging input is missing: {relative}")
            missing.add(relative)
            continue
        if target.is_symlink():
            raise PublicationError(f"symbolic link rejected from staging input: {relative}")
        expanded = expand_includes(root, [relative], plan)
        if target.is_file() and not expanded:
            raise PublicationError(f"required staging input is excluded: {relative}")
        for candidate in expanded:
            key = lexical_relative(candidate, root)
            prior = files.get(key)
            if prior is not None and prior != candidate:
                raise PublicationError(f"staging input path collision: {key}")
            files[key] = candidate
    folded: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    for relative in sorted(files):
        folded_name = relative.casefold()
        if folded_name in folded and folded[folded_name] != relative:
            raise PublicationError("staging input contains a case-folded path collision")
        folded[folded_name] = relative
        path = files[relative]
        before = path.stat()
        digest = sha256_file(path)
        after = path.stat()
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
            raise PublicationError(f"staging input changed while hashing: {relative}")
        rows.append(
            {
                "path": relative,
                "kind": "file",
                "bytes": after.st_size,
                "sha256": digest,
            }
        )
    for relative in sorted(missing):
        rows.append({"path": relative, "kind": "missing"})
    rows.sort(key=lambda item: (item["path"], item["kind"]))
    return rows, sha256_bytes(canonical_bytes(rows))


def assert_snapshot_input_closure(snapshot: Path, input_rows: list[dict[str, Any]]) -> None:
    expected = {
        row["path"]: (row["bytes"], row["sha256"])
        for row in input_rows
        if row.get("kind") == "file"
    }
    actual = {
        row["path"]: (row["bytes"], row["sha256"])
        for row in inventory_rows(snapshot)
    }
    if actual != expected:
        raise PublicationError("base snapshot file closure differs from the bound staging inputs")


def prepare_base_stage(
    plan: dict[str, Any], binding: dict[str, str], state: dict[str, Any]
) -> tuple[Path, dict[str, Any]]:
    transaction_root = TRANSACTIONS / binding["fingerprint"]
    base = transaction_root / "base"
    if base.is_dir():
        manifest = verify_inventory(base, binding)
        if manifest.get("stage") != "base":
            raise PublicationError("base immutable inventory stage marker differs")
        readiness = expect_dict(manifest.get("readiness"), "base readiness")
        _live_rows, live_input_digest = staging_input_inventory(
            plan, PROJECT, require_complete=True
        )
        if live_input_digest != binding["input_inventory_sha256"]:
            raise PublicationError("live staging inputs differ from the transaction binding")
        live_readiness = strict_readiness(plan, PROJECT)
        if live_readiness != readiness:
            raise PublicationError("live readiness differs from the frozen base readiness")
        _live_end_rows, live_end_digest = staging_input_inventory(
            plan, PROJECT, require_complete=True
        )
        if live_end_digest != binding["input_inventory_sha256"]:
            raise PublicationError("live staging inputs changed during base reuse validation")
        pin_inventory(state, "base_inventory_sha256", manifest, base)
        save_state(state)
        return base, readiness
    if base.exists():
        raise PublicationError("base staging target exists but is not a valid directory")
    transaction_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix="base-", suffix=".tmp", dir=transaction_root)
    )
    try:
        snapshot = temporary / "snapshot"
        snapshot.mkdir()
        live_rows, live_input_digest = staging_input_inventory(
            plan, PROJECT, require_complete=True
        )
        if live_input_digest != binding["input_inventory_sha256"]:
            raise PublicationError("live staging inputs changed after transaction binding")
        live_files = [
            (
                validate_relative_name(row["path"], "staging input"),
                ensure_under(PROJECT / row["path"], PROJECT),
            )
            for row in live_rows
            if row["kind"] == "file"
        ]
        for relative, source in live_files:
            copy_stable(source, snapshot / relative)
        staged_rows, staged_input_digest = staging_input_inventory(
            plan, snapshot, require_complete=True
        )
        if staged_input_digest != binding["input_inventory_sha256"]:
            raise PublicationError("staged input inventory differs from the transaction binding")
        staged_plan = snapshot / lexical_relative(PLAN_PATH, PROJECT)
        staged_driver = snapshot / lexical_relative(Path(__file__).resolve(), PROJECT)
        if (
            sha256_file(staged_plan) != binding["plan_sha256"]
            or sha256_file(staged_driver) != binding["driver_sha256"]
        ):
            raise PublicationError("staged plan/driver bytes differ from the transaction binding")
        readiness = strict_readiness(plan, snapshot)
        staged_end_rows, staged_end_digest = staging_input_inventory(
            plan, snapshot, require_complete=True
        )
        if staged_end_digest != binding["input_inventory_sha256"]:
            raise PublicationError("staged inputs changed during readiness validation")
        if staged_end_rows != staged_rows:
            raise PublicationError("staged input inventory changed during readiness validation")
        assert_snapshot_input_closure(snapshot, staged_end_rows)
        rows = inventory_rows(temporary, omit={"inventory.json"})
        manifest = {
            "schema_version": "hefferon-id-immutable-inventory-v1",
            "stage": "base",
            "binding": binding,
            "inventory_sha256": inventory_digest(rows),
            "file_count": len(rows),
            "files": rows,
            "readiness": readiness,
        }
        save_json(temporary / "inventory.json", manifest)
        verify_inventory(temporary, binding)
        os.replace(temporary, base)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    manifest = verify_inventory(base, binding)
    if manifest.get("stage") != "base":
        raise PublicationError("base immutable inventory stage marker differs")
    pin_inventory(state, "base_inventory_sha256", manifest, base)
    save_state(state)
    return base, expect_dict(manifest["readiness"], "base readiness")


def github_release_url(plan: dict[str, Any]) -> str:
    return (
        f"https://github.com/{plan['github']['owner']}/{plan['github']['repository']}"
        f"/releases/tag/{plan['release']['tag']}"
    )


def transaction_marker(fingerprint: str) -> str:
    return f"hefferon-id-transaction:{fingerprint}"


def release_description(
    plan: dict[str, Any], doi: str | None, fingerprint: str
) -> str:
    doi_text = f"https://doi.org/{doi}" if doi else "DOI sedang direservasi"
    return (
        "Edisi lengkap Bahasa Indonesia (id-ID) dari Linear Algebra, edisi "
        "keempat, karya Jim Hefferon. Korpus pembaca mencakup buku teks, buku "
        "jawaban dengan solusi lengkap, dan laboratorium Sage. Sumber LaTeX, "
        "backend modular bebas-lokal, bukti build ganda, pemeriksaan tautan "
        "lintas-PDF, serta manifes hash disertakan. Terjemahan dan produksi "
        "dilakukan oleh Codex atas permintaan pengguna. "
        f"{plan['release']['model_provenance']} Ini bukan edisi resmi "
        "Jim Hefferon dan tidak menyiratkan dukungan beliau. Otoritas sumber "
        f"dipin pada komit {plan['authority']['source_commit']} di "
        f"{plan['authority']['source_commit_url']}. DOI edisi: {doi_text}. "
        f"Penanda transaksi: {transaction_marker(fingerprint)}."
    )


def zenodo_metadata(
    plan: dict[str, Any], doi: str | None, fingerprint: str
) -> dict[str, Any]:
    return {
        "title": plan["release"]["title"],
        "upload_type": plan["zenodo"]["upload_type"],
        "publication_type": plan["zenodo"]["publication_type"],
        "description": release_description(plan, doi, fingerprint),
        "creators": [{"name": plan["zenodo"]["creator"]}],
        "publication_date": plan["release"]["publication_date"],
        "version": plan["release"]["version"],
        "language": plan["zenodo"]["language"],
        "access_right": plan["zenodo"]["access_right"],
        "license": plan["rights"]["selected_license_id"],
        "keywords": plan["zenodo"]["keywords"],
        "notes": plan["rights"]["route"] + " " + transaction_marker(fingerprint),
        "related_identifiers": [
            {
                "identifier": plan["authority"]["source_commit_url"],
                "relation": "isDerivedFrom",
                "resource_type": "software",
            }
        ],
    }


def plain_text(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return " ".join(html.unescape(text).split())


def normalize_zenodo_metadata(metadata_value: Any, *, public: bool) -> dict[str, Any]:
    metadata = expect_dict(metadata_value, "Zenodo metadata")
    creator_names: list[str] = []
    for index, creator_value in enumerate(expect_list(metadata.get("creators"), "creators")):
        creator = expect_dict(creator_value, f"creators[{index}]")
        name = creator.get("name")
        if name is None and isinstance(creator.get("person_or_org"), dict):
            name = creator["person_or_org"].get("name")
        if not isinstance(name, str) or not name:
            raise PublicationError("Zenodo creator name is malformed")
        creator_names.append(name)
    license_value = metadata.get("license")
    license_id = license_value.get("id") if isinstance(license_value, dict) else license_value
    access_value = metadata.get("access_right")
    access_id = access_value.get("id") if isinstance(access_value, dict) else access_value
    language_value = metadata.get("language")
    if language_value is None:
        language_value = metadata.get("languages")
    if isinstance(language_value, list):
        language_ids = [
            item.get("id") if isinstance(item, dict) else item for item in language_value
        ]
        language = language_ids[0] if len(language_ids) == 1 else language_ids
    elif isinstance(language_value, dict):
        language = language_value.get("id")
    else:
        language = language_value
    if public:
        resource = expect_dict(metadata.get("resource_type"), "resource_type")
        resource_id = resource.get("id")
        publication_type = resource.get("subtype")
        upload_type = resource.get("type")
        if (
            (upload_type is None or publication_type is None)
            and isinstance(resource_id, str)
            and "-" in resource_id
        ):
            upload_type, publication_type = resource_id.split("-", 1)
    else:
        upload_type = metadata.get("upload_type")
        publication_type = metadata.get("publication_type")
    related: list[tuple[str, str, str | None]] = []
    for index, item_value in enumerate(metadata.get("related_identifiers") or []):
        item = expect_dict(item_value, f"related_identifiers[{index}]")
        related.append(
            (
                str(item.get("identifier")),
                str(item.get("relation", {}).get("id"))
                if isinstance(item.get("relation"), dict)
                else str(item.get("relation")),
                (
                    str(item.get("resource_type", {}).get("id"))
                    if isinstance(item.get("resource_type"), dict)
                    else str(item.get("resource_type"))
                )
                if item.get("resource_type") is not None
                else None,
            )
        )
    return {
        "title": metadata.get("title"),
        "upload_type": upload_type,
        "publication_type": publication_type,
        "description": plain_text(metadata.get("description")),
        "creators": creator_names,
        "publication_date": metadata.get("publication_date"),
        "version": metadata.get("version"),
        "language": language,
        "access_right": access_id,
        "license": license_id,
        "keywords": sorted(str(item) for item in (metadata.get("keywords") or [])),
        "notes": plain_text(metadata.get("notes")),
        "related_identifiers": sorted(related),
    }


def assert_zenodo_metadata(
    actual: Any, plan: dict[str, Any], doi: str, fingerprint: str, *, public: bool
) -> None:
    expected = normalize_zenodo_metadata(
        zenodo_metadata(plan, doi, fingerprint), public=False
    )
    normalized = normalize_zenodo_metadata(actual, public=public)
    # Legacy deposition language may be surfaced as an ISO id; both must be exact.
    if normalized != expected:
        raise PublicationError(
            "Zenodo metadata differs from the complete normalized transaction metadata"
        )


def deterministic_zip(
    destination: Path,
    sources: list[Path],
    root: Path,
    *,
    public_safe: bool = False,
) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(name)
    entries: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for source in sources:
                relative = lexical_relative(source, root)
                payload = source.read_bytes()
                if public_safe:
                    payload = public_safe_payload(
                        payload,
                        redact_bare_identifier=relative.startswith(
                            "build/hefferon_id/logs/"
                        ),
                    )
                info = zipfile.ZipInfo(relative, FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                mode = 0o755 if source.suffix.lower() in {".sh", ".bat", ".cmd"} else 0o644
                info.external_attr = (mode & 0xFFFF) << 16
                info.create_system = 3
                archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
                entries.append(
                    {
                        "path": relative,
                        "bytes": len(payload),
                        "sha256": sha256_bytes(payload),
                    }
                )
        os.replace(temporary, destination)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
    with zipfile.ZipFile(destination, "r") as archive:
        names = archive.namelist()
        bad = archive.testzip()
    if bad is not None or names != [item["path"] for item in entries]:
        raise PublicationError(f"deterministic ZIP verification failed: {destination.name}")
    return {
        "path": destination.name,
        "bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        "entry_count": len(entries),
        "uncompressed_bytes": sum(item["bytes"] for item in entries),
        "entries_sha256": sha256_bytes(canonical_bytes(entries)),
    }


def public_safe_payload(
    payload: bytes, *, redact_bare_identifier: bool = False
) -> bytes:
    """Remove the local home-directory identity from UTF-8 publication evidence."""
    identifier = Path.home().name
    if identifier:
        forms = {identifier, identifier.casefold(), identifier.upper()}
        if any(
            value.encode(encoding) in payload
            for encoding in ("utf-16-le", "utf-16-be")
            for value in forms
        ):
            raise PublicationError("public binary evidence contains the local user identifier")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        if payload_contains_local_identifier(payload):
            raise PublicationError("public binary evidence contains the local user identifier")
        return payload
    home = str(Path.home())
    replacements = {
        json.dumps(home)[1:-1]: "%USERPROFILE%",
        json.dumps(Path.home().as_posix())[1:-1]: "%USERPROFILE%",
        home: "%USERPROFILE%",
        Path.home().as_posix(): "%USERPROFILE%",
    }
    for private, portable in sorted(replacements.items(), key=lambda item: -len(item[0])):
        text = text.replace(private, portable)
    if redact_bare_identifier and identifier:
        # TeX wraps long paths across log lines, leaving the account name
        # detached from its home prefix.  These are generated diagnostics, so
        # redact the detached token only in their public ZIP representation.
        text = re.sub(re.escape(identifier), "%USER%", text, flags=re.IGNORECASE)
    reject_local_user_identifier(text, "public evidence")
    return text.encode("utf-8")


def payload_contains_local_identifier(payload: bytes) -> bool:
    identifier = Path.home().name
    if not identifier:
        return False
    try:
        if identifier.casefold() in payload.decode("utf-8").casefold():
            return True
    except UnicodeDecodeError:
        pass
    forms = {identifier, identifier.casefold(), identifier.upper()}
    for encoding in ("utf-8", "utf-16-le", "utf-16-be"):
        for value in forms:
            encoded = value.encode(encoding)
            if encoded and encoded in payload:
                return True
    return False


def assert_public_safe_file(path: Path) -> None:
    if payload_contains_local_identifier(path.read_bytes()):
        raise PublicationError(f"public artifact contains a local user identifier: {path.name}")


def release_readme(
    plan: dict[str, Any], doi: str, fingerprint: str, artifacts: list[dict[str, Any]], readiness: dict[str, Any]
) -> bytes:
    lines = [
        f"# {plan['release']['title']}",
        "",
        f"Versi: `{plan['release']['version']}`  ",
        f"Tanggal: `{plan['release']['publication_date']}`  ",
        f"DOI dan rekaman utama: <https://doi.org/{doi}>",
        "",
        "Keluaran pembaca terdiri atas buku teks lengkap, buku jawaban dengan solusi lengkap, dan laboratorium Sage. Edisi ini diterjemahkan dan diproduksi oleh Codex atas permintaan pengguna; ini bukan edisi resmi Jim Hefferon.",
        "",
        plan["release"]["model_provenance"],
        "",
        "## Otoritas dan hak",
        "",
        f"Sumber dipin pada `{plan['authority']['source_commit']}` (pohon `{plan['authority']['source_tree']}`). Jalur lisensi yang dipilih adalah [{plan['rights']['selected_license_name']}]({plan['rights']['selected_license_url']}). Komponen tertanam tetap mengikuti pemberitahuan masing-masing.",
        "",
        "## Aset rilis",
        "",
    ]
    for item in artifacts:
        pages = f", {item['pages']} halaman" if item.get("pages") else ""
        lines.append(
            f"- `{item['path']}` — {item['bytes']:,} byte{pages}; SHA-256 `{item['sha256']}`"
        )
    lines.extend(
        [
            "",
            f"Penanda transaksi: `{transaction_marker(fingerprint)}`.",
            f"Pohon sumber terjemahan: `{readiness['source_tree_sha256']}`.",
            "Build kedua identik dengan baseline; backend final, tautan lintas-PDF, dan render seluruh halaman telah lulus.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def pages_html(plan: dict[str, Any], doi: str, fingerprint: str) -> bytes:
    title = plan["release"]["title"]
    return f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>body{{margin:0 auto;max-width:52rem;padding:3rem 1.25rem;font:18px/1.6 system-ui,sans-serif;color:#17212b}}h1{{line-height:1.15}}.links{{display:flex;flex-wrap:wrap;gap:.75rem;margin:2rem 0}}.links a{{padding:.7rem 1rem;border-radius:.45rem;background:#0b5cab;color:white;text-decoration:none}}code{{overflow-wrap:anywhere}}</style></head>
<body><h1>{title}</h1><p>Buku teks lengkap, buku jawaban dengan solusi lengkap, dan laboratorium Sage dalam Bahasa Indonesia (<code>id-ID</code>), beserta sumber LaTeX dan backend modular.</p>
<div class="links"><a href="https://doi.org/{doi}">Unduh edisi dan lihat rekaman Zenodo</a></div>
<p>Karya asli: <em>Linear Algebra</em>, edisi keempat, oleh Jim Hefferon. Edisi turunan ini diproduksi oleh Codex atas permintaan pengguna dan bukan edisi resmi penulis. {plan['release']['model_provenance']}</p>
<p>Sumber: <code>{plan['authority']['source_commit']}</code>. Lisensi: CC BY-SA 2.5 untuk materi yang dicakup pemberitahuan hulu. Transaksi: <code>{fingerprint}</code>.</p></body></html>
""".encode("utf-8")


def staged_baseline_relative(snapshot: Path, plan: dict[str, Any]) -> str:
    report = load_json(snapshot / plan["qa"]["build_report"])
    reproducibility = expect_dict(report.get("reproducibility"), "reproducibility")
    path = Path(require_string(reproducibility, "path", "reproducibility"))
    if not path.is_absolute():
        path = PROJECT / path
    path = ensure_under(path, PROJECT)
    return lexical_relative(path, PROJECT)


def build_release_payloads(
    plan: dict[str, Any], snapshot: Path, asset_dir: Path, doi: str, binding: dict[str, str], readiness: dict[str, Any]
) -> list[dict[str, Any]]:
    asset_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, Any]] = []
    pdf_by_component = {item["component"]: item for item in readiness["pdfs"]}
    for item_value in plan["reader_pdfs"]:
        item = expect_dict(item_value, "reader_pdf")
        source = snapshot / item["source"]
        destination = asset_dir / item["release_name"]
        copy_stable(source, destination)
        bound = pdf_by_component[item["component"]]
        if destination.stat().st_size != bound["bytes"] or sha256_file(destination) != bound["sha256"]:
            raise PublicationError("staged release PDF differs from frozen report binding")
        artifacts.append(
            {
                "kind": "reader-pdf",
                "component": item["component"],
                "path": destination.name,
                "pages": bound["pages"],
                "bytes": bound["bytes"],
                "sha256": bound["sha256"],
            }
        )
    for bundle_value in plan["bundles"]:
        bundle = expect_dict(bundle_value, "bundle")
        includes = list(bundle["include"])
        if bundle["kind"] == "provenance-qa":
            baseline = staged_baseline_relative(snapshot, plan)
            if baseline not in includes:
                includes.append(baseline)
        destination = asset_dir / bundle["release_name"]
        result = deterministic_zip(
            destination,
            expand_includes(snapshot, includes, plan),
            snapshot,
            public_safe=True,
        )
        artifacts.append({"kind": bundle["kind"], **result})
    readme_name = plan["release_assets"]["readme"]
    readme_payload = release_readme(
        plan, doi, binding["fingerprint"], artifacts, readiness
    )
    atomic_write(asset_dir / readme_name, readme_payload)
    atomic_write(snapshot / "publication" / readme_name, readme_payload)
    readme_record = {
        "kind": "release-readme",
        "path": readme_name,
        "bytes": len(readme_payload),
        "sha256": sha256_bytes(readme_payload),
    }
    manifest = {
        "schema_version": "hefferon-id-release-manifest-v2",
        "title": plan["release"]["title"],
        "version": plan["release"]["version"],
        "tag": plan["release"]["tag"],
        "publication_date": plan["release"]["publication_date"],
        "doi": doi,
        "language": "id-ID",
        "transaction_fingerprint": binding["fingerprint"],
        "binding": binding,
        "authority": plan["authority"],
        "rights": plan["rights"],
        "rights_files": {
            name: {
                "bytes": (snapshot / name).stat().st_size,
                "sha256": sha256_file(snapshot / name),
            }
            for name in ("LICENSE", "NOTICE.id-ID.md")
        },
        "translation_credit": "Codex atas permintaan pengguna",
        "model_provenance": plan["release"]["model_provenance"],
        "source_tree_sha256": readiness["source_tree_sha256"],
        "build_report_sha256": readiness["build_report_sha256"],
        "backend_validation": readiness["backend"],
        "artifacts": artifacts + [readme_record],
        "self_hash": None,
        "self_hash_status": "excluded to avoid self-referential hashing",
    }
    manifest_name = plan["release_assets"]["manifest"]
    manifest_payload = canonical_bytes(manifest, pretty=True)
    atomic_write(asset_dir / manifest_name, manifest_payload)
    atomic_write(snapshot / "publication" / manifest_name, manifest_payload)
    manifest_record = {
        "kind": "release-manifest",
        "path": manifest_name,
        "bytes": len(manifest_payload),
        "sha256": sha256_bytes(manifest_payload),
    }
    checksum_records = artifacts + [readme_record, manifest_record]
    checksum_name = plan["release_assets"]["checksums"]
    checksum_payload = "".join(
        f"{item['sha256']}  {item['path']}\n" for item in checksum_records
    ).encode("utf-8")
    atomic_write(asset_dir / checksum_name, checksum_payload)
    atomic_write(snapshot / "publication" / checksum_name, checksum_payload)
    checksum_record = {
        "kind": "checksums",
        "path": checksum_name,
        "bytes": len(checksum_payload),
        "sha256": sha256_bytes(checksum_payload),
    }
    docs = snapshot / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    atomic_write(docs / "index.html", pages_html(plan, doi, binding["fingerprint"]))
    atomic_write(docs / ".nojekyll", b"")
    closure = artifacts + [readme_record, manifest_record, checksum_record]
    if len(closure) != plan["release_assets"]["expected_count"]:
        raise PublicationError("release asset closure count differs from the plan")
    if len({item["path"].casefold() for item in closure}) != len(closure):
        raise PublicationError("release asset closure contains duplicate basenames")
    for item in closure:
        validate_basename(item["path"], "release artifact")
        path = asset_dir / item["path"]
        if path.stat().st_size != item["bytes"] or sha256_file(path) != item["sha256"]:
            raise PublicationError(f"release artifact byte drift: {item['path']}")
        assert_public_safe_file(path)
    return closure


def prepare_final_stage(
    plan: dict[str, Any], binding: dict[str, str], state: dict[str, Any], base: Path, doi: str
) -> tuple[Path, dict[str, Any]]:
    transaction_root = TRANSACTIONS / binding["fingerprint"]
    final = transaction_root / "final"
    if final.is_dir():
        manifest = verify_inventory(final, binding)
        validate_final_manifest(plan, manifest, doi)
        pin_inventory(state, "final_inventory_sha256", manifest, final)
        pin_state_sha256(state, "artifact_set_sha256", manifest["artifact_set_sha256"])
        save_state(state)
        return final, manifest
    temporary = Path(
        tempfile.mkdtemp(prefix="final-", suffix=".tmp", dir=transaction_root)
    )
    try:
        snapshot = temporary / "snapshot"
        base_manifest = verify_inventory(base, binding)
        pin_inventory(state, "base_inventory_sha256", base_manifest, base)
        shutil.copytree(base / "snapshot", snapshot, symlinks=False)
        verify_inventory(base, binding)
        verify_snapshot_copy(base_manifest, snapshot)
        readiness = expect_dict(base_manifest.get("readiness"), "base readiness")
        artifacts = build_release_payloads(
            plan,
            snapshot,
            temporary / "release-assets",
            doi,
            binding,
            readiness,
        )
        rows = inventory_rows(temporary, omit={"inventory.json"})
        manifest = {
            "schema_version": "hefferon-id-immutable-inventory-v1",
            "stage": "final",
            "binding": binding,
            "doi": doi,
            "inventory_sha256": inventory_digest(rows),
            "file_count": len(rows),
            "files": rows,
            "readiness": readiness,
            "artifacts": artifacts,
            "artifact_set_sha256": sha256_bytes(canonical_bytes(artifacts)),
        }
        save_json(temporary / "inventory.json", manifest)
        verify_inventory(temporary, binding)
        os.replace(temporary, final)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    manifest = verify_inventory(final, binding)
    validate_final_manifest(plan, manifest, doi)
    pin_inventory(state, "final_inventory_sha256", manifest, final)
    pin_state_sha256(state, "artifact_set_sha256", manifest["artifact_set_sha256"])
    save_state(state)
    return final, manifest


def artifact_map(final: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(expect_list(manifest.get("artifacts"), "artifacts")):
        item = expect_dict(value, f"artifacts[{index}]")
        name = validate_basename(require_string(item, "path", "artifact"), "artifact")
        if name.casefold() in {existing.casefold() for existing in result}:
            raise PublicationError("artifact map contains duplicate names")
        path = final / "release-assets" / name
        if path.stat().st_size != require_integer(item, "bytes", "artifact") or sha256_file(path) != require_string(item, "sha256", "artifact"):
            raise PublicationError(f"artifact map byte mismatch: {name}")
        result[name] = item
    return result


def repo_base(plan: dict[str, Any]) -> str:
    return f"/repos/{plan['github']['owner']}/{plan['github']['repository']}"


def expected_repository_settings(plan: dict[str, Any], *, branch_exists: bool) -> dict[str, Any]:
    owner = plan["github"]["owner"]
    repo = plan["github"]["repository"]
    expected: dict[str, Any] = {
        "description": plan["github"]["description"],
        "homepage": f"https://{owner.lower()}.github.io/{repo}/",
        "has_issues": True,
        "has_projects": False,
        "has_wiki": False,
    }
    if branch_exists:
        expected["default_branch"] = plan["github"]["default_branch"]
    return expected


def read_repository_settings(
    client: Any,
    plan: dict[str, Any],
    *,
    branch_exists: bool,
    expected_repository_id: int | None = None,
) -> dict[str, Any]:
    _status, _headers, value = client.request("GET", repo_base(plan))
    repository = expect_dict(value, "repository settings")
    repository_id = require_integer(repository, "id", "repository settings")
    if expected_repository_id is not None and repository_id != expected_repository_id:
        raise PublicationError("GitHub repository ID differs from the transaction binding")
    owner = plan["github"]["owner"]
    repo = plan["github"]["repository"]
    identity = {
        "full_name": f"{owner}/{repo}",
        "private": False,
        "html_url": f"{GITHUB_WEB_ORIGIN}/{owner}/{repo}",
    }
    for key, expected in identity.items():
        if repository.get(key) != expected:
            raise PublicationError(f"GitHub repository identity differs: {key}")
    owner_value = expect_dict(repository.get("owner"), "repository.owner")
    if owner_value.get("login") != owner:
        raise PublicationError("GitHub repository owner identity differs")
    for key, expected in expected_repository_settings(plan, branch_exists=branch_exists).items():
        if repository.get(key) != expected:
            raise PublicationError(f"GitHub repository setting differs: {key}")
    _status, _headers, topics_value = client.request(
        "GET", repo_base(plan) + "/topics"
    )
    topics = expect_dict(topics_value, "repository topics")
    names = require_string_list(topics.get("names"), "repository topics.names", unique=True)
    if sorted(names) != plan["github"]["topics"]:
        raise PublicationError("GitHub repository topic closure differs")
    return repository


def reconcile_repository_settings(
    client: GitHubClient, plan: dict[str, Any], *, branch_exists: bool
) -> dict[str, Any]:
    expected = expected_repository_settings(plan, branch_exists=branch_exists)
    with contextlib.suppress(PublicationError):
        client.request("PATCH", repo_base(plan), body=expected)
    with contextlib.suppress(PublicationError):
        client.request(
            "PUT", repo_base(plan) + "/topics", body={"names": plan["github"]["topics"]}
        )
    return read_repository_settings(client, plan, branch_exists=branch_exists)


def ensure_github_repository(
    client: GitHubClient, plan: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any]:
    base = repo_base(plan)
    status, value = github_optional(client, base)
    if status == 404:
        try:
            _status, _headers, value = client.request(
                "POST",
                "/user/repos",
                body={
                    "name": plan["github"]["repository"],
                    "description": plan["github"]["description"],
                    "homepage": f"https://{plan['github']['owner'].lower()}.github.io/{plan['github']['repository']}/",
                    "private": False,
                    "has_issues": True,
                    "has_projects": False,
                    "has_wiki": False,
                    "auto_init": False,
                },
                expected=(201,),
                retryable=False,
            )
        except PublicationError as original:
            value = poll_github_optional(client, base)
            if value is None:
                raise original
    repository = expect_dict(value, "GitHub repository")
    repository_id = require_integer(repository, "id", "repository")
    if repository.get("private") is not False or repository.get("full_name") != (
        f"{plan['github']['owner']}/{plan['github']['repository']}"
    ):
        raise PublicationError("GitHub repository identity or visibility differs")
    stored_id = state.get("github_repository_id")
    if stored_id is None:
        def refs_or_empty(endpoint: str) -> list[dict[str, Any]]:
            optional_status, optional_value = github_optional(
                client, endpoint + "?per_page=100&page=1", expected_type=list
            )
            if optional_status == 404:
                return []
            return [
                expect_dict(item, endpoint)
                for item in expect_list(optional_value, endpoint)
            ]

        heads = refs_or_empty(base + "/git/matching-refs/heads")
        tags = refs_or_empty(base + "/git/matching-refs/tags")
        branches = refs_or_empty(base + "/branches")
        if heads or tags or branches:
            raise PublicationError(
                "pre-existing GitHub repository has refs/content and is not transaction-bound"
            )
    elif stored_id is not None and stored_id != repository_id:
        raise PublicationError("GitHub repository ID differs from transaction state")
    state["github_repository_id"] = repository_id
    save_state(state)
    reconciled = reconcile_repository_settings(client, plan, branch_exists=False)
    if reconciled.get("id") != repository_id:
        raise PublicationError("GitHub repository ID changed during settings reconciliation")
    return reconciled


def repository_entries(
    plan: dict[str, Any], final: Path
) -> dict[str, dict[str, Any]]:
    snapshot = final / "snapshot"
    files = expand_includes(snapshot, plan["repository_snapshot"]["include"], plan)
    entries: dict[str, dict[str, Any]] = {}
    for path in files:
        assert_public_safe_file(path)
        relative = lexical_relative(path, snapshot)
        mode = "100755" if path.suffix.lower() in {".sh", ".bat", ".cmd"} else "100644"
        entries[relative] = {
            "path": relative,
            "mode": mode,
            "type": "blob",
            "sha": git_blob_sha_file(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "local_path": path,
        }
    if not entries:
        raise PublicationError("repository snapshot is empty")
    return entries


def remote_branch_state(
    client: GitHubClient, plan: dict[str, Any]
) -> tuple[str, str, dict[str, Any]] | None:
    branch = plan["github"]["default_branch"]
    status, value = github_optional(
        client, repo_base(plan) + f"/git/ref/heads/{urllib.parse.quote(branch, safe='')}"
    )
    if status == 404:
        return None
    ref = expect_dict(value, "branch ref")
    if ref.get("ref") != f"refs/heads/{branch}":
        raise PublicationError("GitHub branch ref name differs")
    ref_object = expect_dict(ref.get("object"), "branch ref object")
    if ref_object.get("type") != "commit":
        raise PublicationError("GitHub branch ref does not target a commit")
    commit_sha = require_sha(ref_object.get("sha"), "branch ref object.sha", algorithm="sha1")
    _status, _headers, commit_value = client.request(
        "GET", repo_base(plan) + f"/git/commits/{commit_sha}"
    )
    commit = expect_dict(commit_value, "commit")
    tree = expect_dict(commit.get("tree"), "commit.tree")
    tree_sha = require_sha(tree.get("sha"), "commit.tree.sha", algorithm="sha1")
    return commit_sha, tree_sha, commit


def poll_remote_branch_state(
    client: GitHubClient,
    plan: dict[str, Any],
    *,
    expected_commit: str | None = None,
    expected_tree: str | None = None,
    attempts: int = 8,
) -> tuple[str, str, dict[str, Any]] | None:
    for attempt in range(attempts):
        try:
            current = remote_branch_state(client, plan)
        except PublicationError:
            current = None
        if current is not None and (
            (expected_commit is None or current[0] == expected_commit)
            and (expected_tree is None or current[1] == expected_tree)
        ):
            return current
        if current is not None and expected_commit is not None and current[0] != expected_commit:
            raise PublicationError("GitHub branch reached an unexpected commit during recovery")
        if attempt + 1 < attempts:
            time.sleep(backoff_seconds(min(attempt, 4)))
    return None


def verify_remote_tree(
    client: Any,
    plan: dict[str, Any],
    expected: dict[str, dict[str, Any]],
    tree_sha: str,
) -> dict[str, Any]:
    require_sha(tree_sha, "GitHub tree SHA", algorithm="sha1")
    endpoint = repo_base(plan) + f"/git/trees/{tree_sha}?recursive=1"
    _status, _headers, tree_value = client.request("GET", endpoint)
    tree = expect_dict(tree_value, "recursive tree")
    if tree.get("truncated") is not False or tree.get("sha") != tree_sha:
        raise PublicationError("GitHub recursive tree is truncated or identity-drifted")
    remote: dict[str, dict[str, Any]] = {}
    all_paths: set[str] = set()
    for index, item_value in enumerate(expect_list(tree.get("tree"), "recursive tree entries")):
        item = expect_dict(item_value, f"tree[{index}]")
        path = validate_relative_name(require_string(item, "path", "tree entry"), "tree entry")
        if path in all_paths:
            raise PublicationError("GitHub tree has duplicate paths")
        all_paths.add(path)
        item_type = item.get("type")
        if item_type == "blob":
            remote[path] = item
        elif item_type != "tree":
            raise PublicationError("GitHub tree contains a submodule or unknown entry type")
    if set(remote) != set(expected):
        raise PublicationError("GitHub repository blob-path closure differs")
    for path, local in expected.items():
        item = remote[path]
        if (
            item.get("sha") != local["sha"]
            or item.get("mode") != local["mode"]
            or item.get("size") != local["bytes"]
        ):
            raise PublicationError(f"GitHub tree/blob identity differs: {path}")
    return {
        "tree_sha": tree_sha,
        "blob_count": len(remote),
        "repository_snapshot_sha256": sha256_bytes(
            canonical_bytes(
                [
                    {
                        "path": path,
                        "mode": item["mode"],
                        "bytes": item["bytes"],
                        "sha256": item["sha256"],
                        "git_blob_sha": item["sha"],
                    }
                    for path, item in sorted(expected.items())
                ]
            )
        ),
    }


def verify_remote_repository(
    client: GitHubClient,
    plan: dict[str, Any],
    expected: dict[str, dict[str, Any]],
    expected_commit: str | None = None,
) -> dict[str, Any]:
    branch_state = remote_branch_state(client, plan)
    if branch_state is None:
        raise PublicationError("GitHub default branch ref is absent")
    commit_sha, tree_sha, commit = branch_state
    if expected_commit is not None and commit_sha != expected_commit:
        raise PublicationError("GitHub branch commit differs from transaction state")
    if commit.get("sha") != commit_sha:
        raise PublicationError("GitHub commit response SHA differs from ref")
    tree_result = verify_remote_tree(client, plan, expected, tree_sha)
    return {
        "commit_sha": commit_sha,
        **tree_result,
    }


def publish_repository_snapshot(
    client: GitHubClient,
    plan: dict[str, Any],
    state: dict[str, Any],
    final: Path,
    binding: dict[str, str],
) -> dict[str, Any]:
    verify_inventory(final, binding)
    expected = repository_entries(plan, final)
    current = remote_branch_state(client, plan)
    if current is not None:
        try:
            pinned_commit = state.get("github_commit_sha") or state.get("github_pending_commit_sha")
            verified = verify_remote_repository(
                client, plan, expected, pinned_commit
            )
            state["github_commit_sha"] = verified["commit_sha"]
            state["github_tree_sha"] = verified["tree_sha"]
            state.pop("github_pending_commit_sha", None)
            state.pop("github_pending_tree_sha", None)
            state["repository_snapshot_sha256"] = verified[
                "repository_snapshot_sha256"
            ]
            save_state(state)
            settings = reconcile_repository_settings(client, plan, branch_exists=True)
            if settings.get("id") != state.get("github_repository_id"):
                raise PublicationError("GitHub repository ID differs after resume reconciliation")
            return {**verified, "status": "already-current"}
        except PublicationError:
            if state.get("github_commit_sha") and current[0] != state["github_commit_sha"]:
                raise PublicationError("GitHub branch advanced outside this transaction") from None
            if state.get("github_commit_sha") is None:
                raise PublicationError("nonempty GitHub branch cannot be adopted without exact proof") from None

    pending_commit_value = state.get("github_pending_commit_sha")
    pending_tree_value = state.get("github_pending_tree_sha")
    if current is None and (pending_commit_value is not None or pending_tree_value is not None):
        pending_commit = require_sha(
            pending_commit_value, "state.github_pending_commit_sha", algorithm="sha1"
        )
        pending_tree = require_sha(
            pending_tree_value, "state.github_pending_tree_sha", algorithm="sha1"
        )
        _status, _headers, pending_value = client.request(
            "GET", repo_base(plan) + f"/git/commits/{pending_commit}"
        )
        pending_object = expect_dict(pending_value, "pending GitHub commit")
        pending_object_tree = expect_dict(
            pending_object.get("tree"), "pending GitHub commit.tree"
        )
        if (
            pending_object.get("sha") != pending_commit
            or pending_object_tree.get("sha") != pending_tree
        ):
            raise PublicationError("pending GitHub commit/tree identity differs")
        verify_remote_tree(client, plan, expected, pending_tree)
        branch = plan["github"]["default_branch"]
        try:
            client.request(
                "POST",
                repo_base(plan) + "/git/refs",
                body={"ref": f"refs/heads/{branch}", "sha": pending_commit},
                expected=(201,),
                retryable=False,
            )
        except PublicationError as original:
            recovered = poll_remote_branch_state(
                client,
                plan,
                expected_commit=pending_commit,
                expected_tree=pending_tree,
            )
            if recovered is None:
                raise original
        state["github_commit_sha"] = pending_commit
        state["github_tree_sha"] = pending_tree
        state.pop("github_pending_commit_sha", None)
        state.pop("github_pending_tree_sha", None)
        save_state(state)
        settings = reconcile_repository_settings(client, plan, branch_exists=True)
        if settings.get("id") != state.get("github_repository_id"):
            raise PublicationError("GitHub repository ID differs after pending-ref recovery")
        verified = verify_remote_repository(client, plan, expected, pending_commit)
        state["repository_snapshot_sha256"] = verified["repository_snapshot_sha256"]
        save_state(state)
        return {**verified, "status": "recovered-pending-ref"}

    cache = expect_dict(state.setdefault("blob_cache", {}), "blob cache")
    uploaded_since_save = 0
    for index, (relative, item) in enumerate(sorted(expected.items()), 1):
        cache_item = cache.get(relative)
        if isinstance(cache_item, dict) and (
            cache_item.get("sha256") == item["sha256"]
            and cache_item.get("bytes") == item["bytes"]
            and cache_item.get("remote_sha") == item["sha"]
        ):
            continue
        blob = client.upload_blob(repo_base(plan) + "/git/blobs", item["local_path"])
        if blob.get("sha") != item["sha"]:
            raise PublicationError(f"GitHub blob SHA differs: {relative}")
        cache[relative] = {
            "bytes": item["bytes"],
            "sha256": item["sha256"],
            "remote_sha": item["sha"],
        }
        uploaded_since_save += 1
        if uploaded_since_save >= 20:
            save_state(state)
            uploaded_since_save = 0
        if index % 100 == 0:
            print(json.dumps({"github_blobs": index, "total": len(expected)}))
        time.sleep(0.03)
    save_state(state)
    tree_payload = {
        "tree": [
            {
                "path": relative,
                "mode": item["mode"],
                "type": "blob",
                "sha": item["sha"],
            }
            for relative, item in sorted(expected.items())
        ]
    }
    _status, _headers, tree_value = client.request(
        "POST",
        repo_base(plan) + "/git/trees",
        body=tree_payload,
        expected=(201,),
        retryable=True,
    )
    tree = expect_dict(tree_value, "created tree")
    tree_sha = require_sha(tree.get("sha"), "created tree.sha", algorithm="sha1")
    current = remote_branch_state(client, plan)
    parents = [] if current is None else [current[0]]
    _status, _headers, commit_value = client.request(
        "POST",
        repo_base(plan) + "/git/commits",
        body={
            "message": f"Rilis {plan['release']['tag']}: edisi lengkap id-ID",
            "tree": tree_sha,
            "parents": parents,
        },
        expected=(201,),
        retryable=True,
    )
    commit = expect_dict(commit_value, "created commit")
    commit_sha = require_sha(commit.get("sha"), "created commit.sha", algorithm="sha1")
    branch = plan["github"]["default_branch"]
    state["github_pending_commit_sha"] = commit_sha
    state["github_pending_tree_sha"] = tree_sha
    save_state(state)
    try:
        if current is None:
            client.request(
                "POST",
                repo_base(plan) + "/git/refs",
                body={"ref": f"refs/heads/{branch}", "sha": commit_sha},
                expected=(201,),
                retryable=False,
            )
        else:
            client.request(
                "PATCH",
                repo_base(plan) + f"/git/refs/heads/{urllib.parse.quote(branch, safe='')}",
                body={"sha": commit_sha, "force": False},
            )
    except PublicationError as original:
        recovered = poll_remote_branch_state(
            client,
            plan,
            expected_commit=commit_sha,
            expected_tree=tree_sha,
        )
        if recovered is None:
            raise original
    observed = poll_remote_branch_state(
        client,
        plan,
        expected_commit=commit_sha,
        expected_tree=tree_sha,
    )
    if observed is None:
        raise PublicationError("GitHub branch ref did not become consistent after publication")
    state["github_commit_sha"] = commit_sha
    state["github_tree_sha"] = tree_sha
    state.pop("github_pending_commit_sha", None)
    state.pop("github_pending_tree_sha", None)
    save_state(state)
    settings = reconcile_repository_settings(client, plan, branch_exists=True)
    if settings.get("id") != state.get("github_repository_id"):
        raise PublicationError("GitHub repository ID differs after branch publication")
    verified = verify_remote_repository(client, plan, expected, commit_sha)
    state["repository_snapshot_sha256"] = verified["repository_snapshot_sha256"]
    save_state(state)
    return {**verified, "status": "published"}


def resolve_tag(client: GitHubClient, plan: dict[str, Any]) -> str | None:
    tag = plan["release"]["tag"]
    status, value = github_optional(
        client, repo_base(plan) + f"/git/ref/tags/{urllib.parse.quote(tag, safe='')}"
    )
    if status == 404:
        return None
    ref = expect_dict(value, "tag ref")
    if ref.get("ref") != f"refs/tags/{tag}":
        raise PublicationError("GitHub tag ref name differs")
    obj = expect_dict(ref.get("object"), "tag ref object")
    sha = require_sha(obj.get("sha"), "tag ref object.sha", algorithm="sha1")
    object_type = require_string(obj, "type", "tag ref object")
    if object_type == "commit":
        return sha
    if object_type != "tag":
        raise PublicationError("tag ref has an unsupported object type")
    _status, _headers, tag_value = client.request(
        "GET", repo_base(plan) + f"/git/tags/{sha}"
    )
    tag_object = expect_dict(tag_value, "annotated tag")
    target = expect_dict(tag_object.get("object"), "annotated tag object")
    if target.get("type") != "commit":
        raise PublicationError("annotated tag does not target a commit")
    return require_sha(target.get("sha"), "annotated tag object.sha", algorithm="sha1")


def poll_tag_target(
    client: GitHubClient,
    plan: dict[str, Any],
    *,
    expected_commit: str | None = None,
    attempts: int = 8,
) -> str | None:
    for attempt in range(attempts):
        try:
            target = resolve_tag(client, plan)
        except PublicationError:
            target = None
        if target is not None:
            target = require_sha(target, "resolved tag target", algorithm="sha1")
            if expected_commit is not None and target != expected_commit:
                raise PublicationError("GitHub tag reached an unexpected commit during recovery")
            return target
        if attempt + 1 < attempts:
            time.sleep(backoff_seconds(min(attempt, 4)))
    return None


def ensure_tag(
    client: GitHubClient, plan: dict[str, Any], state: dict[str, Any]
) -> str:
    commit_sha = require_sha(
        state.get("github_commit_sha"), "state.github_commit_sha", algorithm="sha1"
    )
    target = resolve_tag(client, plan)
    if target is None:
        _status, _headers, value = client.request(
            "POST",
            repo_base(plan) + "/git/tags",
            body={
                "tag": plan["release"]["tag"],
                "message": plan["release"]["title"],
                "object": commit_sha,
                "type": "commit",
            },
            expected=(201,),
            retryable=True,
        )
        tag_object = expect_dict(value, "created annotated tag")
        tag_sha = require_sha(
            tag_object.get("sha"), "created annotated tag.sha", algorithm="sha1"
        )
        state["github_pending_tag_object_sha"] = tag_sha
        save_state(state)
        try:
            client.request(
                "POST",
                repo_base(plan) + "/git/refs",
                body={"ref": f"refs/tags/{plan['release']['tag']}", "sha": tag_sha},
                expected=(201,),
                retryable=False,
            )
        except PublicationError as original:
            target = poll_tag_target(client, plan, expected_commit=commit_sha)
            if target is None:
                raise original
        else:
            target = poll_tag_target(client, plan, expected_commit=commit_sha)
    if target != commit_sha:
        raise PublicationError("GitHub release tag does not target the frozen commit")
    state["github_tag_commit_sha"] = target
    state.pop("github_pending_tag_object_sha", None)
    save_state(state)
    return target


def expected_release_metadata(
    plan: dict[str, Any], final: Path, commit_sha: str, *, draft: bool
) -> dict[str, Any]:
    body_path = final / "snapshot" / "publication" / plan["release_assets"]["readme"]
    return {
        "tag_name": plan["release"]["tag"],
        "target_commitish": commit_sha,
        "name": plan["release"]["title"],
        "body": body_path.read_text(encoding="utf-8"),
        "draft": draft,
        "prerelease": False,
    }


def find_release(client: GitHubClient, plan: dict[str, Any]) -> dict[str, Any] | None:
    matches = [
        item
        for item in github_paginated(client, repo_base(plan) + "/releases")
        if item.get("tag_name") == plan["release"]["tag"]
    ]
    if len(matches) > 1:
        raise PublicationError("multiple GitHub releases use the exact target tag")
    return matches[0] if matches else None


def poll_find_release(
    client: GitHubClient, plan: dict[str, Any], *, attempts: int = 8
) -> dict[str, Any] | None:
    for attempt in range(attempts):
        release = find_release(client, plan)
        if release is not None:
            return release
        if attempt + 1 < attempts:
            time.sleep(backoff_seconds(min(attempt, 4)))
    return None


def assert_expected_release_fields(
    release: dict[str, Any], plan: dict[str, Any], final: Path, commit_sha: str, *, draft: bool
) -> None:
    expected = expected_release_metadata(plan, final, commit_sha, draft=draft)
    for key, expected_value in expected.items():
        if release.get(key) != expected_value:
            raise PublicationError(f"GitHub release metadata differs: {key}")


def poll_release_state(
    client: GitHubClient,
    plan: dict[str, Any],
    final: Path,
    commit_sha: str,
    *,
    draft: bool,
    release_id: int,
    attempts: int = 8,
) -> dict[str, Any] | None:
    for attempt in range(attempts):
        release = find_release(client, plan)
        if release is not None:
            if require_integer(release, "id", "release") != release_id:
                raise PublicationError("GitHub release ID changed during recovery")
            try:
                assert_expected_release_fields(
                    release, plan, final, commit_sha, draft=draft
                )
                return release
            except PublicationError:
                pass
        if attempt + 1 < attempts:
            time.sleep(backoff_seconds(min(attempt, 4)))
    return None


def reconcile_release_metadata(
    client: GitHubClient,
    plan: dict[str, Any],
    final: Path,
    release: dict[str, Any],
    commit_sha: str,
    *,
    draft: bool,
) -> dict[str, Any]:
    release_id = require_integer(release, "id", "release")
    if resolve_tag(client, plan) != commit_sha:
        raise PublicationError("release tag target differs from transaction commit")
    expected = expected_release_metadata(plan, final, commit_sha, draft=draft)
    patch = {**expected, "make_latest": "true"}
    try:
        _status, _headers, value = client.request(
            "PATCH", repo_base(plan) + f"/releases/{release_id}", body=patch
        )
        refreshed = expect_dict(value, "reconciled release")
    except PublicationError as original:
        recovered = poll_release_state(
            client,
            plan,
            final,
            commit_sha,
            draft=draft,
            release_id=release_id,
        )
        if recovered is None:
            raise original
        refreshed = recovered
    assert_expected_release_fields(
        refreshed, plan, final, commit_sha, draft=draft
    )
    return refreshed


def release_assets(client: GitHubClient, plan: dict[str, Any], release_id: int) -> list[dict[str, Any]]:
    return github_paginated(
        client, repo_base(plan) + f"/releases/{release_id}/assets"
    )


def release_assets_by_name(
    client: GitHubClient, plan: dict[str, Any], release_id: int
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in release_assets(client, plan, release_id):
        name = validate_basename(require_string(item, "name", "release asset"), "release asset")
        if name in result:
            raise PublicationError("GitHub release has duplicate asset names")
        result[name] = item
    return result


def poll_release_assets(
    client: GitHubClient,
    plan: dict[str, Any],
    release_id: int,
    *,
    expected_names: set[str] | None = None,
    required_name: str | None = None,
    attempts: int = 8,
) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for attempt in range(attempts):
        latest = release_assets_by_name(client, plan, release_id)
        if expected_names is not None and set(latest) == expected_names:
            return latest
        if required_name is not None and required_name in latest:
            return latest
        if expected_names is None and required_name is None:
            return latest
        if attempt + 1 < attempts:
            time.sleep(backoff_seconds(min(attempt, 4)))
    return latest


def poll_release_asset_absent(
    client: GitHubClient,
    plan: dict[str, Any],
    release_id: int,
    name: str,
    *,
    attempts: int = 8,
) -> bool:
    for attempt in range(attempts):
        if name not in release_assets_by_name(client, plan, release_id):
            return True
        if attempt + 1 < attempts:
            time.sleep(backoff_seconds(min(attempt, 4)))
    return False


def verify_github_asset_bytes(
    client: GitHubClient,
    plan: dict[str, Any],
    asset: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    asset_id = require_integer(asset, "id", "release asset")
    if asset.get("name") != expected["path"] or asset.get("size") != expected["bytes"]:
        raise PublicationError(f"GitHub asset metadata differs: {expected['path']}")
    size, digest = client.authenticated_asset_sha256(
        plan["github"]["owner"],
        plan["github"]["repository"],
        asset_id,
        expected["bytes"],
    )
    if size != expected["bytes"] or digest != expected["sha256"]:
        raise PublicationError(f"GitHub asset content hash differs: {expected['path']}")


def ensure_github_release(
    client: GitHubClient,
    plan: dict[str, Any],
    state: dict[str, Any],
    final: Path,
    manifest: dict[str, Any],
    binding: dict[str, str],
) -> dict[str, Any]:
    verify_inventory(final, binding)
    artifacts = artifact_map(final, manifest)
    commit_sha = ensure_tag(client, plan, state)
    release = find_release(client, plan)
    if release is None:
        try:
            _status, _headers, value = client.request(
                "POST",
                repo_base(plan) + "/releases",
                body={
                    **expected_release_metadata(plan, final, commit_sha, draft=True),
                    "make_latest": "true",
                },
                expected=(201,),
                retryable=False,
            )
            release = expect_dict(value, "created draft release")
        except PublicationError as original:
            release = poll_find_release(client, plan)
            if release is None:
                raise original
    is_public = release.get("draft") is False
    release = reconcile_release_metadata(
        client, plan, final, release, commit_sha, draft=not is_public
    )
    release_id = require_integer(release, "id", "release")
    by_name = release_assets_by_name(client, plan, release_id)
    extras = set(by_name) - set(artifacts)
    if extras:
        raise PublicationError(f"GitHub release has unexpected assets: {sorted(extras)}")
    if is_public and set(by_name) != set(artifacts):
        raise PublicationError("public GitHub release is incomplete and cannot be repaired invisibly")
    upload_template = require_string(release, "upload_url", "release").split("{")[0]
    if origin(upload_template) != origin(GITHUB_UPLOAD_ORIGIN):
        raise PublicationError("GitHub release upload URL has an unexpected origin")
    upload_parts = urllib.parse.urlsplit(upload_template)
    expected_upload_path = (
        f"/repos/{plan['github']['owner']}/{plan['github']['repository']}"
        f"/releases/{release_id}/assets"
    )
    if upload_parts.path != expected_upload_path or upload_parts.query or upload_parts.fragment:
        raise PublicationError("GitHub release upload URL has an unexpected endpoint")
    for name, expected in artifacts.items():
        asset = by_name.get(name)
        if asset is not None:
            try:
                verify_github_asset_bytes(client, plan, asset, expected)
                continue
            except PublicationError:
                if is_public:
                    raise
                try:
                    client.request(
                        "DELETE",
                        repo_base(plan) + f"/releases/assets/{require_integer(asset, 'id', 'asset')}",
                        expected_type=None,
                        expected=(204,),
                    )
                except PublicationError as original:
                    if not poll_release_asset_absent(
                        client, plan, release_id, name
                    ):
                        raise original
                else:
                    if not poll_release_asset_absent(
                        client, plan, release_id, name
                    ):
                        raise PublicationError(
                            f"GitHub draft asset deletion did not become consistent: {name}"
                        )
        query = urllib.parse.urlencode({"name": name})
        try:
            uploaded = client.upload_release_asset(
                upload_template + "?" + query, final / "release-assets" / name
            )
        except PublicationError as original:
            recovered_assets = poll_release_assets(
                client, plan, release_id, required_name=name
            )
            uploaded = recovered_assets.get(name)
            if uploaded is None:
                raise original
        verify_github_asset_bytes(client, plan, uploaded, expected)
    refreshed_by_name = poll_release_assets(
        client, plan, release_id, expected_names=set(artifacts)
    )
    if set(refreshed_by_name) != set(artifacts):
        raise PublicationError("GitHub draft asset closure differs immediately before publication")
    for name, expected in artifacts.items():
        verify_github_asset_bytes(client, plan, refreshed_by_name[name], expected)
    verify_inventory(final, binding)
    verify_remote_repository(client, plan, repository_entries(plan, final), commit_sha)
    if resolve_tag(client, plan) != commit_sha:
        raise PublicationError("GitHub tag drifted before release publication")
    if not is_public:
        release = reconcile_release_metadata(
            client, plan, final, release, commit_sha, draft=False
        )
    if require_integer(release, "id", "release") != release_id:
        raise PublicationError("GitHub release ID changed after publication")
    state["github_release_id"] = release_id
    state["github_release_url"] = require_string(release, "html_url", "release")
    state["github_release_public"] = True
    save_state(state)
    latest: dict[str, Any] | None = None
    for attempt in range(8):
        _latest_status, latest_value = github_optional(
            client, repo_base(plan) + "/releases/latest"
        )
        if latest_value is not None:
            candidate = expect_dict(latest_value, "latest release")
            if candidate.get("id") == release_id:
                latest = candidate
                break
        if attempt + 1 < 8:
            time.sleep(backoff_seconds(min(attempt, 4)))
    if latest is None:
        raise PublicationError("GitHub release is not the repository's latest release")
    return release


def ensure_pages(client: GitHubClient, plan: dict[str, Any]) -> dict[str, Any]:
    endpoint = repo_base(plan) + "/pages"
    expected_source = {
        "branch": plan["github"]["default_branch"],
        "path": plan["github"]["pages_path"],
    }
    status, value = github_optional(client, endpoint)
    if status == 404:
        try:
            client.request(
                "POST", endpoint, body={"source": expected_source}, expected=(201,), retryable=False
            )
        except PublicationError as original:
            value = poll_github_optional(client, endpoint)
            if value is None:
                raise original
        else:
            value = poll_github_optional(client, endpoint)
    pages = expect_dict(value, "GitHub Pages")
    source = expect_dict(pages.get("source"), "GitHub Pages source")
    if source != expected_source:
        raise PublicationError("GitHub Pages source differs from main:/docs")
    if pages.get("https_enforced") is not True:
        try:
            client.request(
                "PUT", endpoint, body={"https_enforced": True}, expected_type=None, expected=(204,)
            )
        except PublicationError:
            # The response may be lost after the idempotent setting change;
            # the exact readback loop below is the authority.
            pass
    for attempt in range(8):
        value = poll_github_optional(client, endpoint, attempts=1)
        pages = expect_dict(value, "GitHub Pages") if value is not None else {}
        if pages.get("source") == expected_source and pages.get("https_enforced") is True:
            return pages
        if attempt + 1 < 8:
            time.sleep(backoff_seconds(min(attempt, 4)))
    raise PublicationError("GitHub Pages settings did not become exactly consistent")


def zenodo_doi(deposition: dict[str, Any]) -> str:
    metadata = expect_dict(deposition.get("metadata"), "deposition.metadata")
    reserved = metadata.get("prereserve_doi")
    doi = deposition.get("doi")
    if doi is None and isinstance(reserved, dict):
        doi = reserved.get("doi")
    if not isinstance(doi, str) or not re.fullmatch(r"10\.5281/zenodo\.\d+", doi):
        raise PublicationError("Zenodo deposition lacks a valid reserved DOI")
    return doi


def validate_deposition_identity(
    deposition_value: Any,
    plan: dict[str, Any],
    binding: dict[str, str],
    *,
    require_final_metadata: bool,
) -> dict[str, Any]:
    deposition = expect_dict(deposition_value, "Zenodo deposition")
    require_integer(deposition, "id", "deposition")
    metadata = expect_dict(deposition.get("metadata"), "deposition.metadata")
    combined = plain_text(metadata.get("description")) + " " + plain_text(metadata.get("notes"))
    if transaction_marker(binding["fingerprint"]) not in combined:
        raise PublicationError("Zenodo deposition lacks the exact transaction fingerprint")
    if metadata.get("title") != plan["release"]["title"] or metadata.get("version") != plan["release"]["version"]:
        raise PublicationError("Zenodo deposition title/version identity differs")
    doi = zenodo_doi(deposition)
    if require_final_metadata:
        assert_zenodo_metadata(
            metadata, plan, doi, binding["fingerprint"], public=False
        )
    return deposition


def exact_zenodo_depositions(
    client: ZenodoClient, plan: dict[str, Any], binding: dict[str, str]
) -> list[dict[str, Any]]:
    exact: list[dict[str, Any]] = []
    marker = transaction_marker(binding["fingerprint"])
    for index, candidate_value in enumerate(
        zenodo_paginated(client, binding["fingerprint"])
    ):
        candidate = expect_dict(candidate_value, f"Zenodo search candidate[{index}]")
        metadata = expect_dict(
            candidate.get("metadata"), f"Zenodo search candidate[{index}].metadata"
        )
        combined = plain_text(metadata.get("description")) + " " + plain_text(
            metadata.get("notes")
        )
        if marker not in combined:
            continue
        # Once the exact marker is present, any other identity drift is a
        # collision, not an unrelated search result.  Fail closed rather than
        # creating a second deposition with the same transaction marker.
        exact.append(
            validate_deposition_identity(
                candidate, plan, binding, require_final_metadata=False
            )
        )
    if len(exact) > 1:
        raise PublicationError("multiple exact-fingerprint Zenodo depositions exist")
    return exact


def _zenodo_transaction_fingerprint(metadata: dict[str, Any]) -> str | None:
    combined = plain_text(metadata.get("description")) + " " + plain_text(
        metadata.get("notes")
    )
    matches = set(re.findall(r"hefferon-id-transaction:([0-9a-f]{64})", combined))
    if len(matches) > 1:
        raise PublicationError("Zenodo title/version record has conflicting transaction markers")
    return next(iter(matches), None)


def _zenodo_title_version_rows(
    rows: Iterable[dict[str, Any]], plan: dict[str, Any], context: str
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for index, value in enumerate(rows):
        row = expect_dict(value, f"{context}[{index}]")
        metadata = expect_dict(row.get("metadata"), f"{context}[{index}].metadata")
        if (
            metadata.get("title") == plan["release"]["title"]
            and metadata.get("version") == plan["release"]["version"]
        ):
            matches.append(row)
    return matches


def _zenodo_search_record_id(value: Any, context: str) -> int:
    """Get a search row's record ID without requiring its optional DOI fields."""

    row = expect_dict(value, context)
    metadata = expect_dict(row.get("metadata"), f"{context}.metadata")
    candidates: list[int] = []
    if row.get("record_id") is not None:
        candidates.append(
            _zenodo_positive_id(row["record_id"], f"{context}.record_id")
        )
    reserved = metadata.get("prereserve_doi")
    if reserved is not None:
        reserved_dict = expect_dict(reserved, f"{context}.metadata.prereserve_doi")
        if reserved_dict.get("recid") is not None:
            candidates.append(
                _zenodo_positive_id(
                    reserved_dict["recid"],
                    f"{context}.metadata.prereserve_doi.recid",
                )
            )
    if not candidates:
        candidates.append(_zenodo_positive_id(row.get("id"), f"{context}.id"))
    if len(set(candidates)) != 1:
        raise PublicationError(f"{context} record IDs disagree")
    return candidates[0]


def zenodo_title_version_guard(
    client: ZenodoClient, plan: dict[str, Any], binding: dict[str, str]
) -> dict[str, Any] | None:
    """Fail closed before creation on a same-title/version transaction collision.

    Both the account's depositions and anonymous public records are checked.
    An exact current-fingerprint deposition is reusable; any other marker (or
    missing marker) under the same release title and version blocks creation.
    """

    title = plan["release"]["title"]
    version = plan["release"]["version"]
    authenticated = _zenodo_title_version_rows(
        zenodo_paginated(client, f'"{title}"'), plan, "Zenodo deposition"
    )
    escaped_title = title.replace("\\", "\\\\").replace('"', '\\"')
    escaped_version = version.replace("\\", "\\\\").replace('"', '\\"')
    public_query = (
        f'metadata.title:"{escaped_title}" AND metadata.version:"{escaped_version}"'
    )
    public = _zenodo_title_version_rows(
        zenodo_public_paginated(public_query), plan, "Zenodo public record"
    )
    fingerprint = binding["fingerprint"]
    for channel, rows in (("authenticated", authenticated), ("public", public)):
        for row in rows:
            metadata = expect_dict(row.get("metadata"), f"Zenodo {channel} metadata")
            marker = _zenodo_transaction_fingerprint(metadata)
            if marker != fingerprint:
                marker_text = marker if marker is not None else "missing"
                raise PublicationError(
                    "Zenodo already has the exact release title/version under a "
                    f"different transaction marker ({channel}: {marker_text})"
                )
    authenticated_ids = {
        _zenodo_search_record_id(row, "Zenodo deposition") for row in authenticated
    }
    public_ids = {
        _zenodo_search_record_id(row, "Zenodo public record") for row in public
    }
    if len(authenticated_ids) > 1 or len(public_ids) > 1:
        raise PublicationError(
            "multiple exact-title/version Zenodo records use this transaction marker"
        )
    if public_ids and not public_ids.issubset(authenticated_ids):
        raise PublicationError(
            "the public exact transaction cannot be matched to an authenticated deposition"
        )
    return authenticated[0] if authenticated else None


def _zenodo_positive_id(value: Any, context: str) -> int:
    if isinstance(value, bool):
        raise PublicationError(f"{context} is not a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise PublicationError(f"{context} is not a positive integer") from None
    if result <= 0 or str(value).strip() != str(result):
        raise PublicationError(f"{context} is not a positive integer")
    return result


def _zenodo_id_from_link(value: Any, context: str) -> int:
    if not isinstance(value, str) or not value:
        raise PublicationError(f"{context} is malformed")
    validate_origin(value, {origin(ZENODO_ORIGIN)})
    parsed = urllib.parse.urlsplit(value)
    match = re.fullmatch(
        r"/api/(?:records|deposit/depositions)/(\d+)/?", parsed.path
    )
    if parsed.query or parsed.fragment or match is None:
        raise PublicationError(f"{context} is not an exact Zenodo record link")
    return _zenodo_positive_id(match.group(1), context)


def zenodo_record_identity(value: Any, context: str) -> tuple[int, str]:
    """Normalize one legacy deposition/public-record identity without guessing."""

    row = expect_dict(value, context)
    metadata = expect_dict(row.get("metadata"), f"{context}.metadata")
    ids: list[int] = []
    if row.get("record_id") is not None:
        ids.append(_zenodo_positive_id(row["record_id"], f"{context}.record_id"))
    reserved = metadata.get("prereserve_doi")
    if reserved is not None:
        reserved_dict = expect_dict(reserved, f"{context}.metadata.prereserve_doi")
        if reserved_dict.get("recid") is not None:
            ids.append(
                _zenodo_positive_id(
                    reserved_dict["recid"],
                    f"{context}.metadata.prereserve_doi.recid",
                )
            )
    # In legacy deposit responses ``id`` is the deposition resource identity;
    # it is not assumed to equal the reserved/public record ID.  Public record
    # rows lack record_id/prereserve_doi, so only there does top-level id supply
    # the record identity.
    if not ids and row.get("id") is not None:
        ids.append(_zenodo_positive_id(row["id"], f"{context}.id"))
    if not ids or len(set(ids)) != 1:
        raise PublicationError(f"{context} record IDs are missing or disagree")
    record_id = ids[0]

    dois: list[str] = []
    for key in ("doi",):
        if row.get(key) is not None:
            dois.append(str(row[key]))
    if reserved is not None:
        reserved_doi = expect_dict(
            reserved, f"{context}.metadata.prereserve_doi"
        ).get("doi")
        if reserved_doi is not None:
            dois.append(str(reserved_doi))
    if row.get("doi_url") is not None:
        doi_url = str(row["doi_url"])
        validate_origin(doi_url, {origin("https://doi.org")})
        parsed = urllib.parse.urlsplit(doi_url)
        if parsed.query or parsed.fragment:
            raise PublicationError(f"{context}.doi_url is malformed")
        dois.append(urllib.parse.unquote(parsed.path.strip("/")))
    pids = row.get("pids")
    if pids is not None:
        pids_dict = expect_dict(pids, f"{context}.pids")
        if pids_dict.get("doi") is not None:
            doi_pid = expect_dict(pids_dict["doi"], f"{context}.pids.doi")
            dois.append(require_string(doi_pid, "identifier", f"{context}.pids.doi"))
    expected_doi = f"10.5281/zenodo.{record_id}"
    if not dois or any(doi != expected_doi for doi in dois):
        raise PublicationError(f"{context} DOI/record identities are missing or disagree")
    return record_id, expected_doi


def zenodo_deposition_id(value: Any, context: str) -> int:
    row = expect_dict(value, context)
    return _zenodo_positive_id(row.get("id"), f"{context}.id")


def zenodo_concept_identity(value: Any, context: str) -> tuple[int, str]:
    """Normalize a Zenodo conceptrecid/concept DOI pair from either API shape."""

    row = expect_dict(value, context)
    metadata = expect_dict(row.get("metadata"), f"{context}.metadata")
    concept_ids: list[int] = []
    for owner, key in ((row, "conceptrecid"), (metadata, "conceptrecid")):
        if owner.get(key) is not None:
            concept_ids.append(
                _zenodo_positive_id(owner[key], f"{context}.{key}")
            )
    concept_dois: list[str] = []
    for owner, key in ((row, "conceptdoi"), (metadata, "conceptdoi")):
        if owner.get(key) is not None:
            concept_dois.append(str(owner[key]))
    for concept_doi in concept_dois:
        match = re.fullmatch(r"10\.5281/zenodo\.(\d+)", concept_doi)
        if match is None:
            raise PublicationError(f"{context} concept DOI is malformed")
        concept_ids.append(_zenodo_positive_id(match.group(1), f"{context} concept DOI"))
    if not concept_ids or len(set(concept_ids)) != 1:
        raise PublicationError(f"{context} concept identities are missing or disagree")
    conceptrecid = concept_ids[0]
    expected_doi = f"10.5281/zenodo.{conceptrecid}"
    if concept_dois and any(value != expected_doi for value in concept_dois):
        raise PublicationError(f"{context} concept DOI/record identities disagree")
    return conceptrecid, expected_doi


def validate_zenodo_work_metadata(
    metadata_value: Any, plan: dict[str, Any], context: str
) -> dict[str, Any]:
    metadata = expect_dict(metadata_value, f"{context}.metadata")
    title = metadata.get("title")
    if not isinstance(title, str) or not title:
        raise PublicationError(f"{context} title is malformed")
    creators = expect_list(metadata.get("creators"), f"{context}.metadata.creators")
    creator_names: set[str] = set()
    for index, value in enumerate(creators):
        creator = expect_dict(value, f"{context}.metadata.creators[{index}]")
        name = creator.get("name")
        if name is None and isinstance(creator.get("person_or_org"), dict):
            name = creator["person_or_org"].get("name")
        if not isinstance(name, str) or not name:
            raise PublicationError(f"{context} creator identity is malformed")
        creator_names.add(name)
    expected_people = {
        tuple(sorted(re.findall(r"[a-z0-9]+", value.casefold())))
        for value in (plan["zenodo"]["creator"], plan["authority"]["author"])
    }
    creator_matches = any(
        tuple(sorted(re.findall(r"[a-z0-9]+", name.casefold())))
        in expected_people
        for name in creator_names
    )
    exact_title = title == plan["release"]["title"]
    if exact_title and not creator_matches:
        raise PublicationError(f"{context} exact title has a different creator")
    related_text = " ".join(
        plain_text(value)
        for value in (
            metadata.get("description"),
            metadata.get("notes"),
            metadata.get("related_identifiers"),
        )
    ).casefold()
    title_text = " ".join(re.findall(r"[a-z0-9]+", title.casefold()))
    title_identifies_work = (
        "linear algebra" in title_text or "aljabar linear" in title_text
    )
    authority_identifies_work = any(
        str(value).casefold() in related_text
        for value in (
            plan["authority"]["source_commit"],
            plan["authority"]["source_commit_url"],
            plan["authority"]["repository"],
            plan["authority"]["homepage"],
        )
    )
    if not exact_title and not (
        creator_matches and (title_identifies_work or authority_identifies_work)
    ):
        raise PublicationError(f"{context} is not provably the intended work")
    return metadata


def _zenodo_exact_work_rows(
    rows: Iterable[dict[str, Any]], plan: dict[str, Any], context: str
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for index, value in enumerate(rows):
        row = expect_dict(value, f"{context}[{index}]")
        metadata = expect_dict(row.get("metadata"), f"{context}[{index}].metadata")
        try:
            validate_zenodo_work_metadata(metadata, plan, f"{context}[{index}]")
        except PublicationError:
            if metadata.get("title") == plan["release"]["title"]:
                raise
            continue
        else:
            matches.append(row)
    return matches


def discover_zenodo_lineage(
    client: ZenodoClient, plan: dict[str, Any], binding: dict[str, str]
) -> dict[str, Any]:
    """Discover the one authenticated concept for this exact work, or none.

    Exact-title records in the public index must reconcile to the authenticated
    account.  Multiple concepts, an unowned public concept, malformed lineage
    identifiers, or multiple open drafts all fail closed.
    """

    title = plan["release"]["title"]
    search_terms = (
        title,
        plan["authority"]["source_commit"],
        plan["zenodo"]["creator"],
        plan["authority"]["author"],
    )
    escaped_terms = [
        str(value).replace("\\", "\\\\").replace('"', '\\"')
        for value in search_terms
    ]
    same_work_query = " OR ".join(f'"{value}"' for value in escaped_terms)
    authenticated = _zenodo_exact_work_rows(
        zenodo_paginated(client, same_work_query), plan, "Zenodo deposition"
    )
    public = _zenodo_exact_work_rows(
        zenodo_public_paginated(same_work_query),
        plan,
        "Zenodo public record",
    )
    if not authenticated and not public:
        return {
            "status": "absent",
            "authenticated_record_count": 0,
            "public_record_count": 0,
            "open_draft_ids": [],
        }

    for channel, rows in (("authenticated", authenticated), ("public", public)):
        for index, row in enumerate(rows):
            metadata = expect_dict(
                row.get("metadata"), f"Zenodo {channel} same-work row[{index}].metadata"
            )
            if metadata.get("version") != plan["release"]["version"]:
                continue
            marker = _zenodo_transaction_fingerprint(metadata)
            if (
                metadata.get("title") != plan["release"]["title"]
                or marker != binding["fingerprint"]
            ):
                marker_text = marker if marker is not None else "missing"
                raise PublicationError(
                    "the same-work Zenodo concept already has the target version "
                    f"under a different identity ({channel}: {marker_text})"
                )

    authenticated_concepts = {
        zenodo_concept_identity(row, "Zenodo deposition")[0]
        for row in authenticated
    }
    public_concepts = {
        zenodo_concept_identity(row, "Zenodo public record")[0] for row in public
    }
    all_concepts = authenticated_concepts | public_concepts
    if len(all_concepts) != 1:
        raise PublicationError(
            "ambiguous existing same-work Zenodo concepts were discovered"
        )
    if public_concepts and not authenticated_concepts:
        raise PublicationError(
            "a public same-work Zenodo concept is not present in authenticated deposits"
        )
    if public_concepts and public_concepts != authenticated_concepts:
        raise PublicationError(
            "authenticated and public same-work Zenodo concepts disagree"
        )
    conceptrecid = next(iter(all_concepts))
    concept_doi = f"10.5281/zenodo.{conceptrecid}"

    published: dict[int, tuple[str, dict[str, Any] | None]] = {}
    authenticated_deposition_records: dict[int, int] = {}
    open_drafts: dict[int, dict[str, Any]] = {}
    explicit_latest_record_ids: set[int] = set()
    explicit_latest_deposition_ids: set[int] = set()
    for channel, rows in (("authenticated", authenticated), ("public", public)):
        for index, row in enumerate(rows):
            row_concept, row_concept_doi = zenodo_concept_identity(
                row, f"Zenodo {channel} row[{index}]"
            )
            if (row_concept, row_concept_doi) != (conceptrecid, concept_doi):
                raise PublicationError("Zenodo same-work concept identity drifted")
            record_id, record_doi = zenodo_record_identity(
                row, f"Zenodo {channel} row[{index}]"
            )
            if channel == "authenticated":
                deposition_id = zenodo_deposition_id(
                    row, f"Zenodo {channel} row[{index}]"
                )
                prior_record = authenticated_deposition_records.get(deposition_id)
                if prior_record not in {None, record_id}:
                    raise PublicationError(
                        "one Zenodo deposition maps to conflicting record identities"
                    )
                authenticated_deposition_records[deposition_id] = record_id
            is_published = (
                channel == "public"
                or row.get("state") == "done"
                or row.get("submitted") is True
            )
            if is_published:
                prior = published.get(record_id)
                if prior is not None and prior[0] != record_doi:
                    raise PublicationError("Zenodo lineage record DOI identities disagree")
                published[record_id] = (
                    record_doi,
                    row if channel == "authenticated" else (prior[1] if prior else None),
                )
            else:
                open_drafts[record_id] = row
            links_value = row.get("links")
            if links_value is not None:
                links = expect_dict(links_value, f"Zenodo {channel} row[{index}].links")
                if is_published and links.get("latest") is not None:
                    latest_link = str(links["latest"])
                    latest_id = _zenodo_id_from_link(
                        latest_link, f"Zenodo {channel} row[{index}].links.latest"
                    )
                    if "/api/deposit/depositions/" in latest_link:
                        explicit_latest_deposition_ids.add(latest_id)
                    else:
                        explicit_latest_record_ids.add(latest_id)
            if is_published and row.get("is_latest") is True:
                explicit_latest_record_ids.add(record_id)

    if len(open_drafts) > 1:
        raise PublicationError("multiple open drafts exist in the intended Zenodo concept")
    if not published:
        return {
            "status": "unpublished-concept",
            "conceptrecid": conceptrecid,
            "concept_doi": concept_doi,
            "authenticated_record_count": len(authenticated),
            "public_record_count": len(public),
            "open_draft_ids": sorted(open_drafts),
            "open_drafts": list(open_drafts.values()),
        }
    for deposition_id in explicit_latest_deposition_ids:
        if deposition_id not in authenticated_deposition_records:
            raise PublicationError(
                "Zenodo latest deposition link is outside authenticated same-work deposits"
            )
        explicit_latest_record_ids.add(
            authenticated_deposition_records[deposition_id]
        )
    if len(explicit_latest_record_ids) > 1:
        raise PublicationError("Zenodo same-work records disagree about the latest version")
    latest_record_id = (
        next(iter(explicit_latest_record_ids))
        if explicit_latest_record_ids
        else max(published)
    )
    if latest_record_id not in published:
        raise PublicationError("Zenodo latest-version link is outside the discovered work")
    latest_record_doi, latest_deposition = published[latest_record_id]
    if latest_deposition is None:
        raise PublicationError(
            "the public latest Zenodo record has no authenticated deposition identity"
        )
    latest_deposition_id = zenodo_deposition_id(
        latest_deposition, "Zenodo latest deposition"
    )
    latest_concept = zenodo_concept_identity(
        latest_deposition, "Zenodo latest deposition"
    )
    latest_identity = zenodo_record_identity(
        latest_deposition, "Zenodo latest deposition"
    )
    validate_zenodo_work_metadata(
        latest_deposition.get("metadata"), plan, "Zenodo latest deposition"
    )
    if latest_concept != (conceptrecid, concept_doi) or latest_identity != (
        latest_record_id,
        latest_record_doi,
    ):
        raise PublicationError("Zenodo latest deposition identity differs from its lineage")
    if latest_deposition.get("state") != "done" and latest_deposition.get("submitted") is not True:
        raise PublicationError("Zenodo latest lineage record is not published")
    return {
        "status": "existing",
        "conceptrecid": conceptrecid,
        "concept_doi": concept_doi,
        "latest_deposition_id": latest_deposition_id,
        "latest_record_id": latest_record_id,
        "latest_record_doi": latest_record_doi,
        "latest_deposition": latest_deposition,
        "authenticated_record_count": len(authenticated),
        "public_record_count": len(public),
        "open_draft_ids": sorted(open_drafts),
        "open_drafts": list(open_drafts.values()),
    }


def zenodo_lineage_summary(lineage: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "status",
        "conceptrecid",
        "concept_doi",
        "latest_deposition_id",
        "latest_record_id",
        "latest_record_doi",
        "authenticated_record_count",
        "public_record_count",
        "open_draft_ids",
    )
    return {key: lineage[key] for key in keys if key in lineage}


def pin_zenodo_lineage(state: dict[str, Any], lineage: dict[str, Any]) -> None:
    expected = {
        "zenodo_conceptrecid": _zenodo_positive_id(
            lineage.get("conceptrecid"), "Zenodo lineage conceptrecid"
        ),
        "zenodo_concept_doi": str(lineage.get("concept_doi")),
        "zenodo_lineage_latest_deposition_id": _zenodo_positive_id(
            lineage.get("latest_deposition_id"),
            "Zenodo lineage latest deposition ID",
        ),
        "zenodo_lineage_latest_record_id": _zenodo_positive_id(
            lineage.get("latest_record_id"), "Zenodo lineage latest record ID"
        ),
        "zenodo_lineage_latest_record_doi": str(lineage.get("latest_record_doi")),
    }
    if expected["zenodo_concept_doi"] != (
        f"10.5281/zenodo.{expected['zenodo_conceptrecid']}"
    ):
        raise PublicationError("Zenodo lineage concept identity is malformed")
    if expected["zenodo_lineage_latest_record_doi"] != (
        f"10.5281/zenodo.{expected['zenodo_lineage_latest_record_id']}"
    ):
        raise PublicationError("Zenodo lineage latest-record identity is malformed")
    for key, value in expected.items():
        if state.get(key) not in {None, value}:
            raise PublicationError(f"stored {key} differs from discovered Zenodo lineage")
        state[key] = value


def validate_pinned_zenodo_lineage(
    client: ZenodoClient, plan: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any] | None:
    if "zenodo_conceptrecid" not in state:
        return None
    latest_deposition_id = _zenodo_positive_id(
        state.get("zenodo_lineage_latest_deposition_id"),
        "stored Zenodo latest deposition ID",
    )
    _status, _headers, value = client.request(
        "GET", f"/deposit/depositions/{latest_deposition_id}"
    )
    row = expect_dict(value, "stored Zenodo latest deposition")
    if zenodo_concept_identity(row, "stored Zenodo latest deposition") != (
        state["zenodo_conceptrecid"],
        state["zenodo_concept_doi"],
    ):
        raise PublicationError("stored Zenodo concept lineage differs on resume")
    if zenodo_record_identity(row, "stored Zenodo latest deposition") != (
        state["zenodo_lineage_latest_record_id"],
        state["zenodo_lineage_latest_record_doi"],
    ):
        raise PublicationError("stored Zenodo latest-record identity differs on resume")
    if zenodo_deposition_id(row, "stored Zenodo latest deposition") != latest_deposition_id:
        raise PublicationError("stored Zenodo latest-deposition identity differs on resume")
    validate_zenodo_work_metadata(
        row.get("metadata"), plan, "stored Zenodo latest deposition"
    )
    return row


def validate_zenodo_newversion_draft(
    draft_value: Any, plan: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any]:
    draft = expect_dict(draft_value, "Zenodo new-version draft")
    draft_id = zenodo_deposition_id(draft, "Zenodo new-version draft")
    parent_id = _zenodo_positive_id(
        state.get("zenodo_lineage_latest_deposition_id"),
        "stored Zenodo latest deposition ID",
    )
    if draft_id == parent_id:
        raise PublicationError("Zenodo latest_draft still resolves to the published parent")
    if zenodo_concept_identity(draft, "Zenodo new-version draft") != (
        state.get("zenodo_conceptrecid"),
        state.get("zenodo_concept_doi"),
    ):
        raise PublicationError("Zenodo new-version draft left the pinned concept")
    validate_zenodo_work_metadata(
        draft.get("metadata"), plan, "Zenodo new-version draft"
    )
    if draft.get("state") == "done" or draft.get("submitted") is True:
        raise PublicationError("Zenodo new-version target is not an editable draft")
    return draft


def zenodo_latest_draft_from_response(
    client: ZenodoClient,
    response_value: Any,
    plan: dict[str, Any],
    state: dict[str, Any],
    *,
    allow_absent: bool = False,
) -> dict[str, Any] | None:
    """Follow the documented links.latest_draft from the original resource."""

    response = expect_dict(response_value, "Zenodo new-version response")
    parent_id = _zenodo_positive_id(
        state.get("zenodo_lineage_latest_deposition_id"),
        "stored Zenodo latest deposition ID",
    )
    if zenodo_deposition_id(response, "Zenodo new-version response") != parent_id:
        raise PublicationError("Zenodo new-version action did not return the original resource")
    if zenodo_concept_identity(response, "Zenodo new-version response") != (
        state.get("zenodo_conceptrecid"),
        state.get("zenodo_concept_doi"),
    ):
        raise PublicationError("Zenodo new-version response left the pinned concept")
    links = expect_dict(response.get("links"), "Zenodo new-version response.links")
    latest_draft_url = links.get("latest_draft")
    if latest_draft_url is None:
        if allow_absent:
            return None
        raise PublicationError("Zenodo new-version response omitted links.latest_draft")
    draft_id = _zenodo_id_from_link(
        latest_draft_url, "Zenodo new-version response.links.latest_draft"
    )
    if draft_id == parent_id:
        if allow_absent:
            return None
        raise PublicationError("Zenodo latest_draft did not advance to a new record")
    _status, _headers, value = client.request("GET", latest_draft_url)
    draft = validate_zenodo_newversion_draft(value, plan, state)
    if zenodo_deposition_id(draft, "Zenodo new-version draft") != draft_id:
        raise PublicationError("Zenodo latest_draft link and draft identity disagree")
    return draft


def recover_zenodo_newversion_draft(
    client: ZenodoClient, plan: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any] | None:
    parent_id = _zenodo_positive_id(
        state.get("zenodo_lineage_latest_deposition_id"),
        "stored Zenodo latest deposition ID",
    )
    try:
        _status, _headers, parent = client.request(
            "GET", f"/deposit/depositions/{parent_id}"
        )
    except PublicationError:
        return None
    return zenodo_latest_draft_from_response(
        client, parent, plan, state, allow_absent=True
    )


def request_zenodo_newversion(
    client: ZenodoClient, plan: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any]:
    parent_id = _zenodo_positive_id(
        state.get("zenodo_lineage_latest_deposition_id"),
        "stored Zenodo latest deposition ID",
    )
    prior_phase = state.get("zenodo_newversion_phase")
    if prior_phase in {"requested", "done"}:
        recovered = recover_zenodo_newversion_draft(client, plan, state)
        if recovered is None:
            raise PublicationError(
                "a prior Zenodo new-version action remains ambiguous; refusing a duplicate action"
            )
        state["zenodo_newversion_phase"] = "done"
        state["zenodo_deposition_id"] = zenodo_deposition_id(
            recovered, "Zenodo new-version draft"
        )
        save_state(state)
        return recovered
    state["zenodo_newversion_phase"] = "requested"
    save_state(state)
    try:
        _status, _headers, original_resource = client.request(
            "POST",
            f"/deposit/depositions/{parent_id}/actions/newversion",
            expected=(201,),
            retryable=False,
        )
        draft = zenodo_latest_draft_from_response(
            client, original_resource, plan, state
        )
    except PublicationError as original:
        draft = recover_zenodo_newversion_draft(client, plan, state)
        if draft is None:
            raise original
    state["zenodo_newversion_phase"] = "done"
    state["zenodo_deposition_id"] = zenodo_deposition_id(
        draft, "Zenodo new-version draft"
    )
    save_state(state)
    return draft


def zenodo_lineage_from_deposition(deposition: dict[str, Any]) -> dict[str, Any]:
    conceptrecid, concept_doi = zenodo_concept_identity(
        deposition, "Zenodo deposition"
    )
    record_id, record_doi = zenodo_record_identity(
        deposition, "Zenodo deposition"
    )
    return {
        "status": "existing",
        "conceptrecid": conceptrecid,
        "concept_doi": concept_doi,
        "latest_deposition_id": zenodo_deposition_id(
            deposition, "Zenodo deposition"
        ),
        "latest_record_id": record_id,
        "latest_record_doi": record_doi,
    }


def poll_exact_zenodo_deposition(
    client: ZenodoClient,
    plan: dict[str, Any],
    binding: dict[str, str],
    *,
    attempts: int = 8,
) -> dict[str, Any] | None:
    for attempt in range(attempts):
        exact = exact_zenodo_depositions(client, plan, binding)
        if exact:
            return exact[0]
        if attempt + 1 < attempts:
            time.sleep(backoff_seconds(min(attempt, 4)))
    return None


def reserve_zenodo(
    client: ZenodoClient,
    plan: dict[str, Any],
    binding: dict[str, str],
    state: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    deposition: dict[str, Any] | None = None
    if "zenodo_conceptrecid" in state:
        validate_pinned_zenodo_lineage(client, plan, state)
    stored_id = state.get("zenodo_deposition_id")
    if stored_id is not None:
        if not isinstance(stored_id, int):
            raise PublicationError("stored Zenodo deposition ID is malformed")
        _status, _headers, value = client.request(
            "GET", f"/deposit/depositions/{stored_id}"
        )
        try:
            deposition = validate_deposition_identity(
                value, plan, binding, require_final_metadata=False
            )
        except PublicationError:
            if state.get("zenodo_newversion_phase") not in {"requested", "done"}:
                raise
            deposition = validate_zenodo_newversion_draft(value, plan, state)
        if "zenodo_conceptrecid" in state and zenodo_concept_identity(
            deposition, "stored Zenodo deposition"
        ) != (state["zenodo_conceptrecid"], state["zenodo_concept_doi"]):
            raise PublicationError("stored Zenodo deposition left the pinned concept")
    else:
        exact = exact_zenodo_depositions(client, plan, binding)
        if exact:
            deposition = exact[0]
        else:
            prior_create_phase = state.get("zenodo_create_phase")
            if prior_create_phase in {"requested", "done"}:
                deposition = poll_exact_zenodo_deposition(client, plan, binding)
                if deposition is None:
                    raise PublicationError(
                        "a prior Zenodo deposition-create action remains ambiguous; "
                        "refusing a duplicate create action"
                    )
        if deposition is None:
            guarded = zenodo_title_version_guard(client, plan, binding)
            if guarded is not None:
                deposition = validate_deposition_identity(
                    guarded, plan, binding, require_final_metadata=False
                )
            else:
                lineage = discover_zenodo_lineage(client, plan, binding)
                status = lineage.get("status")
                if status == "existing":
                    if "zenodo_conceptrecid" in state:
                        if state["zenodo_conceptrecid"] != lineage["conceptrecid"]:
                            raise PublicationError(
                                "stored and discovered Zenodo concept lineages differ"
                            )
                    else:
                        pin_zenodo_lineage(state, lineage)
                        save_state(state)
                    open_ids = set(lineage.get("open_draft_ids", []))
                    if open_ids and state.get("zenodo_newversion_phase") not in {
                        "requested",
                        "done",
                    }:
                        raise PublicationError(
                            "the intended Zenodo concept already has an unrelated open draft"
                        )
                    deposition = request_zenodo_newversion(client, plan, state)
                elif status == "unpublished-concept":
                    raise PublicationError(
                        "an unpublished same-work Zenodo concept exists without a resumable exact transaction"
                    )
                elif status == "absent":
                    if "zenodo_conceptrecid" in state:
                        raise PublicationError(
                            "stored Zenodo concept lineage disappeared before creation"
                        )
                    initial_metadata = zenodo_metadata(plan, None, binding["fingerprint"])
                    state["zenodo_create_phase"] = "requested"
                    save_state(state)
                    try:
                        _status, _headers, value = client.request(
                            "POST",
                            "/deposit/depositions",
                            body={"metadata": initial_metadata},
                            expected=(201,),
                            retryable=False,
                        )
                        deposition = validate_deposition_identity(
                            value, plan, binding, require_final_metadata=False
                        )
                    except PublicationError as original:
                        deposition = poll_exact_zenodo_deposition(client, plan, binding)
                        if deposition is None:
                            raise original
                    pin_zenodo_lineage(
                        state, zenodo_lineage_from_deposition(deposition)
                    )
                else:
                    raise PublicationError("Zenodo lineage discovery returned an invalid status")
        if "zenodo_conceptrecid" not in state:
            lineage = discover_zenodo_lineage(client, plan, binding)
            if lineage.get("status") == "existing":
                pin_zenodo_lineage(state, lineage)
            else:
                pin_zenodo_lineage(
                    state, zenodo_lineage_from_deposition(deposition)
                )
        state["zenodo_deposition_id"] = deposition["id"]
        if state.get("zenodo_newversion_phase") not in {"requested", "done"}:
            state["zenodo_create_phase"] = "done"
        save_state(state)
    if "zenodo_conceptrecid" not in state:
        pin_zenodo_lineage(state, zenodo_lineage_from_deposition(deposition))
    if zenodo_concept_identity(deposition, "Zenodo deposition") != (
        state["zenodo_conceptrecid"],
        state["zenodo_concept_doi"],
    ):
        raise PublicationError("Zenodo deposition concept differs from transaction state")
    doi = zenodo_doi(deposition)
    if state.get("zenodo_doi") not in {None, doi}:
        raise PublicationError("Zenodo DOI differs from transaction state")
    state["zenodo_doi"] = doi
    record_id, record_doi = zenodo_record_identity(deposition, "Zenodo deposition")
    if record_doi != doi:
        raise PublicationError("Zenodo DOI differs from deposition record identity")
    state["zenodo_record_id"] = record_id
    save_state(state)
    if deposition.get("state") != "done":
        try:
            _status, _headers, value = client.request(
                "PUT",
                f"/deposit/depositions/{deposition['id']}",
                body={"metadata": zenodo_metadata(plan, doi, binding["fingerprint"])},
            )
            deposition = validate_deposition_identity(
                value, plan, binding, require_final_metadata=True
            )
        except PublicationError as original:
            try:
                deposition = refresh_deposition(
                    client, deposition["id"], plan, binding
                )
            except PublicationError:
                raise original
    else:
        deposition = validate_deposition_identity(
            deposition, plan, binding, require_final_metadata=True
        )
    return deposition, doi


def zenodo_files_by_name(deposition: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, item_value in enumerate(expect_list(deposition.get("files") or [], "deposition.files")):
        item = expect_dict(item_value, f"deposition.files[{index}]")
        name = validate_basename(require_string(item, "filename", "Zenodo file"), "Zenodo file")
        if name in result:
            raise PublicationError("Zenodo deposition has duplicate filenames")
        result[name] = item
    return result


def verify_zenodo_files_authenticated(
    client: ZenodoClient,
    deposition: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    files = zenodo_files_by_name(deposition)
    if set(files) != set(artifacts):
        raise PublicationError("Zenodo file-name closure differs from frozen artifacts")
    results: list[dict[str, Any]] = []
    for name, expected in artifacts.items():
        item = files[name]
        size = require_integer(item, "filesize", "Zenodo file")
        checksum = require_string(item, "checksum", "Zenodo file").removeprefix("md5:").lower()
        require_sha(checksum, "Zenodo file checksum", algorithm="md5")
        path = Path(expected["local_path"])
        if size != expected["bytes"] or checksum != md5_file(path):
            raise PublicationError(f"Zenodo file size/MD5 differs: {name}")
        links = expect_dict(item.get("links"), "Zenodo file links")
        download = require_string(links, "download", "Zenodo file links")
        validate_origin(download, client.origins)
        downloaded_size, digest = client.content_sha256(download, expected["bytes"])
        if downloaded_size != expected["bytes"] or digest != expected["sha256"]:
            raise PublicationError(f"Zenodo authenticated SHA-256 readback differs: {name}")
        results.append({"name": name, "bytes": downloaded_size, "sha256": digest})
    return results


def zenodo_artifacts(final: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, item in artifact_map(final, manifest).items():
        result[name] = {**item, "local_path": str(final / "release-assets" / name)}
    return result


def refresh_deposition(
    client: ZenodoClient,
    deposition_id: int,
    plan: dict[str, Any],
    binding: dict[str, str],
) -> dict[str, Any]:
    _status, _headers, value = client.request(
        "GET", f"/deposit/depositions/{deposition_id}"
    )
    return validate_deposition_identity(
        value, plan, binding, require_final_metadata=True
    )


def poll_deposition(
    client: ZenodoClient,
    deposition_id: int,
    plan: dict[str, Any],
    binding: dict[str, str],
    *,
    require_done: bool = False,
    attempts: int = 10,
) -> dict[str, Any] | None:
    for attempt in range(attempts):
        try:
            deposition = refresh_deposition(client, deposition_id, plan, binding)
        except PublicationError:
            deposition = None
        if deposition is not None and (
            not require_done or deposition.get("state") == "done"
        ):
            return deposition
        if attempt + 1 < attempts:
            time.sleep(backoff_seconds(min(attempt, 4)))
    return None


def zenodo_file_matches_local(item: dict[str, Any], expected: dict[str, Any]) -> bool:
    path = Path(expected["local_path"])
    checksum = str(item.get("checksum") or "").removeprefix("md5:").lower()
    return item.get("filesize") == expected["bytes"] and checksum == md5_file(path)


def upload_zenodo_draft(
    client: ZenodoClient,
    plan: dict[str, Any],
    binding: dict[str, str],
    deposition: dict[str, Any],
    final: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    if deposition.get("state") == "done":
        return deposition
    artifacts = zenodo_artifacts(final, manifest)
    links = expect_dict(deposition.get("links"), "deposition.links")
    bucket = require_string(links, "bucket", "deposition.links").rstrip("/")
    validate_origin(bucket, client.origins)
    files = zenodo_files_by_name(deposition)
    extras = set(files) - set(artifacts)
    if extras:
        raise PublicationError(f"Zenodo draft has unexpected files: {sorted(extras)}")
    for name, expected in artifacts.items():
        prior = files.get(name)
        local_path = Path(expected["local_path"])
        if prior is not None:
            if zenodo_file_matches_local(prior, expected):
                continue
            prior_links = expect_dict(prior.get("links"), "Zenodo prior file links")
            delete_url = require_string(prior_links, "self", "Zenodo prior file links")
            validate_origin(delete_url, client.origins)
            try:
                client.request(
                    "DELETE", delete_url, expected_type=None, expected=(204,)
                )
            except PublicationError as original:
                recovered = poll_deposition(
                    client, deposition["id"], plan, binding, attempts=4
                )
                if recovered is None or name in zenodo_files_by_name(recovered):
                    raise original
        upload_url = bucket + "/" + urllib.parse.quote(name, safe="")
        try:
            client.upload(upload_url, local_path)
        except PublicationError as original:
            recovered = poll_deposition(
                client, deposition["id"], plan, binding, attempts=8
            )
            if recovered is None:
                raise original
            recovered_file = zenodo_files_by_name(recovered).get(name)
            if recovered_file is None or not zenodo_file_matches_local(
                recovered_file, expected
            ):
                raise original
    return refresh_deposition(client, deposition["id"], plan, binding)


def poll_zenodo_public(
    record_id: int, *, attempts: int = 12
) -> dict[str, Any]:
    url = f"{ZENODO_ORIGIN}/api/records/{record_id}"
    last_error: PublicationError | None = None
    for attempt in range(attempts):
        try:
            return expect_dict(anonymous_json(url), "Zenodo public record")
        except PublicationError as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(backoff_seconds(min(attempt, 4)))
    raise PublicationError(f"Zenodo public record did not become consistent: {last_error}")


def publish_zenodo(
    client: ZenodoClient,
    plan: dict[str, Any],
    binding: dict[str, str],
    state: dict[str, Any],
    deposition: dict[str, Any],
    final: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    artifacts = zenodo_artifacts(final, manifest)
    deposition_id = require_integer(deposition, "id", "deposition")
    prior_phase = state.get("zenodo_publish_phase")
    if prior_phase in {"requested", "done"} and deposition.get("state") != "done":
        recovered = poll_deposition(
            client,
            deposition_id,
            plan,
            binding,
            require_done=True,
        )
        if recovered is None:
            raise PublicationError(
                "a prior Zenodo publish action remains ambiguous; refusing a duplicate action"
            )
        deposition = recovered
    deposition = upload_zenodo_draft(
        client, plan, binding, deposition, final, manifest
    )
    # This is the irreversible boundary. Re-read every frozen local byte, all
    # normalized metadata, remote MD5, and authenticated remote content SHA-256.
    verify_inventory(final, binding)
    deposition = refresh_deposition(client, deposition_id, plan, binding)
    verified_files = verify_zenodo_files_authenticated(client, deposition, artifacts)
    assert_zenodo_metadata(
        deposition["metadata"],
        plan,
        zenodo_doi(deposition),
        binding["fingerprint"],
        public=False,
    )
    if deposition.get("state") != "done":
        state["zenodo_publish_phase"] = "requested"
        save_state(state)
        try:
            _status, _headers, value = client.request(
                "POST",
                f"/deposit/depositions/{deposition_id}/actions/publish",
                expected=(202,),
                retryable=False,
            )
            deposition = validate_deposition_identity(
                value, plan, binding, require_final_metadata=True
            )
        except PublicationError as original:
            # A lost response is ambiguous; query the exact fingerprint-bound
            # deposition instead of issuing a second publish action.
            recovered = poll_deposition(
                client,
                deposition_id,
                plan,
                binding,
                require_done=True,
            )
            if recovered is None:
                raise original
            deposition = recovered
        if deposition.get("state") != "done":
            recovered = poll_deposition(
                client,
                deposition_id,
                plan,
                binding,
                require_done=True,
            )
            if recovered is None:
                raise PublicationError("Zenodo deposition did not reach done after publication")
            deposition = recovered
    validate_deposition_identity(
        deposition, plan, binding, require_final_metadata=True
    )
    if zenodo_doi(deposition) != require_string(state, "zenodo_doi", "state"):
        raise PublicationError("published Zenodo DOI differs from transaction state")
    record_id = deposition.get("record_id") or state.get("zenodo_record_id")
    try:
        record_id = int(record_id)
    except (TypeError, ValueError):
        raise PublicationError("published Zenodo record ID is missing") from None
    public = poll_zenodo_public(record_id)
    state["zenodo_record_id"] = record_id
    state["zenodo_published"] = True
    state["zenodo_publish_phase"] = "done"
    state["zenodo_prepublish_authenticated_files"] = verified_files
    save_state(state)
    return public


class PublicGitHubClient:
    """Anonymous GitHub API client matching the read-only client interface."""

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        body: Any | None = None,
        expected_type: type | None = dict,
        expected: Sequence[int] = (200,),
        retryable: bool | None = None,
    ) -> tuple[int, dict[str, str], Any]:
        if body is not None or method not in {"GET", "HEAD"}:
            raise PublicationError("anonymous GitHub client is strictly read-only")
        status, headers, payload, _final = http_bytes(
            method,
            GITHUB_API_ORIGIN + endpoint,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            expected=expected,
            allowed_origins={origin(GITHUB_API_ORIGIN)},
            retryable=True if retryable is None else retryable,
        )
        value = (
            None
            if expected_type is None
            else decode_bounded_json(payload, expected_type, endpoint)
        )
        return status, headers, value


def assert_release_metadata(
    release: dict[str, Any], plan: dict[str, Any], final: Path, commit_sha: str
) -> None:
    expected = expected_release_metadata(plan, final, commit_sha, draft=False)
    for key, value in expected.items():
        if release.get(key) != value:
            raise PublicationError(f"public GitHub release metadata differs: {key}")


def poll_exact_public_file(
    url: str,
    local: Path,
    *,
    allowed_origins: set[tuple[str, str, int]],
    attempts: int = 12,
) -> tuple[int, str, str]:
    expected_bytes = local.stat().st_size
    expected_sha = sha256_file(local)
    last_error: PublicationError | None = None
    for attempt in range(attempts):
        try:
            result = stream_sha256(
                url,
                allowed_origins=allowed_origins,
                expected_bytes=expected_bytes,
                retryable=False,
                timeout=60,
            )
            if result[1] != expected_sha:
                raise PublicationError("public file byte hash differs")
            return result
        except PublicationError as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(backoff_seconds(min(attempt, 4)))
    raise PublicationError(f"public file did not become byte-consistent: {last_error}")


def verify_public_github(
    plan: dict[str, Any], state: dict[str, Any], final: Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    public = PublicGitHubClient()
    repository_settings = read_repository_settings(
        public,
        plan,
        branch_exists=True,
        expected_repository_id=require_integer(state, "github_repository_id", "state"),
    )
    expected_repository = repository_entries(plan, final)
    commit_sha = require_string(state, "github_commit_sha", "state")
    repository = verify_remote_repository(public, plan, expected_repository, commit_sha)  # type: ignore[arg-type]
    if resolve_tag(public, plan) != commit_sha:  # type: ignore[arg-type]
        raise PublicationError("anonymous GitHub tag does not resolve to the frozen commit")
    _status, _headers, release_value = public.request(
        "GET", repo_base(plan) + f"/releases/tags/{urllib.parse.quote(plan['release']['tag'], safe='')}"
    )
    release = expect_dict(release_value, "public release")
    assert_release_metadata(release, plan, final, commit_sha)
    if release.get("html_url") != github_release_url(plan):
        raise PublicationError("public GitHub release URL differs")
    release_id = require_integer(release, "id", "public release")
    _status, _headers, latest_value = public.request(
        "GET", repo_base(plan) + "/releases/latest"
    )
    latest = expect_dict(latest_value, "latest public release")
    if latest.get("id") != release_id:
        raise PublicationError("target GitHub release is not anonymously latest")
    assets = github_paginated(public, repo_base(plan) + f"/releases/{release_id}/assets")  # type: ignore[arg-type]
    by_name: dict[str, dict[str, Any]] = {}
    for item in assets:
        name = validate_basename(require_string(item, "name", "public asset"), "public asset")
        if name in by_name:
            raise PublicationError("public GitHub release has duplicate assets")
        by_name[name] = item
    expected_artifacts = artifact_map(final, manifest)
    if set(by_name) != set(expected_artifacts) or len(assets) != len(expected_artifacts):
        raise PublicationError("public GitHub release asset closure differs")
    readbacks: list[dict[str, Any]] = []
    for name, expected in expected_artifacts.items():
        asset = by_name[name]
        if asset.get("size") != expected["bytes"]:
            raise PublicationError(f"public GitHub asset size differs: {name}")
        download = require_string(asset, "browser_download_url", "public asset")
        expected_download = (
            f"{GITHUB_WEB_ORIGIN}/{plan['github']['owner']}/{plan['github']['repository']}"
            f"/releases/download/{urllib.parse.quote(plan['release']['tag'], safe='')}/"
            f"{urllib.parse.quote(name, safe='')}"
        )
        if download != expected_download:
            raise PublicationError(f"public GitHub asset URL differs: {name}")
        validate_origin(download, {origin(GITHUB_WEB_ORIGIN)})
        size, digest, _final_url = stream_sha256(
            download, expected_bytes=expected["bytes"], retryable=True
        )
        if digest != expected["sha256"]:
            raise PublicationError(f"public GitHub asset SHA-256 differs: {name}")
        readbacks.append({"name": name, "bytes": size, "sha256": digest})
    raw_readme = (
        f"https://raw.githubusercontent.com/{plan['github']['owner']}/"
        f"{plan['github']['repository']}/{plan['github']['default_branch']}/README.md"
    )
    local_readme = final / "snapshot" / "README.md"
    size, digest, _url = stream_sha256(
        raw_readme,
        allowed_origins={origin(GITHUB_RAW_ORIGIN)},
        expected_bytes=local_readme.stat().st_size,
        retryable=True,
    )
    if digest != sha256_file(local_readme):
        raise PublicationError("anonymous raw repository README differs")
    page_url = (
        f"https://{plan['github']['owner'].lower()}.github.io/"
        f"{plan['github']['repository']}/"
    )
    local_page = final / "snapshot" / "docs" / "index.html"
    page_result = poll_exact_public_file(
        page_url, local_page, allowed_origins={origin(page_url)}
    )
    return {
        "release_id": release_id,
        "release_url": require_string(release, "html_url", "public release"),
        "repository": {**repository, "settings": repository_settings},
        "assets": readbacks,
        "raw_readme": {"bytes": size, "sha256": digest},
        "pages": {
            "url": page_url,
            "bytes": page_result[0],
            "sha256": page_result[1],
        },
    }


def public_record_files(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, item_value in enumerate(expect_list(record.get("files"), "record.files")):
        item = expect_dict(item_value, f"record.files[{index}]")
        name = validate_basename(require_string(item, "key", "record file"), "record file")
        if name in result:
            raise PublicationError("Zenodo public record has duplicate filenames")
        result[name] = item
    return result


def public_record_doi(record: dict[str, Any]) -> str:
    """Normalize the exact DOI identity from legacy or current record shapes."""

    values: list[tuple[str, str]] = []
    top_level = record.get("doi")
    if top_level is not None:
        if not isinstance(top_level, str) or not re.fullmatch(
            r"10\.5281/zenodo\.\d+", top_level
        ):
            raise PublicationError("record.doi is malformed")
        values.append(("record.doi", top_level))
    doi_url = record.get("doi_url")
    if doi_url is not None:
        if not isinstance(doi_url, str):
            raise PublicationError("record.doi_url is malformed")
        validate_origin(doi_url, {origin("https://doi.org")})
        parsed = urllib.parse.urlsplit(doi_url)
        url_doi = urllib.parse.unquote(parsed.path.strip("/"))
        if parsed.query or parsed.fragment or not re.fullmatch(
            r"10\.5281/zenodo\.\d+", url_doi
        ):
            raise PublicationError("record.doi_url is malformed")
        values.append(("record.doi_url", url_doi))
    if "pids" in record:
        pids = expect_dict(record.get("pids"), "record.pids")
        if "doi" in pids:
            doi_pid = expect_dict(pids.get("doi"), "record.pids.doi")
            pid_value = require_string(doi_pid, "identifier", "record.pids.doi")
            if not re.fullmatch(r"10\.5281/zenodo\.\d+", pid_value):
                raise PublicationError("record.pids.doi.identifier is malformed")
            values.append(("record.pids.doi.identifier", pid_value))
    if not values:
        raise PublicationError("Zenodo public record has no DOI identity")
    if len({value for _source, value in values}) != 1:
        raise PublicationError("Zenodo public record DOI identities disagree")
    return values[0][1]


def verify_public_zenodo(
    plan: dict[str, Any],
    binding: dict[str, str],
    state: dict[str, Any],
    final: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    record_id = state.get("zenodo_record_id")
    if not isinstance(record_id, int):
        raise PublicationError("transaction state lacks an integer Zenodo record ID")
    record = poll_zenodo_public(record_id)
    doi = require_string(state, "zenodo_doi", "state")
    if public_record_doi(record) != doi or str(record.get("id")) != str(record_id):
        raise PublicationError("Zenodo public DOI/record identity differs")
    assert_zenodo_metadata(
        record.get("metadata"), plan, doi, binding["fingerprint"], public=True
    )
    expected_artifacts = artifact_map(final, manifest)
    files = public_record_files(record)
    if set(files) != set(expected_artifacts):
        raise PublicationError("Zenodo public file closure differs")
    readbacks: list[dict[str, Any]] = []
    for name, expected in expected_artifacts.items():
        item = files[name]
        size_value = item.get("size")
        checksum = str(item.get("checksum") or "").removeprefix("md5:")
        checksum = checksum.lower()
        require_sha(checksum, "Zenodo public file checksum", algorithm="md5")
        local = final / "release-assets" / name
        if size_value != expected["bytes"] or checksum != md5_file(local):
            raise PublicationError(f"Zenodo public size/MD5 differs: {name}")
        links = expect_dict(item.get("links"), "record file links")
        download = links.get("content") or links.get("self")
        if not isinstance(download, str) or not download:
            raise PublicationError(f"Zenodo public download link is absent: {name}")
        validate_origin(download, {origin(ZENODO_ORIGIN)})
        size, digest, _url = stream_sha256(
            download,
            allowed_origins={origin(ZENODO_ORIGIN)},
            expected_bytes=expected["bytes"],
            retryable=True,
        )
        if digest != expected["sha256"]:
            raise PublicationError(f"Zenodo public SHA-256 differs: {name}")
        readbacks.append({"name": name, "bytes": size, "sha256": digest})
    doi_url = f"https://doi.org/{doi}"
    _size, _digest, resolved = stream_sha256(doi_url, retryable=True, timeout=120)
    parsed = urllib.parse.urlsplit(resolved)
    if (
        origin(resolved) != origin(ZENODO_ORIGIN)
        or parsed.path.rstrip("/") != f"/records/{record_id}"
        or parsed.query
        or parsed.fragment
    ):
        raise PublicationError("DOI does not resolve to the intended Zenodo record")
    return {
        "record_id": record_id,
        "record_url": f"https://zenodo.org/records/{record_id}",
        "doi": doi,
        "doi_resolved_url": resolved,
        "metadata_sha256": sha256_bytes(
            canonical_bytes(
                normalize_zenodo_metadata(record["metadata"], public=True)
            )
        ),
        "assets": readbacks,
    }


def pin_final_release_state(
    plan: dict[str, Any],
    binding: dict[str, str],
    state: dict[str, Any],
    final: Path,
    manifest: dict[str, Any],
) -> str:
    verify_inventory(final, binding)
    doi = require_string(state, "zenodo_doi", "state")
    validate_final_manifest(plan, manifest, doi)
    pin_inventory(state, "final_inventory_sha256", manifest, final)
    pin_state_sha256(state, "artifact_set_sha256", manifest["artifact_set_sha256"])
    save_state(state)
    return doi


def zenodo_anonymous_readback(
    plan: dict[str, Any],
    binding: dict[str, str],
    state: dict[str, Any],
    final: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Verify only Zenodo and leave combined/GitHub completion pending."""

    pin_final_release_state(plan, binding, state, final, manifest)
    zenodo: dict[str, Any] | None = None
    zenodo_error: PublicationError | None = None
    for attempt in range(10):
        try:
            zenodo = verify_public_zenodo(plan, binding, state, final, manifest)
            break
        except PublicationError as exc:
            zenodo_error = exc
            if attempt + 1 < 10:
                time.sleep(backoff_seconds(min(attempt, 4)))
    if zenodo is None:
        raise PublicationError(
            f"anonymous Zenodo state did not become consistent: {zenodo_error}"
        )
    verify_inventory(final, binding)
    result = {
        "schema_version": "hefferon-id-public-readback-zenodo-v1",
        "publication_target": "zenodo",
        "transaction_fingerprint": binding["fingerprint"],
        "release_tag": plan["release"]["tag"],
        "final_inventory_sha256": manifest["inventory_sha256"],
        "artifact_set_sha256": manifest["artifact_set_sha256"],
        "github": {"status": "pending"},
        "zenodo": zenodo,
        "all_zenodo_release_bytes_verified": True,
        "complete_metadata_and_doi_verified": True,
        "combined_release_complete": False,
    }
    save_json(ZENODO_READBACK_PATH, result)
    state["zenodo_anonymous_readback_sha256"] = sha256_file(ZENODO_READBACK_PATH)
    save_state(state)
    return result


def github_anonymous_readback(
    plan: dict[str, Any],
    binding: dict[str, str],
    state: dict[str, Any],
    final: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Verify only GitHub and leave combined completion untouched."""

    pin_final_release_state(plan, binding, state, final, manifest)
    github: dict[str, Any] | None = None
    github_error: PublicationError | None = None
    for attempt in range(10):
        try:
            github = verify_public_github(plan, state, final, manifest)
            break
        except PublicationError as exc:
            github_error = exc
            if attempt + 1 < 10:
                time.sleep(backoff_seconds(min(attempt, 4)))
    if github is None:
        raise PublicationError(
            f"anonymous GitHub state did not become consistent: {github_error}"
        )
    verify_inventory(final, binding)
    result = {
        "schema_version": "hefferon-id-public-readback-github-v1",
        "publication_target": "github",
        "transaction_fingerprint": binding["fingerprint"],
        "release_tag": plan["release"]["tag"],
        "final_inventory_sha256": manifest["inventory_sha256"],
        "artifact_set_sha256": manifest["artifact_set_sha256"],
        "github": github,
        "zenodo": {
            "status": "published" if state.get("zenodo_published") is True else "pending"
        },
        "all_github_release_bytes_verified": True,
        "repository_snapshot_verified": True,
        "combined_release_complete": False,
    }
    save_json(GITHUB_READBACK_PATH, result)
    state["github_anonymous_readback_sha256"] = sha256_file(GITHUB_READBACK_PATH)
    save_state(state)
    return result


def anonymous_readback(
    plan: dict[str, Any], binding: dict[str, str], state: dict[str, Any], final: Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    github_receipt = github_anonymous_readback(plan, binding, state, final, manifest)
    zenodo_receipt = zenodo_anonymous_readback(plan, binding, state, final, manifest)
    result = {
        "schema_version": "hefferon-id-public-readback-v3",
        "publication_target": "all",
        "transaction_fingerprint": binding["fingerprint"],
        "release_tag": plan["release"]["tag"],
        "final_inventory_sha256": manifest["inventory_sha256"],
        "artifact_set_sha256": manifest["artifact_set_sha256"],
        "github": github_receipt["github"],
        "zenodo": zenodo_receipt["zenodo"],
        "all_release_bytes_verified": True,
        "repository_snapshot_verified": True,
        "complete_metadata_and_doi_verified": True,
        "combined_release_complete": True,
    }
    save_json(READBACK_PATH, result)
    state["anonymous_readback_sha256"] = sha256_file(READBACK_PATH)
    state["complete"] = True
    save_state(state)
    return result


def local_preflight(plan: dict[str, Any]) -> dict[str, Any]:
    try:
        readiness = strict_readiness(plan, PROJECT)
        return {"ready": True, "issues": [], **readiness}
    except PublicationError as exc:
        return {"ready": False, "issues": [str(exc)]}


def package_only(
    plan: dict[str, Any], binding: dict[str, str], doi: str
) -> dict[str, Any]:
    state = load_state(binding)
    base, _readiness = prepare_base_stage(plan, binding, state)
    final, manifest = prepare_final_stage(plan, binding, state, base, doi)
    verify_inventory(final, binding)
    return {
        "status": "packaged",
        "transaction_fingerprint": binding["fingerprint"],
        "final_inventory_sha256": manifest["inventory_sha256"],
        "artifact_set_sha256": manifest["artifact_set_sha256"],
        "artifacts": manifest["artifacts"],
    }


def frozen_final_release(
    plan: dict[str, Any], binding: dict[str, str], state: dict[str, Any]
) -> tuple[Path, dict[str, Any]]:
    """Load the one DOI-bound final stage without rebuilding or restaging it."""

    doi = require_string(state, "zenodo_doi", "state")
    final = TRANSACTIONS / binding["fingerprint"] / "final"
    manifest = verify_inventory(final, binding)
    validate_final_manifest(plan, manifest, doi)
    pin_inventory(state, "final_inventory_sha256", manifest, final)
    pin_state_sha256(state, "artifact_set_sha256", manifest["artifact_set_sha256"])
    save_state(state)
    return final, manifest


def require_verified_zenodo_receipt_for_github(
    plan: dict[str, Any],
    binding: dict[str, str],
    state: dict[str, Any],
    final: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Prove the DOI and frozen bytes were publicly read back before mirroring.

    This gate is deliberately local-only: the isolated GitHub route must not
    construct a Zenodo client or make a Zenodo request.  The authenticated
    Zenodo publication action and anonymous byte readback already persist a
    receipt whose exact bytes are pinned in the transaction state.
    """

    if state.get("zenodo_published") is not True:
        raise PublicationError(
            "GitHub-only publication requires a completed Zenodo publication"
        )
    receipt_sha = require_sha(
        state.get("zenodo_anonymous_readback_sha256"),
        "state.zenodo_anonymous_readback_sha256",
    )
    if not ZENODO_READBACK_PATH.is_file() or ZENODO_READBACK_PATH.is_symlink():
        raise PublicationError("verified Zenodo anonymous-readback receipt is missing")
    if sha256_file_stable(ZENODO_READBACK_PATH) != receipt_sha:
        raise PublicationError("verified Zenodo anonymous-readback receipt hash differs")
    receipt = load_json(ZENODO_READBACK_PATH)
    expected_identity = {
        "schema_version": "hefferon-id-public-readback-zenodo-v1",
        "publication_target": "zenodo",
        "transaction_fingerprint": binding["fingerprint"],
        "release_tag": plan["release"]["tag"],
        "final_inventory_sha256": manifest["inventory_sha256"],
        "artifact_set_sha256": manifest["artifact_set_sha256"],
        "all_zenodo_release_bytes_verified": True,
        "complete_metadata_and_doi_verified": True,
        "combined_release_complete": False,
    }
    for key, expected in expected_identity.items():
        if receipt.get(key) != expected:
            raise PublicationError(f"verified Zenodo receipt identity differs: {key}")
    zenodo = expect_dict(receipt.get("zenodo"), "verified Zenodo receipt.zenodo")
    state_doi = require_string(state, "zenodo_doi", "state")
    state_record_id = require_integer(state, "zenodo_record_id", "state")
    if zenodo.get("doi") != state_doi or zenodo.get("record_id") != state_record_id:
        raise PublicationError("verified Zenodo receipt record identity differs")
    expected_artifacts = artifact_map(final, manifest)
    received: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(
        expect_list(zenodo.get("assets"), "verified Zenodo receipt assets")
    ):
        row = expect_dict(value, f"verified Zenodo receipt assets[{index}]")
        name = validate_basename(
            require_string(row, "name", "verified Zenodo receipt asset"),
            "verified Zenodo receipt asset",
        )
        if name in received:
            raise PublicationError("verified Zenodo receipt has duplicate assets")
        received[name] = row
    if set(received) != set(expected_artifacts):
        raise PublicationError("verified Zenodo receipt asset closure differs")
    for name, expected in expected_artifacts.items():
        row = received[name]
        if (
            row.get("bytes") != expected["bytes"]
            or row.get("sha256") != expected["sha256"]
        ):
            raise PublicationError(f"verified Zenodo receipt asset differs: {name}")
    return receipt


def publish_zenodo_only(
    plan: dict[str, Any], binding: dict[str, str]
) -> dict[str, Any]:
    """Publish and publicly verify Zenodo without constructing a GitHub client."""

    state = load_state(binding)
    base, _readiness = prepare_base_stage(plan, binding, state)
    zenodo = zenodo_client(plan)
    deposition, doi = reserve_zenodo(zenodo, plan, binding, state)
    final, manifest = prepare_final_stage(plan, binding, state, base, doi)
    verify_inventory(final, binding)
    public_record = publish_zenodo(
        zenodo, plan, binding, state, deposition, final, manifest
    )
    readback = zenodo_anonymous_readback(plan, binding, state, final, manifest)
    return {
        "status": "zenodo-published-github-pending",
        "publication_target": "zenodo",
        "transaction_fingerprint": binding["fingerprint"],
        "github": {"status": "pending"},
        "zenodo": {
            "record_id": state["zenodo_record_id"],
            "doi": state["zenodo_doi"],
            "public_id": public_record.get("id"),
        },
        "final_inventory_sha256": manifest["inventory_sha256"],
        "artifact_set_sha256": manifest["artifact_set_sha256"],
        "combined_release_complete": False,
        "readback": readback,
    }


def publish_github_only(
    plan: dict[str, Any], binding: dict[str, str]
) -> dict[str, Any]:
    """Mirror the frozen Zenodo-bound bytes to GitHub without any Zenodo call."""

    state = load_state(binding)
    final, manifest = frozen_final_release(plan, binding, state)
    require_verified_zenodo_receipt_for_github(
        plan, binding, state, final, manifest
    )
    github, authentication = github_client(plan)
    ensure_github_repository(github, plan, state)
    repository = publish_repository_snapshot(github, plan, state, final, binding)
    release = ensure_github_release(
        github, plan, state, final, manifest, binding
    )
    pages = ensure_pages(github, plan)
    readback = github_anonymous_readback(plan, binding, state, final, manifest)
    return {
        "status": "github-published-combined-verification-pending",
        "publication_target": "github",
        "transaction_fingerprint": binding["fingerprint"],
        "github_authenticated_login": authentication["login"],
        "repository": repository,
        "release": {
            "id": release["id"],
            "url": release["html_url"],
            "draft": release["draft"],
        },
        "pages": pages,
        "zenodo": {
            "status": "published" if state.get("zenodo_published") is True else "pending",
            "doi": state["zenodo_doi"],
        },
        "final_inventory_sha256": manifest["inventory_sha256"],
        "artifact_set_sha256": manifest["artifact_set_sha256"],
        "combined_release_complete": False,
        "readback": readback,
    }


def publish(plan: dict[str, Any], binding: dict[str, str]) -> dict[str, Any]:
    state = load_state(binding)
    base, _readiness = prepare_base_stage(plan, binding, state)
    zenodo = zenodo_client(plan)
    deposition, doi = reserve_zenodo(zenodo, plan, binding, state)
    final, manifest = prepare_final_stage(plan, binding, state, base, doi)
    verify_inventory(final, binding)
    github, authentication = github_client(plan)
    ensure_github_repository(github, plan, state)
    repository = publish_repository_snapshot(
        github, plan, state, final, binding
    )
    release = ensure_github_release(
        github, plan, state, final, manifest, binding
    )
    pages = ensure_pages(github, plan)
    public_record = publish_zenodo(
        zenodo, plan, binding, state, deposition, final, manifest
    )
    readback = anonymous_readback(plan, binding, state, final, manifest)
    return {
        "status": "complete",
        "transaction_fingerprint": binding["fingerprint"],
        "github_authenticated_login": authentication["login"],
        "repository": repository,
        "release": {
            "id": release["id"],
            "url": release["html_url"],
            "draft": release["draft"],
        },
        "pages": pages,
        "zenodo": {
            "record_id": state["zenodo_record_id"],
            "doi": state["zenodo_doi"],
            "public_id": public_record.get("id"),
        },
        "final_inventory_sha256": manifest["inventory_sha256"],
        "artifact_set_sha256": manifest["artifact_set_sha256"],
        "readback": readback,
    }


def verify_existing(plan: dict[str, Any], binding: dict[str, str]) -> dict[str, Any]:
    state = load_state(binding)
    final = TRANSACTIONS / binding["fingerprint"] / "final"
    manifest = verify_inventory(final, binding)
    doi = require_string(state, "zenodo_doi", "state")
    validate_final_manifest(plan, manifest, doi)
    pin_inventory(state, "final_inventory_sha256", manifest, final)
    pin_state_sha256(state, "artifact_set_sha256", manifest["artifact_set_sha256"])
    save_state(state)
    return anonymous_readback(plan, binding, state, final, manifest)


def verify_zenodo_existing(
    plan: dict[str, Any], binding: dict[str, str]
) -> dict[str, Any]:
    state = load_state(binding)
    final, manifest = frozen_final_release(plan, binding, state)
    return zenodo_anonymous_readback(plan, binding, state, final, manifest)


def verify_github_existing(
    plan: dict[str, Any], binding: dict[str, str]
) -> dict[str, Any]:
    state = load_state(binding)
    final, manifest = frozen_final_release(plan, binding, state)
    return github_anonymous_readback(plan, binding, state, final, manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "preflight",
            "package",
            "publish",
            "verify",
            "zenodo-preflight",
            "zenodo-publish",
            "zenodo-verify",
            "github-preflight",
            "github-publish",
            "github-verify",
        ),
    )
    parser.add_argument("--doi", help="reserved DOI for a local package-only run")
    args = parser.parse_args()
    plan = load_plan()
    binding = transaction_binding(plan)
    if (
        sha256_file_stable(PLAN_PATH) != binding["plan_sha256"]
        or sha256_file_stable(Path(__file__).resolve()) != binding["driver_sha256"]
        or load_json(PLAN_PATH) != plan
    ):
        raise PublicationError("publication plan or driver changed while binding the transaction")
    if args.command in {"preflight", "zenodo-preflight", "github-preflight"}:
        if args.command == "preflight":
            remote = remote_preflight(plan, binding)
            target = "all"
        elif args.command == "zenodo-preflight":
            remote = {"zenodo": zenodo_remote_preflight(plan, binding)}
            target = "zenodo"
        else:
            remote = {"github": github_remote_preflight(plan)}
            target = "github"
        result = {
            "schema_version": "hefferon-id-publication-preflight-v2",
            "publication_target": target,
            "transaction_fingerprint": binding["fingerprint"],
            "local": local_preflight(plan),
            "remote": remote,
            "mutations": 0,
        }
    else:
        with TransactionLock():
            if args.command == "package":
                if not args.doi or not re.fullmatch(r"10\.5281/zenodo\.\d+", args.doi):
                    raise PublicationError("package requires a valid already-reserved --doi")
                result = package_only(plan, binding, args.doi)
            elif args.command == "publish":
                result = publish(plan, binding)
            elif args.command == "verify":
                result = verify_existing(plan, binding)
            elif args.command == "zenodo-publish":
                result = publish_zenodo_only(plan, binding)
            elif args.command == "zenodo-verify":
                result = verify_zenodo_existing(plan, binding)
            elif args.command == "github-publish":
                result = publish_github_only(plan, binding)
            else:
                result = verify_github_existing(plan, binding)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublicationError as exc:
        print(f"PUBLICATION FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
