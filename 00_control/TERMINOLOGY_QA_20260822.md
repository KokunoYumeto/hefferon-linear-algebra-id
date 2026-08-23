# Terminology QA — Indonesian linear-algebra usage

Date: 2026-08-22
Status: complete; no reader-text propagation required

## Search and fallback

Direct arXiv searches for `aljabar linear`, `aljabar linier`, and `ruang
vektor` returned no suitable Indonesian linear-algebra source with downloadable
TeX. A direct arXiv API check of the exact quoted all-field queries returned
`totalResults = 0` for each of those three phrases on 2026-08-22. The required
fallback therefore uses the official open textbook record:

- Nuril Lutvi Azizah and Novia Ariyanti, *Buku Ajar Mata Kuliah Dasar-Dasar
  Aljabar Linear* (UMSIDA Press, 2020/2021), DOI
  `10.21070/2020/978-623-6833-41-4`;
- official article record:
  `https://press.umsida.ac.id/index.php/umsidapress/article/view/978-623-6833-41-4`,
  which identifies the title, authors, 159-page extent, CC BY 4.0 license, and
  `citation_pdf_url` used for retrieval;
- the DOI remains the work identifier shown in that official metadata, but its
  resolver currently redirects to a different UMSIDA title, so the DOI resolver
  was not treated as the retrieval route;
- downloaded PDF: 159 pages, 1,675,339 bytes, SHA-256
  `f687c749c0dee07538a7a5d1dc7b230306b83ec30574e8e75f5c3eb34cec995d`;
- extracted UTF-8 text: 230,804 bytes, SHA-256
  `7ef9a6a5a5d57182e266e0611e200a17c33052455098c70b90f3264779e3b8fd`.

The PDF was inspected directly, including physical pages 145 and 148. It is
representative evidence of Indonesian classroom usage, but not a prescriptive
house-style authority: it alternates `linear`/`linier`, `variabel`/`peubah`,
`sub ruang`/`sub-ruang`, and `transpose`/`transpos`, and contains visible
copyediting errors.

## Decisions

The reference supports the edition's existing consistent choices: `aljabar
linear`, `ruang vektor`, `rentang`/`merentang`, `hasil kali titik`, `ortogonal`,
`ruang baris`, `ruang kolom`, `rank`, `basis`, `dimensi`, and `determinan`.
Existing variants such as `peubah`, `unsur matriks`, and `eliminasi Gauss`
remain valid contextual variants. No already translated reader sentence needs
revision.

One substantive clarification was added to `TERMINOLOGY.csv`: use `ruang nol`
for *null space* and reject `ruang kosong`, because the space always contains
the zero vector. `Nulitas` remains the preferred term for *nullity*; the
fallback's `kekosongan` is only a recorded variant and `nullitas` is rejected
as an unnormalized spelling.

The edition and release metadata also record the production provenance exactly
as: `OpenAI Codex gpt-5.6-sol, Ultra.` Original author, source, and component
credits remain unchanged.
