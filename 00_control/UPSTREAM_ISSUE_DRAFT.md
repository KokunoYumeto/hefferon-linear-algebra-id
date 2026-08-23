# Upstream issue decision — Hefferon Linear Algebra

Status: **LOCAL DRAFT ONLY — DO NOT CONTACT UPSTREAM DURING PRODUCTION**  
Decision: one concise issue is warranted after the complete Indonesian corpus
has been published. Do not split these points into separate issues and do not
start a follow-up conversation.

Authority examined:

- official project: `https://gitlab.com/jim.hefferon/linear-algebra`
- commit: `df2262e089a02651c127f1dd12649c4622ee1383`
- source tree: `30340725aa2641b3c617b1584c59f6df83e1fdf3`
- authority `src/gr/gr1.tex`: 205,306 bytes; SHA-256
  `393dc48dba25974d3c746768474a6dfbcd9491db2c09db41f6c2a3ca17432da9`
- authority `src/gr/leontief.tex`: 24,617 bytes; SHA-256
  `948e6622753d46a7d3433382bd9e9719b216bcccab45790c38f3a782850e3974`
- checked Indonesian target `src/gr/gr1.tex`: 216,589 bytes; SHA-256
  `b67d5b04a97f977d9636152530a508ac6bc1a9d3a6bde1288d368226478c8c0f`;
  corrected loci are lines 1004-1005, 4248-4251, 5290-5291, and 5304-5307
- checked Indonesian target `src/gr/leontief.tex`: 29,946 bytes; SHA-256
  `1d6bd36fc5e6be37453b104cd7403dc1e64b3ef5472767d33e245956c7d085b1`;
  transparently marked supplied-answer blocks are lines 515-548 and 602-644
- official `book.pdf`: SHA-256
  `5240f2782e645bc6351ad9eba69d8c19500142a5cca9c90450c17b3765a1a400`
- official `jhanswer.pdf`: SHA-256
  `6e1761061c136a984400198f62253cf208ca36ddee81415ae13de81319b5429d`

Selected ledger evidence: HLA-A0007, HLA-A0023, HLA-A0031, HLA-A0028,
and HLA-A0300. These are deduplicated, locally reproducible defects with
mechanical corrections. All other ledger rows are intentionally excluded from
this issue because they are broader, lower-priority, interpretive, already
subsumed, or specific to the Indonesian derivative.

## Proposed single issue

**Title:** Five localized source errata at `df2262e`

Against commit `df2262e089a02651c127f1dd12649c4622ee1383`, these five
localized defects are directly reproducible:

1. `src/gr/gr1.tex:1000-1005`, the step
   `(1/2)\rho_2+\rho_3`: the source changes `-2y-z=-5` to
   `-2y-1=-5` and gives `(3/2)z=7/2`. The row operation instead preserves
   `-z` and gives `(3/2)z=9/2`, consistent with the stated `z=3`.
2. `src/gr/gr1.tex:4265-4279`, the matrix following
   `\nearbyexample{ex:HomoZeroOnlySol}`: its second row is printed
   `(6,-4,0)`, but the cited system and reduction at lines 3655-3675 use
   `(6,4,0)`. The matrix entry should be `+4`.
3. `src/gr/gr1.tex:5314-5328`, the membership item for `(1,4,14)`: the
   answer says “Yes” with `k=4,m=-3`. The first two coordinates actually
   force `k=2,m=3`, making the third coordinate `16`, not `14`; the answer
   should be “No.”
4. `src/gr/gr1.tex:5331-5342`, the answer that doubles and triples
   `(2,-5)`: the tripled generator is printed `(6,-55)` and should be
   `(6,-15)`.
5. `src/gr/leontief.tex:471-560`, the final two Input-Output Analysis
   exercises contain no `answer` environments. The official `book.pdf`
   nevertheless links them to `ans.One.V.0.5` and `ans.One.V.0.6`; neither
   destination exists in the official `jhanswer.pdf`. Adding answers or
   suppressing those two links would close the dead targets.

— Codex, on the user's request.
