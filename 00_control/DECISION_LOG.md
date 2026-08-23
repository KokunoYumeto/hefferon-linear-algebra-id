# Decision Log — Hefferon Linear Algebra id-ID

## HLA-D0001 — Corpus boundary

Date: 2026-08-20
Status: admitted

The lane covers the complete Hefferon textbook, worked-answer book, and relevant
Sage material. It does not coordinate other curriculum tasks.

## HLA-D0002 — Translation and backend run together

Date: 2026-08-20
Status: admitted

Translation remains dominant. Machine indexing is additive and developed beside
each translated unit, not as a long pre-translation architecture exercise.

## HLA-D0003 — Authority meaning of “freeze”

Date: 2026-08-20
Status: admitted

Freeze binds exact upstream bytes, edition identity, rights, and baseline build
for reproducibility. It does not prevent better indexing, identifiers, tooling,
or separately logged corrections in the derivative.

## HLA-D0004 — License selection

Date: 2026-08-20
Status: admitted

The pinned repository LICENSE offers GFDL or CC BY-SA 2.5. Select CC BY-SA 2.5
for the Indonesian text/source derivative. Preserve attribution, change notice,
ShareAlike, source/license links, and non-endorsement. Track separately licensed
code/fonts/assets at component level rather than flattening the repository.

## HLA-D0005 — Generated archives are retrieval receipts

Date: 2026-08-20
Status: admitted

Two official GitLab ZIP routes returned different bytes for the same commit.
Canonical source identity is commit + tree + per-file hashes. Archive byte hashes
remain exact retrieval receipts and are never promoted to edition identity.

## HLA-D0006 — First modular unit boundary

Date: 2026-08-20
Status: admitted

The complete `src/pref/pref.tex` is stable unit
`r005.hefferon-linear-algebra.unit.frontmatter.preface`. Its 31 active LaTeX
blocks are stable source–target segment IDs. Neither the unit nor segment IDs
depend on localized titles or page numbers.

## HLA-D0007 — Locale-specific range anchors

Date: 2026-08-20
Status: admitted

Source and target prose anchors may differ after translation. The backend
therefore stores and validates separate exact source/target range markers while
retaining one locale-neutral unit ID. This prevents localized wording from
weakening deterministic range identity.

## HLA-D0008 — Chapter 1 contiguous exercise boundary

Date: 2026-08-20
Status: admitted

The third Chapter 1 range begins at the first `Solve each system` exercise
(target: `Selesaikan setiap sistem`) and ends immediately before the stable
label `ex:ProveGaussMethod`. It includes every intervening exercise and inline
worked answer in native order; no answer-book linkage is split across units.

## HLA-D0009 — Structural brace validation excludes escaped delimiters

Date: 2026-08-20
Status: admitted

The backend's brace-balance gate counts only grouping braces. LaTeX delimiter
tokens `\{` and `\}` are printable symbols, not group boundaries, so the
validator removes those exact escaped tokens before counting. This permits the
upstream `\left\{ ... \right.` construction without weakening ordinary command
group validation.

## HLA-D0010 — Relation IDs include semantic unit scope

Date: 2026-08-20
Status: admitted

Every relation ID must be unique across the edition. Frontmatter and answer-book
units may share native filenames such as `cover` or `preface`, so relation IDs
include their complete semantic unit scope (`frontmatter-cover`,
`answers-cover`, and so on). This keeps all endpoints stable without deriving
identity from localized titles.

## HLA-D0011 — General/particular/homogeneous range boundaries

Date: 2026-08-20
Status: admitted

The subsection is segmented at proof-complete conceptual boundaries. Part 001
contains the theorem, homogeneous-system exposition, first spanning lemma,
induction walk-through, and its proof. Part 002 contains generated spans, the
particular-plus-homogeneous set-equality lemma and proof, two examples, and the
three-cardinalities corollary and proof. Each boundary is contiguous and uses
separate source/target prose anchors while retaining locale-neutral unit IDs.

## HLA-D0012 — Admitted source closure excludes unrelated teaching archives

Date: 2026-08-21
Status: admitted

The edition covers the complete textbook, its inline complete worked answers
and separately compiled answer book, the full published Sage lab, and the
reader-distributed Sage/Python sources used by that lab. Upstream homework
archives, old examinations, question banks, slide decks, vendor font sources,
and dormant developer test copies are preserved as upstream material but are
not represented as translated reader content. Publication metadata must name
this boundary rather than imply that every auxiliary repository file was
translated.

## HLA-D0013 — Pinned lab figures may be recovered from the official PDF

Date: 2026-08-21
Status: admitted

Native Sage is unavailable on the Windows host, but the pinned 105-page
official lab PDF embeds the 64 generated PDF figures as discrete vector Form
XObjects in the same document order as the active source references. A bounded
tool may recover those forms into a staging tree after verifying the official
PDF SHA-256, exact 64-target source order, exact XObject closure, one-page PDF
validity, and a deterministic manifest. Recovered figures never overwrite the
translated source and are disclosed as pinned official generated assets.

## HLA-D0014 — Seven book Asymptote figures use a bounded staged recovery path

Date: 2026-08-21
Status: admitted

The local MiKTeX Asymptote 3.06 process does not complete reliably on this
Windows host. Five of the seven active Asymptote-produced book figures are
embedded as discrete vector Form XObjects in the pinned official textbook PDF.
The staging tool therefore recovers those five forms after validating the
official PDF hash, page count, exact page/XObject mapping, dimensions, and
one-page closure. Two Wilberforce forms replace only their terminal English
text-label layer with Indonesian labels. The official PDF predates the active
Inner Product topic, so its two simple 2-D figures are reconstructed
deterministically from the exact coordinates, vectors, labels, and geometry in
the pinned `jc/asy/innerproduct.asy`. Generated PDFs are written only to the
staging tree. Two independent runs must have one identical canonical manifest,
and every result must be visually inspected before use.

## HLA-D0015 — Reader-visible generator labels are translation content

Date: 2026-08-21
Status: admitted

Text embedded by active MetaPost and Asymptote figure generators is part of the
reader-facing corpus even when it is not present in a TeX prose file. Only
generator blocks reached by active `\includegraphics` calls are in the release
localization gate. Their natural-language labels are translated while geometry,
mathematical notation, SI units, proper place names, stable code identifiers,
and unused/dormant generator blocks remain unchanged. Final PDF text and visual
QA must verify the generated label layer rather than relying on a source-prose
scan alone.

## HLA-D0016 — Execute Sage natively, then restore the pinned figure witness

Date: 2026-08-21
Status: admitted

The lab build executes PythonTeX and all 148 SageTeX command blocks in the
disposable staging tree under Ubuntu 22.04 WSL, SageMath 9.5, and the SageTeX
3.6.1 distribution with a fixed random seed, epoch, and timezone. The installed
3.6.1 Python distribution exposes the historical internal version string
`2021/10/16 v3.6`, while the current TeX package emits
`2022/08/21 v3.6.1`; therefore only the strict string check in a generated
staging copy is disabled, with both programs and hashes recorded. The canonical
translated source is not patched.

Native execution must produce the exact `@sagecmdline0` through
`@sagecmdline147` closure. It is also expected to overwrite 63 of the 64 lab
figure PDFs, leaving only `asy/ellipsoid1.pdf` unchanged. Those side effects are
audited, then all 64 figures are restored byte-for-byte from the already
verified pinned-authority extraction before final TeX passes. Thus real code
execution supplies the command output, while the published figure layer remains
the frozen official visual witness admitted in HLA-D0013.

## HLA-D0017 — Reflow the Indonesian notation table within the text block

Date: 2026-08-21
Status: admitted pending final visual confirmation

The natural Indonesian descriptions in `src/cover/symlist.tex` are longer than
the English source and produced the open HLA-A0006 overflow (83.26 pt in the
textbook and 59.69 pt in the answer book). Preserve every notation/description
pair and order, but replace the unbreakable natural-width `r|l` table with two
paragraph columns occupying 36% and 56% of `\textwidth`, right-aligned on the
notation side and ragged-right on the explanation side. This is a derivative
layout-only reflow; it does not alter mathematical or linguistic content. Close
HLA-A0006 only after both reader PDFs visibly confirm the repaired page.

## HLA-D0018 — Recompute publication evidence from live bound fields

Date: 2026-08-22
Status: admitted

Publication readiness may not accept two mutually consistent but falsified
runtime witnesses. The release driver therefore verifies the exact Sage and
PythonTeX deterministic controls against the pinned build contract, rebuilds
the reproducibility-v2 projection directly from the live build report, and
recomputes its canonical SHA-256 before comparing it with the external
baseline. Cross-PDF and SageTeX sidecars remain byte/hash-bound to the report.
This is a fail-closed release gate; it does not alter translated source or PDF
content.

## HLA-D0019 — Backend final-build validation replays live receipts

Date: 2026-08-22
Status: admitted

Schema 0.5.2 remains the interchange contract, while workflow
`hefferon-id.complete-corpus-index.v7` records a stricter evidence policy.
The generator and independent validator must bind and semantically replay the
live successful build report, cross-PDF link sidecar, SageTeX runtime sidecar,
and all three reader PDFs. Exact paths, byte counts, lowercase SHA-256 values,
independently parsed page counts, zero runtime placeholders, reciprocal answer
links, and SageTeX/PythonTeX closure are mandatory. Serialized backend claims
alone are insufficient for `--require-final-build`.

## HLA-D0020 — Publication requires complete visual-review dispositions

Date: 2026-08-22
Status: admitted

Automated all-page rendering is necessary but does not itself establish a
reader-ready layout. Strict publication readiness must bind the generated
`qa/final_pdf_qa.json` to the live build/PDF/render bytes with zero hard
failures, then require a separate `qa/final_visual_review.json`. That receipt
must cover every page through verified contact-sheet ranges, dispose every
automated review finding and ranked candidate exactly once, bind targeted
full-page inspections to their manifest PNGs, include at least one target in
each PDF, and leave zero unresolved findings. No receipt may be generated until
the actual visual inspection has occurred.

## HLA-D0021 — Tool identity must not be recorded as a CLI error

Date: 2026-08-22
Status: admitted

The generic `--version` probe is invalid for MiKTeX `makeindex` and Poppler
`pdftoppm`. Use `pdftoppm -v`; because the installed `makeindex` exposes no
version flag, record its exact executable byte count and SHA-256 instead. A
clean build whose reproducibility fingerprint contains an error string in a
tool-version field is not final evidence even when its reader PDFs compile.
Changing this probe changes the builder hash, so both clean builds and their
baseline must restart.

## HLA-D0022 — Accept the corrected-provenance baseline only as run one

Date: 2026-08-22
Status: admitted

The first clean run with builder
`99255760f702d64e45a526251a28b4ce8339c2aa2ee1b5410aaa00fee0dbddf0`
completed from the unchanged final source tree
`f5d5d1a7920f7add9c6dfb141cd6c4af79231f4d0ad00f8ca4f178e770f3c315`.
Its tool-identity fields contain no error strings: Poppler is recorded through
`pdftoppm -v`, while `makeindex.exe` is bound by 169,472 bytes and SHA-256
`a3f0a55e8a1333a54e7c90b6ae2f19cabe81d4ede8a6c690a085a9b6ba4c20d4`.
The resulting v2 baseline is 3,897 bytes with SHA-256
`fc359ecfc5f356501297efc92baf78799519ccb5ed53967de35ab47a900924b0`.

This evidence is accepted only as the first member of the clean pair. A second
complete clean run must match that baseline exactly before backend generation,
final PDF audit, packaging, or publication can proceed. The 57 first-run
contact sheets were copied byte-for-byte into a task-local QA witness so their
visual review can overlap the repeat build; they are usable as final evidence
only if the repeat run proves identical PDF and render fingerprints.

## HLA-D0023 — Bind the edition's pdfTeX font maps locally

Date: 2026-08-22
Status: admitted

The system-generated MiKTeX `pdftex.map` changed between the textbook and
answer-book processes, after the textbook had already loaded its earlier map.
The next process therefore treated Concrete `ecssdc10` and Bera `fvmr8r` as
bitmap fonts; microtype first failed on the notation page and a later diagnostic
attempt failed at final font embedding. Shared MiKTeX state is not an edition
authority and must not be repaired or mutated by this lane.

The edition now explicitly adds `cm-super-t1.map`, `cm-super-ts1.map`,
`bera.map`, `ugq.map`, and `pbsi.map` under pdfTeX. The builder independently
resolves and fail-closes 23 directly used map, encoding, and Type 1 font files by
name, byte count, and SHA-256, copies all 1,594,916 verified bytes into its
task-local TeX tree, places that tree first in the map/encoding/Type-1 search
paths, and includes the path-neutral dependency projection in a v3
reproducibility fingerprint. A full 435-page answer-book diagnostic then
completed, with the scalable Concrete and Bera fonts restored. Its one Type 3
font is inherited inside the pinned `map/pix/bridges.pdf` graphic on reader page
299; the page is centered, intact, and readable at 144 dpi and is not a generated
body-text fallback.

This source and builder change invalidates v2 baseline SHA-256
`fc359ecfc5f356501297efc92baf78799519ccb5ed53967de35ab47a900924b0`.
Both complete clean builds restart from the new source and v3 builder; no prior
PDF or render witness is final evidence for the changed bytes.

## HLA-D0024 — Vendor the exact pdfTeX font-program closure

Date: 2026-08-22
Status: admitted

Resolving the 23 pinned font files through a mutable host TeX installation is
not a sufficient offline or reproducibility boundary, even when each resolved
byte is checked before compilation. The edition therefore preserves the exact
unchanged map, encoding, and Type 1 font-program bytes under
`tools/pdftex-font-closure/`, together with component-specific notices,
provenance material, a machine-readable rights inventory, and a complete
non-self SHA-256 manifest. The CM-Super source payload is retained as provenance
and corresponding-source support; it is not described as an independently
reproducible exact-PFB generation tree.

The builder now reads only these repository-owned paths for the pinned set,
checks their admitted byte counts and SHA-256 values before staging, validates
the closure inventory and notices, and proves both the staged files and the live
repository closure unchanged at build end. `kpsewhich` is no longer used to
resolve these files or recorded as a build tool. This changes the v3 fingerprint
projection, so no run started before this decision can be accepted as either
member of the final reproducibility pair.

## HLA-D0025 — Replace the partial v3 boundary with a fail-closed v4 build

Date: 2026-08-22
Status: admitted; supersedes HLA-D0023/D0024 only where their closure claims
were narrower

The second complete v3 run correctly failed its exact-baseline gate. Relative
to the accepted first run, only `book.pdf` changed by 13 bytes and SHA-256 and
`jhanswer.pdf` changed SHA-256 at the same byte count; `lab.pdf` and every other
v3 fingerprint field matched. The failed report, second-run readers, an
additional byte-identical textbook pass, and the first-run baseline are retained
under `tmp/repro_diagnostic_20260822/`. They are diagnostic evidence, not
release candidates.

The investigation proved that the five `\pdfmapfile{+...}` directives did not
replace pdfTeX's default map: the mutable host `pdftex.map` loaded first, and 27
actually embedded Type 1 programs still came from host MiKTeX. It also proved
that the builder generated 307 numeric-suffix MetaPost assets but fingerprinted
only seven `.1` files, and that the generated answer stream and TeX convergence
intermediates were not members of the v3 baseline. The host map is therefore an
unadmitted input even though its timestamp does not prove that it caused this
particular two-run difference.

The v4 boundary loads repository-owned `hefferon-standard.map` first without a
modifier, so the default host map is not read, then appends the five component
maps. Map, encoding, and Type 1 search paths are private-only. The exact runtime
closure is 51 files / 2,289,616 bytes and includes all 27 formerly external font
programs. Those bytes match retained official CTAN distributions for AMSFonts
3.04, RSFS, and URW Base 35, with component notices and authority archives. The
complete closure is 73 files / 10,325,900 bytes / canonical tree SHA-256
`542e2566a14b473654387a8a263cc1d49392e35db7058880d56f95cc6059ce56`.

Every pdfTeX process now writes a recorder file. The builder rejects any map,
encoding, PFB, or PFA outside the private tree and fingerprints the exact TFM/VF
metric bytes it observed. MetaPost is invoked through a staging-only wrapper
with explicit `randomseed := 1`, which is equivalent to the prior fixed
`SOURCE_DATE_EPOCH` seed and reproduces the existing geometry. All 307 outputs
are inventoried. The textbook and answer book each receive a dedicated extra
pass that must leave the PDF, answer stream, index, table/navigation files, and
all auxiliary files byte-identical; pdfTeX's time-seeded trailer ID is omitted.

The style-only source change does not alter mathematical or reader-visible
content. It changes the canonical source tree to
`5c161ff7584a281156094bcebf4a78b5ec5d2ff98c362dc21c0c26c386093f5a`.
The v3 baseline is permanently ineligible for v4. Two fresh complete clean v4
builds must be identical before any final backend, QA, package, or publication
claim.

## HLA-D0026 — Bind the final index and published offline inputs

Date: 2026-08-22
Status: admitted before either final v4 build

The first v4 convergence implementation proved that textbook passes 5 and 6
were byte-identical, but `makeindex` had run only after pass 1. That could admit
a TeX fixed point whose `book.ind` was stale relative to the final `book.idx`.
The final contract now refreshes the index after pass 5, runs textbook pass 6,
reruns `makeindex`, requires the exact `book.idx`/`book.ind` pair to remain
unchanged, and then requires pass 7 to leave the full PDF/index/answer/auxiliary
state byte-identical. The publication driver independently reconstructs this
index fixed-point record.

Publication also rehashes the five live repository build tools, all 51 runtime
font dependencies, the complete 73-file font closure, and both authority PDFs
against the matched build report. The editable-source ZIP, immutable staging
snapshot, and GitHub repository snapshot each include
`authority/official/book.pdf` and `authority/official/lab.pdf`, because the
offline builder requires those exact inputs to recover 71 pinned graphics.
The release must fail if any of these live bytes differ from the two-build
fingerprint; a bundle that cannot execute its advertised offline build is not
eligible for publication.

## HLA-D0027 — Select official stable PDF siblings for answer-only graphics

Date: 2026-08-22
Status: admitted; invalidates the former v4 baseline

The second clean-build comparison proved that only `jhanswer.pdf` varied. Two
answer environments requested `learn5.eps` and `ws.eps`; MiKTeX's implicit
conversion injected wall-clock dates, XMP UUIDs, and trailer IDs on every run.
The pinned official source already contains visually equivalent PDF siblings
for both graphics. The Indonesian source now requests those exact supplied PDF
bytes directly. This is smaller and more auditable than rewriting generated
PDF metadata, preserves the mathematical graphic and geometry, and removes the
volatile converter from the dependency path. Tests bind the two official PDF
byte counts and SHA-256 values. A new two-build baseline pair is mandatory.

## HLA-D0028 — Admit three local reader-reflow repairs

Date: 2026-08-22
Status: admitted; content-preserving target-edition corrections

Full-corpus visual review found one clipped textbook topic opener and inherited
answer-book presentation defects. The Fields topic's Indonesian reflow pushed
an unbreakable table forward while `\flushbottom` over-stretched elastic topic
spacing, placing its heading outside the page. An explicit
`\par\vfill\pagebreak` before that table assigns the underfill deliberately.
The answer-topic override's `\thispagestyle{empty}` attached to whichever page
was active when a topic began, suppressing headers and folios inconsistently;
removing it restores the global answer-book furniture without changing flow.
Two short Octave listings that split across leaves are wrapped in local
minipages so each moves intact. These repairs alter no mathematical statement,
notation, code, exercise, or solution and are bound by focused source-contract
tests plus full-size post-build inspection.

## HLA-D0029 — Preserve one Zenodo concept lineage across checkpoints

Date: 2026-08-22
Status: admitted before remote preflight

Zenodo is the active preservation channel while GitHub is suspended, but a
fresh-deposition fallback could create a competing concept when an older public
checkpoint exists under a related title. The isolated Zenodo route now searches
authenticated deposits and public records using the work title, creator, and
source markers. An exact deposition resumes. One proved existing concept with
no target version advances only through the latest version's
`actions/newversion`, follows `links.latest_draft`, and pins the concept DOI/ID,
parent deposition ID, and parent record DOI/ID separately. Ambiguous, unowned,
or mismatched concepts fail closed. Only proved absence permits one fresh
concept. A lost action response is recovered from `latest_draft` without
reposting. The 105-test publication suite passes, and Zenodo-only routes remain
incapable of constructing a GitHub client.
