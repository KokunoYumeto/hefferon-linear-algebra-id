#!/usr/bin/env python3
"""Recover the lab's generated PDF figures from the pinned official lab PDF.

The pinned Hefferon source generates these figures with Sage.  This Windows
release lane does not have Sage, while the official PDF embeds every generated
figure as an unmodified Form XObject.  This tool extracts those forms into
one-page PDFs for a staging build.  It deliberately refuses to write into the
translated source tree.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import re
import tempfile

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject


AUTHORITY_SHA256 = "0ca33cb79632c3b27c964a6dc8e31f8315d5a529f9e7214ced7f8cb49003b6a2"
LAB_TEX_ORDER = (
    "cover.tex",
    "preface.tex",
    "sageintro.tex",
    "gauss.tex",
    "spaces.tex",
    "matrices.tex",
    "maps.tex",
    "svd.tex",
    "geometry.tex",
    "eigen.tex",
)
FORM_NUMBERS = tuple(range(1, 22)) + tuple(range(26, 69))
INCLUDEGRAPHICS_RE = re.compile(
    r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}"
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def active_tex(line: str) -> str:
    """Return the active prefix, respecting an escaped percent sign."""
    for index, character in enumerate(line):
        if character != "%":
            continue
        slash_count = 0
        cursor = index - 1
        while cursor >= 0 and line[cursor] == "\\":
            slash_count += 1
            cursor -= 1
        if slash_count % 2 == 0:
            return line[:index]
    return line


def discover_pdf_targets(source_lab_root: Path) -> list[PurePosixPath]:
    targets: list[PurePosixPath] = []
    for relative_name in LAB_TEX_ORDER:
        source_path = source_lab_root / relative_name
        if not source_path.is_file():
            raise ValueError(f"missing lab source: {source_path}")
        for line in source_path.read_text(encoding="utf-8").splitlines():
            for match in INCLUDEGRAPHICS_RE.finditer(active_tex(line)):
                value = PurePosixPath(match.group(1))
                if value.suffix.lower() == ".pdf":
                    targets.append(value)

    if len(targets) != 64:
        raise ValueError(f"expected 64 active PDF figure targets, found {len(targets)}")
    if len(set(targets)) != len(targets):
        raise ValueError("active PDF figure targets are not unique")
    for target in targets:
        if target.is_absolute() or ".." in target.parts:
            raise ValueError(f"unsafe target path: {target}")
    return targets


def collect_forms(reader: PdfReader):
    forms = {}
    for page_number, page in enumerate(reader.pages, start=1):
        resources = page.get("/Resources") or {}
        xobjects = resources.get("/XObject") or {}
        for raw_name, reference in xobjects.items():
            name = str(raw_name)
            if not re.fullmatch(r"/Fm\d+", name):
                continue
            if name in forms:
                if forms[name][1] != reference:
                    raise ValueError(f"form name {name} identifies multiple objects")
                continue
            forms[name] = (page_number, reference, reference.get_object())

    expected_names = {f"/Fm{number}" for number in FORM_NUMBERS}
    actual_names = set(forms)
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)
        raise ValueError(f"unexpected form closure; missing={missing}, extra={extra}")
    return forms


def form_dimensions(form) -> tuple[float, float, float, float]:
    if str(form.get("/Subtype")) != "/Form":
        raise ValueError("expected a Form XObject")
    bbox = form.get("/BBox")
    if bbox is None or len(bbox) != 4:
        raise ValueError("Form XObject lacks a four-value BBox")
    x0, y0, x1, y1 = (float(value) for value in bbox)
    if not x1 > x0 or not y1 > y0:
        raise ValueError(f"invalid Form XObject BBox: {bbox}")
    matrix = [float(value) for value in (form.get("/Matrix") or [1, 0, 0, 1, 0, 0])]
    if matrix != [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]:
        raise ValueError(f"unsupported nonidentity Form XObject matrix: {matrix}")
    return x0, y0, x1, y1


def extracted_pdf_bytes(reference, form_name: str, form) -> tuple[bytes, float, float]:
    x0, y0, x1, y1 = form_dimensions(form)
    width = x1 - x0
    height = y1 - y0

    writer = PdfWriter()
    page = writer.add_blank_page(width=width, height=height)
    cloned_reference = reference.clone(writer)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/XObject"): DictionaryObject(
                {NameObject(form_name): cloned_reference}
            )
        }
    )
    content = StreamObject()
    content.set_data(
        f"q 1 0 0 1 {-x0:.12g} {-y0:.12g} cm {form_name} Do Q\n".encode("ascii")
    )
    page[NameObject("/Contents")] = writer._add_object(content)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue(), width, height


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


def canonical_manifest(rows: list[dict[str, object]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=(
            "path",
            "form_xobject",
            "authority_page",
            "width_points",
            "height_points",
            "bytes",
            "sha256",
        ),
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority-pdf", required=True, type=Path)
    parser.add_argument("--source-lab-root", required=True, type=Path)
    parser.add_argument("--output-lab-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()

    authority_pdf = args.authority_pdf.resolve(strict=True)
    source_lab_root = args.source_lab_root.resolve(strict=True)
    output_lab_root = args.output_lab_root.resolve()
    manifest_path = args.manifest.resolve()

    if output_lab_root == source_lab_root:
        raise ValueError("refusing to write recovered graphics into the source lab tree")
    if sha256_path(authority_pdf) != AUTHORITY_SHA256:
        raise ValueError("authority lab PDF SHA-256 does not match the frozen artifact")

    targets = discover_pdf_targets(source_lab_root)
    reader = PdfReader(authority_pdf)
    if len(reader.pages) != 105:
        raise ValueError(f"expected 105 authority pages, found {len(reader.pages)}")
    forms = collect_forms(reader)

    rows: list[dict[str, object]] = []
    for target, form_number in zip(targets, FORM_NUMBERS, strict=True):
        form_name = f"/Fm{form_number}"
        authority_page, reference, form = forms[form_name]
        payload, width, height = extracted_pdf_bytes(reference, form_name, form)
        output_path = output_lab_root.joinpath(*target.parts)
        atomic_write(output_path, payload)

        reopened = PdfReader(io.BytesIO(payload))
        if len(reopened.pages) != 1:
            raise ValueError(f"extracted figure is not one page: {target}")
        page = reopened.pages[0]
        if abs(float(page.mediabox.width) - width) > 1e-6:
            raise ValueError(f"width mismatch after reopening: {target}")
        if abs(float(page.mediabox.height) - height) > 1e-6:
            raise ValueError(f"height mismatch after reopening: {target}")

        rows.append(
            {
                "path": target.as_posix(),
                "form_xobject": form_name[1:],
                "authority_page": authority_page,
                "width_points": f"{width:.9f}".rstrip("0").rstrip("."),
                "height_points": f"{height:.9f}".rstrip("0").rstrip("."),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )

    manifest_payload = canonical_manifest(rows)
    atomic_write(manifest_path, manifest_payload)
    print(
        f"extracted={len(rows)} bytes={sum(int(row['bytes']) for row in rows)} "
        f"manifest_sha256={hashlib.sha256(manifest_payload).hexdigest()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
