# Build and QA Log — Hefferon Linear Algebra id-ID

## 2026-08-21T22:47:07+02:00 — first post-answer full-build attempt

- Canonical translated source closure at build start: 858 files,
  53,980,562 bytes, canonical tree SHA-256
  `b033f9ceab32e7c1ebc975fb73da1d63bec134aa3f3119de948168b9505ac172`.
- Builder SHA-256:
  `ce7b515a750ca1ab38e0b426647914e9eb155ded125a9574420f41366b2b7672`.
- The generated answer-stream gate passed with 1,032 compiled answers in total
  and 133 answers under the 24 topical divisions: 131 native topical answers
  plus the two Indonesian-edition-supplied answers authorized by HLA-A0300.
- All three PDFs compiled and every page rendered nonempty:
  - textbook: 578 pages, 8,981,221 bytes,
    SHA-256 `77c48dde8ca3d1eba5952a4e8a483a43d0c30071bbd953559118a375b1f2704d`;
  - worked answers: 433 pages, 2,668,432 bytes,
    SHA-256 `3b9f0d442d8334a3c31af1e59b4ab889f3ada28963bb588e7e2cc7460b0c5bfb`;
  - Sage lab: 73 pages, 13,103,630 bytes,
    SHA-256 `47b715d1bd89f154e64703f4a6f6c9aee7b9cf3abffe9a9dfd8071c89653a316`.
- Cross-PDF audit passed: 2,064 GoToR actions, 1,032 book-to-answer and
  1,032 answer-to-book, zero unresolved; audit SHA-256
  `4bc6c95a6260ef8aac64edfa48e930eb417545ce7e5e320114582bb14390f6ab`.
- Generated English structural-label hits: zero.
- The run correctly failed the final reference gate. The textbook and answer
  book have zero undefined-reference diagnostics. The lab has 148 undefined
  `@sagecmdline0` through `@sagecmdline147` labels plus the aggregate warning.
  This is substantive: the build omitted the source-native SageTeX execution,
  so the command blocks are unresolved placeholders and the lab is only 73
  pages versus the 105-page official witness.
- Failed build report: 90,741 bytes, SHA-256
  `ab8ddc83f05c68bde9a0de47b6a3164f9cd080f85d5a609b58ee8dd87157a5c1`.

Disposition: do not baseline, package, or publish these PDFs. WSL2 Ubuntu 22.04
and SageMath 9.5 are being installed as a bounded toolchain so the generated
`lab.sagetex.sage` can produce real command output. The builder must then run
PythonTeX and SageTeX in staging, verify the generated-output closure, compile
all three PDFs twice from clean staging, and require an exact second-run
reproducibility match.

## 2026-08-21T22:47:07+02:00 — provisional backend checkpoint

- Schema `0.5.2`; normal validator passes.
- Manifest SHA-256:
  `9faa2393a7036afd79a0e541a2ef4031f32589699b27637376464eb553d944c2`.
- 1,037 exercises, 1,037 answer relations, zero unanswered exercises.
- 1,035 answers are native upstream answers; exactly two are explicitly
  `indonesian_edition_supplied`, bound to HLA-A0300 and derivative edition
  `r005.hefferon-linear-algebra.edition.derivative.locale.id-id.df2262e`.
- The six relations touching those supplied-answer entities are derivative
  scoped. The derivative edition and three PDF artifacts use the mandated
  `.locale.id-id` identity segment.
- Final-build validation remains intentionally ineligible (`build_result` is
  `not_run`) until two successful reproducible builds exist.

## 2026-08-21T23:05:00+02:00 — deterministic SageTeX integration checkpoint

- Installed and pinned runtime: Ubuntu 22.04 WSL, SageMath 9.5, SageTeX PyPI
  distribution 3.6.1. The package exposes internal module version
  `2021/10/16 v3.6`; the generated TeX program declares
  `2022/08/21 v3.6.1`. Only the strict string check is disabled in a disposable
  generated copy; the canonical translated source remains unchanged.
- The staging runner fixes random seed `20260821`, `SOURCE_DATE_EPOCH`
  `1633046400`, and timezone `UTC`.
- Two consecutive complete integration runs matched exactly. Each produced
  labels `@sagecmdline0` through `@sagecmdline147`, with no missing or duplicate
  index. Output hashes:
  - `lab.sagetex.sout`:
    `2f3c4b976d829fb1842302b1ddc41cf9d3ee134167379e1030d4335888e979a1`;
  - `lab.sagetex.scmd`:
    `26d5db4f18d4beaee923520dad841e0218502ca700dbdb5260061f09a70f282c`.
- Native Sage execution changed exactly 63 of the 64 expected figure targets;
  only `asy/ellipsoid1.pdf` remained identical. The runner then restored and
  rehashed all 64 pinned official figures. Both the stable runtime fingerprint
  and raw generated-figure inventory matched across the two executions.
- Runtime manifest SHA-256:
  `ed274065b71aa08c324ca1c0b8375f5b4161c950e54688f7160e4e2ad939f3cf`.
- Production builder SHA-256:
  `b7d0e9b3db37b44b9d33eb05bab32f0818ed40eb2211d8c9238193a237f22154`.
  Sage runner SHA-256:
  `e39b20613783cffb475000ad13b6d4cd28cebf6a602b059a8a33536cbcd523b7`.

Disposition: integration gate passes. Start two full builds from clean staging;
do not reuse the earlier rejected 73-page lab.

## 2026-08-21T23:30:09+02:00 — first clean-pair attempt rejected before Sage

- The builder completed all five textbook passes, all three answer-book passes,
  and the first lab XeLaTeX/PythonTeX pass.
- PythonTeX itself passed with exactly zero errors and zero warnings and its
  seeded random example was stable (`2`, then `0.57`).
- The builder then rejected the run because the Pygments output contained zero
  timestamp comments under `SOURCE_DATE_EPOCH`, while the normalizer required
  exactly one. The separate macros output contained the one volatile timestamp.
- No Sage execution, PDF inspection, reproducibility baseline, package, or
  publication followed. The task-owned baseline path remained absent.
- The gate now admits zero or one timestamp per PythonTeX reader output, rejects
  duplicates, and normalizes the single macros timestamp to the fixed epoch.
  Targeted replay on the failed staging output passes. Stable PythonTeX hashes:
  - macros: `a47c567695519dc7094e345c7ce49ceaa944c8cc1f687358b4b8f9fab454d7c7`;
  - Pygments: `bd1621464436f3e3afecf96e216e7a6d6229b2f3b3292936f3192f22c6e5f313`.
- Current builder SHA-256:
  `bf15ac80827fa1fa4b4542ed19a10d647a08d9c7194f6166f7d45d9d80934de5`.

Disposition: restart the clean two-build sequence. This rejected run is not a
baseline and none of its PDFs is release-eligible.

## 2026-08-21T23:43:00+02:00 — HLA-A0006 reflow gate

- A later clean attempt was stopped before baseline creation after the live
  textbook log reconfirmed the open HLA-A0006 warning: 83.26271 pt overflow in
  `cover/symlist.tex`; the answer-book surface had the same table at 59.68524 pt.
- The notation/description pairs and their order are unchanged. The first table
  now uses wrapping paragraph columns of `0.36\textwidth` and
  `0.56\textwidth`, with the notation column right-aligned and descriptions
  ragged-right.
- Updated `src/cover/symlist.tex`: 4,590 bytes, SHA-256
  `8fd0f5360d222041462b698362e1c0d4bd83bc074156534ed501f60ac31690df`.
- Updated canonical source closure: 858 files, 53,980,659 bytes, tree SHA-256
  `0379ad3e8263dfe0a4542ee14b1998278435e18992dab443f2d8ac2f2cbd828c`.

Disposition: restart both clean builds. HLA-A0006 remains open until the final
textbook and answer-book pages are visually inspected and the overflow is absent.

## 2026-08-22T02:42:37+02:00 — targeted reflow visual refinement

- The first post-overflow clean build completed successfully and recorded a
  provisional baseline. It produced textbook 580 pages / 8,983,942 bytes /
  SHA-256 `e1bbb600acd44faf73216e1ddd49922796d7a2a4d7390a1e86c05c0c55a68c24`,
  answer book 435 pages / 2,671,471 bytes / SHA-256
  `80816e87350e03190069924b0423d3629cf280f489e4e6abc25777d8d4fb1777`,
  and lab 109 pages / 13,164,259 bytes / SHA-256
  `adb78966020355a90442c7ae68c734f1fd6b44b5d935a3f75e531ea666eeee4a`.
  Source unchanged, 2,064 reciprocal actions resolved, zero undefined
  references, zero runtime placeholders, and zero generated-English structural
  labels.
- Targeted inspection of textbook/answer pages 2–3 showed the width overflow
  gone, but the lists still sat high with unnecessary dead space and the answer
  book's Greek page inherited a running header. This did not satisfy the user's
  explicit centering/reflow requirement, so the provisional baseline was not
  accepted.
- The shared source now makes the notation and Greek lists two explicit,
  headerless pages, balances each vertically with top/bottom fill, keeps the
  bounded wrapping notation columns, and increases row spacing to 1.15/1.25.
  A targeted textbook pass and 144-dpi render confirm centered, readable pages
  using the available text block without clipping or overflow.
- Final `src/cover/symlist.tex`: 4,735 bytes, SHA-256
  `1defc2a8b40959e75cd293133c993de8f9c9e2c3607b2a90b1dad9903a6814de`.
- Final canonical source closure: 858 files, 53,980,804 bytes, tree SHA-256
  `f5d5d1a7920f7add9c6dfb141cd6c4af79231f4d0ad00f8ca4f178e770f3c315`.
- The invalidated task-local baseline was explicitly removed; it cannot be
  mistaken for evidence for the refined source.

Disposition: rerun the complete clean pair against a new baseline, then repeat
the targeted inspection on the second-build reader PDFs before closing HLA-A0006.

## 2026-08-22T02:52:35+02:00 — publication evidence-gate hardening

- A bounded adversarial review proved that coordinated mutations to both the
  Sage/PythonTeX report and its sidecar could previously remain self-consistent,
  and that the reproducibility-v2 object was compared without independently
  rebuilding it from the live report fields.
- The publication driver now pins the deterministic runtime controls, rebuilds
  the v2 fingerprint from live report fields, recomputes the canonical digest,
  and retains exact byte/hash/count closure for the all-page, cross-PDF, and
  SageTeX sidecars.
- `publication/publish_release.py`: SHA-256
  `7964b371b225ffbd18cf95be5fd1109a28821b606992dc79a7d7351d42e09d9f`.
- `publication/tests/test_publish_release.py`: SHA-256
  `feb81fb96dc4b426e34185f6616970583746951085e418b7c4e96009d8f6a1d4`.
- Independent local replay: 67 tests, 67 passed, zero failures; no network,
  credentials, Git, packaging, or publication action occurred.

Disposition: the hardened release gate is admitted. It remains ineligible
until the clean PDF pair, final backend, and human visual QA all pass.

## 2026-08-22T03:00:18.3442151+02:00 — backend live-receipt replay hardening

- Backend workflow advanced from v6 to v7 without changing schema 0.5.2.
- The final-build validator now reopens the live build report, both execution
  sidecars, and all three reader PDFs; it rejects stale paths/bytes/hashes,
  bool-as-integer count coercion, wrong semantic counts, PDF page mismatches,
  runtime placeholders, and incomplete SageTeX/PythonTeX closure.
- Independent replay: 13 focused tests passed in 0.136 seconds; three Python
  files also passed AST parsing.
- Generator SHA-256:
  `05c112d4a498627ba4e585bbe78892a8242bd1d2c687fccd36ef94ca6341779c`.
- Validator SHA-256:
  `e06857af1a129c901680546f414242fa725209dbdf18ec4a7c763833c4e1236d`.
- Test SHA-256:
  `74ac5631b9ce53ba9429b1488f17fc19310f7339d0ceab380a8db1d144aec6a2`.

Disposition: tooling gate passes. Generated projections remain deliberately
stale until the matched second PDF build exists, then must be regenerated and
validated twice.

## 2026-08-22T03:14:16.3712399+02:00 — fail-closed human visual-review publication gate

- The publication plan now requires both the automated final-PDF audit and a
  separate visual-review receipt.
- The visual receipt must cover every PDF page through byte/hash-bound contact
  sheets, dispose every automated finding and ranked page exactly once, bind
  full-page inspections to render-manifest PNGs, and report zero unresolved
  findings. No receipt has been created before inspection.
- Independent full publication-suite replay: 76 tests, 76 passed.
- Publication driver SHA-256:
  `09c77f238a76e26418cbb01d3a10c7d70fa07b1039284248fb4d85f001caacd4`.
- Publication plan uses the actual release date/version `2026.08.22`; SHA-256:
  `6c7a2d4d64c3c35a3c1a108b50b8ab590bc6b79fad79acae1cc44e2fee3fa6df`.
- Focused visual-gate test SHA-256:
  `aaaeda1d7754d0d263ffc6c761a531da1074d901acf1fc981b9da5194ad66b78`.

Disposition: gate implementation passes; publication remains blocked by the
still-pending matched build and actual visual-review receipt.

## 2026-08-22T03:35:27.9592326+02:00 — first final-source baseline rejected for tool-provenance defect

- The clean build itself succeeded with an unchanged source tree, zero undefined
  references, zero generated-English structural labels, zero runtime
  placeholders, all 2,064 reciprocal PDF actions resolved, and 1,124 rendered
  pages.
- Outputs were textbook 580 pages / 8,984,180 bytes / SHA-256
  `dedcebfe01755d5fe8020724e3f08ea63d1d26a397885c90b543dc8312b90a9a`;
  answers 435 pages / 2,670,928 bytes / SHA-256
  `443ff4fd763e3b2bc7b74185c49803d93c1f6138a8eaf38ecb2b558fff141d89`;
  lab 109 pages / 13,164,259 bytes / SHA-256
  `adb78966020355a90442c7ae68c734f1fd6b44b5d935a3f75e531ea666eeee4a`.
- The recorded tool-version fields for MiKTeX `makeindex` and Poppler
  `pdftoppm` were error strings because those programs reject the generic
  `--version` flag. The PDF bytes are not rejected, but that baseline is not
  acceptable as final provenance.
- The builder now uses `pdftoppm -v` and records `makeindex.exe` as 169,472
  bytes / SHA-256
  `a3f0a55e8a1333a54e7c90b6ae2f19cabe81d4ede8a6c690a085a9b6ba4c20d4`.
  Targeted probe and AST checks pass. Updated builder SHA-256:
  `99255760f702d64e45a526251a28b4ce8339c2aa2ee1b5410aaa00fee0dbddf0`.

Disposition: invalidate and remove baseline SHA-256
`53430441b80277ec1769b4a8e1f0c5e5ff3babeccf2a88af4bc39d6a7e19b3c8`,
then restart both clean builds. No source content changed.

## 2026-08-22T05:02:00+02:00 — corrected-provenance clean run one accepted

- Builder SHA-256:
  `99255760f702d64e45a526251a28b4ce8339c2aa2ee1b5410aaa00fee0dbddf0`.
- Source remained unchanged throughout: 858 files, tree SHA-256
  `f5d5d1a7920f7add9c6dfb141cd6c4af79231f4d0ad00f8ca4f178e770f3c315`,
  with zero added, changed, or removed live files at build end.
- Build report: 104,246 bytes, SHA-256
  `0224cb70de4328b97dcfd439433fe5d79f4eeaf183fda9f5181228e8bc88dffa`;
  status `success`; reproducibility status `baseline_recorded`.
- New v2 baseline: 3,897 bytes, SHA-256
  `fc359ecfc5f356501297efc92baf78799519ccb5ed53967de35ab47a900924b0`.
  Its tool-version projection contains no error or invalid-option text.
- Reader outputs:
  - textbook: 580 pages / 8,984,178 bytes / SHA-256
    `0c91c32cdf1c690b7619020c4604ada0f12a700785e8387a01b999c8e87d6d3b`;
  - worked answers: 435 pages / 2,670,928 bytes / SHA-256
    `68bf13c0b6f6add8bff23609cce5da871ff17a77dd50e931479768eba5e2045e`;
  - Sage lab: 109 pages / 13,164,259 bytes / SHA-256
    `adb78966020355a90442c7ae68c734f1fd6b44b5d935a3f75e531ea666eeee4a`.
- Zero undefined-reference lines, zero runtime-placeholder lines, zero
  generated-English structural-label hits. All 2,064 reciprocal cross-PDF
  actions resolved (1,032 in each direction), with zero unresolved.
- All 1,124 pages rendered. Contact-sheet closure is 29 textbook, 22 answer,
  and 6 lab sheets. Exact byte-identical copies were retained under
  `qa/visual_review/first_corrected_build_contact_sheets/` for review during the
  repeat run.
- There are 218 overfull-box diagnostics. They remain review candidates rather
  than automatic failures and must be disposed through the final automated and
  human visual audit. The known pypdf duplicate `/Group` notices remain subject
  to the independent MuPDF parser gate.

Disposition: start the second complete clean run against this exact baseline.
No backend, package, release, DOI, or upstream contact is yet authorized by this
checkpoint alone.

## 2026-08-22T05:34:00+02:00 — second-run process terminated externally

- The exact second-run command started from the accepted baseline and reached
  textbook pass 3 after completing the seven deterministic MetaPost groups and
  the first two textbook passes.
- The process then disappeared without a builder failure report or terminal
  diagnostic. The live `book.log` ended mid-token after page 223; therefore the
  attempt is an externally interrupted partial build, not a failed
  reproducibility comparison and not usable evidence.
- The accepted first-run baseline remains present and unchanged. No canonical
  translated source or builder file changed during the interrupted attempt.

Disposition: restart only the complete second clean run from the same pinned
inputs and baseline. Do not reuse any partial staging output.

## 2026-08-22T06:18:50+02:00 — mutable system font-map failure isolated and closed

- A restarted repeat completed all five textbook passes, then the first
  answer-book pass failed at `cover/symlist.tex:41`: microtype could not expand
  the non-scalable fallback for Concrete `ecssdc10`.
- The system `pdftex.map` had changed after the textbook process loaded its map
  and no longer contained the edition-used CM-Super, Bera, URW Grotesk, or Brush
  Script mappings. No global MiKTeX file was changed by this task.
- A disposable full-answer diagnostic proved the task-local closure:
  `cm-super-t1.map`, `cm-super-ts1.map`, `bera.map`, `ugq.map`, and `pbsi.map`.
  It produced 435 pages / 2,670,928 bytes; all edition body fonts were scalable.
- The diagnostic PDF's sole Type 3 entry belongs to the pinned upstream
  `src/map/pix/bridges.pdf` graphic on reader page 299. A 144-dpi full-page
  inspection found the plot, code block, text, margins, and centering intact.
- Canonical `src/sty/bookjhconcrete.sty` is now 39,524 bytes, SHA-256
  `ddda9a74090fb969884cd901d6c0283a3d1fd7574c7e0ad18e01956578b19521`.
- Canonical translated source is 858 files / 53,981,150 bytes, tree SHA-256
  `70bbff81288f44c0659c1d8f0e035a7ebde5bf25172c9955067dec624d70e9f3`.
- Builder is 75,193 bytes, SHA-256
  `411ae35627e05989425786fb716c90b461e016faae4dae6a70be0efcafb70c92`;
  AST parsing passes and all 23 pinned font dependencies resolve, copy into the
  task-local TeX tree, and reverify with their exact admitted byte counts and
  hashes. The local closure contains 1,594,916 bytes; `kpsewhich` resolves its
  map and Type 1 files from that task-local tree before the system installation.
- The builder rehashes the complete private closure at build end. Three focused
  tests bind the exact 23-name set and five source map directives, prove that
  the v3 projection excludes machine paths, and prove that a changed staged byte
  fails closed. Builder-test SHA-256:
  `1135482b6847bf84796d24e6fff8569d0e4a4126acfbdea66eabe60481061d7a`.
- Publication fingerprint reconstruction now independently validates the same
  v3 dependency/end-verification projection. Its 37 focused tests pass;
  publication driver SHA-256
  `a06e895d3088855fb9d4c4e8d1fc1c9b1b973b5faa0359f0db68c632d5776d47`.

Disposition: invalidate the old v2 baseline and restart both complete clean
builds with the v3 fingerprint. All first-run PDF/contact-sheet hashes are now
historical only.

## 2026-08-22T07:19:02+02:00 — first v3 foreground attempt terminated externally

- The first clean v3 command completed authority extraction, all seven MetaPost
  groups, textbook passes 1 through 3, and reached textbook pass 4 page 450.
- The foreground worker then disappeared across an app turn boundary. There is
  no `build_report.json` and no reproducibility baseline, so the attempt is a
  discarded partial run and proves neither success nor failure.
- No `python.exe` process for `tools/build_hefferon_id.py` remains. Canonical
  source and builder were not changed by the interrupted worker.

Disposition: restart the same exact clean v3 command as a hidden task-local
background process with stdout/stderr outside the builder-replaced build tree;
accept only a complete report and baseline.

## 2026-08-22T07:36:00+02:00 — offline font closure admitted before baseline

- The hidden restart reached textbook pass 1 page 537. It was intentionally
  stopped before producing a report or baseline when the release audit showed
  that exact host-resolved font bytes still had to be preserved inside the
  repository for an honest offline closure. This is a discarded partial run,
  not a failed PDF or reproducibility result.
- The 23 exact dependencies (1,594,916 bytes) are now preserved unchanged under
  `tools/pdftex-font-closure/`. Including notices, provenance, README, JSON, and
  checksum manifest, that tree is 35 files / 1,691,921 bytes with canonical
  tree SHA-256
  `38c9e8f3fb6ca59d92fb16476f1a9b5789c1626062fefc98a661951b892d312c`.
- `SHA256SUMS` covers every non-self file and validates; its SHA-256 is
  `3a5c48d76bbed0a3950d613205fe8f3f5a4b6f71d5412f7c50be5813ceefcf20`.
  The machine-readable third-party notice inventory SHA-256 is
  `b1e6e3ae0d5d53fa0b0d309bbb325b07ed4fcfe6cec76ed47116feaacb9a74e0`.
- Builder SHA-256 is
  `64d0bde44c3e4b5571af32e4e5b2fa18b4d104eefe48c0481e942129acf7978e`.
  It no longer resolves the pinned files with `kpsewhich`; it validates and
  stages the repository closure, then reverifies both staged and source bytes at
  build end. Four focused tests pass; test SHA-256 is
  `ffba56e07c7df5d05ee1a6272a965e833f725ec7ef2d4eed0218c7f42c34f301`.
- A staging-only run completed from source tree
  `70bbff81288f44c0659c1d8f0e035a7ebde5bf25172c9955067dec624d70e9f3`;
  the 7 book and 64 lab recovered-graphics manifests retained their expected
  hashes. No baseline exists.
- The publication driver independently validates and reconstructs the opening
  and end-verified closure fields in the path-neutral v3 fingerprint. Its full
  78-test suite passes; driver SHA-256 is
  `4b60f8430b05b4ab797a00dffc8f52af99881e10116be68d99adeabda2babc52`.

Disposition: run two new complete builds with this exact builder and closure;
record the first v3 baseline and require the second to match it exactly.

## 2026-08-22T08:23:13+02:00 — first complete offline-closure v3 build accepted

- The complete clean build succeeded from canonical source tree
  `70bbff81288f44c0659c1d8f0e035a7ebde5bf25172c9955067dec624d70e9f3`;
  the live end tree is identical and `unchanged_during_build` is true.
- It recorded a new path-neutral v3 baseline: 7,877 bytes, SHA-256
  `1a7e0b5dbf9873588c5fa196929b40f4b2b63cba8343c5a23d3f2aa7733c7461`.
  Build-report SHA-256 is
  `437be5f602f028ac5f19c529ac7cfa3dcbf420ca4140e7c7899d11def2810394`.
- Reader outputs are textbook 580 pages / 8,984,183 bytes / SHA-256
  `84fd7a4d15c5efcb52fc64a0c5658415479aa1011b3ad2a5caf8ba6d56b8770f`;
  worked answers 435 pages / 2,670,928 bytes / SHA-256
  `f96f1a8e24b005d5f2c7bc7f46c111bcef8825a5346c4800b5f7c4afd054b839`;
  lab 109 pages / 13,164,259 bytes / SHA-256
  `adb78966020355a90442c7ae68c734f1fd6b44b5d935a3f75e531ea666eeee4a`.
- All 1,124 pages rendered into 57 contact sheets. The render manifest is
  370,285 bytes / SHA-256
  `ac8c0208a5a07031b1867350e4933604a1c5fcf299f0e67dcb2a8b5359766193`.
- All 2,064 reciprocal remote actions resolve: 1,032 textbook-to-answer and
  1,032 answer-to-textbook, zero unresolved. Zero undefined references,
  runtime placeholders, or generated-English structural labels remain.
- SageTeX status is pass with 148 command labels and 63 expected figure
  mutations followed by restoration of all 64 authority figures. Runtime
  manifest SHA-256 remains
  `9445f1e6aee67f41425dd8e830cc17f28ba6ea1bd031bf0ddea41caff1794f3b`.
- The repository closure opened as 35 files / 1,691,921 bytes / tree
  `38c9e8f3fb6ca59d92fb16476f1a9b5789c1626062fefc98a661951b892d312c`
  and matched at build end; all 23 staged dependencies / 1,594,916 bytes also
  matched. The stderr lines are the already-known duplicate `/Group` notices
  emitted by pypdf for inherited PDFs; independent parser/visual gates remain
  mandatory.

Disposition: this is accepted only as run one. Launch a second clean build
against the exact baseline and require `reproducibility.matched == true` before
using its PDFs, renders, report, or contact sheets as final evidence.

## 2026-08-22T16:50:24+02:00 — v3 mismatch diagnosed; fail-closed v4 boundary admitted

- The complete second v3 build reached all three final PDFs and all 1,124 page
  renders, but the exact comparison failed as designed. The second textbook is
  580 pages / 8,984,170 bytes / SHA-256
  `132d5c99d6ea6e35186946a3447b262ac0fbc509d51709d1d04580142edf65ea`;
  the answer book is 435 pages / 2,670,928 bytes / SHA-256
  `61f99fd3c591fc0227b01346a2cbdd7bca4715e326dfee3f7a440b274d4cdc7d`;
  the lab remains byte-identical at SHA-256
  `adb78966020355a90442c7ae68c734f1fd6b44b5d935a3f75e531ea666eeee4a`.
  Only the two pdfTeX reader hashes and the textbook's 13-byte delta differed
  from the v3 baseline; all other v3 fingerprint fields matched.
- The failed report is 135,976 bytes / SHA-256
  `e9203cea99eb4bcfcce94322d5ddfef4fa01a9df4063636634a24b725bcde3f3`.
  An additional textbook pass is exactly identical to the second-run textbook,
  proving that run's local convergence but not cross-clean-build identity.
- Both pdfTeX logs proved that the host default `pdftex.map` loaded before the
  five appended private maps. Across the two readers, 27 embedded Type 1
  programs / 693,298 bytes remained host-resolved. The repository closure now
  includes exact CTAN-matching copies, their notices, and three retained
  authority ZIPs. The 51 runtime dependencies total 2,289,616 bytes; the full
  73-file closure is 10,325,900 bytes / tree SHA-256
  `542e2566a14b473654387a8a263cc1d49392e35db7058880d56f95cc6059ce56`.
- `hefferon-standard.map` is loaded without a modifier before the five
  component maps. pdfTeX map/encoding/Type-1 searches are private-only and
  `-recorder` input audits fail on any external controlled font input.
- The explicit MetaPost seed reproduced all previously checked `.1` outputs
  exactly. The full inventory is 307 files / 1,999,626 bytes / canonical
  SHA-256 `08dd090a4e41f943a851abb80c48a92cdd6502a7dbebe86f7fdbbdd6125aa629`;
  its manifest SHA-256 is
  `d9bbbc58eb588336856b058dc89ea6e1175711c2712940e83119de979df75081`.
- Source staging succeeds from 858 files / 53,981,354 bytes / tree SHA-256
  `5c161ff7584a281156094bcebf4a78b5ec5d2ff98c362dc21c0c26c386093f5a`.
  Six focused builder tests and 79 publication tests pass. The publication
  driver independently reconstructs the v4 fingerprint and reads back the two
  new sidecars byte-for-byte.

Disposition: finish the bounded textbook/answer diagnostic now in flight. If
the private input audit and dedicated convergence passes succeed, remove only
the superseded live v3 baseline (the diagnostic copy remains), then run two
fresh complete v4 builds and require an exact second-run match.

## 2026-08-22T17:13:27+02:00 — v4 reader/input diagnostic passed; final gates strengthened

- The bounded diagnostic completed successfully. Its textbook convergence
  state is SHA-256
  `f44a278fe2b90c8445f8284db018c28c9adb85c3dacdf64a51146d086e0d2a40`;
  answer convergence is
  `0db487bfd5215f6d5877eea2629999a09bdaf611b45847544466e5558c0e6ad8`;
  the generated answer stream is
  `e4094963573b6825a5585f32c378ae95d93adccba9f22f97359f1a2e8a0d96cf`.
- The recorder audit contains 94 controlled records across `book` and
  `jhanswer`, representing all 51 distinct private map/encoding/Type-1 files,
  plus 158 TFM/VF metric records. `all_map_encoding_font_program_inputs_private`
  is true, zero controlled records lack a closure path, and the canonical audit
  SHA-256 is
  `45340fc6c652d1780cf7cbd4119eb9dfe79d6a62b8255bee523606eb06661388`.
  The sidecar is 56,287 bytes / SHA-256
  `844b4db2149eaa50f05ed536514ec2637654ca5a0a55bdb6683cc84ff0070e2e`.
- Review identified a stale-index possibility in the prior six-pass textbook
  sequence. Before the final pair, the builder was changed to refresh
  `makeindex` after pass 5, verify the exact `.idx`/`.ind` fixed point after
  pass 6, and require full-state identity on pass 7. Nine focused builder tests
  pass.
- Review also identified that publication did not rehash live build-tool/font
  bytes and that the offline source routes omitted the two authority PDFs used
  to recover 71 graphics. The publication driver and plan now fail closed on
  those bytes and include both inputs in staging, editable-source, and GitHub
  snapshot routes. Publication regression fixtures are being brought to the
  exact 51-file/73-file contract before the final suite is accepted.

Disposition: close the final review and publication tests. Then discard only
the superseded live v3 baseline (after verifying its preserved diagnostic copy)
and run the two complete v4 builds with the stable final builder bytes.

## 2026-08-22T17:18:00+02:00 — final v4 code boundary frozen; run one launched

- Independent read-only review reports no remaining release blocker. It
  verified authority-PDF hashes in both v4 fingerprint implementations; live
  five-tool, two-authority-input, 51-runtime-file, and 73-file closure rehashing;
  index refresh/verification before textbook pass 7; exact 133-answer counts;
  offline authority-PDF packaging; map isolation; and MetaPost wrapper/jobname
  handling.
- Final frozen identities are builder 101,420 bytes / SHA-256
  `5e6593cb652e790346453306978e2ff682d02bc18c0168636a255b75280de5ee`;
  publication driver 278,732 bytes / SHA-256
  `4ccd6c6d90726bbc4e816cfff84806491438d1579d7da35525dfd2cb7ce57579`;
  publication plan 7,927 bytes / SHA-256
  `a5a182b22dde7042cfa21c3277cefc5c769327aebb6123beffef77453c6fd8b1`.
  Nine builder tests and 82 publication tests pass independently.
- The superseded live v3 baseline was removed only after its preserved copy was
  verified at 7,877 bytes / SHA-256
  `1a7e0b5dbf9873588c5fa196929b40f4b2b63cba8343c5a23d3f2aa7733c7461`.
  The first complete v4 build is now executing with a nonexistent live
  baseline path and must record a new one.

Disposition: accept run one only if every build/QA/render/end-verification gate
passes and the new baseline is recorded; then execute a second clean build
without changing any fingerprinted byte and require exact equality.

## 2026-08-22T18:27:00+02:00 — complete v4 run one passed and recorded baseline

- Status is `success`; source remained 858 files / tree SHA-256
  `5c161ff7584a281156094bcebf4a78b5ec5d2ff98c362dc21c0c26c386093f5a`
  through build end. The report is 288,839 bytes / SHA-256
  `12b183ec2ae3c85fd439b624dea47394abc9d4f4d572a5d771d3c971dd4a83dd`.
- The new v4 baseline is 171,840 bytes / SHA-256
  `65b85a974b91bcf7b36ecf708684527103a5effb31bea280f2258d7f16d8abe7`.
  It includes both authority-PDF hashes, the pass-7 textbook/index fixed point,
  pass-4 answer fixed point, all 307 MetaPost assets, the generated answer
  stream, private recorded inputs, build tools, runtime/closure bytes, and the
  three PDFs.
- Reader outputs are textbook 580 pages / 8,984,108 bytes / SHA-256
  `654ea77dbe5fc55a76a3e79852fc34d7f9c36d91e4e05adf31f9439e294c92fe`;
  worked answers 435 / 2,670,853 /
  `4a6310e9900ac46544e9d557fe410d177562dea9b5c77221891d7e58d195c921`;
  lab 109 / 13,164,259 /
  `adb78966020355a90442c7ae68c734f1fd6b44b5d935a3f75e531ea666eeee4a`.
- All 1,124 pages rendered; render-manifest SHA-256 is
  `78c44e70e9d0911f66a6b8e58cdf5d38f1d0bfcc76b36a4f1677a1224ed77009`.
  All 2,064 reciprocal actions resolve, with zero unresolved. Undefined
  references, generated-English labels, and runtime placeholders are all zero.
- The 51 runtime dependencies / 2,289,616 bytes and complete 73-file closure /
  10,325,900 bytes verified unchanged. The input audit remains 94 controlled /
  158 metric records and all controlled inputs are private. The textbook index
  fixed point is exact, and both reader convergence records are true.

Disposition: run one is accepted only as the baseline member. Start the second
clean build with no fingerprinted-byte changes and require exact equality.

## 2026-08-22T18:30:00+02:00 — first repeat attempt discarded after transient MetaPost launcher failure

- The first repeat attempt stopped before reader compilation in
  `mpost_det_mp_ch4`: nested `latex` produced its complete 150-page, 79,344-byte
  DVI but nevertheless returned a nonzero status to `makempx`, so MetaPost
  returned 3. No comparison or release artifact from this partial attempt is
  accepted.
- A bounded diagnostic reran the exact same seeded command in the same staging
  directory and environment. It returned 0 and wrote all 68 expected
  `ch4.1`–`ch4.70` outputs. This proves the source/job itself is sound and the
  one-time failure was transient; no builder, source, authority, closure, or
  baseline byte was changed.
- Before restart, the baseline remained 171,840 bytes / SHA-256
  `65b85a974b91bcf7b36ecf708684527103a5effb31bea280f2258d7f16d8abe7`
  and the builder remained 101,420 bytes / SHA-256
  `5e6593cb652e790346453306978e2ff682d02bc18c0168636a255b75280de5ee`.

Disposition: discard the partial attempt and execute the unchanged clean repeat
from new staging. It still must complete every gate and match the baseline.

## 2026-08-22T19:00:18+02:00 — clean repeat externally terminated; hidden restart required

- The unchanged clean restart passed all seven MetaPost jobs and completed
  textbook passes 1–3, but its foreground execution session was terminated by
  an app-turn steering event during pass 4. No build report or comparison was
  produced, so the partial attempt is discarded without any reproducibility
  claim.
- The accepted baseline remains 171,840 bytes / SHA-256
  `65b85a974b91bcf7b36ecf708684527103a5effb31bea280f2258d7f16d8abe7`.
  No source, builder, authority, or closure input changed.
- The user reports the GitHub account is temporarily suspended after VPN use and
  a support ticket is open. Do not call GitHub APIs or mutate that account while
  suspended. This must not block the independent Zenodo preservation path:
  after the local build/backend/QA gates pass, maintain one deduplicated Zenodo
  lineage, publish the exact bounded release there, and anonymously read back
  all public bytes. GitHub remains a separate pending mirror, not a Zenodo hold.

Disposition: restart the exact repeat as a hidden task-local process so app-turn
steering cannot terminate it. Develop/test a Zenodo-only publication route in
parallel; do not contact either remote until the artifact gates pass.

## 2026-08-22T19:48:14+02:00 — run-two mismatch diagnosed; v4 baseline retired

- The hidden repeat completed every TeX, MetaPost, Sage, render, and audit step,
  then correctly failed its final fingerprint comparison. Textbook and lab were
  exact matches; only `jhanswer.pdf` changed at the same byte count. The three
  differing fingerprint paths were the answer PDF SHA-256, answer convergence
  SHA-256, and duplicate answer-PDF inventory SHA-256.
- The cause was confined to two answer-only `epstopdf` conversions in
  `src/map/markov.tex`: `learn5.eps` and `ws.eps`. The converter writes current
  timestamps, UUIDs, and trailer IDs. The translated source now selects the
  exact stable PDF siblings already supplied in the pinned official source:
  `learn5.pdf` (5,134 bytes, SHA-256
  `611dce6daa57dab15dfd6eb18c0eca3c43cab025261584b6a5f50fc38e1e97e6`)
  and `ws.pdf` (5,781 bytes, SHA-256
  `f633a32038a2fb9257ba1db0af5ffd681675801fa8af49885ac9aab4275c3d3b`).
- All 1,124 rendered pages were covered by contact-sheet review and ranked
  full-size inspection. One true textbook overflow and inherited answer-topic
  furniture defects were found. The local repairs are: an explicit flexible
  page break before the unbreakable Fields table; removal of the answer-topic
  `\thispagestyle{empty}` timing hazard; and unbreakable wrappers around the two
  Octave listings previously split across leaves. Answer p316 and the lab p73
  graphic were proved complete and retained unchanged.
- Changed source closure: 858 files / 53,981,473 bytes / SHA-256
  `df240083cfd6c7a91438d087c7002482aca247cdec879399884e124b335ce2f1`.
  Exact changed-file hashes: `fields.tex`
  `5fbf1e5f902c13552651fce19df542868da66fee4afcaf856dc0aba1dadb4c42`,
  `answerjh.sty`
  `9dc14ef5c10f7c2aacc33e6f3638e75a4fcd123b8e766812c910c4a251db05d9a`,
  and `markov.tex`
  `5c81467ef2e2fb663b1acedc908941c6463aad489cd07ed7af231f2ba7c61e38`.
- The focused build/PDF suite passes 19/19. The isolated Zenodo/GitHub
  publication suite passes 92/92. The builder itself remains 101,420 bytes /
  SHA-256 `5e6593cb652e790346453306978e2ff682d02bc18c0168636a255b75280de5ee`.

Disposition: the former v4 baseline is ineligible because the source closure
changed. Run a fresh complete clean build as the new baseline, inspect the
affected pages, then require a second clean build to match it exactly. GitHub
remains untouched while suspended; the first remote transaction after all
local gates will be the clean, deduplicated Zenodo path.

## 2026-08-22T20:15:00+02:00 — Zenodo lineage/update route closed locally

- A bounded code audit found that exact drafts resumed safely but an older
  public concept could otherwise be bypassed by a fresh deposition.
- The Zenodo-only implementation now performs same-work concept discovery,
  fails closed on ambiguity, and uses the official latest-version
  `actions/newversion` plus `links.latest_draft` route whenever a concept
  already exists. Exact drafts remain resumable; proved absence permits one
  initial concept.
- Independent local replay: 105 publication tests pass and Python compilation
  succeeds. No credential was read and no Zenodo or GitHub request was made.
- Anonymous public search found zero exact-title Hefferon Indonesian records;
  authenticated preflight still remains mandatory because unpublished drafts
  are not visible publicly.

Disposition: after all local build/backend/visual gates pass, run authenticated
`zenodo-preflight`; freeze transaction inputs; then publish and anonymously
verify without any intervening local mutation or GitHub call.

## 2026-08-22T20:22:39+02:00 — repaired-source run one passed; new baseline recorded

- Complete hidden build PID 50164 returned successfully from source tree
  `df240083cfd6c7a91438d087c7002482aca247cdec879399884e124b335ce2f1`;
  the live source remained exact through end verification.
- New baseline: `tmp/hefferon_id_reproducibility_baseline_v5.json`, 171,840
  bytes, SHA-256
  `fde215f9416100bedb4a3624a3fe8560c17567f7de8e73bc2f750c0a31a685ec`.
  Build report: 288,842 bytes, SHA-256
  `d39d83637372ce95dc7712041b7d6c0651700ddfc6263f88692bfd1420fd6e64`.
- Reader artifacts:
  - textbook: 580 pages / 8,984,100 bytes / SHA-256
    `20b3ac3a57d08932649cf817b561d83a27ba2f4917d5af0ec57ade4767d02ca5`;
  - worked answers: 435 pages / 2,672,266 bytes / SHA-256
    `22a41d02abba4954514e35017425c6a310b1a3d39efcc5e036e5884f12cf1dd1`;
  - Sage lab: 109 pages / 13,164,259 bytes / SHA-256
    `adb78966020355a90442c7ae68c734f1fd6b44b5d935a3f75e531ea666eeee4a`.
- All 1,124 pages rendered. Undefined references, runtime placeholders, and
  generated-English structural labels are zero. All 2,064 reciprocal cross-PDF
  actions resolve.
- Full-size repair inspection passed: textbook pp181-184 now contain the intact
  Lapangan opener and table without clipping; answer p306 and pp425-430 retain
  headers/folios; both targeted Octave blocks move intact; stable official
  answer graphics render correctly on pp314 and 318. No implicit EPS-converted
  PDFs exist in staging.

Disposition: accept this only as member one. Run a second clean build against
the new v5 baseline without changing source or builder; require exact identity
for all fingerprinted inputs, intermediates, assets, and three PDFs.

## 2026-08-22T21:05:55+02:00 — clean pair and final backend gates passed

- Hidden run two completed with status `success`. Reproducibility status is
  `verified`, `matched` is true, and both the baseline and current projection
  equal SHA-256
  `fde215f9416100bedb4a3624a3fe8560c17567f7de8e73bc2f750c0a31a685ec`.
- Final build report: 688,999 bytes / SHA-256
  `330500dee08e1b3b7cd609e9ff3f903d3ac2d2c9685b0bb765a05dcd43da66ba`.
  The final readers remain exactly: textbook 580 pages / 8,984,100 bytes /
  `20b3ac3a57d08932649cf817b561d83a27ba2f4917d5af0ec57ade4767d02ca5`;
  worked answers 435 / 2,672,266 /
  `22a41d02abba4954514e35017425c6a310b1a3d39efcc5e036e5884f12cf1dd1`;
  lab 109 / 13,164,259 /
  `adb78966020355a90442c7ae68c734f1fd6b44b5d935a3f75e531ea666eeee4a`.
- The backend regenerated twice with byte-identical 2,154-byte manifest SHA-256
  `936fe87b0a20b99a4e0c789ce7535cd518b17fa1b2b07b64c9656a369ef8d7ce`.
  Its final validator passes with 3,540 units, 3,527 segments, 1,037 exercises,
  1,037 answers, 1,035 native answers, two derivative-supplied answers, 13,943
  relations, zero unanswered exercises, and `final_build_required: true`.
- Automated final PDF audit wrote `qa/final_pdf_qa.json`, 4,003,771 bytes /
  SHA-256
  `3a5cef653a03f051278d0d749ec32f43c235ba81bff04b0f94ebeef4404bb2ef`.
  It has zero hard failures and five explicit human-review findings. The exact
  final contact sheets were copied to
  `qa/visual_review/final-330500dee08e`: 29 textbook, 22 answer-book, and six
  lab sheets.
- The user reports GitHub reinstated. A bounded unauthenticated read-only check
  confirms `KokunoYumeto` is publicly reachable again; the planned
  `hefferon-linear-algebra-id` repository is not yet public. GitHub therefore
  returns to the final publication sequence instead of remaining deferred.

Disposition: finish the all-page and ranked-candidate visual review, then run
the frozen authenticated GitHub/Zenodo publication sequence and anonymous
readback. Figshare remains a separate bounded preservation mirror after Zenodo.

## 2026-08-22T21:36:10+02:00 — exhaustive review found and closed two late trim defects

- The all-page contact-sheet sweep and full-size ranked-candidate review covered
  the complete matched v5 readers: 335 textbook candidates, 131 answer-book
  candidates, and 64 lab candidates. Answer book and lab passed. The textbook
  had exactly two true defects: PDF page 28 clipped the final equation of a long
  inline set-builder description, and PDF page 92 clipped the final tokens of a
  long inline C assignment. Four suspected running-header defects were rejected
  after direct full-size inspection because their text and rules are intact.
- `src/gr/gr1.tex` now presents the same three defining equations in a compact
  two-line gathered set display. A 144-dpi diagnostic proves page 28 fully
  inside the trim and page 29's continuation intact.
- `src/gr/ppivot.tex` now presents the identical assignment in a local
  breakable code listing. A 144-dpi diagnostic proves page 92 fully inside the
  trim and page 93's continuation intact.
- The adverse ledger now closes HLA-A0306 and HLA-A0307: 307 records / 103,796
  bytes / SHA-256
  `845fd8361b909cfb3e6809f2ff42ba2c7e4c860a09f31c001b62c72a39bde23e`.
- Repaired source closure: 858 files / 53,981,603 bytes / SHA-256
  `c0772dff373b103192c72f639e68a1e507d40e9ebdd102af98eb6475e8692c36`.
  Changed-file identities are `src/gr/gr1.tex` 216,680 bytes /
  `21fc305ab61092dbd973b743a7e356aa0764a56ccc19c4c094b141a458513dd7`
  and `src/gr/ppivot.tex` 17,558 bytes /
  `3b32bdbd7ce027453f4b7e658781758638230ddb131a86c7c26c9270a83cc9a2`.
  Nineteen focused build/PDF tests pass.
- Because reader bytes and pagination can change, the otherwise matched v5
  pair, final backend snapshot, automated PDF audit, and visual-review staging
  are all superseded. They remain historical evidence only and are not release
  eligible.

Disposition: record a fresh v6 baseline from the repaired source, inspect its
affected pages, then require a second complete unchanged build to match before
regenerating backend and final QA.

## 2026-08-22T22:50:31+02:00 — v6 baseline passed; terminology QA closed; match run active

- Repaired-source v6 run one completed successfully from exact translated
  source tree
  `c0772dff373b103192c72f639e68a1e507d40e9ebdd102af98eb6475e8692c36`.
  Source remained unchanged through end verification.
- Baseline: `tmp/hefferon_id_reproducibility_baseline_v6.json`, 171,840 bytes,
  SHA-256
  `fa8ceb8e983dd086deac7f86004003c02d2bb0c84a8ffa34df0f062da679e69f`.
  Build report: 288,677 bytes, SHA-256
  `36169046031835f54f0fbf6e2f096517a645782dc5d32e496e16027560ee7b63`.
- Reader artifacts: textbook 580 pages / 8,984,459 bytes /
  `0462ddc8ffcc901efbc81205f79a249ae716e838a6ec32eda033444a90b8755e`;
  worked answers 435 / 2,672,266 /
  `61f8a344cade529249d4f165bb62bce17579b6a4408b11634999e9f73ec9c01b`;
  Sage lab 109 / 13,164,259 /
  `adb78966020355a90442c7ae68c734f1fd6b44b5d935a3f75e531ea666eeee4a`.
  All 1,124 pages rendered, with zero undefined references, runtime
  placeholders, or generated-English structural labels; all reciprocal links
  resolve.
- Full-size current-render inspection passed repaired textbook pages 28 and 92
  and their adjacent continuation pages 29 and 93. Neither repaired line
  crosses trim.
- Direct arXiv search yielded no suitable Indonesian linear-algebra source.
  The honest fallback is Azizah and Ariyanti's official UMSIDA Press textbook,
  DOI `10.21070/2020/978-623-6833-41-4`, 159 pages / 1,675,339 bytes / SHA-256
  `f687c749c0dee07538a7a5d1dc7b230306b83ec30574e8e75f5c3eb34cec995d`.
  Direct PDF/text comparison supports existing house terms. The terminology
  ledger now explicitly binds `null space` to `ruang nol` and `nullity` to
  `nulitas`; no reader source changes were warranted.
- The exact production provenance `OpenAI Codex gpt-5.6-sol, Ultra.` was added
  to edition, backend, repository, and release metadata without replacing the
  original author or component credits. Public packaging is now fail-closed
  against disclosure of the local user identifier.
- Unchanged v6 run two started hidden as PID 2968 at
  2026-08-22T22:50:31+02:00 against the exact baseline above.

Disposition: require exact v6 match, then regenerate the backend twice and
complete new build-bound automated and visual QA before any remote mutation.

## 2026-08-22T23:14:12+02:00 — discarded partial match attempt restarted persistently

- The unchanged match attempt identified above was externally terminated while
  textbook pass 6 was active. It had completed textbook passes 1 through 5 and
  the refreshed index, but emitted no build report, output inventory, or
  reproducibility comparison. It is rejected and proves no member of the clean
  pair.
- The accepted v6 baseline and canonical translated source remain unchanged.
- The exact command was restarted without source mutation in persistent
  execution session 74984:
  `python -B tools/build_hefferon_id.py --reproducibility-baseline
  tmp/hefferon_id_reproducibility_baseline_v6.json`.

Disposition: require session 74984 to exit zero and emit a verified exact
baseline match before regenerating any backend or final QA artifact.

## 2026-08-22T23:45:49+02:00 — v6 unchanged pair verified exactly

- Persistent execution session 74984 exited zero after completing all seven
  textbook passes and index fixed point, all four worked-answer passes, all five
  Sage-lab passes, PythonTeX, pinned SageTeX, BibTeX, PDF diagnostics, 1,124-page
  rendering, link audit, font/input closure, source end verification, and
  reproducibility comparison.
- Build report: 688,834 bytes / SHA-256
  `2b463cbced3f53fbc4253d0ff5570878488a3af0a7ee241602c2258e0a6e10e0`;
  status `success`.
- Reproducibility status is `verified`; `matched` is true; baseline and current
  fingerprints both equal
  `fa8ceb8e983dd086deac7f86004003c02d2bb0c84a8ffa34df0f062da679e69f`.
- Reader artifacts exactly match run one: textbook 580 pages / 8,984,459 bytes /
  `0462ddc8ffcc901efbc81205f79a249ae716e838a6ec32eda033444a90b8755e`;
  worked answers 435 / 2,672,266 /
  `61f8a344cade529249d4f165bb62bce17579b6a4408b11634999e9f73ec9c01b`;
  Sage lab 109 / 13,164,259 /
  `adb78966020355a90442c7ae68c734f1fd6b44b5d935a3f75e531ea666eeee4a`.
- Source remained unchanged at 858 files / tree SHA-256
  `c0772dff373b103192c72f639e68a1e507d40e9ebdd102af98eb6475e8692c36`.
  Undefined-reference, runtime-placeholder, and generated-English-label counts
  are zero. All 2,064 reciprocal actions resolve. MetaPost, private font input,
  73-file closure, and 51-runtime-dependency end checks pass.

Disposition: the clean reproducible PDF pair is accepted. Regenerate and
validate the backend twice, then bind the final automated and all-page visual
QA to this exact report and reader set.

## 2026-08-23 — final backend, automated PDF audit, and visual receipt accepted

- The live release gate exposed one machine-specific absolute path in the
  build-report reproducibility metadata. Only that path spelling was normalized
  to `tmp/hefferon_id_reproducibility_baseline_v6.json`. The source tree,
  baseline and current fingerprints, all three PDFs, all renders, and all build
  assertions remained byte-identical. The final build report is 688,743 bytes /
  SHA-256
  `c371bf8a1527602ba57af9ad0b6ff0225a96f8882d4f2a226d336090e1370851`.
- The backend then regenerated twice with identical canonical output. Final
  `backend/manifest.json`: 2,154 bytes / SHA-256
  `4c79fad12bda1552f03d6dae7c962f4d7a51ff68b3dcef09e88c437bfe773fad`.
  `python -B backend/validate_backend.py --require-final-build` passes with
  8,132 records, 3,541 units, 3,528 segments, 1,037 exercises, 1,037 answers,
  13,999 relations, 432 assets, 114 terms, 307 corrections, and zero
  unanswered exercises.
- Final automated audit `qa/final_pdf_qa.json`: 4,002,372 bytes / SHA-256
  `d2b529e787accc685a9b07080f610bfdc70d252714f56b1747928ee18dc4e22d`;
  all 1,124 pages rendered, zero hard failures, and five review categories.
- Final human review `qa/final_visual_review.json`: 482,412 bytes / SHA-256
  `78c475d4e6b3bc347327333b0b064e34400a6430528750cb2dd678941c43a240`;
  status pass, 57 contact sheets covering every page, 532 ranked-candidate
  dispositions, 534 manifest-bound targeted inspections, all five findings
  passed, and zero unresolved findings.
- The reviewed contact-sheet directory is preserved in every relevant release
  closure. Focused visual-review tests: 9 passed. Focused publication-privacy
  tests: 6 passed.

Disposition: the final reader and backend artifacts are release-eligible.
Proceed through the complete publication suite, authenticated channel
preflights, publication, and anonymous byte readback without changing frozen
inputs.
