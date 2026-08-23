# Pinned pdfTeX font closure

This directory contains the exact font-map, encoding, and embedded Type 1 font
bytes needed by the Indonesian Hefferon pdfTeX readers. Runtime files were
copied without modification from matching upstream distributions. The reader
style first loads `maps/hefferon-standard.map` without a modifier, which
suppresses pdfTeX's mutable system `pdftex.map`, and then appends the five
repository-owned component maps. The build also makes map, encoding, and Type
1 searches private-only and rejects any recorded external input of those
types.

The machine-readable inventory is `THIRD_PARTY_NOTICES.json`. It groups the
exact runtime paths by package and records license, notice, source, and CTAN
authority-archive routes. `SHA256SUMS` binds every individual payload,
provenance file, and these two documentation files; `SHA256SUMS` necessarily
does not contain a checksum for itself.

## Components and license routes

- **CM-Super runtime files** (`cm-super-*.map`, `cm-super-*.enc`, and the
  `sf*.pfb` files) are distributed under GPL-2.0-or-later with the package's
  stated special exception for including the font programs in PostScript or
  PDF documents. The preserved notices are `licenses/cm-super/README` and
  `licenses/cm-super/COPYING`.
- **AMSFonts 3.04** supplies the 25 unmodified Computer Modern, Euler, LaTeX
  line/circle, and AMS symbol Type 1 programs used by the two readers. They
  follow SIL Open Font License 1.1. The license, FAQ, package README, and exact
  CTAN authority archive are retained under `licenses/amsfonts/` and
  `sources/amsfonts-3.04-ctan.zip`.
- **RSFS** supplies the unmodified `rsfs10.pfb`. Ralph Smith's source notice
  permits use and distribution and requires a renamed, credited fork if
  modified; Taco Hoekwater's Type 1 conversion notice donates that conversion
  to the public domain without adding restrictions. Both notices and the exact
  CTAN archive are retained.
- **URW Base 35** supplies the unmodified patched Nimbus Sans Regular 1.05a
  byte `uhvr8a.pfb` under GNU GPL version 2. The matching CTAN archive,
  `README.base35`, and `COPYING` are retained.
- **Bera Type 1 fonts** (`fvmr8a.pfb`, `fvsb8a.pfb`, and `fvsr8a.pfb`) follow
  the Bitstream Vera font license preserved in `licenses/bera/LICENSE`.
  `maps/bera.map` is Bera TeX support material distributed under LPPL-1.2-or-
  later as stated in `licenses/bera/README`.
- **URW Grotesq** (`maps/ugq.map` and `type1/ugqb8a.pfb`) follows the
  GPL-2.0-or-later route stated in
  `licenses/urw-grotesq/readme.grotesq`; the GPL text is preserved at
  `licenses/cm-super/COPYING`.
- **BrushScriptX** (`maps/pbsi.map` and
  `type1/BrushScriptX-Italic.pfa`) is identified as public domain by
  `licenses/brushscr/README`.
- **TeX Base 1 encoding** (`encodings/8r.enc`) is preserved with its own
  PSNFSS header. `licenses/psnfss/manifest.txt` records the PSNFSS carriage
  and expressly separates `8r.enc` from the bundle-distribution restriction;
  `licenses/dvips/dvips.tpm` records the installed dvips package's GPL route,
  with the GPL text preserved at `licenses/cm-super/COPYING`.

The CM-Super source archive at `sources/cm-super-src.tar.bz2` is retained as
provenance and corresponding-source support material. It is not represented as
a complete, independently reproducible tree for regenerating the exact
optimized and hinted PFB files: the upstream README describes additional tools
and processing, including TeXtrace, AutoTrace, Ghostscript, t1utils, Perl
scripts, and FontLab 3.1.

The three dated CTAN ZIPs are durable authority/source-distribution evidence,
not transient downloads. Their exact URLs, byte counts, and SHA-256 hashes are
recorded in `THIRD_PARTY_NOTICES.json`.

No component name, author name, organization name, or trademark is used to
imply endorsement of this project.

## Integrity check

From this directory, verify every line of `SHA256SUMS` against the named file.
The expected inventory and per-component provenance can then be independently
checked against `THIRD_PARTY_NOTICES.json`. Paths use forward slashes and are
relative to this directory.
