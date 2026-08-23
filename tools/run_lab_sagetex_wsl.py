#!/usr/bin/env python3
"""Execute the Hefferon lab's generated SageTeX program in pinned WSL Sage.

The command is deliberately limited to the disposable Hefferon staging tree.
It verifies the generated SageTeX program, executes every command block, audits
the resulting ``.sout``/``.scmd`` closure, and restores the 64 pinned official
figure PDFs after recording Sage's expected figure-generation side effects.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = PROJECT_ROOT / "build" / "hefferon_id"
EXPECTED_LAB_ROOT = BUILD_ROOT / "staging" / "linear-algebra" / "src" / "lab"
EXPECTED_GRAPHICS_MANIFEST = BUILD_ROOT / "lab_graphics_manifest.csv"
EXPECTED_RUNTIME_MANIFEST = BUILD_ROOT / "lab_sagetex_runtime_manifest.json"

EXPECTED_WSL_DISTRO = "Ubuntu-22.04"
EXPECTED_SAGE_VERSION = "SageMath version 9.5, Release Date: 2022-01-30"
EXPECTED_SAGETEX_DISTRIBUTION_VERSION = "3.6.1"
EXPECTED_SAGETEX_MODULE_VERSION = "2021/10/16 v3.6"
EXPECTED_GENERATED_SAGETEX_VERSION = "2022/08/21 v3.6.1"
EXPECTED_COMMAND_LABELS = 148
EXPECTED_COMMAND_SOURCE_LISTINGS = 1018
EXPECTED_SCMD_LINES = 1237
EXPECTED_UNCHANGED_FIGURES = {"asy/ellipsoid1.pdf"}
DEFAULT_RANDOM_SEED = 20260821
DEFAULT_SOURCE_DATE_EPOCH = "1633046400"


class SageBuildFailure(RuntimeError):
    """A required SageTeX execution or audit step failed."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def require_exact_paths(
    lab_root: Path, graphics_manifest: Path, runtime_manifest: Path
) -> None:
    if lab_root.resolve() != EXPECTED_LAB_ROOT.resolve():
        raise SageBuildFailure(f"unexpected lab staging root: {lab_root.resolve()}")
    if graphics_manifest.resolve() != EXPECTED_GRAPHICS_MANIFEST.resolve():
        raise SageBuildFailure(
            f"unexpected authority-graphics manifest: {graphics_manifest.resolve()}"
        )
    if runtime_manifest.resolve() != EXPECTED_RUNTIME_MANIFEST.resolve():
        raise SageBuildFailure(
            f"unexpected SageTeX runtime manifest: {runtime_manifest.resolve()}"
        )


def load_authority_graphics(
    lab_root: Path, manifest_path: Path
) -> tuple[list[dict[str, str]], dict[str, bytes]]:
    with manifest_path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 64:
        raise SageBuildFailure(
            f"expected 64 authority figure records, found {len(rows)}"
        )

    seen: set[str] = set()
    preserved: dict[str, bytes] = {}
    for row in rows:
        relative = Path(row["path"])
        relative_text = relative.as_posix()
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.suffix.lower() != ".pdf"
            or relative_text in seen
        ):
            raise SageBuildFailure(f"unsafe or duplicate figure path: {relative_text}")
        seen.add(relative_text)
        target = (lab_root / relative).resolve()
        if not target.is_relative_to(lab_root.resolve()) or not target.is_file():
            raise SageBuildFailure(f"missing authority figure: {target}")
        payload = target.read_bytes()
        if len(payload) != int(row["bytes"]):
            raise SageBuildFailure(f"authority figure byte mismatch: {relative_text}")
        if sha256_bytes(payload) != row["sha256"]:
            raise SageBuildFailure(f"authority figure SHA-256 mismatch: {relative_text}")
        if len(PdfReader(target, strict=True).pages) != 1:
            raise SageBuildFailure(f"authority figure is not one page: {relative_text}")
        preserved[relative_text] = payload

    if EXPECTED_UNCHANGED_FIGURES - seen:
        raise SageBuildFailure("the frozen ellipsoid figure is absent from the manifest")
    return rows, preserved


def run_wsl(
    wsl_executable: str,
    distro: str,
    lab_root: Path,
    arguments: list[str],
    env: dict[str, str],
    *,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    command = [
        wsl_executable,
        "-d",
        distro,
        "-u",
        "root",
        "--cd",
        str(lab_root),
        "--",
        *arguments,
    ]
    try:
        completed = subprocess.run(
            command,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SageBuildFailure(
            f"WSL command timed out after {timeout} seconds: {arguments}"
        ) from exc
    if completed.returncode != 0:
        tail = "\n".join(completed.stdout.splitlines()[-20:])
        raise SageBuildFailure(
            f"WSL command failed with exit {completed.returncode}: {arguments}\n{tail}"
        )
    return completed


def sagetex_source_md5(script_text: str) -> str:
    digest = hashlib.md5()
    excluded_prefixes = (
        " _st_.goboom",
        "print('SageT",
        "_st_.current_tex_line",
        " _st_.current_tex_line",
    )
    for line in script_text.splitlines(keepends=True):
        if not line.startswith(excluded_prefixes):
            digest.update(line.encode("utf-8"))
    return digest.hexdigest()


def inspect_sagetex_outputs(
    lab_root: Path, original_script: str
) -> dict[str, object]:
    sout = lab_root / "lab.sagetex.sout"
    scmd = lab_root / "lab.sagetex.scmd"
    for path in (sout, scmd):
        if not path.is_file() or path.stat().st_size == 0:
            raise SageBuildFailure(f"missing or empty SageTeX output: {path.name}")

    sout_text = sout.read_text(encoding="utf-8")
    scmd_text = scmd.read_text(encoding="utf-8")
    label_numbers = [
        int(number)
        for number in re.findall(r"\\newlabel\{@sagecmdline(\d+)\}", sout_text)
    ]
    expected_labels = list(range(EXPECTED_COMMAND_LABELS))
    if label_numbers != expected_labels:
        raise SageBuildFailure(
            "SageTeX command-label closure differs from the exact 0..147 sequence"
        )

    listing_pattern = re.compile(
        r"\\lstinputlisting\[firstline=(\d+),lastline=(\d+),"
        r"firstnumber=(\d+),style=SageInput\]\{lab\.sagetex\.scmd\}"
    )
    listings = [tuple(map(int, match)) for match in listing_pattern.findall(sout_text)]
    scmd_line_count = len(scmd_text.splitlines())
    if len(listings) != EXPECTED_COMMAND_SOURCE_LISTINGS:
        raise SageBuildFailure(
            "SageTeX command-source listing count differs from the frozen 1,018"
        )
    if scmd_line_count != EXPECTED_SCMD_LINES:
        raise SageBuildFailure(
            "SageTeX command-source line count differs from the frozen 1,237"
        )
    for firstline, lastline, firstnumber in listings:
        if (
            firstline < 1
            or lastline < firstline
            or lastline > scmd_line_count
            or firstnumber < 1
        ):
            raise SageBuildFailure(
                "SageTeX command-source listing lies outside lab.sagetex.scmd"
            )

    marker_pattern = re.compile(
        r'^%([0-9a-f]{32})% md5sum of corresponding \.sage file '
        r'\(minus "goboom", "current_tex_line", and pause/unpause lines\)$',
        re.MULTILINE,
    )
    expected_md5 = sagetex_source_md5(original_script)
    sout_markers = marker_pattern.findall(sout_text)
    scmd_markers = marker_pattern.findall(scmd_text)
    if sout_markers != [expected_md5] or scmd_markers != [expected_md5]:
        raise SageBuildFailure(
            "SageTeX output MD5 markers do not bind the original generated .sage file"
        )
    for temporary_name in ("lab.sagetex.sout.tmp", "lab.sagetex.scmd.tmp"):
        if (lab_root / temporary_name).exists():
            raise SageBuildFailure(f"stale SageTeX temporary output remains: {temporary_name}")

    return {
        "sout": {
            "path": str(sout),
            "bytes": sout.stat().st_size,
            "sha256": sha256_path(sout),
        },
        "scmd": {
            "path": str(scmd),
            "bytes": scmd.stat().st_size,
            "sha256": sha256_path(scmd),
            "line_count": scmd_line_count,
        },
        "command_label_count": len(label_numbers),
        "command_label_first": label_numbers[0],
        "command_label_last": label_numbers[-1],
        "command_source_listing_count": len(listings),
        "maximum_listed_source_line": max(lastline for _, lastline, _ in listings),
        "source_md5": expected_md5,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab-root", required=True, type=Path)
    parser.add_argument("--authority-graphics-manifest", required=True, type=Path)
    parser.add_argument("--output-manifest", required=True, type=Path)
    parser.add_argument("--distro", default=EXPECTED_WSL_DISTRO)
    parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED)
    parser.add_argument("--source-date-epoch", default=DEFAULT_SOURCE_DATE_EPOCH)
    args = parser.parse_args()

    lab_root = args.lab_root.resolve(strict=True)
    graphics_manifest = args.authority_graphics_manifest.resolve(strict=True)
    runtime_manifest = args.output_manifest.resolve()
    require_exact_paths(lab_root, graphics_manifest, runtime_manifest)
    if args.distro != EXPECTED_WSL_DISTRO:
        raise SageBuildFailure(f"unapproved WSL distribution: {args.distro}")
    if args.seed != DEFAULT_RANDOM_SEED:
        raise SageBuildFailure(f"unapproved random seed: {args.seed}")
    if args.source_date_epoch != DEFAULT_SOURCE_DATE_EPOCH:
        raise SageBuildFailure(
            f"unapproved SOURCE_DATE_EPOCH: {args.source_date_epoch}"
        )

    sage_script = lab_root / "lab.sagetex.sage"
    pytxcode = lab_root / "lab.pytxcode"
    for path in (sage_script, pytxcode):
        if not path.is_file() or path.stat().st_size == 0:
            raise SageBuildFailure(f"required generated input is missing: {path.name}")

    original_script = sage_script.read_text(encoding="utf-8")
    processor_pattern = re.compile(
        r"_st_ = sagetex\.SageTeXProcessor\('lab', "
        r"version='([^']+)', version_check=True\)"
    )
    matches = processor_pattern.findall(original_script)
    if matches != [EXPECTED_GENERATED_SAGETEX_VERSION]:
        raise SageBuildFailure(
            "generated SageTeX processor declaration differs from the pinned v3.6.1 form"
        )
    compatibility_script = original_script.replace(
        f"version='{EXPECTED_GENERATED_SAGETEX_VERSION}', version_check=True)",
        f"version='{EXPECTED_GENERATED_SAGETEX_VERSION}', version_check=False)",
        1,
    )
    if compatibility_script.count("version_check=False") != 1:
        raise SageBuildFailure("compatibility copy did not change exactly one version check")

    compatibility_path = lab_root / "lab.sagetex.compat.sage"
    runner_path = lab_root / "lab.sagetex.runner.sage"
    atomic_write(compatibility_path, compatibility_script.encode("utf-8"))
    runner_text = (
        "import os\n"
        f"os.environ['SOURCE_DATE_EPOCH'] = '{args.source_date_epoch}'\n"
        "os.environ['TZ'] = 'UTC'\n"
        "os.environ['PYTHONHASHSEED'] = '0'\n"
        "os.environ['OPENBLAS_NUM_THREADS'] = '1'\n"
        "os.environ['OMP_NUM_THREADS'] = '1'\n"
        "os.environ['MKL_NUM_THREADS'] = '1'\n"
        "os.environ['MPLBACKEND'] = 'Agg'\n"
        f"set_random_seed({args.seed})\n"
        "load('lab.sagetex.compat.sage')\n"
    )
    atomic_write(runner_path, runner_text.encode("utf-8"))

    graphics_rows, preserved_graphics = load_authority_graphics(
        lab_root, graphics_manifest
    )
    authority_manifest_sha256 = sha256_path(graphics_manifest)

    wsl_executable = shutil.which("wsl.exe")
    if wsl_executable is None:
        raise SageBuildFailure("wsl.exe is unavailable")
    runtime_env = os.environ.copy()
    runtime_env.update(
        {
            "SOURCE_DATE_EPOCH": args.source_date_epoch,
            "FORCE_SOURCE_DATE": "1",
            "TZ": "UTC",
            "PYTHONHASHSEED": "0",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "MPLBACKEND": "Agg",
        }
    )

    version_result = run_wsl(
        wsl_executable,
        args.distro,
        lab_root,
        ["sage", "--version"],
        runtime_env,
        timeout=120,
    )
    sage_version = version_result.stdout.strip()
    if sage_version != EXPECTED_SAGE_VERSION:
        raise SageBuildFailure(f"unexpected Sage version: {sage_version!r}")

    sagetex_result = run_wsl(
        wsl_executable,
        args.distro,
        lab_root,
        [
            "sage",
            "-python",
            "-c",
            (
                "import importlib.metadata, sagetex; "
                "print(importlib.metadata.version('sagetex')); "
                "print(sagetex.pyversion)"
            ),
        ],
        runtime_env,
        timeout=120,
    )
    sagetex_version_lines = sagetex_result.stdout.strip().splitlines()
    expected_sagetex_lines = [
        EXPECTED_SAGETEX_DISTRIBUTION_VERSION,
        EXPECTED_SAGETEX_MODULE_VERSION,
    ]
    if sagetex_version_lines != expected_sagetex_lines:
        raise SageBuildFailure(
            f"unexpected SageTeX package identity: {sagetex_version_lines!r}"
        )

    for stale_output in (lab_root / "lab.sagetex.sout", lab_root / "lab.sagetex.scmd"):
        stale_output.unlink(missing_ok=True)

    generated_figure_rows: list[dict[str, object]] = []
    execution_result: subprocess.CompletedProcess[str] | None = None
    outputs: dict[str, object] | None = None
    try:
        execution_result = run_wsl(
            wsl_executable,
            args.distro,
            lab_root,
            ["sage", runner_path.name],
            runtime_env,
            timeout=1800,
        )
        outputs = inspect_sagetex_outputs(lab_root, original_script)
        if sage_script.read_text(encoding="utf-8") != original_script:
            raise SageBuildFailure("native Sage execution altered the original generated script")
        if "Traceback (most recent call last)" in execution_result.stdout:
            raise SageBuildFailure("native Sage output contains a Python traceback")
        for row in graphics_rows:
            relative_text = row["path"]
            target = lab_root / Path(relative_text)
            if not target.is_file():
                raise SageBuildFailure(
                    f"Sage removed an expected figure without replacing it: {relative_text}"
                )
            if len(PdfReader(target, strict=True).pages) != 1:
                raise SageBuildFailure(
                    f"Sage-generated figure is not one page: {relative_text}"
                )
            generated_sha256 = sha256_path(target)
            generated_figure_rows.append(
                {
                    "path": relative_text,
                    "changed_from_authority": generated_sha256 != row["sha256"],
                    "generated_bytes": target.stat().st_size,
                    "generated_sha256": generated_sha256,
                }
            )
        unchanged = {
            str(row["path"])
            for row in generated_figure_rows
            if row["changed_from_authority"] is False
        }
        if unchanged != EXPECTED_UNCHANGED_FIGURES:
            raise SageBuildFailure(
                "Sage figure side-effect closure drifted; expected only ellipsoid1 unchanged, "
                f"found {sorted(unchanged)}"
            )
    finally:
        for relative_text, payload in preserved_graphics.items():
            atomic_write(lab_root / Path(relative_text), payload)

    if execution_result is None or outputs is None:
        raise SageBuildFailure("Sage execution did not produce an auditable result")

    for row in graphics_rows:
        restored = lab_root / Path(row["path"])
        if (
            restored.stat().st_size != int(row["bytes"])
            or sha256_path(restored) != row["sha256"]
        ):
            raise SageBuildFailure(
                f"authority figure restoration failed: {row['path']}"
            )

    changed_paths = sorted(
        str(row["path"])
        for row in generated_figure_rows
        if row["changed_from_authority"] is True
    )
    stable_fingerprint = {
        "schema_version": "hefferon-id-sagetex-stable-fingerprint-v1",
        "wsl_distro": args.distro,
        "sage_version": sage_version,
        "sagetex_distribution_version": sagetex_version_lines[0],
        "sagetex_module_version": sagetex_version_lines[1],
        "random_seed": args.seed,
        "source_date_epoch": args.source_date_epoch,
        "generated_sage_script_sha256": sha256_path(sage_script),
        "compatibility_sage_script_sha256": sha256_path(compatibility_path),
        "runner_sha256": sha256_path(runner_path),
        "pytxcode_sha256": sha256_path(pytxcode),
        "sout_sha256": outputs["sout"]["sha256"],
        "scmd_sha256": outputs["scmd"]["sha256"],
        "source_md5": outputs["source_md5"],
        "command_label_count": outputs["command_label_count"],
        "command_source_listing_count": outputs["command_source_listing_count"],
        "authority_graphics_manifest_sha256": authority_manifest_sha256,
        "sage_changed_figure_count": len(changed_paths),
        "sage_changed_paths_sha256": sha256_bytes(
            (json.dumps(changed_paths, separators=(",", ":")) + "\n").encode("utf-8")
        ),
        "final_figure_source": "pinned_authority_pdf_forms_restored_after_execution",
    }
    manifest = {
        "schema_version": "hefferon-id-sagetex-runtime-v1",
        "status": "pass",
        "lab_root": str(lab_root),
        "toolchain": {
            "wsl_executable": wsl_executable,
            "wsl_distro": args.distro,
            "sage_version": sage_version,
            "sagetex_distribution_version": sagetex_version_lines[0],
            "sagetex_module_version": sagetex_version_lines[1],
            "generated_sagetex_version": EXPECTED_GENERATED_SAGETEX_VERSION,
        },
        "deterministic_controls": {
            "random_seed": args.seed,
            "source_date_epoch": args.source_date_epoch,
            "timezone": "UTC",
        },
        "compatibility_override": {
            "scope": "disposable_generated_staging_copy_only",
            "reason": (
                "SageTeX distribution 3.6.1 exposes the compatible historical "
                "module version string 2021/10/16 v3.6; only the generated "
                "processor's strict version-string check is disabled"
            ),
            "original": {
                "path": str(sage_script),
                "bytes": sage_script.stat().st_size,
                "sha256": sha256_path(sage_script),
            },
            "compatibility_copy": {
                "path": str(compatibility_path),
                "bytes": compatibility_path.stat().st_size,
                "sha256": sha256_path(compatibility_path),
            },
            "runner": {
                "path": str(runner_path),
                "bytes": runner_path.stat().st_size,
                "sha256": sha256_path(runner_path),
            },
        },
        "generated_inputs": {
            "pytxcode": {
                "path": str(pytxcode),
                "bytes": pytxcode.stat().st_size,
                "sha256": sha256_path(pytxcode),
            }
        },
        "outputs": outputs,
        "execution_stdout": {
            "line_count": len(execution_result.stdout.splitlines()),
            "sha256": sha256_bytes(execution_result.stdout.encode("utf-8")),
        },
        "figure_execution": {
            "target_count": len(graphics_rows),
            "changed_from_authority_count": len(changed_paths),
            "unchanged_from_authority_paths": sorted(EXPECTED_UNCHANGED_FIGURES),
            "generated_state": generated_figure_rows,
            "authority_manifest": {
                "path": str(graphics_manifest),
                "sha256": authority_manifest_sha256,
            },
            "final_state": "all_64_pinned_authority_figures_restored_and_rehashed",
        },
        "stable_fingerprint": stable_fingerprint,
    }
    manifest_payload = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    atomic_write(runtime_manifest, manifest_payload)
    print(
        json.dumps(
            {
                "status": "pass",
                "command_labels": outputs["command_label_count"],
                "sage_changed_figures": len(changed_paths),
                "restored_authority_figures": len(graphics_rows),
                "sout_sha256": outputs["sout"]["sha256"],
                "scmd_sha256": outputs["scmd"]["sha256"],
                "manifest_sha256": sha256_bytes(manifest_payload),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SageBuildFailure as exc:
        print(f"SAGETEX BUILD FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
