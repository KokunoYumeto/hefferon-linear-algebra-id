#!/usr/bin/env python3
"""Focused tests for the deterministic Hefferon id-ID build contract."""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).with_name("build_hefferon_id.py")
PROJECT_ROOT = MODULE_PATH.parent.parent
SPEC = importlib.util.spec_from_file_location("hefferon_build", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


EXPECTED_FONT_DEPENDENCIES = {
    "hefferon-standard.map": (
        "maps",
        1402,
        "943c2cf5f3b69e428c313c3e62326c4f80ef1c0652407bc011a55b68334d6c87",
    ),
    "cm-super-t1.map": (
        "maps",
        32335,
        "226289f0eeddb7426a1ba1987af893df82174b433743a1c02d87d83240d59e56",
    ),
    "cm-super-ts1.map": (
        "maps",
        27973,
        "e7906fae5ee5d56fe8343f245a8c440670420b98dcb4dec055046221d35c82d1",
    ),
    "bera.map": (
        "maps",
        1044,
        "f7a09a12f0bae99c5d81aaa714ab6a809d186aa9a49b193e2f98cee8d7f3fff5",
    ),
    "ugq.map": (
        "maps",
        184,
        "0c0c975c2d03492cbf577575547b166a91d3929c95c8666abf967cfb00f3eb6a",
    ),
    "pbsi.map": (
        "maps",
        210,
        "54813ca4f26ca6e04f396209d975e25336454c1a68c9f673adecbb500f7928cf",
    ),
    "cm-super-t1.enc": (
        "encodings",
        2971,
        "0b8a4865363ad2acb3718af53a43a8b1a16a143900bba8e672813d4a6e07b4fc",
    ),
    "cm-super-ts1.enc": (
        "encodings",
        2900,
        "558da5de87db45ed719dda9c679e6b164d520b21d9100357dcf17124291ed97c",
    ),
    "8r.enc": (
        "encodings",
        4993,
        "4b74cff10f36f444270ed8f0c576b4e7b605538aa2f6b99a77bc9129f07e4a17",
    ),
    "sfssdc10.pfb": (
        "type1",
        149381,
        "60b674ac5edbd2f49db48b46e95804fd91aa4dce987f9454a3069160cdef12da",
    ),
    "sfoti10.pfb": (
        "type1",
        170923,
        "c39fe0a8559c893bc4bbfa247abd75d22e69bcfd39153f97a0b6e91de510504b",
    ),
    "sfocc10.pfb": (
        "type1",
        102054,
        "5a9e668ccf717579f0895859b73e242fcb7bd420cff245c188cadee0274c26b2",
    ),
    "sfosl10.pfb": (
        "type1",
        130712,
        "ac4336eb7a7dfb6d188dabe004b08331b9ee8674a37732a26454584e82db5e1a",
    ),
    "sform5.pfb": (
        "type1",
        130755,
        "d317f5d0ed8d0b12c21764976fe2291bd30344f9eba85dbe6258cff95bae9f70",
    ),
    "sform6.pfb": (
        "type1",
        132848,
        "4874948fe50731f4411c3729ab3a394be93222e3012e753cf3061fb939e35ab6",
    ),
    "sform7.pfb": (
        "type1",
        128188,
        "5dec921f263037b2be59b3c1e15b3f69f0198200484b3fc31e7f0bf27c70900a",
    ),
    "sform8.pfb": (
        "type1",
        129377,
        "d454b14229cd7c49ac3e77c5762700856cb254c56f2f695a144338500b4ce2ea",
    ),
    "sform9.pfb": (
        "type1",
        126436,
        "be25d646b1b4bf5dc4f7defea590211566d6c1de68c2d56ecdaaf07358bee625",
    ),
    "sform10.pfb": (
        "type1",
        127772,
        "f6e2c981d84638f36548431f4a3ae2e65577b585dcc1e08e1ef2d9cd79609dcc",
    ),
    "fvmr8a.pfb": (
        "type1",
        29228,
        "6c3f939eb29b72b597464010001935af5eddb05c3031a25c1f66633d68e5cd8c",
    ),
    "fvsb8a.pfb": (
        "type1",
        29275,
        "755d71a280ba7d1b77a7cc0f826cf2da2468e4733cbbcc494d7f96c7ae47cb4d",
    ),
    "fvsr8a.pfb": (
        "type1",
        29095,
        "aab1418ee7723378b02505a5e63b2fb8e39cfe58e92eeb3038acc97770940181",
    ),
    "ugqb8a.pfb": (
        "type1",
        29942,
        "e5ff54b29562b758aaeb20c3a1a70b931f418f0278a9cf367b9cc49cac334c4b",
    ),
    "BrushScriptX-Italic.pfa": (
        "type1",
        76320,
        "bf0f78dfa79365fa21af7efa46c742907b2e7dd70c53f26c8d4e74c5b55516f0",
    ),
    "cmex10.pfb": ("type1", 30251, "791b31aa1db8608d0144b3a40fc0fe53383a60f6b00d0e8fd9f06ac4a11df8cb"),
    "cmmi10.pfb": ("type1", 36299, "e3661061e8aa474d6de5ffa916edceb0e3d8b998862018c147f0357fce00bcd7"),
    "cmmi5.pfb": ("type1", 37912, "35048e58e53f4aa53025069c1d0de33a16d8d4c111bfa329669e6456ec0a967b"),
    "cmmi7.pfb": ("type1", 36281, "5b293a581ddb937b02559c3ce1a60184cc434295533204a2cd3864a6ad8a1f53"),
    "cmr10.pfb": ("type1", 35752, "fdcede8794018df5f2b58f0905fb20a2b418ed8f67b73ee12445855dfbe5b1be"),
    "cmsy10.pfb": ("type1", 32569, "62ee8cef552017551cd3e026a483e700730103eceaad959c87b7730017f59cff"),
    "cmsy5.pfb": ("type1", 32915, "46da57e5a06866efa9a20f3dd350811b5d3279a5ae789af63e530f1f570e3c7f"),
    "cmsy7.pfb": ("type1", 32716, "583b65bd1857bffc2ab184fcb4aad4e70e12eb05c9ca9f1c58c9a00a86c8bccf"),
    "euex10.pfb": ("type1", 12536, "a93b3c5d1e64c2305c1648de7c7b4903c55b5a59a816e37222e8ec8c418cc605"),
    "eufm10.pfb": ("type1", 21098, "0d4adc0d8d6b3fd993fe138b6863126d7122cd1ae180d0a19eca0759bf7d0975"),
    "eufm5.pfb": ("type1", 21550, "5e9e9e208ecdc198f68f87785ef84fccf3ab93291c7ead0a9ea1b1d6107983ee"),
    "eufm7.pfb": ("type1", 21251, "8c5202802ed024ad905ab81b34a882c9473acf9e9ab7a717bcee3f0f57e985f2"),
    "eurb10.pfb": ("type1", 22394, "2aa1cd6768ce9159f7704593b58e4e24c846cea7d789242266aee31d1e74b900"),
    "eurm10.pfb": ("type1", 22644, "988a860101f4b64cc0ca6e9b7b065db1b316e78da5d1838c89524bf098e4aec6"),
    "eurm5.pfb": ("type1", 23170, "5cb5143825f985edc442eb71038f001ef5076c33702fba67484cfa5da118a7ef"),
    "eurm7.pfb": ("type1", 22927, "df9a5603b3d8777ca91530bb8cb771b0ca84f5b464a29fb4ab65d9b98149c9f3"),
    "eusm10.pfb": ("type1", 10538, "eb4a18f8f72bef82051509701331e459cd547c573b74430401cb699812a66a59"),
    "eusm7.pfb": ("type1", 10655, "71d135350b292822e5b5d96cf3dd07c9da3fa3e88a0b298b42110e9f98b9c536"),
    "lcircle1.pfb": ("type1", 10594, "503d59829700006b46d6ddf4f90b045ee7f08350f89544b302e7d73711c4b68f"),
    "line10.pfb": ("type1", 11493, "8bed0f3db560ddcd98fb1a1e9d58aed3ab2aef553c4364a32841b51ee5dc84a7"),
    "linew10.pfb": ("type1", 11895, "415d63b2859d9dc7ba7e4c83a5e73463d059cfdb03bd3a8f509c211cdb166315"),
    "msam10.pfb": ("type1", 31764, "f2e3b470b988a46272125e917531690d3c4d03ac7238f112b07337f972a537fa"),
    "msam7.pfb": ("type1", 33366, "c96c9138119d9879757ad8c1ecb2cc25b0cac303ba3ee13d25d117fdbc71d2f3"),
    "msbm10.pfb": ("type1", 34694, "d2121de7e7c14490a2d352e3b62e62882d6c300235464bfa577e6055696e6e62"),
    "msbm7.pfb": ("type1", 35309, "bd86d36def0f2d226cf773a195a88f88e424759f3ddaaf654de2ae670906734e"),
    "rsfs10.pfb": ("type1", 16077, "60ba5026b2feb5cac34615abbcaaa4e9746b43c1f9ad9c0a81b97fa60ac69a26"),
    "uhvr8a.pfb": ("type1", 44648, "bb553b044d70f86c879229d4f9b6ae191176d21775f6746921165c877f4748d9"),
}


class FontDependencyContractTests(unittest.TestCase):
    def test_exact_repository_owned_dependency_closure(self) -> None:
        self.assertEqual(len(EXPECTED_FONT_DEPENDENCIES), 51)
        self.assertEqual(
            BUILD.PDFTEX_FONT_CLOSURE,
            BUILD.PROJECT_ROOT / "tools" / "pdftex-font-closure",
        )
        self.assertEqual(
            BUILD.PDFTEX_FONT_BUCKETS,
            {
                ".map": "maps",
                ".enc": "encodings",
                ".pfb": "type1",
                ".pfa": "type1",
            },
        )
        self.assertEqual(
            {
                name: (expected_bytes, expected_sha256)
                for name, expected_bytes, expected_sha256
                in BUILD.PDFTEX_FONT_DEPENDENCIES
            },
            {
                name: (expected_bytes, expected_sha256)
                for name, (_bucket, expected_bytes, expected_sha256)
                in EXPECTED_FONT_DEPENDENCIES.items()
            },
        )

        expected_by_bucket = {"maps": set(), "encodings": set(), "type1": set()}
        for name, (bucket, expected_bytes, expected_sha256) in (
            EXPECTED_FONT_DEPENDENCIES.items()
        ):
            expected_by_bucket[bucket].add(name)
            path = BUILD.PDFTEX_FONT_CLOSURE / bucket / name
            with self.subTest(dependency=name, path=path):
                self.assertEqual(
                    BUILD.pdftex_font_dependency_source(name), path.resolve()
                )
                self.assertTrue(path.is_file())
                self.assertEqual(path.stat().st_size, expected_bytes)
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(), expected_sha256
                )

        for bucket, expected_names in expected_by_bucket.items():
            with self.subTest(bucket=bucket):
                actual_names = {
                    path.name
                    for path in (BUILD.PDFTEX_FONT_CLOSURE / bucket).iterdir()
                    if path.is_file()
                }
                self.assertEqual(actual_names, expected_names)

    def test_source_map_directives_are_exactly_the_required_closure(self) -> None:
        style = (
            BUILD.SOURCE_ROOT / "src" / "sty" / "bookjhconcrete.sty"
        ).read_text(encoding="utf-8")
        expected_maps = {
            name
            for name, (bucket, _bytes, _sha256) in EXPECTED_FONT_DEPENDENCIES.items()
            if bucket == "maps"
        }
        base_maps = re.findall(r"\\pdfmapfile\{([^+=][^}]*)\}", style)
        appended_maps = re.findall(r"\\pdfmapfile\{\+([^}]+)\}", style)
        self.assertEqual(base_maps, ["hefferon-standard.map"])
        self.assertEqual(
            set(appended_maps), expected_maps - {"hefferon-standard.map"}
        )
        self.assertEqual(len(appended_maps), len(expected_maps) - 1)
        self.assertEqual(style.count(r"\pdftrailerid{}"), 1)

    def test_font_program_map_and_encoding_searches_are_private_only(self) -> None:
        env = BUILD.command_environment()
        for name in ("T1FONTS", "ENCFONTS", "TEXFONTMAPS"):
            with self.subTest(variable=name):
                self.assertNotEqual(env[name], "")
                self.assertFalse(env[name].endswith(os.pathsep))
                self.assertEqual(env[name].count(os.pathsep), 0)

    def test_rights_and_authority_inventory_binds_complete_closure(self) -> None:
        closure = BUILD.inspect_pdftex_font_closure()
        self.assertEqual(closure["file_count"], 73)
        self.assertEqual(closure["bytes"], 10325900)
        self.assertEqual(
            closure["tree_sha256"],
            "542e2566a14b473654387a8a263cc1d49392e35db7058880d56f95cc6059ce56",
        )

    def test_tex_commands_enable_recorder_and_metapost_closure_is_exact(self) -> None:
        self.assertIn("-recorder", BUILD.tex_command("pdflatex", "book"))
        self.assertEqual(sum(BUILD.EXPECTED_METAPOST_OUTPUT_COUNTS.values()), 307)
        self.assertEqual(
            set(BUILD.EXPECTED_METAPOST_OUTPUT_COUNTS),
            {source for source, _output in BUILD.METAPOST_ASSETS},
        )
        self.assertEqual(BUILD.METAPOST_RANDOM_SEED, 1)

    def test_book_index_is_refreshed_verified_and_then_tex_converged(self) -> None:
        commands: list[str] = []
        index_state = {
            "schema_version": "hefferon-id-book-index-state-v1",
            "file_count": 2,
            "bytes": 2,
            "canonical_sha256": "a" * 64,
            "files": [],
        }

        def record(name, *_args, **_kwargs):
            commands.append(name)
            return mock.Mock(returncode=0)

        convergence = {
            "schema_version": "hefferon-id-tex-convergence-v1",
            "job": "book",
            "comparison_pass": 7,
            "matched": True,
            "state": {},
        }
        with (
            mock.patch.object(BUILD, "run_command", side_effect=record),
            mock.patch.object(
                BUILD, "inspect_book_index_state", side_effect=[index_state, index_state]
            ),
            mock.patch.object(
                BUILD, "require_tex_convergence", return_value=convergence
            ) as require_convergence,
        ):
            result = BUILD.build_book({}, [])

        self.assertLess(
            commands.index("book_makeindex_refresh_after_pass_5"),
            commands.index("book_pdflatex_6"),
        )
        self.assertLess(
            commands.index("book_pdflatex_6"),
            commands.index("book_makeindex_verify_after_pass_6"),
        )
        require_convergence.assert_called_once_with("book", 7, {}, [])
        self.assertTrue(result["index_fixed_point"]["matched"])

    def test_book_index_drift_fails_before_final_tex_convergence(self) -> None:
        with (
            mock.patch.object(BUILD, "run_command"),
            mock.patch.object(
                BUILD,
                "inspect_book_index_state",
                side_effect=[{"canonical_sha256": "a"}, {"canonical_sha256": "b"}],
            ),
            mock.patch.object(BUILD, "require_tex_convergence") as require_convergence,
        ):
            with self.assertRaisesRegex(BUILD.BuildFailure, "index input/output changed"):
                BUILD.build_book({}, [])
        require_convergence.assert_not_called()

    def test_reproducibility_projection_excludes_machine_paths(self) -> None:
        report = {
            "source": {"tree_sha256": "1" * 64},
            "authority_book_pdf": {
                "path": "C:/machine/authority/book.pdf",
                "sha256": "a" * 64,
            },
            "authority_lab_pdf": {
                "path": "C:/machine/authority/lab.pdf",
                "sha256": "b" * 64,
            },
            "book_graphics": {"manifest_sha256": "2" * 64},
            "lab_graphics": {"manifest_sha256": "3" * 64},
            "missing_lab_asset": {"manifest_sha256": "4" * 64},
            "lab_sagetex": {"stable_fingerprint": {"seed": 1}},
            "metapost_assets": {
                "schema_version": "hefferon-id-metapost-assets-v1",
                "random_seed": 1,
                "source_date_epoch": "1633046400",
                "asset_count": 1,
                "bytes": 2,
                "canonical_sha256": "e" * 64,
                "files": [{"path": "ch.1", "bytes": 2, "sha256": "f" * 64}],
                "manifest_path": "C:/machine/metapost.json",
                "manifest_bytes": 3,
                "manifest_sha256": "0" * 64,
            },
            "metapost_assets_end_verification": {
                "asset_count": 1,
                "bytes": 2,
                "canonical_sha256": "e" * 64,
                "all_verified": True,
            },
            "generated_answer_stream": {
                "path": "C:/machine/bookans.tex",
                "bytes": 11,
                "sha256": "1" * 64,
                "all_answers": 1,
                "topic_count": 1,
                "topic_answers": 1,
                "expected_native_topic_answers": 1,
                "expected_indonesian_edition_supplied_topic_answers": 0,
                "expected_topic_answers": 1,
                "topic_answer_entries": [{"topic_ordinal": 1}],
            },
            "tex_convergence": {"book": {"matched": True}},
            "pdftex_input_audit": {
                "schema_version": "hefferon-id-pdftex-input-audit-v1",
                "all_map_encoding_font_program_inputs_private": True,
                "jobs": ["book", "jhanswer"],
                "controlled_input_count": 1,
                "metric_input_count": 1,
                "controlled_inputs": [{"name": "fixture.map"}],
                "metric_inputs": [{"name": "fixture.tfm"}],
                "canonical_sha256": "2" * 64,
                "path": "C:/machine/pdftex-input-audit.json",
                "bytes": 4,
                "sha256": "3" * 64,
            },
            "build_tools": {"builder": {"sha256": "5" * 64}},
            "tool_versions": {"python": "fixture"},
            "pdftex_font_dependencies": {
                "fixture.map": {
                    "source_path": "C:/machine/source/fixture.map",
                    "staged_path": "C:/machine/staged/fixture.map",
                    "bytes": 7,
                    "sha256": "6" * 64,
                }
            },
            "pdftex_font_dependencies_end_verification": {
                "dependency_count": 1,
                "bytes": 7,
                "all_verified": True,
            },
            "pdftex_font_closure": {
                "path": "C:/machine/source/pdftex-font-closure",
                "file_count": 35,
                "bytes": 1700000,
                "tree_sha256": "a" * 64,
                "sha256sums_bytes": 2500,
                "sha256sums_sha256": "b" * 64,
                "third_party_notices_bytes": 16000,
                "third_party_notices_sha256": "c" * 64,
                "readme_bytes": 2800,
                "readme_sha256": "d" * 64,
            },
            "pdftex_font_closure_end_verification": {
                "file_count": 35,
                "bytes": 1700000,
                "tree_sha256": "a" * 64,
                "all_verified": True,
            },
            "pdfs": {
                "book": {"pages": 1, "bytes": 2, "sha256": "7" * 64},
                "jhanswer": {"pages": 1, "bytes": 2, "sha256": "8" * 64},
                "lab": {"pages": 1, "bytes": 2, "sha256": "9" * 64},
            },
        }
        other_machine_report = {
            **report,
            "authority_book_pdf": {
                **report["authority_book_pdf"],
                "path": "/opt/other/authority/book.pdf",
            },
            "authority_lab_pdf": {
                **report["authority_lab_pdf"],
                "path": "/opt/other/authority/lab.pdf",
            },
            "pdftex_font_dependencies": {
                "fixture.map": {
                    **report["pdftex_font_dependencies"]["fixture.map"],
                    "source_path": "/opt/other/source/fixture.map",
                    "staged_path": "/tmp/other/staged/fixture.map",
                }
            },
            "pdftex_font_closure": {
                **report["pdftex_font_closure"],
                "path": "/opt/other/source/pdftex-font-closure",
            },
            "metapost_assets": {
                **report["metapost_assets"],
                "manifest_path": "/tmp/other/metapost.json",
            },
            "generated_answer_stream": {
                **report["generated_answer_stream"],
                "path": "/tmp/other/bookans.tex",
            },
            "pdftex_input_audit": {
                **report["pdftex_input_audit"],
                "path": "/tmp/other/pdftex-input-audit.json",
            },
        }
        fingerprint = BUILD.reproducibility_fingerprint(report)
        other_machine_fingerprint = BUILD.reproducibility_fingerprint(
            other_machine_report
        )
        self.assertEqual(
            fingerprint["schema_version"], "hefferon-id-build-reproducibility-v4"
        )
        self.assertEqual(fingerprint, other_machine_fingerprint)
        self.assertEqual(
            fingerprint["pdftex_font_dependencies"],
            {"fixture.map": {"bytes": 7, "sha256": "6" * 64}},
        )
        self.assertNotIn("source_path", str(fingerprint))
        self.assertNotIn("staged_path", str(fingerprint))
        self.assertNotIn("C:/machine/source", str(fingerprint))
        self.assertNotIn("/opt/other/source", str(fingerprint))
        self.assertEqual(
            fingerprint["authority_pdf_sha256"],
            {"book": "a" * 64, "lab": "b" * 64},
        )
        changed_authority = {
            **report,
            "authority_book_pdf": {
                **report["authority_book_pdf"],
                "sha256": "c" * 64,
            },
        }
        self.assertNotEqual(
            fingerprint, BUILD.reproducibility_fingerprint(changed_authority)
        )

    def test_end_verification_fails_after_staged_byte_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.map"
            payload = b"stable-font-map"
            path.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            dependencies = (("fixture.map", len(payload), digest),)
            resolved = {"fixture.map": {"staged_path": str(path)}}
            with mock.patch.object(BUILD, "PDFTEX_FONT_DEPENDENCIES", dependencies):
                self.assertTrue(
                    BUILD.verify_staged_pdftex_font_dependencies(resolved)[
                        "all_verified"
                    ]
                )
                path.write_bytes(payload + b"!")
                with self.assertRaises(BUILD.BuildFailure):
                    BUILD.verify_staged_pdftex_font_dependencies(resolved)

    def test_reader_reflow_repairs_are_bound_to_translated_source(self) -> None:
        source_root = PROJECT_ROOT / "source" / "linear-algebra" / "src"
        fields = (source_root / "vs" / "fields.tex").read_text(encoding="utf-8")
        answer_style = (source_root / "sty" / "answerjh.sty").read_text(
            encoding="utf-8"
        )
        markov = (source_root / "map" / "markov.tex").read_text(encoding="utf-8")
        gr1 = (source_root / "gr" / "gr1.tex").read_text(encoding="utf-8")
        ppivot = (source_root / "gr" / "ppivot.tex").read_text(encoding="utf-8")

        self.assertEqual(
            fields.count("\\par\\vfill\\pagebreak\n\\begin{center}"), 1
        )
        topic_override = answer_style.split("\\renewcommand{\\topic}[1]{", 1)[1]
        topic_override = topic_override.split("\n}", 1)[0]
        self.assertNotIn("\\thispagestyle{empty}", topic_override)
        self.assertEqual(
            markov.count(
                "\\par\\noindent\\begin{minipage}{\\linewidth}\n"
                "\\begin{lstlisting}"
            ),
            2,
        )
        self.assertEqual(markov.count("\\end{lstlisting}\n\\end{minipage}\\par"), 2)
        self.assertIn("{map/pix/learn5.pdf}", markov)
        self.assertIn("{map/pix/ws.pdf}", markov)
        self.assertNotIn("{map/pix/learn5.eps}", markov)
        self.assertNotIn("{map/pix/ws.eps}", markov)
        self.assertNotIn(
            "$\\set{(x,y,z)\\suchthat\\text{$2x+z=3$ dan $x-y-z=1$ dan $3x-y=4$}}$",
            gr1,
        )
        self.assertEqual(
            gr1.count(
                "\\set{(x,y,z)\\suchthat\n"
                "    \\begin{gathered}\n"
                "      2x+z=3\\text{ dan }x-y-z=1 \\\\\n"
                "      \\text{dan }3x-y=4\n"
                "    \\end{gathered}}"
            ),
            1,
        )
        self.assertIn(
            "\\lstinline[style=inline]!-=! pada perulangan terdalam menghasilkan kode berikut.\n"
            "\\begin{lstlisting}[breaklines=true]\n"
            "a[row_below,col]=-1*multiplier*a[row,col]+a[row_below,col]\n"
            "\\end{lstlisting}",
            ppivot,
        )
        self.assertNotIn(
            "\\lstinline[style=inline]!a[row_below,col]=-1*multiplier*a[row,col]+a[row_below,col]!.",
            ppivot,
        )

    def test_answer_graphic_pdf_assets_are_exact_official_source_bytes(self) -> None:
        pixels = PROJECT_ROOT / "source" / "linear-algebra" / "src" / "map" / "pix"
        expected = {
            "learn5.pdf": (
                5134,
                "611dce6daa57dab15dfd6eb18c0eca3c43cab025261584b6a5f50fc38e1e97e6",
            ),
            "ws.pdf": (
                5781,
                "f633a32038a2fb9257ba1db0af5ffd681675801fa8af49885ac9aab4275c3d3b",
            ),
        }
        for filename, (expected_bytes, expected_sha256) in expected.items():
            payload = (pixels / filename).read_bytes()
            self.assertEqual(len(payload), expected_bytes)
            self.assertEqual(hashlib.sha256(payload).hexdigest(), expected_sha256)


if __name__ == "__main__":
    unittest.main()
