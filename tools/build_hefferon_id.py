#!/usr/bin/env python3
"""Build the three Hefferon id-ID PDFs in a disposable staging tree.

The canonical translated source is never compiled in place.  Each run replaces
only ``build/hefferon_id`` and ``tmp/pdfs/hefferon_id``, copies the source into
staging, recovers the 64 lab figures and seven book figures from frozen official
artifacts/source coordinates, rebuilds the MetaPost assets, executes the lab's
PythonTeX and SageTeX programs in pinned WSL Sage, and compiles the textbook,
answer book, and lab.  Asymptote is deliberately never invoked.
Command transcripts, all-page renders, and machine-readable QA reports are
retained beside the provisional PDFs.
"""

from __future__ import annotations

import argparse
import csv
from fnmatch import fnmatchcase
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

from pypdf import PdfReader
from pypdf.generic import DictionaryObject, IndirectObject
from PIL import Image, ImageDraw, __version__ as PILLOW_VERSION


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "source" / "linear-algebra"
AUTHORITY_LAB_PDF = PROJECT_ROOT / "authority" / "official" / "lab.pdf"
AUTHORITY_BOOK_PDF = PROJECT_ROOT / "authority" / "official" / "book.pdf"
EXTRACTOR = PROJECT_ROOT / "tools" / "extract_lab_graphics_from_authority_pdf.py"
BOOK_GRAPHICS_RECOVERER = PROJECT_ROOT / "tools" / "recover_book_asy_graphics.py"
LAB_SAGETEX_RUNNER = PROJECT_ROOT / "tools" / "run_lab_sagetex_wsl.py"
PYTHONTEX_STARTUP = PROJECT_ROOT / "tools" / "pythontex_startup" / "sitecustomize.py"
PDFTEX_FONT_CLOSURE = PROJECT_ROOT / "tools" / "pdftex-font-closure"
BUILD_ROOT = PROJECT_ROOT / "build" / "hefferon_id"
STAGING_ROOT = BUILD_ROOT / "staging" / "linear-algebra"
STAGING_SRC = STAGING_ROOT / "src"
LOG_ROOT = BUILD_ROOT / "logs"
OUTPUT_ROOT = BUILD_ROOT / "output" / "pdf"
RENDER_ROOT = PROJECT_ROOT / "tmp" / "pdfs" / "hefferon_id"
REPORT_PATH = BUILD_ROOT / "build_report.json"
SOURCE_MANIFEST_PATH = BUILD_ROOT / "staged_source_manifest.json"
LAB_GRAPHICS_MANIFEST = BUILD_ROOT / "lab_graphics_manifest.csv"
BOOK_GRAPHICS_MANIFEST = BUILD_ROOT / "book_graphics_manifest.csv"
MISSING_LAB_ASSET_MANIFEST = BUILD_ROOT / "missing_lab_asset_manifest.json"
LINK_AUDIT_PATH = BUILD_ROOT / "cross_pdf_link_audit.json"
RENDER_MANIFEST_PATH = BUILD_ROOT / "all_page_render_manifest.json"
LAB_SAGETEX_RUNTIME_MANIFEST = BUILD_ROOT / "lab_sagetex_runtime_manifest.json"
METAPOST_ASSET_MANIFEST = BUILD_ROOT / "metapost_asset_manifest.json"
PDFTEX_INPUT_AUDIT_PATH = BUILD_ROOT / "pdftex_input_audit.json"

FIXED_SOURCE_DATE_EPOCH = "1633046400"  # 2021-10-01T00:00:00Z
METAPOST_RANDOM_SEED = 1

# The textbook and answer book deliberately load these maps in
# sty/bookjhconcrete.sty.  Pin both the maps and the exact encoding/font bytes
# that they use in the final PDFs so a mutable system pdftex.map cannot silently
# change the reader artifacts between clean builds.
PDFTEX_FONT_DEPENDENCIES = (
    ("hefferon-standard.map", 1402, "943c2cf5f3b69e428c313c3e62326c4f80ef1c0652407bc011a55b68334d6c87"),
    ("cm-super-t1.map", 32335, "226289f0eeddb7426a1ba1987af893df82174b433743a1c02d87d83240d59e56"),
    ("cm-super-ts1.map", 27973, "e7906fae5ee5d56fe8343f245a8c440670420b98dcb4dec055046221d35c82d1"),
    ("bera.map", 1044, "f7a09a12f0bae99c5d81aaa714ab6a809d186aa9a49b193e2f98cee8d7f3fff5"),
    ("ugq.map", 184, "0c0c975c2d03492cbf577575547b166a91d3929c95c8666abf967cfb00f3eb6a"),
    ("pbsi.map", 210, "54813ca4f26ca6e04f396209d975e25336454c1a68c9f673adecbb500f7928cf"),
    ("cm-super-t1.enc", 2971, "0b8a4865363ad2acb3718af53a43a8b1a16a143900bba8e672813d4a6e07b4fc"),
    ("cm-super-ts1.enc", 2900, "558da5de87db45ed719dda9c679e6b164d520b21d9100357dcf17124291ed97c"),
    ("8r.enc", 4993, "4b74cff10f36f444270ed8f0c576b4e7b605538aa2f6b99a77bc9129f07e4a17"),
    ("sfssdc10.pfb", 149381, "60b674ac5edbd2f49db48b46e95804fd91aa4dce987f9454a3069160cdef12da"),
    ("sfoti10.pfb", 170923, "c39fe0a8559c893bc4bbfa247abd75d22e69bcfd39153f97a0b6e91de510504b"),
    ("sfocc10.pfb", 102054, "5a9e668ccf717579f0895859b73e242fcb7bd420cff245c188cadee0274c26b2"),
    ("sfosl10.pfb", 130712, "ac4336eb7a7dfb6d188dabe004b08331b9ee8674a37732a26454584e82db5e1a"),
    ("sform5.pfb", 130755, "d317f5d0ed8d0b12c21764976fe2291bd30344f9eba85dbe6258cff95bae9f70"),
    ("sform6.pfb", 132848, "4874948fe50731f4411c3729ab3a394be93222e3012e753cf3061fb939e35ab6"),
    ("sform7.pfb", 128188, "5dec921f263037b2be59b3c1e15b3f69f0198200484b3fc31e7f0bf27c70900a"),
    ("sform8.pfb", 129377, "d454b14229cd7c49ac3e77c5762700856cb254c56f2f695a144338500b4ce2ea"),
    ("sform9.pfb", 126436, "be25d646b1b4bf5dc4f7defea590211566d6c1de68c2d56ecdaaf07358bee625"),
    ("sform10.pfb", 127772, "f6e2c981d84638f36548431f4a3ae2e65577b585dcc1e08e1ef2d9cd79609dcc"),
    ("fvmr8a.pfb", 29228, "6c3f939eb29b72b597464010001935af5eddb05c3031a25c1f66633d68e5cd8c"),
    ("fvsb8a.pfb", 29275, "755d71a280ba7d1b77a7cc0f826cf2da2468e4733cbbcc494d7f96c7ae47cb4d"),
    ("fvsr8a.pfb", 29095, "aab1418ee7723378b02505a5e63b2fb8e39cfe58e92eeb3038acc97770940181"),
    ("ugqb8a.pfb", 29942, "e5ff54b29562b758aaeb20c3a1a70b931f418f0278a9cf367b9cc49cac334c4b"),
    ("BrushScriptX-Italic.pfa", 76320, "bf0f78dfa79365fa21af7efa46c742907b2e7dd70c53f26c8d4e74c5b55516f0"),
    ("cmex10.pfb", 30251, "791b31aa1db8608d0144b3a40fc0fe53383a60f6b00d0e8fd9f06ac4a11df8cb"),
    ("cmmi10.pfb", 36299, "e3661061e8aa474d6de5ffa916edceb0e3d8b998862018c147f0357fce00bcd7"),
    ("cmmi5.pfb", 37912, "35048e58e53f4aa53025069c1d0de33a16d8d4c111bfa329669e6456ec0a967b"),
    ("cmmi7.pfb", 36281, "5b293a581ddb937b02559c3ce1a60184cc434295533204a2cd3864a6ad8a1f53"),
    ("cmr10.pfb", 35752, "fdcede8794018df5f2b58f0905fb20a2b418ed8f67b73ee12445855dfbe5b1be"),
    ("cmsy10.pfb", 32569, "62ee8cef552017551cd3e026a483e700730103eceaad959c87b7730017f59cff"),
    ("cmsy5.pfb", 32915, "46da57e5a06866efa9a20f3dd350811b5d3279a5ae789af63e530f1f570e3c7f"),
    ("cmsy7.pfb", 32716, "583b65bd1857bffc2ab184fcb4aad4e70e12eb05c9ca9f1c58c9a00a86c8bccf"),
    ("euex10.pfb", 12536, "a93b3c5d1e64c2305c1648de7c7b4903c55b5a59a816e37222e8ec8c418cc605"),
    ("eufm10.pfb", 21098, "0d4adc0d8d6b3fd993fe138b6863126d7122cd1ae180d0a19eca0759bf7d0975"),
    ("eufm5.pfb", 21550, "5e9e9e208ecdc198f68f87785ef84fccf3ab93291c7ead0a9ea1b1d6107983ee"),
    ("eufm7.pfb", 21251, "8c5202802ed024ad905ab81b34a882c9473acf9e9ab7a717bcee3f0f57e985f2"),
    ("eurb10.pfb", 22394, "2aa1cd6768ce9159f7704593b58e4e24c846cea7d789242266aee31d1e74b900"),
    ("eurm10.pfb", 22644, "988a860101f4b64cc0ca6e9b7b065db1b316e78da5d1838c89524bf098e4aec6"),
    ("eurm5.pfb", 23170, "5cb5143825f985edc442eb71038f001ef5076c33702fba67484cfa5da118a7ef"),
    ("eurm7.pfb", 22927, "df9a5603b3d8777ca91530bb8cb771b0ca84f5b464a29fb4ab65d9b98149c9f3"),
    ("eusm10.pfb", 10538, "eb4a18f8f72bef82051509701331e459cd547c573b74430401cb699812a66a59"),
    ("eusm7.pfb", 10655, "71d135350b292822e5b5d96cf3dd07c9da3fa3e88a0b298b42110e9f98b9c536"),
    ("lcircle1.pfb", 10594, "503d59829700006b46d6ddf4f90b045ee7f08350f89544b302e7d73711c4b68f"),
    ("line10.pfb", 11493, "8bed0f3db560ddcd98fb1a1e9d58aed3ab2aef553c4364a32841b51ee5dc84a7"),
    ("linew10.pfb", 11895, "415d63b2859d9dc7ba7e4c83a5e73463d059cfdb03bd3a8f509c211cdb166315"),
    ("msam10.pfb", 31764, "f2e3b470b988a46272125e917531690d3c4d03ac7238f112b07337f972a537fa"),
    ("msam7.pfb", 33366, "c96c9138119d9879757ad8c1ecb2cc25b0cac303ba3ee13d25d117fdbc71d2f3"),
    ("msbm10.pfb", 34694, "d2121de7e7c14490a2d352e3b62e62882d6c300235464bfa577e6055696e6e62"),
    ("msbm7.pfb", 35309, "bd86d36def0f2d226cf773a195a88f88e424759f3ddaaf654de2ae670906734e"),
    ("rsfs10.pfb", 16077, "60ba5026b2feb5cac34615abbcaaa4e9746b43c1f9ad9c0a81b97fa60ac69a26"),
    ("uhvr8a.pfb", 44648, "bb553b044d70f86c879229d4f9b6ae191176d21775f6746921165c877f4748d9"),
)

PDFTEX_FONT_BUCKETS = {
    ".map": "maps",
    ".enc": "encodings",
    ".pfb": "type1",
    ".pfa": "type1",
}

METAPOST_ASSETS = (
    ("gr/mp/ch1.mp", "gr/mp/ch1.1"),
    ("vs/mp/ch2.mp", "vs/mp/ch2.1"),
    ("vs/mp/voting.mp", "vs/mp/voting.1"),
    ("map/mp/ch3.mp", "map/mp/ch3.1"),
    ("det/mp/ch4.mp", "det/mp/ch4.1"),
    ("jc/mp/ch5.mp", "jc/mp/ch5.1"),
    ("appen/mp/appen.mp", "appen/mp/appen.1"),
)

EXPECTED_METAPOST_OUTPUT_COUNTS = {
    "gr/mp/ch1.mp": 54,
    "vs/mp/ch2.mp": 17,
    "vs/mp/voting.mp": 45,
    "map/mp/ch3.mp": 98,
    "det/mp/ch4.mp": 68,
    "jc/mp/ch5.mp": 11,
    "appen/mp/appen.mp": 14,
}

RECOVERED_BOOK_GRAPHICS = (
    "det/asy/ppiped.pdf",
    "jc/asy/wilber.pdf",
    "jc/asy/wilber001.pdf",
    "jc/asy/wilber003.pdf",
    "jc/asy/wilber002.pdf",
    "jc/asy/innerproduct000.pdf",
    "jc/asy/innerproduct001.pdf",
)

# Upstream intentionally ships these two PDFs and comments out their generator
# rules because the PBR/opacity path is not reliable across Ghostscript builds.
PINNED_UPSTREAM_ASSETS = (
    "cover/asy/axesgraphic.pdf",
    "cover/asy/shadow.pdf",
)

PDF_JOBS = (
    ("book", STAGING_SRC, "pdflatex"),
    ("jhanswer", STAGING_SRC, "pdflatex"),
    ("lab", STAGING_SRC / "lab", "xelatex"),
)

GENERATED_ENGLISH_LABEL_PATTERNS = (
    (
        "document_heading",
        re.compile(
            r"^\s*(?:table of contents|contents|index|bibliography|references|"
            r"answers?|exercises?)\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "numbered_division",
        re.compile(
            r"^\s*(?:chapter|section|appendix)\s+"
            r"(?:\d+|[IVXLCDM]+|[A-Z][A-Za-z-]*)\s*[:.]?\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "numbered_statement",
        re.compile(
            r"^\s*(?:definition|theorem|lemma|corollary|example|exercise|"
            r"remark|figure|table)\s+(?:[A-Za-z]+\.)?[IVXLCDM\d]+"
            r"(?:[.:-][IVXLCDM\d]+)*\s*[:.]?\s*$",
            re.IGNORECASE,
        ),
    ),
    ("proof_heading", re.compile(r"^\s*proof\s*[.:]?\s*$", re.IGNORECASE)),
    ("page_label", re.compile(r"^\s*page\s+\d+\s*$", re.IGNORECASE)),
)

EXPECTED_NATIVE_TOPIC_ANSWERS = 131
EXPECTED_INDONESIAN_EDITION_SUPPLIED_TOPIC_ANSWERS = 2
EXPECTED_TOPIC_ANSWERS = (
    EXPECTED_NATIVE_TOPIC_ANSWERS
    + EXPECTED_INDONESIAN_EDITION_SUPPLIED_TOPIC_ANSWERS
)

MISSING_LAB_ASSET = "lab/pix/greatwave_squeezed.png"
MISSING_LAB_ASSET_BYTES = 2_165_271
MISSING_LAB_ASSET_SHA256 = "975bc4112cd3eeaa0e15de8aa87a5174bc36af7d53f132f26b3a291d82de2789"
GREATWAVE_WIDTH = 1497
GREATWAVE_HEIGHT = 922
GREATWAVE_RGB_SHA256 = "2c3adafcfd6efdeb24210112d6e9e158624d5625631f1f70306df1c5844d7982"
GREATWAVE_ALPHA_SHA256 = "7bf064041934d866b296922248a1cb8adefc44705ecc74cb4002d6a40d2decf2"
GREATWAVE_SQUEEZED_RGB_SHA256 = "a06f4f20ce6a1d9b187304492d75525486c11760aed22b384d3018963fc5eb87"


class BuildFailure(RuntimeError):
    """A required reproducible build step failed."""


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_owned_path(path: Path, anchor: Path) -> None:
    path_resolved = path.resolve()
    anchor_resolved = anchor.resolve()
    if path_resolved == anchor_resolved or not path_resolved.is_relative_to(anchor_resolved):
        raise BuildFailure(f"unsafe task-output path: {path_resolved}")


def replace_directory(path: Path, anchor: Path) -> None:
    ensure_owned_path(path, anchor)
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=False)


def canonical_tree_manifest(root: Path) -> tuple[list[dict[str, object]], str]:
    rows: list[dict[str, object]] = []
    for path in sorted((item for item in root.rglob("*") if item.is_file())):
        relative = path.relative_to(root).as_posix()
        rows.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": sha256_path(path),
            }
        )
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return rows, hashlib.sha256(payload.encode("utf-8")).hexdigest()


def manifest_differences(
    staged_rows: list[dict[str, object]], live_rows: list[dict[str, object]]
) -> dict[str, list[str]]:
    staged = {str(row["path"]): row for row in staged_rows}
    live = {str(row["path"]): row for row in live_rows}
    common = staged.keys() & live.keys()
    return {
        "added": sorted(live.keys() - staged.keys()),
        "removed": sorted(staged.keys() - live.keys()),
        "changed": sorted(
            path
            for path in common
            if staged[path]["bytes"] != live[path]["bytes"]
            or staged[path]["sha256"] != live[path]["sha256"]
        ),
    }


def command_environment() -> dict[str, str]:
    env = os.environ.copy()
    src_recursive = f"{STAGING_SRC.as_posix()}//"
    texmf = BUILD_ROOT / "texmf"
    inherited_values = {
        # Current working directory must precede the recursive source tree.
        # In particular, lab/cover.tex must win over cover/cover.tex.
        "TEXINPUTS": (".", src_recursive, (texmf / "tex").as_posix() + "//"),
        "MPINPUTS": ((STAGING_SRC / "mp").as_posix() + "//", src_recursive),
        "TFMFONTS": ((texmf / "fonts" / "tfm").as_posix() + "//",),
        "VFFONTS": ((texmf / "fonts" / "vf").as_posix() + "//",),
        "TTFONTS": ((texmf / "fonts" / "truetype").as_posix() + "//",),
    }
    for name, prefixes in inherited_values.items():
        existing = env.get(name, "")
        env[name] = os.pathsep.join((*prefixes, existing))
    # These three searches are deliberately private-only.  A trailing empty
    # element would reactivate Kpathsea's mutable system defaults.
    env["T1FONTS"] = (texmf / "fonts" / "type1").as_posix() + "//"
    env["ENCFONTS"] = (texmf / "fonts" / "enc").as_posix() + "//"
    env["TEXFONTMAPS"] = (texmf / "fonts" / "map").as_posix() + "//"
    env.update(
        {
            "SOURCE_DATE_EPOCH": FIXED_SOURCE_DATE_EPOCH,
            "FORCE_SOURCE_DATE": "1",
            "TZ": "UTC",
            "MIKTEX_ENABLE_INSTALLER": "0",
        }
    )
    return env


def run_command(
    name: str,
    arguments: list[str],
    cwd: Path,
    env: dict[str, str],
    records: list[dict[str, object]],
    *,
    required: bool = True,
    timeout: int = 1800,
) -> subprocess.CompletedProcess[str]:
    log_path = LOG_ROOT / f"{name}.log"
    executable = shutil.which(arguments[0])
    if executable is None:
        result_record = {
            "name": name,
            "cwd": str(cwd),
            "command": arguments,
            "returncode": None,
            "log": str(log_path),
            "error": f"executable not found: {arguments[0]}",
        }
        records.append(result_record)
        log_path.write_text(result_record["error"] + "\n", encoding="utf-8")
        if required:
            raise BuildFailure(result_record["error"])
        return subprocess.CompletedProcess(arguments, 127, "", result_record["error"])

    command = [executable, *arguments[1:]]
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        output = completed.stdout
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + f"\nTIMEOUT after {timeout} seconds\n"
        log_path.write_text(output, encoding="utf-8")
        records.append(
            {
                "name": name,
                "cwd": str(cwd),
                "command": command,
                "returncode": None,
                "log": str(log_path),
                "error": f"timeout after {timeout} seconds",
            }
        )
        raise BuildFailure(f"{name} timed out") from exc

    log_path.write_text(output, encoding="utf-8")
    records.append(
        {
            "name": name,
            "cwd": str(cwd),
            "command": command,
            "returncode": completed.returncode,
            "log": str(log_path),
        }
    )
    if required and completed.returncode != 0:
        raise BuildFailure(f"{name} failed with exit code {completed.returncode}; see {log_path}")
    return completed


def pdftex_font_dependency_source(name: str) -> Path:
    """Return one dependency's repository-owned source path, fail-closed."""
    try:
        bucket = PDFTEX_FONT_BUCKETS[Path(name).suffix.lower()]
    except KeyError as exc:
        raise BuildFailure(f"unsupported pinned font dependency type: {name}") from exc
    path = (PDFTEX_FONT_CLOSURE / bucket / name).resolve()
    if not path.is_relative_to(PDFTEX_FONT_CLOSURE.resolve()):
        raise BuildFailure(f"unsafe repository font dependency path: {name}")
    return path


def inspect_pdftex_font_closure() -> dict[str, object]:
    """Validate the repository-owned closure and its self-check manifest."""
    readme = PDFTEX_FONT_CLOSURE / "README.md"
    notices = PDFTEX_FONT_CLOSURE / "THIRD_PARTY_NOTICES.json"
    checksums = PDFTEX_FONT_CLOSURE / "SHA256SUMS"
    for required in (readme, notices, checksums):
        if not required.is_file():
            raise BuildFailure(f"required font-closure metadata is missing: {required}")
    try:
        notices_data = json.loads(notices.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildFailure(f"invalid font-closure notices JSON: {notices}") from exc

    rows, tree_sha256 = canonical_tree_manifest(PDFTEX_FONT_CLOSURE)
    row_by_path = {str(row["path"]): row for row in rows}
    declared: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        checksums.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise BuildFailure(
                f"invalid SHA256SUMS line {line_number} in font closure"
            )
        relative = parts[1].lstrip("* ").replace("\\", "/")
        if relative in declared:
            raise BuildFailure(f"duplicate font-closure checksum path: {relative}")
        declared[relative] = parts[0]

    expected_manifest_paths = set(row_by_path) - {"SHA256SUMS"}
    if set(declared) != expected_manifest_paths:
        missing = sorted(expected_manifest_paths - set(declared))
        extra = sorted(set(declared) - expected_manifest_paths)
        raise BuildFailure(
            "font-closure SHA256SUMS inventory mismatch: "
            f"missing={missing}; extra={extra}"
        )
    for relative, expected_sha256 in declared.items():
        actual_sha256 = str(row_by_path[relative]["sha256"])
        if actual_sha256 != expected_sha256:
            raise BuildFailure(
                f"font-closure checksum mismatch for {relative}: "
                f"expected {expected_sha256}, found {actual_sha256}"
            )

    if (
        not isinstance(notices_data, dict)
        or notices_data.get("schema_version") != "2.0.0"
        or notices_data.get("runtime_dependency_count")
        != len(PDFTEX_FONT_DEPENDENCIES)
        or notices_data.get("integrity_manifest") != "SHA256SUMS"
    ):
        raise BuildFailure("font-closure rights inventory identity differs")
    payload_rows = [
        row
        for row in rows
        if row["path"] not in {"README.md", "THIRD_PARTY_NOTICES.json", "SHA256SUMS"}
    ]
    if (
        notices_data.get("payload_file_count") != len(payload_rows)
        or notices_data.get("payload_total_bytes")
        != sum(int(row["bytes"]) for row in payload_rows)
    ):
        raise BuildFailure("font-closure rights inventory payload totals differ")
    components = notices_data.get("components")
    if not isinstance(components, list) or not components:
        raise BuildFailure("font-closure component-rights inventory is empty")
    runtime_patterns: list[str] = []
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            raise BuildFailure(f"font-closure component {index} is not an object")
        paths = component.get("runtime_paths")
        if (
            not isinstance(component.get("name"), str)
            or not component["name"]
            or not isinstance(component.get("license_route"), str)
            or not component["license_route"]
            or not isinstance(paths, list)
            or not paths
        ):
            raise BuildFailure(f"font-closure component {index} is incomplete")
        for pattern in paths:
            if not isinstance(pattern, str) or not pattern:
                raise BuildFailure(f"font-closure component {index} has an invalid path")
            runtime_patterns.append(pattern)
        for reference_key in ("notice_references", "source_references"):
            references = component.get(reference_key, [])
            if not isinstance(references, list):
                raise BuildFailure(
                    f"font-closure component {index}.{reference_key} is not a list"
                )
            for reference in references:
                if not isinstance(reference, str) or reference not in row_by_path:
                    raise BuildFailure(
                        f"font-closure component {index} has missing reference: {reference}"
                    )
    runtime_paths = {
        f"{PDFTEX_FONT_BUCKETS[Path(name).suffix.lower()]}/{name}"
        for name, _bytes, _sha256 in PDFTEX_FONT_DEPENDENCIES
    }
    for runtime_path in runtime_paths:
        if not any(fnmatchcase(runtime_path, pattern) for pattern in runtime_patterns):
            raise BuildFailure(
                f"font-closure runtime dependency lacks a license route: {runtime_path}"
            )
    for pattern in runtime_patterns:
        if not any(fnmatchcase(runtime_path, pattern) for runtime_path in runtime_paths):
            raise BuildFailure(
                f"font-closure rights inventory pattern matches no runtime file: {pattern}"
            )
    authority_archives = notices_data.get("authority_archives")
    if not isinstance(authority_archives, list) or len(authority_archives) != 3:
        raise BuildFailure("font-closure CTAN authority archive closure differs")
    for index, authority in enumerate(authority_archives):
        if not isinstance(authority, dict):
            raise BuildFailure(f"font-closure authority archive {index} is invalid")
        relative = authority.get("path")
        if not isinstance(relative, str) or relative not in row_by_path:
            raise BuildFailure(f"font-closure authority archive {index} path differs")
        row = row_by_path[relative]
        if (
            authority.get("bytes") != row["bytes"]
            or authority.get("sha256") != row["sha256"]
            or not isinstance(authority.get("url"), str)
            or not str(authority["url"]).startswith("https://")
        ):
            raise BuildFailure(f"font-closure authority archive {index} binding differs")

    return {
        "path": str(PDFTEX_FONT_CLOSURE.resolve()),
        "file_count": len(rows),
        "bytes": sum(int(row["bytes"]) for row in rows),
        "tree_sha256": tree_sha256,
        "sha256sums_bytes": checksums.stat().st_size,
        "sha256sums_sha256": sha256_path(checksums),
        "third_party_notices_bytes": notices.stat().st_size,
        "third_party_notices_sha256": sha256_path(notices),
        "readme_bytes": readme.stat().st_size,
        "readme_sha256": sha256_path(readme),
    }


def verify_pdftex_font_closure_unchanged(
    initial: dict[str, object],
) -> dict[str, object]:
    """Fail if any repository closure byte changes while a build is running."""
    current = inspect_pdftex_font_closure()
    stable_keys = (
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
    unchanged = all(current[key] == initial[key] for key in stable_keys)
    if not unchanged:
        raise BuildFailure("repository pdfTeX font closure changed during build")
    return {
        "file_count": current["file_count"],
        "bytes": current["bytes"],
        "tree_sha256": current["tree_sha256"],
        "all_verified": True,
    }


def resolve_pdftex_font_dependencies() -> dict[str, dict[str, object]]:
    """Fail-close and stage the repository-owned pdfTeX font-map closure."""
    resolved: dict[str, dict[str, object]] = {}
    destination_roots = {
        ".map": BUILD_ROOT / "texmf" / "fonts" / "map" / "hefferon-id",
        ".enc": BUILD_ROOT / "texmf" / "fonts" / "enc" / "hefferon-id",
        ".pfb": BUILD_ROOT / "texmf" / "fonts" / "type1" / "hefferon-id",
        ".pfa": BUILD_ROOT / "texmf" / "fonts" / "type1" / "hefferon-id",
    }
    for name, expected_bytes, expected_sha256 in PDFTEX_FONT_DEPENDENCIES:
        path = pdftex_font_dependency_source(name)
        if not path.is_file():
            raise BuildFailure(
                f"repository font dependency is not a file: {name} -> {path}"
            )
        actual_bytes = path.stat().st_size
        actual_sha256 = sha256_path(path)
        if actual_bytes != expected_bytes or actual_sha256 != expected_sha256:
            raise BuildFailure(
                f"pinned font dependency mismatch for {name}: "
                f"expected {expected_bytes}/{expected_sha256}, "
                f"found {actual_bytes}/{actual_sha256}"
            )
        destination_root = destination_roots[path.suffix.lower()]
        destination_root.mkdir(parents=True, exist_ok=True)
        destination = destination_root / name
        if path != destination.resolve():
            shutil.copyfile(path, destination)
        if (
            destination.stat().st_size != expected_bytes
            or sha256_path(destination) != expected_sha256
        ):
            raise BuildFailure(f"task-local font dependency copy mismatch: {name}")
        resolved[name] = {
            "source_path": str(path),
            "source_project_path": path.relative_to(PROJECT_ROOT).as_posix(),
            "staged_path": str(destination),
            "bytes": actual_bytes,
            "sha256": actual_sha256,
        }
    return resolved


def verify_staged_pdftex_font_dependencies(
    resolved: dict[str, dict[str, object]],
) -> dict[str, object]:
    """Prove that the private font closure stayed byte-identical through build end."""
    expected_names = {name for name, _bytes, _sha256 in PDFTEX_FONT_DEPENDENCIES}
    if set(resolved) != expected_names:
        raise BuildFailure("task-local pdfTeX font dependency name closure changed")
    total_bytes = 0
    for name, expected_bytes, expected_sha256 in PDFTEX_FONT_DEPENDENCIES:
        path = Path(str(resolved[name]["staged_path"]))
        if (
            not path.is_file()
            or path.stat().st_size != expected_bytes
            or sha256_path(path) != expected_sha256
        ):
            raise BuildFailure(f"task-local pdfTeX font dependency changed during build: {name}")
        total_bytes += expected_bytes
    return {
        "dependency_count": len(expected_names),
        "bytes": total_bytes,
        "all_verified": True,
    }


def unpack_lab_font_tree() -> None:
    archive = STAGING_SRC / "lab" / "fonts" / "ProggyCleanSageTree.zip"
    destination = BUILD_ROOT / "texmf"
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            target = (destination / item.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise BuildFailure(f"unsafe lab font ZIP member: {item.filename}")
        bundle.extractall(destination)


def verify_lab_graphics_manifest() -> dict[str, object]:
    with LAB_GRAPHICS_MANIFEST.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 64:
        raise BuildFailure(
            f"authority lab extraction produced {len(rows)} figures instead of 64"
        )
    total_bytes = 0
    for row in rows:
        relative = Path(row["path"])
        output = (STAGING_SRC / "lab" / relative).resolve()
        if not output.is_relative_to((STAGING_SRC / "lab").resolve()):
            raise BuildFailure(f"unsafe lab-graphics manifest path: {row['path']}")
        if not output.is_file():
            raise BuildFailure(f"missing recovered lab figure: {output}")
        expected_bytes = int(row["bytes"])
        if output.stat().st_size != expected_bytes:
            raise BuildFailure(f"byte mismatch for recovered lab figure: {output}")
        if sha256_path(output) != row["sha256"]:
            raise BuildFailure(f"SHA-256 mismatch for recovered lab figure: {output}")
        verify_one_page_pdf_structure(output)
        total_bytes += expected_bytes
    return {
        "count": len(rows),
        "bytes": total_bytes,
        "manifest_path": str(LAB_GRAPHICS_MANIFEST),
        "manifest_sha256": sha256_path(LAB_GRAPHICS_MANIFEST),
        "includes_ellipsoid1": any(row["path"] == "asy/ellipsoid1.pdf" for row in rows),
    }


def verify_one_page_pdf_structure(path: Path) -> None:
    """Require a literal valid page tree, not a permissive-reader fallback."""
    reader = PdfReader(path, strict=True)
    catalog = reader.trailer["/Root"].get_object()
    pages_reference = catalog.get("/Pages")
    if not isinstance(pages_reference, IndirectObject):
        raise BuildFailure(f"catalog /Pages is not indirect: {path}")
    pages = pages_reference.get_object()
    kids = pages.get("/Kids") or []
    if str(pages.get("/Type")) != "/Pages" or int(pages.get("/Count", -1)) != 1:
        raise BuildFailure(f"invalid one-page /Pages node: {path}")
    if len(kids) != 1 or not isinstance(kids[0], IndirectObject):
        raise BuildFailure(f"invalid one-page /Kids closure: {path}")
    page = kids[0].get_object()
    if not isinstance(page, DictionaryObject) or str(page.get("/Type")) != "/Page":
        raise BuildFailure(f"/Kids entry is not a page dictionary: {path}")
    parent = page.get("/Parent")
    if (
        not isinstance(parent, IndirectObject)
        or parent.idnum != pages_reference.idnum
        or parent.generation != pages_reference.generation
    ):
        raise BuildFailure(f"page /Parent does not match /Pages: {path}")
    if "/MediaBox" not in page or "/Contents" not in page or "/Resources" not in page:
        raise BuildFailure(f"page lacks wrapper keys: {path}")
    if len(reader.pages) != 1:
        raise BuildFailure(f"recovered figure is not one page: {path}")


def verify_book_graphics_manifest() -> dict[str, object]:
    with BOOK_GRAPHICS_MANIFEST.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    expected = set(RECOVERED_BOOK_GRAPHICS)
    actual = {row["path"] for row in rows}
    if len(rows) != len(RECOVERED_BOOK_GRAPHICS) or actual != expected:
        raise BuildFailure(
            "book-graphics recovery produced an unexpected target closure; "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    total_bytes = 0
    for row in rows:
        relative = Path(row["path"])
        output = (STAGING_SRC / relative).resolve()
        if not output.is_relative_to(STAGING_SRC.resolve()):
            raise BuildFailure(f"unsafe book-graphics manifest path: {row['path']}")
        if not output.is_file():
            raise BuildFailure(f"missing recovered book figure: {output}")
        expected_bytes = int(row["bytes"])
        if output.stat().st_size != expected_bytes:
            raise BuildFailure(f"byte mismatch for recovered book figure: {output}")
        if sha256_path(output) != row["sha256"]:
            raise BuildFailure(f"SHA-256 mismatch for recovered book figure: {output}")
        verify_one_page_pdf_structure(output)
        total_bytes += expected_bytes
    return {
        "count": len(rows),
        "bytes": total_bytes,
        "manifest_path": str(BOOK_GRAPHICS_MANIFEST),
        "manifest_sha256": sha256_path(BOOK_GRAPHICS_MANIFEST),
        "methods": sorted({row["method"] for row in rows}),
    }


def recover_missing_lab_asset(
    env: dict[str, str], records: list[dict[str, object]]
) -> dict[str, object]:
    """Recover the one unshipped Sage-generated PNG from the official lab PDF."""

    source_image = SOURCE_ROOT / "src" / "lab" / "pix" / "greatwave.png"
    source_generator = SOURCE_ROOT / "src" / "lab" / "img_squeeze.sage"
    with Image.open(source_image) as image:
        source_rgba = image.convert("RGBA")
        if source_rgba.size != (GREATWAVE_WIDTH, GREATWAVE_HEIGHT):
            raise BuildFailure(f"unexpected source greatwave dimensions: {source_rgba.size}")
        source_rgb_sha256 = hashlib.sha256(
            source_rgba.convert("RGB").tobytes()
        ).hexdigest()
        source_alpha_sha256 = hashlib.sha256(
            source_rgba.getchannel("A").tobytes()
        ).hexdigest()
    if source_rgb_sha256 != GREATWAVE_RGB_SHA256:
        raise BuildFailure("source greatwave RGB pixels differ from the frozen authority")
    if source_alpha_sha256 != GREATWAVE_ALPHA_SHA256:
        raise BuildFailure("source greatwave alpha pixels differ from the frozen authority")

    reader = PdfReader(AUTHORITY_LAB_PDF)
    object_specs = (
        (71, "/Im22", GREATWAVE_RGB_SHA256, "/DeviceRGB", 3),
        (72, "/Im23", GREATWAVE_SQUEEZED_RGB_SHA256, "/DeviceRGB", 3),
    )
    object_evidence: list[dict[str, object]] = []
    for page_number, object_name, expected_decoded_sha256, colorspace, channels in object_specs:
        xobjects = (reader.pages[page_number - 1].get("/Resources") or {}).get(
            "/XObject"
        ) or {}
        if set(map(str, xobjects.keys())) != {object_name}:
            raise BuildFailure(
                f"authority lab page {page_number} image closure drifted: "
                f"{sorted(map(str, xobjects.keys()))}"
            )
        reference = xobjects[object_name]
        image_object = reference.get_object()
        decoded = image_object.get_data()
        if str(image_object.get("/Subtype")) != "/Image":
            raise BuildFailure(f"{object_name} on page {page_number} is no longer an image")
        if (
            int(image_object.get("/Width")) != GREATWAVE_WIDTH
            or int(image_object.get("/Height")) != GREATWAVE_HEIGHT
            or str(image_object.get("/ColorSpace")) != colorspace
            or int(image_object.get("/BitsPerComponent")) != 8
            or len(decoded) != GREATWAVE_WIDTH * GREATWAVE_HEIGHT * channels
            or hashlib.sha256(decoded).hexdigest() != expected_decoded_sha256
        ):
            raise BuildFailure(
                f"authority lab page {page_number} {object_name} pixel binding drifted"
            )
        object_evidence.append(
            {
                "authority_page": page_number,
                "xobject": object_name,
                "object_reference": (
                    f"{reference.idnum} {reference.generation} R"
                    if isinstance(reference, IndirectObject)
                    else None
                ),
                "decoded_bytes": len(decoded),
                "decoded_sha256": expected_decoded_sha256,
            }
        )

    original_object = (
        reader.pages[70]["/Resources"]["/XObject"]["/Im22"].get_object()
    )
    smask = original_object.get("/SMask")
    if not isinstance(smask, IndirectObject):
        raise BuildFailure("authority original greatwave no longer has its frozen alpha mask")
    smask_object = smask.get_object()
    smask_decoded = smask_object.get_data()
    if (
        int(smask_object.get("/Width")) != GREATWAVE_WIDTH
        or int(smask_object.get("/Height")) != GREATWAVE_HEIGHT
        or str(smask_object.get("/ColorSpace")) != "/DeviceGray"
        or int(smask_object.get("/BitsPerComponent")) != 8
        or hashlib.sha256(smask_decoded).hexdigest() != GREATWAVE_ALPHA_SHA256
    ):
        raise BuildFailure("authority original greatwave alpha-mask binding drifted")

    extraction_root = BUILD_ROOT / "recovered_lab_images"
    extraction_root.mkdir(parents=True, exist_ok=False)
    prefix = extraction_root / "greatwave"
    run_command(
        "recover_missing_lab_png",
        [
            "pdfimages",
            "-f",
            "71",
            "-l",
            "72",
            "-png",
            str(AUTHORITY_LAB_PDF),
            str(prefix),
        ],
        PROJECT_ROOT,
        env,
        records,
    )
    expected_outputs = [
        extraction_root / "greatwave-000.png",
        extraction_root / "greatwave-001.png",
        extraction_root / "greatwave-002.png",
    ]
    actual_outputs = sorted(extraction_root.glob("*"))
    if actual_outputs != expected_outputs:
        raise BuildFailure(
            "pdfimages output closure drifted: "
            f"{[path.name for path in actual_outputs]}"
        )
    original_png, alpha_png, squeezed_png = expected_outputs
    with Image.open(original_png) as image:
        original_extracted_rgb_sha256 = hashlib.sha256(
            image.convert("RGB").tobytes()
        ).hexdigest()
    with Image.open(alpha_png) as image:
        alpha_extracted_sha256 = hashlib.sha256(image.convert("L").tobytes()).hexdigest()
    with Image.open(squeezed_png) as image:
        squeezed_mode = image.mode
        squeezed_size = image.size
        squeezed_rgb_sha256 = hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()
    if original_extracted_rgb_sha256 != source_rgb_sha256:
        raise BuildFailure("pdfimages object order drifted: first image is not greatwave RGB")
    if alpha_extracted_sha256 != source_alpha_sha256:
        raise BuildFailure("pdfimages object order drifted: second image is not greatwave alpha")
    if (
        squeezed_mode != "RGB"
        or squeezed_size != (GREATWAVE_WIDTH, GREATWAVE_HEIGHT)
        or squeezed_rgb_sha256 != GREATWAVE_SQUEEZED_RGB_SHA256
        or squeezed_png.stat().st_size != MISSING_LAB_ASSET_BYTES
        or sha256_path(squeezed_png) != MISSING_LAB_ASSET_SHA256
    ):
        raise BuildFailure("recovered squeezed-wave PNG differs from the frozen extraction")

    staged_output = STAGING_SRC / MISSING_LAB_ASSET
    staged_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(squeezed_png, staged_output)
    if (
        staged_output.stat().st_size != MISSING_LAB_ASSET_BYTES
        or sha256_path(staged_output) != MISSING_LAB_ASSET_SHA256
    ):
        raise BuildFailure("staged squeezed-wave PNG failed byte-for-byte readback")

    manifest = {
        "schema_version": "hefferon-id-missing-lab-asset-recovery-v1",
        "target": MISSING_LAB_ASSET,
        "method": "pdfimages_png_from_frozen_official_pdf_image_xobject",
        "authority_lab_pdf": {
            "path": str(AUTHORITY_LAB_PDF),
            "sha256": sha256_path(AUTHORITY_LAB_PDF),
        },
        "object_evidence": object_evidence,
        "original_source_image": {
            "path": str(source_image),
            "bytes": source_image.stat().st_size,
            "sha256": sha256_path(source_image),
            "width": GREATWAVE_WIDTH,
            "height": GREATWAVE_HEIGHT,
            "rgb_pixel_sha256": source_rgb_sha256,
            "alpha_pixel_sha256": source_alpha_sha256,
            "authority_rgb_and_alpha_pixel_identity": True,
        },
        "published_generator": {
            "path": str(source_generator),
            "bytes": source_generator.stat().st_size,
            "sha256": sha256_path(source_generator),
            "invocation": (
                'img_squeeze("pix/greatwave.png", '
                '"pix/greatwave_squeezed.png", 0.10)'
            ),
            "execution": "not_rerun; exact published result recovered from authority PDF",
        },
        "output": {
            "path": str(staged_output),
            "bytes": staged_output.stat().st_size,
            "sha256": sha256_path(staged_output),
            "width": squeezed_size[0],
            "height": squeezed_size[1],
            "mode": squeezed_mode,
            "rgb_pixel_sha256": squeezed_rgb_sha256,
        },
    }
    payload = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    MISSING_LAB_ASSET_MANIFEST.write_bytes(payload)
    return {
        "target": MISSING_LAB_ASSET,
        "bytes": MISSING_LAB_ASSET_BYTES,
        "sha256": MISSING_LAB_ASSET_SHA256,
        "manifest_path": str(MISSING_LAB_ASSET_MANIFEST),
        "manifest_bytes": len(payload),
        "manifest_sha256": hashlib.sha256(payload).hexdigest(),
        "authority_page": 72,
        "xobject": "/Im23",
        "source_generator_sha256": sha256_path(source_generator),
    }


def verify_expected_files(paths: tuple[str, ...] | list[str], step_name: str) -> None:
    missing = [relative for relative in paths if not (STAGING_SRC / relative).is_file()]
    if missing:
        raise BuildFailure(f"{step_name} did not produce: {missing}")


def _metapost_output_paths(source: Path) -> list[Path]:
    pattern = re.compile(rf"^{re.escape(source.stem)}\.(?P<number>[0-9]+)$")
    return sorted(
        (
            path
            for path in source.parent.iterdir()
            if path.is_file() and pattern.fullmatch(path.name)
        ),
        key=lambda path: int(pattern.fullmatch(path.name).group("number")),
    )


def inspect_metapost_assets() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for source_relative, _output_relative in METAPOST_ASSETS:
        source = STAGING_SRC / source_relative
        outputs = _metapost_output_paths(source)
        expected_count = EXPECTED_METAPOST_OUTPUT_COUNTS[source_relative]
        if len(outputs) != expected_count:
            raise BuildFailure(
                f"{source_relative} produced {len(outputs)} numeric assets, "
                f"expected {expected_count}"
            )
        for path in outputs:
            rows.append(
                {
                    "source": source_relative,
                    "figure": int(path.suffix[1:]),
                    "path": path.relative_to(STAGING_SRC).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_path(path),
                }
            )
    canonical = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    manifest = {
        "schema_version": "hefferon-id-metapost-assets-v1",
        "random_seed": METAPOST_RANDOM_SEED,
        "source_date_epoch": FIXED_SOURCE_DATE_EPOCH,
        "asset_count": len(rows),
        "bytes": sum(int(row["bytes"]) for row in rows),
        "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
        "files": rows,
    }
    return manifest


def verify_metapost_assets_unchanged(initial: dict[str, object]) -> dict[str, object]:
    current = inspect_metapost_assets()
    stable_keys = (
        "schema_version",
        "random_seed",
        "source_date_epoch",
        "asset_count",
        "bytes",
        "canonical_sha256",
        "files",
    )
    if any(current[key] != initial[key] for key in stable_keys):
        raise BuildFailure("generated MetaPost asset closure changed during reader build")
    return {
        "asset_count": current["asset_count"],
        "bytes": current["bytes"],
        "canonical_sha256": current["canonical_sha256"],
        "all_verified": True,
    }


def build_assets(
    env: dict[str, str], records: list[dict[str, object]]
) -> dict[str, object]:
    verify_expected_files(list(PINNED_UPSTREAM_ASSETS), "pinned upstream cover assets")
    verify_expected_files([MISSING_LAB_ASSET], "recovered missing lab asset")
    for source_relative, output_relative in METAPOST_ASSETS:
        source = STAGING_SRC / source_relative
        for stale_output in _metapost_output_paths(source):
            stale_output.unlink()
        wrapper = source.parent / f"__hefferon_seeded_{source.stem}.mp"
        wrapper.write_text(
            f"randomseed := {METAPOST_RANDOM_SEED};\ninput {source.name};\n",
            encoding="ascii",
            newline="\n",
        )
        run_command(
            "mpost_" + source_relative.removesuffix(".mp").replace("/", "_"),
            [
                "mpost",
                "-interaction=nonstopmode",
                "-tex=latex",
                f"-jobname={source.stem}",
                wrapper.name,
            ],
            source.parent,
            env,
            records,
        )
        verify_expected_files([output_relative], source_relative)
    verify_expected_files(
        list(RECOVERED_BOOK_GRAPHICS), "deterministically recovered book graphics"
    )
    manifest = inspect_metapost_assets()
    METAPOST_ASSET_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        **manifest,
        "manifest_path": str(METAPOST_ASSET_MANIFEST),
        "manifest_bytes": METAPOST_ASSET_MANIFEST.stat().st_size,
        "manifest_sha256": sha256_path(METAPOST_ASSET_MANIFEST),
    }


def tex_command(engine: str, job: str) -> list[str]:
    command = [
        engine,
        "-disable-installer",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        "-recorder",
    ]
    if engine == "xelatex":
        proggy_map = (
            BUILD_ROOT
            / "texmf"
            / "fonts"
            / "map"
            / "dvips"
            / "ProggyCleanSage"
            / "ProggyCleanSage.map"
        )
        command.append(f"-output-driver=xdvipdfmx -f {proggy_map.as_posix()}")
    command.append(f"{job}.tex")
    return command


def inspect_tex_convergence_state(job: str) -> dict[str, object]:
    exact_names = {
        f"{job}.pdf",
        f"{job}.aux",
        f"{job}.toc",
        f"{job}.out",
        f"{job}.idx",
        f"{job}.ind",
        f"{job}.ilg",
    }
    if job == "book":
        exact_names.add("bookans.tex")
    paths = {
        path
        for path in STAGING_SRC.rglob("*.aux")
        if path.is_file()
    }
    paths.update(
        path
        for name in exact_names
        if (path := STAGING_SRC / name).is_file()
    )
    required = {STAGING_SRC / f"{job}.pdf", STAGING_SRC / f"{job}.aux"}
    if not required.issubset(paths):
        missing = sorted(path.name for path in required - paths)
        raise BuildFailure(f"{job} convergence state is missing required files: {missing}")
    rows = [
        {
            "path": path.relative_to(STAGING_SRC).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_path(path),
        }
        for path in sorted(paths)
    ]
    payload = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "schema_version": "hefferon-id-tex-convergence-state-v1",
        "job": job,
        "file_count": len(rows),
        "bytes": sum(int(row["bytes"]) for row in rows),
        "canonical_sha256": hashlib.sha256(payload).hexdigest(),
        "files": rows,
    }


def require_tex_convergence(
    job: str,
    pass_number: int,
    env: dict[str, str],
    records: list[dict[str, object]],
) -> dict[str, object]:
    before = inspect_tex_convergence_state(job)
    run_command(
        f"{job}_pdflatex_{pass_number}_convergence",
        tex_command("pdflatex", job),
        STAGING_SRC,
        env,
        records,
    )
    after = inspect_tex_convergence_state(job)
    matched = before == after
    if not matched:
        raise BuildFailure(
            f"{job} changed on its dedicated convergence pass {pass_number}"
        )
    return {
        "schema_version": "hefferon-id-tex-convergence-v1",
        "job": job,
        "comparison_pass": pass_number,
        "matched": True,
        "state": after,
    }


def inspect_book_index_state() -> dict[str, object]:
    """Fingerprint the exact index input/output pair at a TeX fixed point."""
    rows: list[dict[str, object]] = []
    for name in ("book.idx", "book.ind"):
        path = STAGING_SRC / name
        if not path.is_file():
            raise BuildFailure(f"book index fixed-point state is missing {name}")
        rows.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": sha256_path(path),
            }
        )
    payload = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "schema_version": "hefferon-id-book-index-state-v1",
        "file_count": len(rows),
        "bytes": sum(int(row["bytes"]) for row in rows),
        "canonical_sha256": hashlib.sha256(payload).hexdigest(),
        "files": rows,
    }


def build_book(
    env: dict[str, str], records: list[dict[str, object]]
) -> dict[str, object]:
    cwd = STAGING_SRC
    run_command("book_pdflatex_1", tex_command("pdflatex", "book"), cwd, env, records)
    run_command(
        "book_makeindex",
        ["makeindex", "-s", "sty/book.isty", "book.idx"],
        cwd,
        env,
        records,
    )
    for pass_number in range(2, 6):
        run_command(
            f"book_pdflatex_{pass_number}",
            tex_command("pdflatex", "book"),
            cwd,
            env,
            records,
        )
    # Refresh the index from the stabilized pass-5 .idx, then prove that the
    # pass which consumes that .ind does not change the index input/output
    # pair. This prevents a stale .ind from satisfying a TeX-only fixed point.
    run_command(
        "book_makeindex_refresh_after_pass_5",
        ["makeindex", "-s", "sty/book.isty", "book.idx"],
        cwd,
        env,
        records,
    )
    refreshed_index = inspect_book_index_state()
    run_command(
        "book_pdflatex_6",
        tex_command("pdflatex", "book"),
        cwd,
        env,
        records,
    )
    run_command(
        "book_makeindex_verify_after_pass_6",
        ["makeindex", "-s", "sty/book.isty", "book.idx"],
        cwd,
        env,
        records,
    )
    verified_index = inspect_book_index_state()
    if refreshed_index != verified_index:
        raise BuildFailure(
            "book index input/output changed after pass 6; final .ind is not at a fixed point"
        )
    convergence = require_tex_convergence("book", 7, env, records)
    convergence["index_fixed_point"] = {
        "schema_version": "hefferon-id-book-index-fixed-point-v1",
        "refreshed_after_tex_pass": 5,
        "verified_after_tex_pass": 6,
        "matched": True,
        "state": verified_index,
    }
    return convergence


def inspect_generated_answer_stream() -> dict[str, object]:
    """Prove that all repaired topic answers reached the generated answer stream."""
    path = STAGING_SRC / "bookans.tex"
    if not path.is_file():
        raise BuildFailure(f"book build did not generate its answer stream: {path}")
    text = path.read_text(encoding="utf-8", errors="strict")
    token = re.compile(
        r"(?m)^\s*(?:\\protect\s*)?"
        r"\\(?P<division>chapter|section|subsection|topic)\*?\s*\{"
        r"|^\s*\\begin\s*\{ans\}\s*\{(?P<answer>[^{}]+)\}"
    )
    in_topic = False
    topic_number = 0
    topic_answers: list[dict[str, object]] = []
    all_answers = 0
    for match in token.finditer(text):
        division = match.group("division")
        if division is not None:
            in_topic = division == "topic"
            if in_topic:
                topic_number += 1
            continue
        all_answers += 1
        if in_topic:
            topic_answers.append(
                {
                    "topic_ordinal": topic_number,
                    "answer_argument": match.group("answer"),
                    "line": text.count("\n", 0, match.start()) + 1,
                }
            )
    if len(topic_answers) != EXPECTED_TOPIC_ANSWERS:
        raise BuildFailure(
            "generated answer stream contains "
            f"{len(topic_answers)} topic answers, expected {EXPECTED_TOPIC_ANSWERS}"
        )
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_path(path),
        "all_answers": all_answers,
        "topic_count": topic_number,
        "topic_answers": len(topic_answers),
        "expected_native_topic_answers": EXPECTED_NATIVE_TOPIC_ANSWERS,
        "expected_indonesian_edition_supplied_topic_answers": (
            EXPECTED_INDONESIAN_EDITION_SUPPLIED_TOPIC_ANSWERS
        ),
        "expected_topic_answers": EXPECTED_TOPIC_ANSWERS,
        "topic_answer_entries": topic_answers,
    }


def build_answer_book(
    env: dict[str, str], records: list[dict[str, object]]
) -> dict[str, object]:
    for pass_number in range(1, 4):
        run_command(
            f"jhanswer_pdflatex_{pass_number}",
            tex_command("pdflatex", "jhanswer"),
            STAGING_SRC,
            env,
            records,
        )
    return require_tex_convergence("jhanswer", 4, env, records)


def audit_pdftex_recorded_inputs() -> dict[str, object]:
    controlled_suffixes = {".map", ".enc", ".pfb", ".pfa"}
    metric_suffixes = {".tfm", ".vf"}
    private_root = (BUILD_ROOT / "texmf" / "fonts").resolve()
    allowed_names = {
        name for name, _expected_bytes, _expected_sha256 in PDFTEX_FONT_DEPENDENCIES
    }
    expected_maps = {
        name
        for name, _expected_bytes, _expected_sha256 in PDFTEX_FONT_DEPENDENCIES
        if Path(name).suffix.lower() == ".map"
    }
    controlled_rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    external: list[dict[str, str]] = []
    maps_by_job: dict[str, set[str]] = {}
    for job in ("book", "jhanswer"):
        recorder = STAGING_SRC / f"{job}.fls"
        if not recorder.is_file():
            raise BuildFailure(f"pdfTeX recorder output is missing: {recorder}")
        raw_inputs = [
            line.removeprefix("INPUT ").strip()
            for line in recorder.read_text(encoding="utf-8", errors="strict").splitlines()
            if line.startswith("INPUT ")
        ]
        seen: set[Path] = set()
        maps_by_job[job] = set()
        for raw in raw_inputs:
            path = Path(raw)
            if not path.is_absolute():
                path = STAGING_SRC / path
            path = path.resolve()
            suffix = path.suffix.lower()
            if suffix not in controlled_suffixes | metric_suffixes or path in seen:
                continue
            seen.add(path)
            if not path.is_file():
                raise BuildFailure(f"recorded pdfTeX input is missing: {job}: {path}")
            row = {
                "job": job,
                "name": path.name,
                "suffix": suffix,
                "bytes": path.stat().st_size,
                "sha256": sha256_path(path),
            }
            if suffix in controlled_suffixes:
                if not path.is_relative_to(private_root):
                    external.append({"job": job, "name": path.name, "suffix": suffix})
                    continue
                if path.name not in allowed_names:
                    raise BuildFailure(
                        f"unlisted private pdfTeX font dependency was used: {job}: {path.name}"
                    )
                row["closure_path"] = path.relative_to(
                    (BUILD_ROOT / "texmf").resolve()
                ).as_posix()
                controlled_rows.append(row)
                if suffix == ".map":
                    maps_by_job[job].add(path.name)
            else:
                metric_rows.append(row)
    if external:
        raise BuildFailure(
            "pdfTeX used map/encoding/font-program inputs outside the private closure: "
            f"{external[:5]}"
        )
    for job, actual_maps in maps_by_job.items():
        if actual_maps != expected_maps:
            raise BuildFailure(
                f"{job} map closure mismatch: expected {sorted(expected_maps)}, "
                f"found {sorted(actual_maps)}"
            )
    if not any(row["suffix"] in {".pfb", ".pfa"} for row in controlled_rows):
        raise BuildFailure("pdfTeX recorder did not expose any embedded Type 1 font input")
    controlled_rows.sort(
        key=lambda row: (str(row["job"]), str(row["closure_path"]))
    )
    metric_rows.sort(
        key=lambda row: (
            str(row["job"]),
            str(row["name"]),
            str(row["sha256"]),
        )
    )
    stable = {
        "schema_version": "hefferon-id-pdftex-input-audit-v1",
        "all_map_encoding_font_program_inputs_private": True,
        "jobs": ["book", "jhanswer"],
        "controlled_input_count": len(controlled_rows),
        "metric_input_count": len(metric_rows),
        "controlled_inputs": controlled_rows,
        "metric_inputs": metric_rows,
    }
    payload = json.dumps(
        stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    stable["canonical_sha256"] = hashlib.sha256(payload).hexdigest()
    PDFTEX_INPUT_AUDIT_PATH.write_text(
        json.dumps(stable, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        **stable,
        "path": str(PDFTEX_INPUT_AUDIT_PATH),
        "bytes": PDFTEX_INPUT_AUDIT_PATH.stat().st_size,
        "sha256": sha256_path(PDFTEX_INPUT_AUDIT_PATH),
    }


def inspect_pythontex_outputs(
    cwd: Path, completed: subprocess.CompletedProcess[str]
) -> dict[str, object]:
    success_line = "PythonTeX:  lab - 0 error(s), 0 warning(s)"
    if success_line not in completed.stdout:
        raise BuildFailure("PythonTeX did not report exactly zero errors and warnings")

    output_root = cwd / "pythontex-files-lab"
    paths = {
        "macros": output_root / "lab.pytxmcr",
        "pygments": output_root / "lab.pytxpyg",
        "state": output_root / "pythontex_data.pkl",
    }
    for name, path in paths.items():
        if not path.is_file() or path.stat().st_size == 0:
            raise BuildFailure(f"PythonTeX {name} output is missing or empty")

    timestamp_pattern = re.compile(
        r"^%Last time of file creation:\s+[0-9.]+\s*$", re.MULTILINE
    )
    timestamp_counts: dict[str, int] = {}
    for output_name in ("macros", "pygments"):
        path = paths[output_name]
        text = path.read_text(encoding="utf-8")
        timestamp_count = len(timestamp_pattern.findall(text))
        timestamp_counts[output_name] = timestamp_count
        if timestamp_count > 1:
            raise BuildFailure(
                f"PythonTeX {output_name} output has duplicate timestamp comments"
            )
        if timestamp_count == 1:
            normalized = timestamp_pattern.sub(
                f"%Last time of file creation:  {FIXED_SOURCE_DATE_EPOCH}.0",
                text,
            )
            path.write_text(normalized, encoding="utf-8", newline="\n")

    outputs = {
        name: {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_path(path),
        }
        for name, path in paths.items()
    }
    stable_fingerprint = {
        "schema_version": "hefferon-id-pythontex-stable-fingerprint-v1",
        "version": "PythonTeX 0.19",
        "random_seed": 20260821,
        "pythonhashseed": 0,
        "source_date_epoch": FIXED_SOURCE_DATE_EPOCH,
        "startup_sha256": sha256_path(PYTHONTEX_STARTUP),
        "macros_sha256": outputs["macros"]["sha256"],
        "pygments_sha256": outputs["pygments"]["sha256"],
    }
    return {
        "status": "pass",
        "success_line": success_line,
        "stdout_sha256": hashlib.sha256(completed.stdout.encode("utf-8")).hexdigest(),
        "outputs": outputs,
        "timestamp_comments_normalized": timestamp_counts,
        "stable_fingerprint": stable_fingerprint,
    }


def build_lab(
    env: dict[str, str], records: list[dict[str, object]]
) -> dict[str, object]:
    cwd = STAGING_SRC / "lab"
    run_command("lab_xelatex_1", tex_command("xelatex", "lab"), cwd, env, records)
    pythontex_env = env.copy()
    pythontex_env["PYTHONHASHSEED"] = "0"
    pythontex_path = str(PYTHONTEX_STARTUP.parent)
    existing_pythonpath = pythontex_env.get("PYTHONPATH", "")
    pythontex_env["PYTHONPATH"] = os.pathsep.join(
        item for item in (pythontex_path, existing_pythonpath) if item
    )
    pythontex_result = run_command(
        "lab_pythontex",
        ["pythontex", "--rerun", "always", "lab"],
        cwd,
        pythontex_env,
        records,
    )
    pythontex = inspect_pythontex_outputs(cwd, pythontex_result)
    run_command(
        "lab_sagetex",
        [
            sys.executable,
            str(LAB_SAGETEX_RUNNER),
            "--lab-root",
            str(cwd),
            "--authority-graphics-manifest",
            str(LAB_GRAPHICS_MANIFEST),
            "--output-manifest",
            str(LAB_SAGETEX_RUNTIME_MANIFEST),
        ],
        PROJECT_ROOT,
        env,
        records,
    )
    try:
        runtime = json.loads(LAB_SAGETEX_RUNTIME_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildFailure("invalid SageTeX runtime manifest") from exc
    if (
        runtime.get("schema_version") != "hefferon-id-sagetex-runtime-v1"
        or runtime.get("status") != "pass"
        or runtime.get("outputs", {}).get("command_label_count") != 148
        or runtime.get("figure_execution", {}).get("target_count") != 64
        or runtime.get("figure_execution", {}).get("changed_from_authority_count") != 63
        or runtime.get("figure_execution", {}).get("final_state")
        != "all_64_pinned_authority_figures_restored_and_rehashed"
        or not isinstance(runtime.get("stable_fingerprint"), dict)
    ):
        raise BuildFailure("SageTeX runtime manifest failed its exact closure gate")
    for output_name in ("sout", "scmd"):
        output_details = runtime["outputs"][output_name]
        output_path = Path(output_details["path"]).resolve()
        if (
            not output_path.is_relative_to(cwd.resolve())
            or not output_path.is_file()
            or output_path.stat().st_size != int(output_details["bytes"])
            or sha256_path(output_path) != output_details["sha256"]
        ):
            raise BuildFailure(f"SageTeX {output_name} output failed byte readback")
    runtime["manifest_artifact"] = {
        "path": str(LAB_SAGETEX_RUNTIME_MANIFEST),
        "bytes": LAB_SAGETEX_RUNTIME_MANIFEST.stat().st_size,
        "sha256": sha256_path(LAB_SAGETEX_RUNTIME_MANIFEST),
    }
    runtime["pythontex"] = pythontex
    runtime["stable_fingerprint"]["pythontex"] = pythontex["stable_fingerprint"]
    runtime["post_execution_authority_graphics"] = verify_lab_graphics_manifest()
    run_command("lab_bibtex", ["bibtex", "lab"], cwd, env, records)
    for pass_number in range(2, 6):
        run_command(
            f"lab_xelatex_{pass_number}",
            tex_command("xelatex", "lab"),
            cwd,
            env,
            records,
        )
    for output_name in ("sout", "scmd"):
        output_details = runtime["outputs"][output_name]
        output_path = Path(output_details["path"])
        if (
            output_path.stat().st_size != int(output_details["bytes"])
            or sha256_path(output_path) != output_details["sha256"]
        ):
            raise BuildFailure(f"final TeX pass altered SageTeX {output_name}")
    for output_name in ("macros", "pygments"):
        output_details = pythontex["outputs"][output_name]
        output_path = Path(output_details["path"])
        if (
            output_path.stat().st_size != int(output_details["bytes"])
            or sha256_path(output_path) != output_details["sha256"]
        ):
            raise BuildFailure(f"final TeX pass altered PythonTeX {output_name}")
    final_graphics = verify_lab_graphics_manifest()
    if final_graphics["manifest_sha256"] != runtime[
        "post_execution_authority_graphics"
    ]["manifest_sha256"]:
        raise BuildFailure("final TeX pass altered the restored authority figures")
    return runtime


def diagnostic_lines(log_text: str, pattern: str) -> list[str]:
    expression = re.compile(pattern, re.IGNORECASE)
    return [line.strip() for line in log_text.splitlines() if expression.search(line)]


def generated_english_label_hits(reader: PdfReader) -> list[dict[str, object]]:
    """Return conservative, line-anchored English generated-label matches."""
    hits: list[dict[str, object]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        for line_number, line in enumerate(text.splitlines(), start=1):
            compact = " ".join(line.split())
            if not compact:
                continue
            for label_kind, pattern in GENERATED_ENGLISH_LABEL_PATTERNS:
                if pattern.fullmatch(compact):
                    hits.append(
                        {
                            "page": page_number,
                            "extracted_line": line_number,
                            "kind": label_kind,
                            "text": compact,
                        }
                    )
                    break
    return hits


def png_page_metrics(path: Path) -> dict[str, object]:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        grayscale = image.convert("L")
        histogram = grayscale.histogram()
        pixels = grayscale.width * grayscale.height
        ink_pixels = sum(histogram[:250])
        mean_luminance = sum(value * count for value, count in enumerate(histogram)) / pixels
        return {
            "width": grayscale.width,
            "height": grayscale.height,
            "ink_fraction": round(ink_pixels / pixels, 8),
            "mean_luminance": round(mean_luminance, 4),
            "fully_white": ink_pixels == 0,
        }


def make_contact_sheets(job: str, rendered_pages: list[Path]) -> list[dict[str, object]]:
    contact_root = rendered_pages[0].parent / "contact_sheets"
    contact_root.mkdir(parents=True, exist_ok=False)
    columns, rows_per_sheet = 4, 5
    thumbnail_width, thumbnail_height = 153, 198
    label_height = 16
    rows: list[dict[str, object]] = []
    per_sheet = columns * rows_per_sheet
    for sheet_number, offset in enumerate(range(0, len(rendered_pages), per_sheet), start=1):
        batch = rendered_pages[offset : offset + per_sheet]
        sheet = Image.new(
            "RGB",
            (
                columns * thumbnail_width,
                rows_per_sheet * (thumbnail_height + label_height),
            ),
            "white",
        )
        draw = ImageDraw.Draw(sheet)
        for index, page_path in enumerate(batch):
            row, column = divmod(index, columns)
            x = column * thumbnail_width
            y = row * (thumbnail_height + label_height)
            with Image.open(page_path) as page_image:
                thumbnail = page_image.convert("RGB")
                thumbnail.thumbnail((thumbnail_width, thumbnail_height))
                page_x = x + (thumbnail_width - thumbnail.width) // 2
                page_y = y + (thumbnail_height - thumbnail.height) // 2
                sheet.paste(thumbnail, (page_x, page_y))
            draw.rectangle(
                (x, y, x + thumbnail_width - 1, y + thumbnail_height - 1),
                outline=(175, 175, 175),
            )
            page_number = offset + index + 1
            draw.text((x + 3, y + thumbnail_height + 1), f"{job} {page_number}", fill="black")
        output = contact_root / f"contact-{sheet_number:03d}.png"
        sheet.save(output, format="PNG", optimize=True)
        rows.append(
            {
                "path": str(output),
                "first_page": offset + 1,
                "last_page": offset + len(batch),
                "bytes": output.stat().st_size,
                "sha256": sha256_path(output),
            }
        )
    return rows


def inspect_pdf(
    job: str,
    cwd: Path,
    records: list[dict[str, object]],
    env: dict[str, str],
) -> dict[str, object]:
    staged_pdf = cwd / f"{job}.pdf"
    if not staged_pdf.is_file():
        raise BuildFailure(f"missing compiled PDF: {staged_pdf}")
    reader = PdfReader(staged_pdf)
    pages = len(reader.pages)
    if pages < 1:
        raise BuildFailure(f"compiled PDF has no pages: {staged_pdf}")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    output_pdf = OUTPUT_ROOT / staged_pdf.name
    shutil.copy2(staged_pdf, output_pdf)
    reopened = PdfReader(output_pdf)
    if len(reopened.pages) != pages:
        raise BuildFailure(f"page-count mismatch after copying {job}.pdf")

    tex_log = cwd / f"{job}.log"
    log_text = tex_log.read_text(encoding="utf-8", errors="replace") if tex_log.is_file() else ""
    diagnostics = {
        "errors": diagnostic_lines(log_text, r"^!|fatal error|emergency stop"),
        "undefined_references": diagnostic_lines(
            log_text,
            r"undefined references?|reference .* undefined|citation .* undefined",
        ),
        "overfull_boxes": diagnostic_lines(log_text, r"overfull \\[hv]box"),
        "rerun_warnings": diagnostic_lines(log_text, r"rerun|label\(s\) may have changed"),
        "runtime_placeholders": diagnostic_lines(
            log_text,
            r"Run (?:Sage|PythonTeX)|No file .*sagetex\.sout|"
            r"Non-existent (?:console|Pygments) content|"
            r"SageTeX.*(?:rerun|not processed)|PythonTeX.*(?:rerun|required)",
        ),
    }

    render_dir = RENDER_ROOT / job
    render_dir.mkdir(parents=True, exist_ok=True)
    prefix = render_dir / "page"
    run_command(
        f"render_all_pages_{job}",
        ["pdftoppm", "-png", "-r", "72", str(output_pdf), str(prefix)],
        PROJECT_ROOT,
        env,
        records,
        timeout=3600,
    )
    rendered_pages = sorted(render_dir.glob("page-*.png"))
    if len(rendered_pages) != pages:
        raise BuildFailure(
            f"all-page render count for {job} is {len(rendered_pages)}, expected {pages}"
        )
    render_rows: list[dict[str, object]] = []
    for page_number, rendered in enumerate(rendered_pages, start=1):
        size = rendered.stat().st_size
        if size < 64:
            raise BuildFailure(f"empty or truncated page render: {rendered}")
        metrics = png_page_metrics(rendered)
        if metrics["mean_luminance"] < 10:
            raise BuildFailure(f"page render is effectively black: {rendered}")
        render_rows.append(
            {
                "pdf": job,
                "page": page_number,
                "path": rendered.relative_to(PROJECT_ROOT).as_posix(),
                "bytes": size,
                "sha256": sha256_path(rendered),
                **metrics,
            }
        )
    render_payload = json.dumps(
        render_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    representative_indexes = sorted({0, (pages - 1) // 2, pages - 1})
    contact_sheets = make_contact_sheets(job, rendered_pages)

    return {
        "path": str(output_pdf),
        "bytes": output_pdf.stat().st_size,
        "sha256": sha256_path(output_pdf),
        "pages": pages,
        "diagnostics": diagnostics,
        "generated_english_labels": generated_english_label_hits(reopened),
        "all_page_renders": {
            "directory": str(render_dir),
            "count": len(render_rows),
            "bytes": sum(int(row["bytes"]) for row in render_rows),
            "canonical_sha256": hashlib.sha256(render_payload.encode("utf-8")).hexdigest(),
        },
        "representative_renders": [
            str(rendered_pages[index]) for index in representative_indexes
        ],
        "contact_sheets": {
            "count": len(contact_sheets),
            "paths": [row["path"] for row in contact_sheets],
            "bytes": sum(int(row["bytes"]) for row in contact_sheets),
            "sha256": hashlib.sha256(
                json.dumps(
                    contact_sheets,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        },
        "_render_manifest_rows": render_rows,
    }


def write_render_manifest(pdfs: dict[str, object]) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for details in pdfs.values():
        rows.extend(details.pop("_render_manifest_rows"))
    payload = (
        json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    RENDER_MANIFEST_PATH.write_bytes(payload)
    return {
        "path": str(RENDER_MANIFEST_PATH),
        "count": len(rows),
        "bytes_rendered": sum(int(row["bytes"]) for row in rows),
        "manifest_bytes": len(payload),
        "manifest_sha256": hashlib.sha256(payload).hexdigest(),
    }


def dereference_pdf_object(value: object) -> object:
    get_object = getattr(value, "get_object", None)
    return get_object() if callable(get_object) else value


def pdf_filespec_text(value: object) -> str:
    value = dereference_pdf_object(value)
    if isinstance(value, dict):
        for key in ("/UF", "/F", "/DOS", "/Unix", "/Mac"):
            if key in value:
                return pdf_filespec_text(value[key])
        return repr(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def named_destination_text(value: object) -> tuple[str | None, str]:
    value = dereference_pdf_object(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace"), "named"
    if isinstance(value, str):
        text = str(value)
        if type(value).__name__ == "NameObject" and text.startswith("/"):
            text = text[1:]
        return text, "named"
    if isinstance(value, (list, tuple)):
        return None, "explicit"
    return None, type(value).__name__


def target_pdf_name(filespec: str) -> str | None:
    basename = filespec.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if basename == "book.pdf":
        return "book"
    if basename == "jhanswer.pdf":
        return "jhanswer"
    return None


def annotation_remote_actions(reader: PdfReader, source_name: str) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        annotations = dereference_pdf_object(page.get("/Annots", []))
        for annotation_number, annotation_ref in enumerate(annotations, start=1):
            annotation = dereference_pdf_object(annotation_ref)
            if not isinstance(annotation, dict):
                continue
            action_candidates: list[tuple[str, object]] = []
            if "/A" in annotation:
                action_candidates.append(("/A", annotation["/A"]))
            additional = dereference_pdf_object(annotation.get("/AA", {}))
            if isinstance(additional, dict):
                action_candidates.extend(
                    (f"/AA{event}", action) for event, action in additional.items()
                )
            for action_path, action_ref in action_candidates:
                action = dereference_pdf_object(action_ref)
                if not isinstance(action, dict) or str(action.get("/S")) != "/GoToR":
                    continue
                filespec = pdf_filespec_text(action.get("/F", ""))
                destination, destination_kind = named_destination_text(action.get("/D"))
                rect_object = dereference_pdf_object(annotation.get("/Rect", []))
                rect: list[float] | None = None
                if isinstance(rect_object, (list, tuple)) and len(rect_object) == 4:
                    try:
                        rect = [float(value) for value in rect_object]
                    except (TypeError, ValueError):
                        rect = None
                actions.append(
                    {
                        "source_pdf": source_name,
                        "source_page": page_number,
                        "annotation_number": annotation_number,
                        "annotation_subtype": str(annotation.get("/Subtype", "")),
                        "action_path": action_path,
                        "target_file": filespec,
                        "target_pdf": target_pdf_name(filespec),
                        "destination": destination,
                        "destination_kind": destination_kind,
                        "rect": rect,
                    }
                )
    return actions


def all_indirect_object_references(reader: PdfReader) -> list[IndirectObject]:
    """Return every xref-addressable object without traversing page content streams."""
    references: set[tuple[int, int]] = set()
    for generation, entries in reader.xref.items():
        for object_number in entries:
            if object_number:
                references.add((int(object_number), int(generation)))
    for object_number in reader.xref_objStm:
        references.add((int(object_number), 0))
    return [
        IndirectObject(object_number, generation, reader)
        for object_number, generation in sorted(references)
    ]


def exhaustive_remote_actions(reader: PdfReader, source_name: str) -> list[dict[str, object]]:
    """Find every GoToR dictionary in every indirect PDF object.

    Direct children are recursively inspected, while indirect children are
    skipped because each is scanned once as its own xref-addressable object.
    This covers annotations, outlines, additional actions, name trees, and
    catalog/page actions rather than assuming links occur only in ``/Annots``.
    """

    actions: list[dict[str, object]] = []

    def inspect_direct(value: object, path: str, object_label: str, seen: set[int]) -> None:
        if isinstance(value, IndirectObject):
            return
        if isinstance(value, (dict, list, tuple)):
            identity = id(value)
            if identity in seen:
                return
            seen.add(identity)
        if isinstance(value, dict):
            if str(value.get("/S")) == "/GoToR":
                filespec = pdf_filespec_text(value.get("/F", ""))
                destination, destination_kind = named_destination_text(value.get("/D"))
                actions.append(
                    {
                        "source_pdf": source_name,
                        "object": object_label,
                        "object_path": path,
                        "target_file": filespec,
                        "target_pdf": target_pdf_name(filespec),
                        "destination": destination,
                        "destination_kind": destination_kind,
                    }
                )
            for key, child in value.items():
                inspect_direct(child, f"{path}/{str(key).lstrip('/')}", object_label, seen)
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                inspect_direct(child, f"{path}[{index}]", object_label, seen)

    unreadable: list[str] = []
    for reference in all_indirect_object_references(reader):
        label = f"{reference.idnum} {reference.generation} R"
        try:
            value = reader.get_object(reference)
        except Exception as exc:  # pragma: no cover - corrupt-object diagnostic path
            unreadable.append(f"{label}: {type(exc).__name__}: {exc}")
            continue
        inspect_direct(value, "$", label, set())
    if unreadable:
        raise BuildFailure(
            f"could not inspect {len(unreadable)} indirect PDF objects; first: {unreadable[0]}"
        )
    return actions


def audit_cross_pdf_links(pdfs: dict[str, object]) -> dict[str, object]:
    """Enumerate and resolve every GoToR action between the two reader PDFs."""
    readers = {
        name: PdfReader(Path(details["path"]))
        for name, details in pdfs.items()
        if name in {"book", "jhanswer"}
    }
    if set(readers) != {"book", "jhanswer"}:
        raise BuildFailure("book and jhanswer PDFs are both required for the link audit")

    named_destinations = {
        name: sorted(str(destination) for destination in reader.named_destinations)
        for name, reader in readers.items()
    }
    destination_sets = {
        name: set(destinations) for name, destinations in named_destinations.items()
    }
    actions: list[dict[str, object]] = []
    annotation_actions: list[dict[str, object]] = []
    for source_name, reader in readers.items():
        annotation_actions.extend(annotation_remote_actions(reader, source_name))
        for action in exhaustive_remote_actions(reader, source_name):
            target = action["target_pdf"]
            destination = action["destination"]
            if target in destination_sets and isinstance(destination, str):
                action["resolved"] = destination in destination_sets[target]
                action["resolution"] = (
                    "named destination found" if action["resolved"] else "named destination missing"
                )
            elif target in destination_sets:
                action["resolved"] = False
                action["resolution"] = "cross-PDF destination is not a named destination"
            else:
                action["resolved"] = None
                action["resolution"] = "target is outside the audited PDF pair"
            actions.append(action)

    expected_pairs = {("book", "jhanswer"), ("jhanswer", "book")}
    pair_actions = [
        action
        for action in actions
        if (action["source_pdf"], action["target_pdf"]) in expected_pairs
    ]
    unresolved = [action for action in pair_actions if action["resolved"] is not True]
    audit = {
        "scope": (
            "all GoToR action dictionaries in all xref-addressable objects of "
            "book.pdf and jhanswer.pdf; annotation inventory retained separately"
        ),
        "named_destinations": named_destinations,
        "actions": actions,
        "annotation_actions": annotation_actions,
        "counts": {
            "named_destinations": {
                name: len(destinations) for name, destinations in named_destinations.items()
            },
            "goto_remote_actions": len(actions),
            "annotation_goto_remote_actions": len(annotation_actions),
            "book_to_jhanswer": sum(
                action["source_pdf"] == "book" and action["target_pdf"] == "jhanswer"
                for action in pair_actions
            ),
            "jhanswer_to_book": sum(
                action["source_pdf"] == "jhanswer" and action["target_pdf"] == "book"
                for action in pair_actions
            ),
            "unresolved_pair_actions": len(unresolved),
        },
        "unresolved_pair_actions": unresolved,
        "all_pair_actions_resolved": not unresolved,
    }
    LINK_AUDIT_PATH.write_text(
        json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return audit


def tool_versions(env: dict[str, str], records: list[dict[str, object]]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for tool in (
        "python",
        "pdflatex",
        "xelatex",
        "makeindex",
        "bibtex",
        "mpost",
        "pythontex",
        "pdftoppm",
        "pdfimages",
    ):
        if tool == "makeindex":
            executable = shutil.which(tool)
            if executable is None:
                raise BuildFailure("makeindex executable is missing")
            executable_path = Path(executable).resolve()
            versions[tool] = (
                "CLI exposes no version flag; "
                f"executable_bytes={executable_path.stat().st_size}; "
                f"executable_sha256={sha256_path(executable_path)}"
            )
            continue
        version_flag = "-v" if tool == "pdftoppm" else "--version"
        completed = run_command(
            f"version_{tool}",
            [tool, version_flag],
            PROJECT_ROOT,
            env,
            records,
            required=False,
            timeout=60,
        )
        first_line = completed.stdout.splitlines()[0].strip() if completed.stdout else ""
        versions[tool] = first_line or f"exit {completed.returncode}"
    versions["pillow"] = PILLOW_VERSION
    return versions


def reproducibility_fingerprint(report: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "hefferon-id-build-reproducibility-v4",
        "source_tree_sha256": report["source"]["tree_sha256"],
        "authority_pdf_sha256": {
            "book": report["authority_book_pdf"]["sha256"],
            "lab": report["authority_lab_pdf"]["sha256"],
        },
        "book_graphics_manifest_sha256": report["book_graphics"]["manifest_sha256"],
        "lab_graphics_manifest_sha256": report["lab_graphics"]["manifest_sha256"],
        "missing_lab_asset_manifest_sha256": report["missing_lab_asset"][
            "manifest_sha256"
        ],
        "lab_sagetex_stable_fingerprint": report["lab_sagetex"][
            "stable_fingerprint"
        ],
        "metapost_assets": {
            key: report["metapost_assets"][key]
            for key in (
                "schema_version",
                "random_seed",
                "source_date_epoch",
                "asset_count",
                "bytes",
                "canonical_sha256",
                "files",
                "manifest_bytes",
                "manifest_sha256",
            )
        },
        "metapost_assets_end_verification": report[
            "metapost_assets_end_verification"
        ],
        "generated_answer_stream": {
            key: report["generated_answer_stream"][key]
            for key in (
                "bytes",
                "sha256",
                "all_answers",
                "topic_count",
                "topic_answers",
                "expected_native_topic_answers",
                "expected_indonesian_edition_supplied_topic_answers",
                "expected_topic_answers",
                "topic_answer_entries",
            )
        },
        "tex_convergence": report["tex_convergence"],
        "pdftex_input_audit": {
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
                "bytes",
                "sha256",
            )
        },
        "build_tool_sha256": {
            name: details["sha256"]
            for name, details in sorted(report["build_tools"].items())
        },
        "tool_versions": report["tool_versions"],
        "pdftex_font_dependencies": {
            name: {
                "bytes": details["bytes"],
                "sha256": details["sha256"],
            }
            for name, details in sorted(report["pdftex_font_dependencies"].items())
        },
        "pdftex_font_dependencies_end_verification": report[
            "pdftex_font_dependencies_end_verification"
        ],
        "pdftex_font_closure": {
            key: report["pdftex_font_closure"][key]
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
        },
        "pdftex_font_closure_end_verification": report[
            "pdftex_font_closure_end_verification"
        ],
        "pdfs": {
            name: {
                "pages": details["pages"],
                "bytes": details["bytes"],
                "sha256": details["sha256"],
            }
            for name, details in sorted(report["pdfs"].items())
        },
    }


def check_or_record_reproducibility_baseline(
    path: Path, report: dict[str, object]
) -> dict[str, object]:
    resolved = path.resolve()
    ensure_owned_path(resolved, PROJECT_ROOT / "tmp")
    if resolved == RENDER_ROOT.resolve() or resolved.is_relative_to(RENDER_ROOT.resolve()):
        raise BuildFailure(
            "reproducibility baseline must be outside the replaced all-page-render tree"
        )
    current = reproducibility_fingerprint(report)
    current_payload = (
        json.dumps(current, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    if not resolved.exists():
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_bytes(current_payload)
        return {
            "status": "baseline_recorded",
            "matched": None,
            "path": str(resolved),
            "sha256": hashlib.sha256(current_payload).hexdigest(),
        }

    baseline_payload = resolved.read_bytes()
    try:
        baseline = json.loads(baseline_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildFailure(f"invalid reproducibility baseline: {resolved}") from exc
    matched = baseline == current
    return {
        "status": "verified" if matched else "mismatch",
        "matched": matched,
        "path": str(resolved),
        "sha256": hashlib.sha256(baseline_payload).hexdigest(),
        "current_sha256": hashlib.sha256(current_payload).hexdigest(),
        "baseline": baseline,
        "current": current,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stop-after-staging",
        action="store_true",
        help="prepare and fingerprint staging without running generators or TeX",
    )
    parser.add_argument(
        "--reproducibility-baseline",
        type=Path,
        help=(
            "task-owned JSON path under tmp: record the first successful build, "
            "then require exact source/figure/PDF identity on the second"
        ),
    )
    args = parser.parse_args()

    for required in (
        SOURCE_ROOT,
        AUTHORITY_LAB_PDF,
        AUTHORITY_BOOK_PDF,
        EXTRACTOR,
        BOOK_GRAPHICS_RECOVERER,
        LAB_SAGETEX_RUNNER,
        PYTHONTEX_STARTUP,
        PDFTEX_FONT_CLOSURE,
    ):
        if not required.exists():
            raise BuildFailure(f"required input is missing: {required}")

    replace_directory(BUILD_ROOT, PROJECT_ROOT / "build")
    replace_directory(RENDER_ROOT, PROJECT_ROOT / "tmp")
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE_ROOT, STAGING_ROOT, symlinks=True)
    unpack_lab_font_tree()

    manifest_rows, tree_sha256 = canonical_tree_manifest(STAGING_ROOT)
    SOURCE_MANIFEST_PATH.write_text(
        json.dumps(
            {"tree_sha256": tree_sha256, "files": manifest_rows},
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    command_records: list[dict[str, object]] = []
    env = command_environment()
    versions = tool_versions(env, command_records)
    pdftex_font_closure = inspect_pdftex_font_closure()
    pdftex_font_dependencies = resolve_pdftex_font_dependencies()
    run_command(
        "extract_lab_graphics",
        [
            sys.executable,
            str(EXTRACTOR),
            "--authority-pdf",
            str(AUTHORITY_LAB_PDF),
            "--source-lab-root",
            str(SOURCE_ROOT / "src" / "lab"),
            "--output-lab-root",
            str(STAGING_SRC / "lab"),
            "--manifest",
            str(LAB_GRAPHICS_MANIFEST),
        ],
        PROJECT_ROOT,
        env,
        command_records,
    )
    lab_graphics = verify_lab_graphics_manifest()
    missing_lab_asset = recover_missing_lab_asset(env, command_records)
    run_command(
        "recover_book_graphics",
        [
            sys.executable,
            str(BOOK_GRAPHICS_RECOVERER),
            "--authority-pdf",
            str(AUTHORITY_BOOK_PDF),
            "--source-root",
            str(SOURCE_ROOT / "src"),
            "--output-root",
            str(STAGING_SRC),
            "--manifest",
            str(BOOK_GRAPHICS_MANIFEST),
        ],
        PROJECT_ROOT,
        env,
        command_records,
    )
    book_graphics = verify_book_graphics_manifest()

    if args.stop_after_staging:
        print(f"staged_source_tree_sha256={tree_sha256}")
        print(
            json.dumps(
                {
                    "book_graphics": book_graphics,
                    "lab_graphics": lab_graphics,
                    "missing_lab_asset": missing_lab_asset,
                },
                # Staging-only generated closure is reported separately from
                # the canonical translated-source tree fingerprint.
                sort_keys=True,
            )
        )
        return 0

    report: dict[str, object] = {
        "status": "running",
        "source": {
            "path": str(SOURCE_ROOT),
            "staged_path": str(STAGING_ROOT),
            "file_count": len(manifest_rows),
            "tree_sha256": tree_sha256,
        },
        "authority_lab_pdf": {
            "path": str(AUTHORITY_LAB_PDF),
            "sha256": sha256_path(AUTHORITY_LAB_PDF),
        },
        "authority_book_pdf": {
            "path": str(AUTHORITY_BOOK_PDF),
            "sha256": sha256_path(AUTHORITY_BOOK_PDF),
        },
        "lab_graphics": lab_graphics,
        "missing_lab_asset": missing_lab_asset,
        "book_graphics": book_graphics,
        "pdftex_font_closure": pdftex_font_closure,
        "build_tools": {
            "builder": {
                "path": str(Path(__file__).resolve()),
                "bytes": Path(__file__).resolve().stat().st_size,
                "sha256": sha256_path(Path(__file__).resolve()),
            },
            "lab_graphics_extractor": {
                "path": str(EXTRACTOR),
                "bytes": EXTRACTOR.stat().st_size,
                "sha256": sha256_path(EXTRACTOR),
            },
            "book_graphics_recoverer": {
                "path": str(BOOK_GRAPHICS_RECOVERER),
                "bytes": BOOK_GRAPHICS_RECOVERER.stat().st_size,
                "sha256": sha256_path(BOOK_GRAPHICS_RECOVERER),
            },
            "lab_sagetex_runner": {
                "path": str(LAB_SAGETEX_RUNNER),
                "bytes": LAB_SAGETEX_RUNNER.stat().st_size,
                "sha256": sha256_path(LAB_SAGETEX_RUNNER),
            },
            "pythontex_startup": {
                "path": str(PYTHONTEX_STARTUP),
                "bytes": PYTHONTEX_STARTUP.stat().st_size,
                "sha256": sha256_path(PYTHONTEX_STARTUP),
            },
        },
        "tool_versions": versions,
        "pdftex_font_dependencies": pdftex_font_dependencies,
        "commands": command_records,
        "pdfs": {},
    }

    try:
        report["metapost_assets"] = build_assets(env, command_records)
        report["tex_convergence"] = {
            "book": build_book(env, command_records),
        }
        report["generated_answer_stream"] = inspect_generated_answer_stream()
        report["tex_convergence"]["jhanswer"] = build_answer_book(
            env, command_records
        )
        report["pdftex_input_audit"] = audit_pdftex_recorded_inputs()
        report["lab_sagetex"] = build_lab(env, command_records)
        for job, cwd, _engine in PDF_JOBS:
            report["pdfs"][job] = inspect_pdf(job, cwd, command_records, env)
        report["all_page_render_manifest"] = write_render_manifest(report["pdfs"])
        link_audit = audit_cross_pdf_links(report["pdfs"])
        report["cross_pdf_link_audit"] = {
            "path": str(LINK_AUDIT_PATH),
            "bytes": LINK_AUDIT_PATH.stat().st_size,
            "sha256": sha256_path(LINK_AUDIT_PATH),
            "counts": link_audit["counts"],
            "all_pair_actions_resolved": link_audit["all_pair_actions_resolved"],
        }
        report["qa_summary"] = {
            "undefined_reference_lines": sum(
                len(details["diagnostics"]["undefined_references"])
                for details in report["pdfs"].values()
            ),
            "generated_english_label_hits": sum(
                len(details["generated_english_labels"])
                for details in report["pdfs"].values()
            ),
            "overfull_box_lines": sum(
                len(details["diagnostics"]["overfull_boxes"])
                for details in report["pdfs"].values()
            ),
            "runtime_placeholder_lines": sum(
                len(details["diagnostics"]["runtime_placeholders"])
                for details in report["pdfs"].values()
            ),
        }
        if not link_audit["all_pair_actions_resolved"]:
            unresolved = link_audit["unresolved_pair_actions"]
            first = unresolved[0]
            raise BuildFailure(
                "unresolved cross-PDF GoToR actions: "
                f"{len(unresolved)}; first is {first['source_pdf']} object "
                f"{first['object']} at {first['object_path']} -> "
                f"{first['target_file']}#{first['destination']}"
            )
        if report["qa_summary"]["undefined_reference_lines"]:
            raise BuildFailure(
                "final TeX logs still contain undefined references; see build_report.json"
            )
        if report["qa_summary"]["generated_english_label_hits"]:
            raise BuildFailure(
                "generated English structural labels remain; see build_report.json"
            )
        if report["qa_summary"]["runtime_placeholder_lines"]:
            raise BuildFailure(
                "final TeX logs still contain runtime placeholders; see build_report.json"
            )
        live_rows, live_tree_sha256 = canonical_tree_manifest(SOURCE_ROOT)
        source_differences = manifest_differences(manifest_rows, live_rows)
        source_unchanged = all(not paths for paths in source_differences.values())
        report["source"]["live_end_file_count"] = len(live_rows)
        report["source"]["live_end_tree_sha256"] = live_tree_sha256
        report["source"]["unchanged_during_build"] = source_unchanged
        report["source"]["end_differences"] = source_differences
        if not source_unchanged:
            raise BuildFailure(
                "canonical source changed during the isolated build; rerun from a fresh copy"
            )
        report["pdftex_font_dependencies_end_verification"] = (
            verify_staged_pdftex_font_dependencies(report["pdftex_font_dependencies"])
        )
        report["pdftex_font_closure_end_verification"] = (
            verify_pdftex_font_closure_unchanged(report["pdftex_font_closure"])
        )
        report["metapost_assets_end_verification"] = (
            verify_metapost_assets_unchanged(report["metapost_assets"])
        )
        if args.reproducibility_baseline is not None:
            report["reproducibility"] = check_or_record_reproducibility_baseline(
                args.reproducibility_baseline, report
            )
            if report["reproducibility"]["matched"] is False:
                raise BuildFailure(
                    "second-build fingerprint differs from the reproducibility baseline"
                )
        report["status"] = "success"
    except BaseException as exc:
        report["status"] = "failed"
        report["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    summary = {
        name: {
            "pages": details["pages"],
            "bytes": details["bytes"],
            "sha256": details["sha256"],
        }
        for name, details in report["pdfs"].items()
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildFailure as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
