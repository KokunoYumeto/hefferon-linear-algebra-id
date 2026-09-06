#!/usr/bin/env python3
"""Apply and verify the program-wide reader navigation contract.

This intentionally small, idempotent tool is copied into each repository in
this bounded batch.  It edits only that repository's configured GitHub Pages
source and fails closed for any unrecognised repository name.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MARKER = 'data-program-federated-nav="v1"'
CONFIG = {
    "functional-analysis-erdman-id": {
        "course": "D20",
        "original": "https://web.pdx.edu/~erdman/FAOA/functional_analysis_operator_algebras_pdf.pdf",
        "kind": "existing-nav",
        "roots": ["pages", "output/html", "output/html-companion"],
    },
    "hefferon-linear-algebra-id": {
        "course": "B40",
        "original": "https://hefferon.net/linearalgebra/",
        "kind": "body-nav",
        "roots": ["docs"],
    },
    "introduction-to-probability-id": {
        "course": "B90",
        "original": "https://math.dartmouth.edu/~prob/prob/prob.pdf",
        "kind": "probability-topbar",
        "roots": ["."],
    },
    "mathematical-computing-reproducible-experiments-en": {
        "course": "B80",
        "original": "https://kokunoyumeto.github.io/mathematical-computing-reproducible-experiments-id/",
        "kind": "quarto-header",
        "roots": ["docs"],
    },
    "mathematical-computing-reproducible-experiments-id": {
        "course": "B80",
        "original": "https://kokunoyumeto.github.io/mathematical-computing-reproducible-experiments-id/",
        "kind": "quarto-header",
        "roots": ["docs"],
    },
}


def hrefs(course: str) -> tuple[str, str]:
    base = "https://kokunoyumeto.github.io/program-matematika-indonesia"
    return f"{base}/id/#course-{course}", f"{base}/en/#course-{course}"


def style() -> str:
    return """<!-- program-federated-nav:style -->
<style id="program-federated-nav-style">
.program-federated-nav{display:flex;align-items:center;justify-content:center;flex-wrap:wrap;gap:.38rem;padding:.48rem .7rem;background:#10233f;color:#fff;border-block:3px solid #efb52b;font:700 .86rem/1.3 system-ui,-apple-system,Segoe UI,sans-serif;position:relative;z-index:2147483000}
.program-federated-nav a{display:inline-flex;align-items:center;min-height:2.25rem;padding:.36rem .62rem;border:1px solid rgba(255,255,255,.48);border-radius:.38rem;color:#fff!important;background:rgba(255,255,255,.08);text-decoration:none!important}
.program-federated-nav a:hover{background:rgba(255,255,255,.2)}
.program-federated-nav a:focus-visible{outline:3px solid #fff;outline-offset:2px}
@media(max-width:42rem){.program-federated-nav{font-size:.78rem;padding:.34rem}.program-federated-nav a{min-height:2rem;padding:.28rem .45rem}}
</style>"""


def nav(course: str, original: str, *, lang: str = "id") -> str:
    id_url, en_url = hrefs(course)
    if lang == "en":
        labels = ("Indonesian program", "English program", "Source edition")
        aria = "Course and source navigation"
    else:
        labels = ("Program Indonesia", "Program Inggris", "Sumber asli")
        aria = "Navigasi kursus dan sumber"
    return f"""<!-- program-federated-nav:start -->
<nav class="program-federated-nav" aria-label="{aria}" {MARKER}>
  <a href="{id_url}" rel="external noopener noreferrer">{labels[0]} · ID</a>
  <a href="{en_url}" rel="external noopener noreferrer">{labels[1]} · EN</a>
  <a href="{original}" rel="external noopener noreferrer">{labels[2]} ↗</a>
</nav>
<!-- program-federated-nav:end -->"""


def add_style(text: str) -> str:
    if 'id="program-federated-nav-style"' in text:
        return text
    if "</head>" not in text:
        raise RuntimeError("HTML has no closing head element")
    return text.replace("</head>", style() + "\n</head>", 1)


def patch_existing_nav(text: str, course: str, original: str) -> str:
    id_url, en_url = hrefs(course)
    if MARKER not in text:
        pattern = re.compile(r'<nav(?P<attrs>[^>]*aria-label="Navigasi lintas situs"[^>]*)>')
        match = pattern.search(text)
        if not match:
            raise RuntimeError("existing reciprocal navigation landmark not found")
        opening = match.group(0)[:-1] + f" {MARKER}>"
        text = text[: match.start()] + opening + text[match.end() :]
    if en_url not in text:
        original_anchor = re.search(
            rf'<a(?P<attrs>[^>]*href="{re.escape(original)}"[^>]*)>', text
        )
        if not original_anchor:
            raise RuntimeError("authoritative-original anchor not found")
        en_anchor = (
            f'<a class="site-header__link" href="{en_url}" '
            'rel="external noopener noreferrer">English program · D20</a>'
        )
        text = text[: original_anchor.start()] + en_anchor + text[original_anchor.start() :]
    if id_url not in text or original not in text:
        raise RuntimeError("existing navigation lacks required ID or original link")
    return text


def patch_body_nav(text: str, course: str, original: str, lang: str) -> str:
    if MARKER in text:
        return text
    text = add_style(text)
    match = re.search(r"<body(?:\s[^>]*)?>", text, re.I)
    if not match:
        raise RuntimeError("HTML has no body element")
    return text[: match.end()] + "\n" + nav(course, original, lang=lang) + text[match.end() :]


def patch_probability(text: str, course: str, original: str) -> str:
    if MARKER in text:
        return text
    id_url, en_url = hrefs(course)
    pattern = re.compile(
        rf'\s*<a class="curriculum-return" href="{re.escape(id_url)}".*?</a>',
        re.S,
    )
    match = pattern.search(text)
    if not match:
        raise RuntimeError("probability reader's existing curriculum link not found")
    replacement = f"""
      <!-- program-federated-nav:start -->
      <nav class="federated-nav" aria-label="Navigasi kursus dan sumber" {MARKER}>
        <a class="curriculum-return" href="{id_url}" rel="external noopener noreferrer" aria-label="Program Matematika Indonesia, kursus B90"><span aria-hidden="true">←</span><span class="curriculum-return-label">Program Indonesia</span><span class="curriculum-return-code">ID</span></a>
        <a class="curriculum-return" href="{en_url}" rel="external noopener noreferrer" aria-label="English mathematics program, course B90"><span class="curriculum-return-label">English program</span><span class="curriculum-return-code">EN</span></a>
        <a class="curriculum-return" href="{original}" rel="external noopener noreferrer" aria-label="Buku sumber resmi dalam bahasa Inggris"><span class="curriculum-return-label">Sumber asli</span><span class="curriculum-return-code">ORI</span></a>
      </nav>
      <!-- program-federated-nav:end -->"""
    return text[: match.start()] + replacement + text[match.end() :]


def patch_quarto(text: str, course: str, original: str, lang: str) -> str:
    if MARKER in text:
        return text
    text = add_style(text)
    needle = '<button type="button" class="btn quarto-search-button"'
    pos = text.find(needle)
    if pos < 0:
        raise RuntimeError("Quarto search-button insertion point not found")
    compact = nav(course, original, lang=lang).replace("\n", "")
    return text[:pos] + compact + "\n      " + text[pos:]


def html_files(config: dict[str, object]) -> list[Path]:
    files: set[Path] = set()
    for raw in config["roots"]:
        base = (ROOT / str(raw)).resolve()
        if ROOT.resolve() != base and ROOT.resolve() not in base.parents:
            raise RuntimeError(f"configured root escapes repository: {base}")
        files.update(path for path in base.rglob("*.html") if path.is_file())
    # For a main:/ Pages source, exclude known non-public HTML evidence trees.
    if ROOT.name == "introduction-to-probability-id":
        files = {ROOT / "index.html"}
    return sorted(files)


def normalize_private_author_metadata(files: list[Path], *, check: bool) -> None:
    """Keep the Indonesian B80 rebuild source and generated pages pseudonymous."""
    if ROOT.name != "mathematical-computing-reproducible-experiments-id":
        return
    expected = '<meta name="author" content="Program contributor">'
    for path in files:
        text = path.read_text(encoding="utf-8")
        updated, matches = re.subn(
            r'<meta name="author" content="[^"]*">', expected, text, count=1
        )
        if matches > 1:
            raise RuntimeError(f"unexpected duplicate generated author metadata in {path}")
        if check and matches == 1:
            if expected not in text:
                raise RuntimeError(f"pseudonymous author metadata missing in {path}")
        elif not check and updated != text:
            path.write_text(updated, encoding="utf-8", newline="")
    config_path = ROOT / "_quarto.yml"
    config_text = config_path.read_text(encoding="utf-8")
    updated, matches = re.subn(
        r'(?m)^  author:.*$', '  author: "Program contributor"', config_text, count=1
    )
    if matches != 1:
        raise RuntimeError("expected one Quarto author field")
    if check:
        if '  author: "Program contributor"' not in config_text:
            raise RuntimeError("pseudonymous Quarto author field missing")
    elif updated != config_text:
        config_path.write_text(updated, encoding="utf-8", newline="")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def refresh_reader_manifest(directory: Path) -> dict[str, object]:
    rows = []
    for path in sorted(
        (p for p in directory.rglob("*") if p.is_file() and p.name != "MANIFEST.csv"),
        key=lambda p: p.relative_to(directory).as_posix(),
    ):
        data = path.read_bytes()
        rows.append((path.relative_to(directory).as_posix(), len(data), sha256(data)))
    out = directory / "MANIFEST.csv"
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["path", "bytes", "sha256"])
        writer.writerows(rows)
    data = out.read_bytes()
    return {
        "manifested_files": len(rows),
        "manifested_bytes": sum(row[1] for row in rows),
        "manifest_bytes": len(data),
        "manifest_sha256": sha256(data),
    }


def refresh_functional_analysis_manifests() -> None:
    reader_specs = (
        ("source_reader", ROOT / "output/html", "output/html/"),
        ("companion_reader", ROOT / "output/html-companion", "output/html-companion/"),
    )
    readers = []
    for role, directory, prefix in reader_specs:
        values = refresh_reader_manifest(directory)
        readers.append({"role": role, "public_prefix": prefix, **values})
    metadata_path = ROOT / "pages/PAGES_DEPLOYMENT_METADATA.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["readers"] = readers
    metadata.setdefault("reciprocal_navigation", {})["curriculum_en"] = hrefs("D20")[1]
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    build_dir = ROOT / "qa/pages-build-federated-nav"
    replay_dir = ROOT / "qa/pages-build-federated-nav-replay"
    validation_report = ROOT / "qa/pages-build-federated-nav-validation.json"
    try:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "qa/build_github_pages_payload.py"),
                "--output",
                str(build_dir),
                "--manifest-copy",
                str(ROOT / "qa/GITHUB_PAGES_PUBLIC_MANIFEST.csv"),
            ],
            check=True,
        )
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "qa/build_github_pages_payload.py"),
                "--output",
                str(replay_dir),
            ],
            check=True,
        )
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "qa/validate_github_pages_payload.py"),
                "--payload",
                str(build_dir),
                "--compare",
                str(replay_dir),
                "--expected-manifest",
                str(ROOT / "qa/GITHUB_PAGES_PUBLIC_MANIFEST.csv"),
                "--report",
                str(validation_report),
            ],
            check=True,
        )
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        shutil.rmtree(replay_dir, ignore_errors=True)
        validation_report.unlink(missing_ok=True)


def validate(files: list[Path], course: str, original: str) -> dict[str, object]:
    id_url, en_url = hrefs(course)
    rows = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        counts = {
            "marker": text.count(MARKER),
            "id": text.count(id_url),
            "en": text.count(en_url),
            "original": text.count(original),
        }
        if counts["marker"] != 1 or any(counts[name] < 1 for name in ("id", "en", "original")):
            raise RuntimeError(f"navigation validation failed for {path}: {counts}")
        if "<nav" not in text or "aria-label=" not in text:
            raise RuntimeError(f"accessible navigation landmark missing in {path}")
        data = path.read_bytes()
        rows.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": len(data),
                "sha256": sha256(data),
                "link_counts": counts,
            }
        )
    return {
        "repository": ROOT.name,
        "course_id": course,
        "html_documents": len(rows),
        "published_root": CONFIG[ROOT.name]["roots"],
        "id_course_url": id_url,
        "en_course_url": en_url,
        "authoritative_original_url": original,
        "documents": rows,
        "status": "pass",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if ROOT.name not in CONFIG:
        raise RuntimeError(f"unrecognised repository: {ROOT.name}")
    config = CONFIG[ROOT.name]
    files = html_files(config)
    if not files:
        raise RuntimeError("no published HTML documents found")
    normalize_private_author_metadata(files, check=args.check)
    if not args.check:
        for path in files:
            text = path.read_text(encoding="utf-8")
            lang = "en" if '<html xmlns="http://www.w3.org/1999/xhtml" lang="en"' in text else "id"
            kind = config["kind"]
            if kind == "existing-nav":
                patched = patch_existing_nav(text, str(config["course"]), str(config["original"]))
            elif kind == "body-nav":
                patched = patch_body_nav(text, str(config["course"]), str(config["original"]), lang)
            elif kind == "probability-topbar":
                patched = patch_probability(text, str(config["course"]), str(config["original"]))
            elif kind == "quarto-header":
                patched = patch_quarto(text, str(config["course"]), str(config["original"]), lang)
            else:
                raise RuntimeError(f"unsupported patch kind: {kind}")
            path.write_text(patched, encoding="utf-8", newline="")
        if ROOT.name == "functional-analysis-erdman-id":
            refresh_functional_analysis_manifests()
    report = validate(files, str(config["course"]), str(config["original"]))
    if args.report:
        destination = args.report if args.report.is_absolute() else ROOT / args.report
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({key: report[key] for key in ("repository", "html_documents", "status")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
