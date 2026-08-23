# Hefferon Modular Backend

Status: active complete-corpus projection for R005.

Schema hefferon-modular-backend version 0.5.2 indexes the complete active
source closure of three reader surfaces:

- src/book.tex, including the full textbook and every inline answer;
- src/jhanswer.tex, the answer-book shell whose generated body is supplied
  by those inline answers; and
- src/lab/lab.tex, the Sage lab, its localized listings, code, data, media,
  and build dependencies.

The closure is discovered from active LaTeX include and input commands rather
than a translation cursor or a hard-coded chapter list. File IDs derive from
upstream paths; semantic IDs prefer native LaTeX labels and otherwise use
source order. Neither depends on Indonesian titles, rendered pages, or target
wording. Source units and concepts retain those locale-neutral IDs across
languages; derivative editions, programs, courses, localized terms, and target
artifacts are explicitly locale-scoped, preventing id-ID/zh-CN merge
collisions. Chapters, sections, subsections, mathematical environments, tables,
code/interactive blocks, exercise groups, numbered exercises, inline answers,
and unnumbered exercise rubrics retain hierarchy, source order, exact locators,
and paired source/target hashes.

build_index.py fails closed before writing if the source and target include
closures, heading topology, mathematical environments, exercise/answer
topology, labels, ledger schemas/IDs, parent/relation endpoints, serialization,
or input-byte stability diverge. It rereads every consumed authority, target,
asset, ledger, official-PDF, and builder byte immediately before atomic output.
JSON/JSONL/CSV projections are canonical UTF-8 with LF line endings and are
round-trip validated. A second identical run must reproduce the manifest hash.
`validate_backend.py` independently replays the manifest and verifies entity,
field, state, topology, rights, segment-hash, and exercise-answer invariants
without importing the generator.

Workflow `hefferon-id.complete-corpus-index.v7` retains schema 0.5.2 because
the interchange entity contract is unchanged. The workflow revision records a
materially stronger final-build admission rule: both generator and independent
validator bind the live build report, cross-PDF link audit, and SageTeX runtime
manifest by exact path, byte count, SHA-256, and semantic counts; the validator
also reopens all three live reader PDFs and verifies their report/artifact path,
byte count, SHA-256, and independently parsed page count. Zero runtime-placeholder
and SageTeX/PythonTeX closure are replayed from the live receipts when
`--require-final-build` is used.

The backend exports:

- resource, edition, program, and course authority;
- ordered unit hierarchy and dependency/xref topology;
- paired translatable segments;
- terminology-derived locale-neutral concepts and localized terms;
- all native exercise items and 1,035 upstream inline answers, plus two
  locale-scoped Indonesian-edition-supplied answers authorized by HLA-A0300,
  each with a normal typed `answers` link, derivative-edition relation binding,
  and explicit non-upstream provenance;
- figures, media, source code, data, local build dependencies, and explicit
  placeholders for external or build-generated dependencies absent from the
  repository snapshot;
- the selected CC BY-SA 2.5 derivative route plus component-level LPPL,
  GPL-2, GPL-3, Proggy permissive, OFL-1.1, CC0, unresolved third-party,
  unlicensed embedded-subtree, and external-toolchain rights;
- every live terminology and adverse-ledger row, with affected closure records
  where the ledger supplies an admitted locator;
- typed QA events, source/backend snapshots, expected or built target outputs,
  and the three URL/page/hash-bound official upstream comparison PDFs; and
- source_closure.json plus manifest.json for deterministic replay.

When `build/hefferon_id/build_report.json` is a successful report bound to the
current complete target tree, the generator independently rechecks the three
PDF bytes and admits their hashes, page counts, toolchain, cross-PDF-link gate,
and reproducibility receipt. A failed, stale, or absent report cannot be
mistaken for a built artifact.

Known upstream gaps are data, not suppressed failures: two Leontief exercises
have no answer in the pinned source or official answer book. The Indonesian
edition closes both deliverable links with independently derived, verified
answers whose unit and segment IDs are locale-scoped and whose provenance is
`indonesian_edition_supplied`; they are not represented as translated upstream
answers. Corrections whose evidence names source outside the active build
closure retain their exact ledger locator instead of receiving a false unit
mapping; external TeX packages and unmaterialized generated graphics remain
explicit dependency assets; and a full TeX/Sage build is intentionally not run
by this backend-only generator.

Regenerate from the lane root with:

    python -B backend/build_index.py

Independently validate the current projection with:

    python -B backend/validate_backend.py

For the publication gate, additionally require three PDFs and a matched second
build fingerprint:

    python -B backend/validate_backend.py --require-final-build

Generated projections:

- authority.jsonl
- programs.jsonl
- courses.jsonl
- units.jsonl
- segments.jsonl
- concepts.jsonl
- terminology.jsonl
- assets.jsonl
- rights.jsonl
- corrections.jsonl
- relations.csv
- qa_events.jsonl
- artifacts.jsonl
- source_closure.json
- interoperability.json
- manifest.json
