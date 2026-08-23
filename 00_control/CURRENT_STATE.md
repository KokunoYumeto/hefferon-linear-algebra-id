# Current State — Hefferon Linear Algebra id-ID

Updated: 2026-08-22T23:45:49+02:00
Status: translation complete; terminology/provenance QA closed; repaired-source v6 pair exactly reproducible

## Exact state

- The canonical user-task file remains
  `%USERPROFILE%\Documents\Obsidian notes\Untitled 1693.md`, 10,476 bytes,
  SHA-256 `cf913e8cb4d487f4c6958c079b372ccbb2fb5929dd483068441e80cefd6794f2`.
- Official source remains pinned to GitLab commit
  `df2262e089a02651c127f1dd12649c4622ee1383` and source tree
  `30340725aa2641b3c617b1584c59f6df83e1fdf3`.
- The Indonesian derivative uses the pinned repository's CC BY-SA 2.5 route.
  Component licenses and notices remain separate rather than being flattened.
- The live translated source is now 858 files / 53,981,603 bytes / canonical
  tree SHA-256
  `c0772dff373b103192c72f639e68a1e507d40e9ebdd102af98eb6475e8692c36`.
  Its adverse ledger contains 307 contiguous records through HLA-A0307,
  103,796 bytes / SHA-256
  `845fd8361b909cfb3e6809f2ff42ba2c7e4c860a09f31c001b62c72a39bde23e`.
  The last two records bind local, content-preserving reflow repairs for the
  page-28 set-builder line and page-92 C assignment found by exhaustive
  full-size review. Both repaired pages and their adjacent continuation pages
  pass isolated 144-dpi inspection.
- The prior v5 build pair was byte-identical, but its readers, build report,
  backend, and final PDF audit are superseded because those two visible trim
  defects were still present. The repaired-source v6 baseline now passes from
  the exact source tree above. Its baseline is 171,840 bytes / SHA-256
  `fa8ceb8e983dd086deac7f86004003c02d2bb0c84a8ffa34df0f062da679e69f`;
  its build report is 288,677 bytes / SHA-256
  `36169046031835f54f0fbf6e2f096517a645782dc5d32e496e16027560ee7b63`.
  The readers are textbook 580 pages / 8,984,459 bytes /
  `0462ddc8ffcc901efbc81205f79a249ae716e838a6ec32eda033444a90b8755e`,
  worked answers 435 / 2,672,266 /
  `61f8a344cade529249d4f165bb62bce17579b6a4408b11634999e9f73ec9c01b`,
  and Sage lab 109 / 13,164,259 /
  `adb78966020355a90442c7ae68c734f1fd6b44b5d935a3f75e531ea666eeee4a`.
  All 1,124 pages rendered; source remained unchanged; all build gates passed.
  Full-size inspection confirms repaired textbook pages 28 and 92 plus adjacent
  pages 29 and 93 are readable and remain inside trim. The first unchanged v6
  match attempt was externally terminated during textbook pass 6, before any
  build report or comparison existed; it is rejected as a partial run. The
  persistent rerun then exited zero and emitted a successful 688,834-byte build
  report, SHA-256
  `2b463cbced3f53fbc4253d0ff5570878488a3af0a7ee241602c2258e0a6e10e0`.
  Its reproducibility status is `verified`, `matched` is true, and baseline and
  current fingerprints are exactly
  `fa8ceb8e983dd086deac7f86004003c02d2bb0c84a8ffa34df0f062da679e69f`.
  All three PDF byte counts and hashes exactly match run one. Source remained
  unchanged at 858 files / tree SHA-256
  `c0772dff373b103192c72f639e68a1e507d40e9ebdd102af98eb6475e8692c36`;
  all 2,064 reciprocal PDF actions resolve; all 1,124 pages render; controlled
  font inputs are private; and MetaPost, 73-file font closure, and 51 runtime
  font-dependency end verifications all pass.
- One-time terminology QA found no suitable Indonesian linear-algebra arXiv
  source, so it used the official 159-page UMSIDA Press fallback, DOI
  `10.21070/2020/978-623-6833-41-4`, PDF SHA-256
  `f687c749c0dee07538a7a5d1dc7b230306b83ec30574e8e75f5c3eb34cec995d`.
  The official article page is the retrieval authority and proves title,
  authors, extent, CC BY 4.0, and the PDF URL. The DOI remains its metadata
  identifier, but its resolver currently misdirects to an unrelated publisher
  title and was not used for retrieval.
  The comparison supports the edition's terminology. It adds explicit ledger
  records for `null space` -> `ruang nol` and `nullity` -> `nulitas`; no reader
  text requires propagation. Physical fallback pages 145 and 148 were visually
  checked. The live terminology ledger is 114 contiguous rows through
  HLA-T0114, 16,710 bytes / SHA-256
  `b41a97ec28b3d5d1f2151ba6947a6dcfcd26ee16ff7a4eb94471211fcde6f11b`.
  Eight focused terminology/backend tests were added; the combined focused
  backend suite passes 21 tests. The emitted backend deliberately remains stale
  at 112 terms until it is regenerated after the matched clean PDF pair.
- Edition and release surfaces now carry the exact production provenance
  `OpenAI Codex gpt-5.6-sol, Ultra.` while preserving original authorship and
  component credits. Public ZIP, repository, Figshare, credential-path, and
  final-PDF-audit paths now fail closed against local user-identity leakage.
  The focused privacy/PDF suite passes 15 tests and the full publication suite
  passes 142 tests. Because publication-driver bytes changed, transaction
  preflight and fingerprints must be created only after every final QA artifact
  is frozen.
- All reader-facing textbook, inline worked-answer, answer-book, and Sage-lab
  TeX files in the admitted edition closure have been translated through EOF.
  The relevant reader-distributed Sage/Python scripts are also localized while
  executable identifiers and mathematical operations are preserved.
- The independent complete-source audit closed with no P1/P2 finding after two
  mathematically verified, transparently marked Indonesian-edition-supplied
  answers were added for the two genuine upstream omissions in Input--Output
  Analysis. The authority source and official answer PDF remain unmodified.
- `00_control/ADVERSE_LEDGER.csv` contains 300 contiguous records through
  `HLA-A0300`; SHA-256
  `1cd6f195406c4bb4250177311389101c9c26a26cd4b139911cf72800fdf3b95e`.
- The translated source closure is 858 files and 53,980,804 bytes; canonical
  tree SHA-256
  `f5d5d1a7920f7add9c6dfb141cd6c4af79231f4d0ad00f8ca4f178e770f3c315`.
- The last provisional backend snapshot (schema `0.5.2`, 3,540 units, 3,527
  segments, 1,037 exercises, 1,037 answers, 432 assets, and 13,941 relations)
  is intentionally stale after the final notation-page source refinement and
  must not be treated as a current passing projection. Its historical manifest
  SHA-256 is
  `9faa2393a7036afd79a0e541a2ef4031f32589699b27637376464eb553d944c2`.
  The final backend will be regenerated twice only after the matched clean PDF
  pair, with 1,035 native answers, two derivative-supplied answers, and zero
  unanswered target exercises required again.
- The pinned official PDFs are recorded as authority artifacts: textbook 525
  pages, answer book 404 pages, and Sage lab 105 pages (1,034 pages total).
- The official lab PDF embeds all 64 generated PDF figures as vector Form
  XObjects. The bounded extraction tool
  reproduces 64 one-page figure PDFs deterministically (653,625 bytes total;
  manifest SHA-256
  `8bcbb15cce199f0b9f482c72b54f174f68ae0fc19199e293462c57382a5a99d0`).
  All 64 render nonblank and were visually reviewed in four contact sheets.
- The first full post-answer staging build compiled and rendered all three PDFs
  and resolved all 2,064 cross-PDF actions, but correctly failed because all
  148 Sage command blocks lacked executed SageTeX output. The 73-page lab is
  rejected.
- Ubuntu 22.04 WSL, SageMath 9.5, and the SageTeX 3.6.1 distribution are now
  installed and bounded to the disposable lab staging tree. Two consecutive
  integration runs produced the identical 148-label command-output closure:
  `lab.sagetex.sout` SHA-256
  `2f3c4b976d829fb1842302b1ddc41cf9d3ee134167379e1030d4335888e979a1`
  and `lab.sagetex.scmd` SHA-256
  `26d5db4f18d4beaee923520dad841e0218502ca700dbdb5260061f09a70f282c`.
  Sage changed exactly the expected 63 generated figures; all 64 pinned official
  figures were then restored and rehashed. The deterministic runtime-manifest
  SHA-256 is
  `9445f1e6aee67f41425dd8e830cc17f28ba6ea1bd031bf0ddea41caff1794f3b`.
- The production builder now includes PythonTeX plus that fail-closed SageTeX
  step. Builder SHA-256 is
  `bf15ac80827fa1fa4b4542ed19a10d647a08d9c7194f6166f7d45d9d80934de5`;
  Sage runner SHA-256 is
  `ddda97f69d3fb653c4b686ccf2dcce13791b065b837b2ed576915d3d08d248ac`.
- Final-log review exposed the still-open HLA-A0006 notation-table overflow.
  The source now uses bounded wrapping columns without changing any table
  content. A targeted 144-dpi review proved two explicit, headerless,
  horizontally and vertically centered pages with readable row spacing. The
  intermediate baseline was invalidated and removed because this final visual
  reflow changes the canonical source; both clean builds must now be rerun.
- A complete build of that final source then passed all reader/runtime/render
  gates, but its first baseline exposed error strings in the `makeindex` and
  `pdftoppm` tool-version fields. The builder now records the exact
  `makeindex.exe` bytes/SHA-256 and uses `pdftoppm -v`; builder SHA-256 is
  `99255760f702d64e45a526251a28b4ce8339c2aa2ee1b5410aaa00fee0dbddf0`.
  Because the builder identity changed, that baseline is rejected and both
  clean builds restart. The translated source remains unchanged.
- The first clean run with the corrected builder has now succeeded from the
  unchanged final source and recorded a new v2 baseline: 3,897 bytes, SHA-256
  `fc359ecfc5f356501297efc92baf78799519ccb5ed53967de35ab47a900924b0`.
  The tool projection contains no CLI error strings. It produced textbook
  580 pages / 8,984,178 bytes / SHA-256
  `0c91c32cdf1c690b7619020c4604ada0f12a700785e8387a01b999c8e87d6d3b`,
  worked answers 435 pages / 2,670,928 bytes / SHA-256
  `68bf13c0b6f6add8bff23609cce5da871ff17a77dd50e931479768eba5e2045e`,
  and lab 109 pages / 13,164,259 bytes / SHA-256
  `adb78966020355a90442c7ae68c734f1fd6b44b5d935a3f75e531ea666eeee4a`.
  Zero undefined references, runtime placeholders, or generated-English
  structural labels remain; all 2,064 reciprocal PDF actions resolve; all
  1,124 pages render. The second complete run is still mandatory.
- The first repeat attempt was externally terminated during textbook pass 3,
  after page 223, without a build report or reproducibility comparison. It is a
  discarded partial run. The accepted baseline and canonical source remain
  intact; restart the complete repeat from clean staging.
- A later complete restart exposed mutable shared MiKTeX font-map state between
  the textbook and answer-book processes. The edition now loads its five used
  pdfTeX maps explicitly, and the builder fail-closes 23 map, encoding, and Type
  1 font dependencies by exact bytes and SHA-256 without changing global
  MiKTeX. A full 435-page answer diagnostic passed with scalable body fonts; the
  sole Type 3 font is inherited inside pinned `map/pix/bridges.pdf` on reader
  page 299 and was visually verified intact at 144 dpi.
- Canonical source is now 858 files / 53,981,150 bytes, tree SHA-256
  `70bbff81288f44c0659c1d8f0e035a7ebde5bf25172c9955067dec624d70e9f3`.
  The 23 pinned font dependencies (1,594,916 bytes) and their component notices
  are preserved in the repository rather than resolved from mutable host TeX
  state. The complete closure is 35 files / 1,691,921 bytes / tree SHA-256
  `38c9e8f3fb6ca59d92fb16476f1a9b5789c1626062fefc98a661951b892d312c`.
  Builder SHA-256 is
  `64d0bde44c3e4b5571af32e4e5b2fa18b4d104eefe48c0481e942129acf7978e`;
  it validates the closure and checksum inventory, copies the exact 23 build
  dependencies into the private TeX tree, and reverifies both staged and source
  closure bytes at build end without using `kpsewhich` for resolution.
  The publication driver independently reconstructs the same path-neutral v3
  projection; 4 builder tests and 78 publication tests pass. Publication-driver
  SHA-256 is
  `4b60f8430b05b4ab797a00dffc8f52af99881e10116be68d99adeabda2babc52`.
- The first v3 foreground attempt was externally terminated during textbook
  pass 4 at page 450, with no report or baseline. It is discarded. The same
  command must run as a hidden task-local worker so app turn boundaries do not
  terminate it.
  The superseded v2 baseline `fc359ecf...` was hash-verified and removed; the
  next successful run must record a new v3 baseline and the following clean run
  must match it exactly.
- A hidden restart was intentionally stopped during textbook pass 1 page 537,
  before a report or baseline, to admit the repository-owned font closure just
  described. A subsequent staging-only run passed from the unchanged source and
  recovered the expected 7 book and 64 lab graphics. No v3 baseline existed at
  that checkpoint.
- The first complete run with the repository-owned closure has now succeeded
  and recorded v3 baseline SHA-256
  `1a7e0b5dbf9873588c5fa196929b40f4b2b63cba8343c5a23d3f2aa7733c7461`.
  It produced 580/435/109 pages with 1,124 renders, zero undefined references,
  zero runtime placeholders, zero generated-English structural labels, all
  2,064 reciprocal actions resolved, and both font-closure end checks true.
  This is accepted only as the first member; the second complete clean run is
  still mandatory.
- The complete second v3 run was not identical and is rejected. Diagnostic
  evidence proves the host default `pdftex.map`, 27 host Type 1 programs, 307
  incompletely fingerprinted MetaPost outputs, and omitted TeX intermediates
  were outside the claimed boundary. The first baseline and failed second run
  are preserved only under `tmp/repro_diagnostic_20260822/`.
- The prior v4 source tree was 858 files / 53,981,354 bytes / SHA-256
  `5c161ff7584a281156094bcebf4a78b5ec5d2ff98c362dc21c0c26c386093f5a`.
  Its first complete build is now superseded as a baseline: the repeat exposed
  volatile answer-only EPS conversion metadata plus one clipped topic opener.
  The repaired source tree is 858 files / 53,981,473 bytes / SHA-256
  `df240083cfd6c7a91438d087c7002482aca247cdec879399884e124b335ce2f1`.
  It retains the repository-owned map/trailer controls, selects exact official
  PDF graphic siblings, and applies only local content-preserving reflow fixes.
- The complete private embedded-font boundary is now 51 runtime files /
  2,289,616 bytes. Including notices and exact CTAN authority archives, its
  repository tree is 73 files / 10,325,900 bytes / SHA-256
  `542e2566a14b473654387a8a263cc1d49392e35db7058880d56f95cc6059ce56`.
  Map, encoding, PFB, and PFA searches are private-only; recorder audits reject
  external controlled font inputs.
- MetaPost uses explicit seed 1 and fingerprints all 307 generated figures.
  The bounded textbook/answer diagnostic succeeded: textbook convergence
  SHA-256 `f44a278fe2b90c8445f8284db018c28c9adb85c3dacdf64a51146d086e0d2a40`,
  answer convergence SHA-256
  `0db487bfd5215f6d5877eea2629999a09bdaf611b45847544466e5558c0e6ad8`,
  generated answer-stream SHA-256
  `e4094963573b6825a5585f32c378ae95d93adccba9f22f97359f1a2e8a0d96cf`,
  and recorded-input canonical SHA-256
  `45340fc6c652d1780cf7cbd4119eb9dfe79d6a62b8255bee523606eb06661388`.
  All 94 controlled records bind the 51 private closure files; 158 TFM/VF
  metric records are fingerprinted and no controlled input lacks a closure
  path.
- Final review strengthened the textbook contract again before either accepted
  v4 build: refresh the index after pass 5, prove pass 6 leaves the exact
  `.idx`/`.ind` fixed point unchanged after a second `makeindex`, then prove a
  seventh TeX pass leaves the complete state unchanged. Publication now also
  rehashes the live five-tool/51-runtime/73-file closure and preserves both
  authority PDFs in every offline source route.
- No upstream contact has occurred. No Git push, release, DOI publication, or
  central-hub handoff is yet claimed.

## Immediate next actions

1. Run the complete narrow publication test suite against the final release
   plan and frozen visual-review evidence.
2. Run authenticated Zenodo, GitHub, and Figshare preflights without mutating
   any frozen input.
3. Publish the existing Zenodo lineage, GitHub mirror, and one bounded
   reader-first Figshare item; anonymously download and hash every public byte.
4. Write the central-curriculum integration handoff and the durable decision
   not to contact upstream unless one deduplicated high-confidence source issue
   is actually supported by the completed corpus audit.

## Blocking condition

None. No failed or placeholder-bearing lab artifact is eligible for publication.

## 2026-08-23 — final backend and visual-release gate passed

- A live publication-gate check found that the otherwise exact v6 build report
  retained the local absolute spelling of its reproducibility-baseline path.
  Only that JSON value was normalized to the portable project-relative
  `tmp/hefferon_id_reproducibility_baseline_v6.json`; source, baseline bytes,
  reproducibility fingerprints, PDFs, renders, links, and build results were
  unchanged. The final report is 688,743 bytes / SHA-256
  `c371bf8a1527602ba57af9ad0b6ff0225a96f8882d4f2a226d336090e1370851`.
- The locale-neutral backend was then regenerated twice and matched exactly.
  `backend/manifest.json` is 2,154 bytes / SHA-256
  `4c79fad12bda1552f03d6dae7c962f4d7a51ff68b3dcef09e88c437bfe773fad`.
  Final-build validation passes with 8,132 records, 3,541 units, 3,528
  segments, 1,037 exercises, 1,037 answers, 13,999 relations, 432 assets,
  114 terms, 307 corrections, and zero unanswered exercises.
- The regenerated final automated PDF audit is 4,002,372 bytes / SHA-256
  `d2b529e787accc685a9b07080f610bfdc70d252714f56b1747928ee18dc4e22d`.
  It covers all 1,124 rendered pages and has zero hard failures.
- The regenerated machine-readable human visual-review receipt is 482,412
  bytes / SHA-256
  `78c475d4e6b3bc347327333b0b064e34400a6430528750cb2dd678941c43a240`.
  It records pass dispositions for all 57 contact sheets, all 532 ranked
  candidates, 534 manifest-bound full-page inspections, and all five review
  findings, with zero unresolved findings. The focused nine-test gate passes.
- The release plan now includes `qa/visual_review/final-2b463cbced3f` in the
  provenance archive, repository snapshot, and staging-input closure, so the
  reviewed 57-sheet evidence remains reproducible rather than being referenced
  only by a JSON receipt. The plan is 8,320 bytes / SHA-256
  `458d585b26a522e79eaccd382b9a8b405b95060dbfa68fca0b8107f498b7f896`.
- The focused privacy suite passes six tests. No remote mutation or upstream
  contact has occurred at this checkpoint.

Disposition: run the complete publication suite, then freeze, publish, and
anonymously verify all three authorized preservation channels without another
confirmation pause.
