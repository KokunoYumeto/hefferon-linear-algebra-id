#!/usr/bin/env python3
"""Recover or deterministically reconstruct the book's seven Asymptote figures.

Five vector figures are embedded as unmodified Form XObjects in the pinned
official book PDF.  Two of those forms have small English labels; their decoded
content streams are changed only in the terminal text-label block.  The pinned
official PDF predates the Inner Product topic, so its two simple 2-D diagrams
are reconstructed from the coordinates in the pinned ``innerproduct.asy``.

The tool writes only to a staging tree and deliberately refuses to write into
the translated source tree.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import logging
import os
from pathlib import Path, PurePosixPath
import re
import tempfile

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    IndirectObject,
    NameObject,
    StreamObject,
)


AUTHORITY_SHA256 = "5240f2782e645bc6351ad9eba69d8c19500142a5cca9c90450c17b3765a1a400"
EXPECTED_TARGETS = (
    PurePosixPath("det/asy/ppiped.pdf"),
    PurePosixPath("jc/asy/wilber.pdf"),
    PurePosixPath("jc/asy/wilber001.pdf"),
    PurePosixPath("jc/asy/wilber003.pdf"),
    PurePosixPath("jc/asy/wilber002.pdf"),
    PurePosixPath("jc/asy/innerproduct000.pdf"),
    PurePosixPath("jc/asy/innerproduct001.pdf"),
)
FORM_SPECS = {
    PurePosixPath("det/asy/ppiped.pdf"): (367, "/Im9", None),
    PurePosixPath("jc/asy/wilber.pdf"): (492, "/Im12", None),
    PurePosixPath("jc/asy/wilber001.pdf"): (492, "/Im13", None),
    PurePosixPath("jc/asy/wilber003.pdf"): (493, "/Im14", "cosine"),
    PurePosixPath("jc/asy/wilber002.pdf"): (493, "/Im15", "spring"),
}
INCLUDEGRAPHICS_RE = re.compile(
    r"\\includegraphics(?:\[[^]]*\])?\{((?:det|jc)/asy/[^}]+\.pdf)\}"
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def active_tex(line: str) -> str:
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


def discover_targets(source_root: Path) -> tuple[PurePosixPath, ...]:
    found: list[PurePosixPath] = []
    for source_path in sorted(source_root.rglob("*.tex")):
        for line in source_path.read_text(encoding="utf-8").splitlines():
            found.extend(
                PurePosixPath(match.group(1))
                for match in INCLUDEGRAPHICS_RE.finditer(active_tex(line))
            )
    if len(found) != len(EXPECTED_TARGETS) or set(found) != set(EXPECTED_TARGETS):
        raise ValueError(
            "unexpected active Asymptote PDF closure; "
            f"expected={EXPECTED_TARGETS!r}, found={tuple(found)!r}"
        )
    return EXPECTED_TARGETS


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


def localized_form_data(data: bytes, localization: str | None) -> bytes:
    if localization is None:
        return data
    if localization == "cosine":
        anchor = b"0 g\nq\n10 0 0 10 0 0 cm BT\n/R8 9.96264 Tf\n"
        if data.count(anchor) != 1 or not data.endswith(b"ET\nQ\nQ\n"):
            raise ValueError("official cosine form no longer has the frozen label block")
        return data[: data.index(anchor)] + b"Q\n"
    if localization == "spring":
        anchor = b"q\n10 0 0 10 0 0 cm BT\n/R8 7.97011 Tf\n"
        if data.count(anchor) != 1 or not data.endswith(b"ET\nQ\nQ\n"):
            raise ValueError("official spring form no longer has the frozen label block")
        return data[: data.index(anchor)] + b"Q\n"
    raise ValueError(f"unknown localization profile: {localization}")


def extracted_pdf_bytes(reference, form_name: str, form, localization: str | None):
    x0, y0, x1, y1 = form_dimensions(form)
    width = x1 - x0
    height = y1 - y0
    data = localized_form_data(form.get_data(), localization)

    writer = PdfWriter()
    page = writer.add_blank_page(width=width, height=height)
    if localization is None:
        # ``IndirectObject.clone(writer)`` returns the cloned stream object,
        # not a writer-owned indirect reference.  Inserting that stream
        # directly can collide with the blank page's object slot, yielding a
        # file whose /Pages /Kids entry resolves to null.  Register the cloned
        # form explicitly so pdfTeX and strict page-tree readers see a valid
        # one-page PDF.
        cloned_form = form.clone(writer)
        for key in ("/PTEX.FileName", "/PTEX.PageNumber", "/PTEX.InfoDict"):
            cloned_form.pop(NameObject(key), None)
        cloned_reference = getattr(cloned_form, "indirect_reference", None)
        if (
            not isinstance(cloned_reference, IndirectObject)
            or cloned_reference.pdf is not writer
        ):
            raise ValueError("cloned Form was not registered as a writer-owned object")
    else:
        modified = DecodedStreamObject()
        for key, value in form.items():
            if str(key) not in {
                "/Length",
                "/Filter",
                "/DecodeParms",
                "/PTEX.FileName",
                "/PTEX.PageNumber",
                "/PTEX.InfoDict",
            }:
                modified[key] = value
        modified.set_data(data)
        cloned_reference = writer._add_object(modified.clone(writer))
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
    payload = output.getvalue()
    if localization is not None:
        base_reader = PdfReader(io.BytesIO(payload))
        overlay_reader = PdfReader(
            io.BytesIO(localization_overlay_pdf(localization, width, height))
        )
        base_page = base_reader.pages[0]
        base_page.merge_page(overlay_reader.pages[0])
        merged_writer = PdfWriter()
        merged_writer.add_page(base_page)
        merged = io.BytesIO()
        merged_writer.write(merged)
        payload = merged.getvalue()
    return payload, width, height


def _matplotlib_setup():
    # Use a sane fixed epoch near the pinned source commit.  FontTools warns on
    # the Unix epoch because TrueType timestamps use a 1904-based date field.
    os.environ["SOURCE_DATE_EPOCH"] = "1667865600"
    logging.getLogger("fontTools.ttLib.tables._h_e_a_d").setLevel(logging.ERROR)
    import matplotlib

    matplotlib.use("pdf")
    from matplotlib import rcParams

    rcParams.update(
        {
            "font.family": "serif",
            "mathtext.fontset": "cm",
            "pdf.compression": 9,
            "pdf.fonttype": 42,
        }
    )
    from matplotlib.backends.backend_pdf import FigureCanvasPdf
    from matplotlib.figure import Figure

    return Figure, FigureCanvasPdf


def _save_figure(figure) -> bytes:
    output = io.BytesIO()
    figure.savefig(
        output,
        format="pdf",
        metadata={
            "Title": None,
            "Author": None,
            "Subject": None,
            "Keywords": None,
            "Creator": "recover_book_asy_graphics.py",
            "Producer": "Matplotlib",
            "CreationDate": None,
            "ModDate": None,
        },
    )
    return output.getvalue()


def localization_overlay_pdf(localization: str, width: float, height: float) -> bytes:
    Figure, FigureCanvasPdf = _matplotlib_setup()
    figure = Figure(figsize=(width / 72.0, height / 72.0))
    figure.patch.set_alpha(0)
    FigureCanvasPdf(figure)
    axis = figure.add_axes((0, 0, 1, 1))
    axis.set_xlim(0, width)
    axis.set_ylim(0, height)
    axis.axis("off")
    if localization == "cosine":
        axis.text(0.36, 36.36, "posisi", fontsize=10, ha="left", va="baseline")
        axis.text(34.0, 36.36, r"$x$", fontsize=10, ha="left", va="baseline")
        axis.text(170.0, 12.12, r"waktu $t$", fontsize=8.5, ha="left", va="baseline")
    elif localization == "spring":
        axis.text(0.1, 8.76, "pegas memanjang", fontsize=6.5, ha="left", va="baseline")
        axis.text(80.0, 3.72, "pegas memendek", fontsize=6.5, ha="left", va="baseline")
    else:
        raise ValueError(f"unknown localization profile: {localization}")
    return _save_figure(figure)


def innerproduct_complex_pdf() -> bytes:
    Figure, FigureCanvasPdf = _matplotlib_setup()
    figure = Figure(figsize=(4.0 / 2.54, 3.25 / 2.54))
    FigureCanvasPdf(figure)
    axis = figure.add_axes((0.05, 0.05, 0.92, 0.9))
    axis.set_xlim(-0.75, 7.7)
    axis.set_ylim(-2.65, 2.65)
    axis.set_aspect("equal", adjustable="box")
    axis.axis("off")
    gray = "#7f7f7f"
    axis.plot((-0.75, 5.5), (0, 0), color=gray, linewidth=0.7)
    axis.plot((0, 0), (-2.5, 2.5), color=gray, linewidth=0.7)
    axis.plot((4, 4), (0.0, -0.11), color=gray, linewidth=0.7)
    axis.plot((-0.11, 0.0), (2, 2), color=gray, linewidth=0.7)
    axis.scatter((4, 4), (2, -2), color="#4c4c4c", s=12, zorder=3)
    axis.text(4.18, 2.02, r"$z=a+bi$", fontsize=9, ha="left", va="center")
    axis.text(4.18, -2.02, r"$\overline{z}=a-bi$", fontsize=9, ha="left", va="center")
    axis.text(4.0, -0.23, r"$a$", fontsize=9, ha="center", va="top")
    axis.text(-0.18, 2.0, r"$b$", fontsize=9, ha="right", va="center")
    return _save_figure(figure)


def innerproduct_parallelogram_pdf() -> bytes:
    Figure, FigureCanvasPdf = _matplotlib_setup()
    figure = Figure(figsize=(4.0 / 2.54, 2.75 / 2.54))
    FigureCanvasPdf(figure)
    axis = figure.add_axes((0.04, 0.06, 0.92, 0.9))
    axis.set_xlim(-0.35, 7.55)
    axis.set_ylim(-0.65, 4.75)
    axis.set_aspect("equal", adjustable="box")
    axis.axis("off")
    v = (6.0, 0.0)
    w = (1.0, 4.0)
    gray = "#888888"
    axis.plot((w[0], v[0] + w[0]), (w[1], v[1] + w[1]), color=gray, linewidth=0.8)
    axis.plot((v[0], v[0] + w[0]), (v[1], v[1] + w[1]), color=gray, linewidth=0.8)
    arrow = dict(arrowstyle="-|>", color="#333333", lw=1.3, mutation_scale=8)
    axis.annotate("", xy=v, xytext=(0, 0), arrowprops=arrow)
    axis.annotate("", xy=w, xytext=(0, 0), arrowprops=arrow)
    axis.annotate("", xy=(v[0] + w[0], v[1] + w[1]), xytext=(0, 0), arrowprops=arrow)
    axis.annotate("", xy=v, xytext=w, arrowprops=arrow)
    axis.text(3.0, -0.24, r"$\vec{v}$", fontsize=9, ha="center", va="top")
    axis.text(0.25, 2.05, r"$\vec{w}$", fontsize=9, ha="right", va="center")
    axis.text(4.7, 3.05, r"$\vec{v}+\vec{w}$", fontsize=9, ha="center", va="bottom")
    axis.text(4.7, 1.5, r"$\vec{v}-\vec{w}$", fontsize=9, ha="left", va="center")
    return _save_figure(figure)


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


def validate_one_page_tree(payload: bytes, target: PurePosixPath):
    """Reject wrappers that permissive readers can render via broken-tree fallback."""
    reader = PdfReader(io.BytesIO(payload), strict=True)
    catalog = reader.trailer["/Root"].get_object()
    pages_reference = catalog.get("/Pages")
    if not isinstance(pages_reference, IndirectObject):
        raise ValueError(f"catalog /Pages is not indirect: {target}")
    pages = pages_reference.get_object()
    kids = pages.get("/Kids") or []
    if str(pages.get("/Type")) != "/Pages" or int(pages.get("/Count", -1)) != 1:
        raise ValueError(f"invalid one-page /Pages node: {target}")
    if len(kids) != 1 or not isinstance(kids[0], IndirectObject):
        raise ValueError(f"invalid one-page /Kids closure: {target}")
    page = kids[0].get_object()
    if not isinstance(page, DictionaryObject) or str(page.get("/Type")) != "/Page":
        raise ValueError(f"/Kids entry is not a page dictionary: {target}")
    parent = page.get("/Parent")
    if (
        not isinstance(parent, IndirectObject)
        or parent.idnum != pages_reference.idnum
        or parent.generation != pages_reference.generation
    ):
        raise ValueError(f"page /Parent does not point to the /Pages node: {target}")
    if "/MediaBox" not in page or "/Contents" not in page or "/Resources" not in page:
        raise ValueError(f"page lacks required wrapper keys: {target}")
    if len(reader.pages) != 1:
        raise ValueError(f"recovered figure is not one page: {target}")
    return reader, reader.pages[0]


def canonical_manifest(rows: list[dict[str, object]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=(
            "path",
            "method",
            "authority_page",
            "form_xobject",
            "source_asy",
            "source_asy_sha256",
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
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()

    authority_pdf = args.authority_pdf.resolve(strict=True)
    source_root = args.source_root.resolve(strict=True)
    output_root = args.output_root.resolve()
    manifest_path = args.manifest.resolve()
    if output_root == source_root or source_root in output_root.parents:
        raise ValueError("refusing to write recovered graphics into the source tree")
    if sha256_path(authority_pdf) != AUTHORITY_SHA256:
        raise ValueError("authority book PDF SHA-256 does not match the frozen artifact")
    discover_targets(source_root)

    reader = PdfReader(authority_pdf)
    if len(reader.pages) != 525:
        raise ValueError(f"expected 525 authority pages, found {len(reader.pages)}")

    rows: list[dict[str, object]] = []
    payloads: dict[PurePosixPath, tuple[bytes, str, int | str, str, str]] = {}
    for target, (page_number, form_name, localization) in FORM_SPECS.items():
        page = reader.pages[page_number - 1]
        xobjects = (page.get("/Resources") or {}).get("/XObject") or {}
        if form_name not in xobjects:
            raise ValueError(f"missing frozen form {form_name} on page {page_number}")
        reference = xobjects[form_name]
        payload, _, _ = extracted_pdf_bytes(
            reference, form_name, reference.get_object(), localization
        )
        method = "official_form" if localization is None else "official_form_localized"
        source_asy = "det/asy/ppiped.asy" if target.parts[0] == "det" else "jc/asy/wilber.asy"
        payloads[target] = (payload, method, page_number, form_name[1:], source_asy)

    payloads[PurePosixPath("jc/asy/innerproduct000.pdf")] = (
        innerproduct_complex_pdf(),
        "source_coordinate_reconstruction",
        "",
        "",
        "jc/asy/innerproduct.asy",
    )
    payloads[PurePosixPath("jc/asy/innerproduct001.pdf")] = (
        innerproduct_parallelogram_pdf(),
        "source_coordinate_reconstruction",
        "",
        "",
        "jc/asy/innerproduct.asy",
    )

    for target in EXPECTED_TARGETS:
        payload, method, page_number, form_name, source_asy = payloads[target]
        reopened, page = validate_one_page_tree(payload, target)
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        if width <= 0 or height <= 0:
            raise ValueError(f"recovered figure has invalid dimensions: {target}")
        output_path = output_root.joinpath(*target.parts)
        atomic_write(output_path, payload)
        source_path = source_root.joinpath(*PurePosixPath(source_asy).parts)
        rows.append(
            {
                "path": target.as_posix(),
                "method": method,
                "authority_page": page_number,
                "form_xobject": form_name,
                "source_asy": source_asy,
                "source_asy_sha256": sha256_path(source_path),
                "width_points": f"{width:.9f}".rstrip("0").rstrip("."),
                "height_points": f"{height:.9f}".rstrip("0").rstrip("."),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )

    manifest_payload = canonical_manifest(rows)
    atomic_write(manifest_path, manifest_payload)
    print(
        f"recovered={len(rows)} bytes={sum(int(row['bytes']) for row in rows)} "
        f"manifest_sha256={hashlib.sha256(manifest_payload).hexdigest()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
