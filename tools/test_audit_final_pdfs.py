from __future__ import annotations

from pathlib import Path
import logging
import tempfile
import unittest
from unittest import mock

from PIL import Image, ImageDraw
from pypdf import PdfWriter

from tools.audit_final_pdfs import (
    annotate_layout_outliers,
    capture_pypdf_notices,
    classify_mutool_stderr,
    inspect_pdf_geometry,
    inspect_render_png,
    parse_pdffonts_output,
    relative_path,
    scan_log_text,
    scan_page_text,
)


class FinalPdfAuditTests(unittest.TestCase):
    def test_emitted_paths_are_project_relative_and_portable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "qa" / "portable.json"
            with mock.patch("tools.audit_final_pdfs.PROJECT_ROOT", root):
                emitted = relative_path(target)
        self.assertEqual(emitted, "qa/portable.json")
        self.assertNotIn(Path.home().name.casefold(), emitted.casefold())

    def test_pypdf_duplicate_group_warning_is_captured_as_review_evidence(self) -> None:
        with capture_pypdf_notices() as captured:
            logging.getLogger("pypdf._reader").warning(
                "Multiple definitions in dictionary at byte 0x123 for key /Group"
            )
        self.assertEqual(captured["notice_count"], 1)
        self.assertEqual(captured["duplicate_dictionary_key_notice_count"], 1)
        self.assertEqual(captured["duplicate_group_dictionary_notice_count"], 1)
        self.assertEqual(
            captured["notices"][0]["classification"],
            "human_review_duplicate_dictionary_key",
        )

    def test_mutool_stderr_separates_duplicate_warning_from_parse_error(self) -> None:
        classified = classify_mutool_stderr(
            "warning: duplicate entry in dictionary for key /Group\n"
            "error: malformed xref table\n"
        )
        self.assertEqual(classified["duplicate_dictionary_key_notice_count"], 1)
        self.assertEqual(classified["hard_parse_error_count"], 1)

    def test_pdffonts_parser_handles_spaced_font_types(self) -> None:
        sample = """name                                 type              encoding         emb sub uni object ID
------------------------------------ ----------------- ---------------- --- --- --- ---------
ABCDEE+LMRoman10-Regular             CID Type 0C       Identity-H       yes yes yes     12  0
CMR10                                Type 1            Builtin          no  no  no      18  0
"""
        fonts, unparsed = parse_pdffonts_output(sample)
        self.assertEqual(unparsed, [])
        self.assertEqual(len(fonts), 2)
        self.assertEqual(fonts[0]["type"], "CID Type 0C")
        self.assertTrue(fonts[0]["embedded"])
        self.assertFalse(fonts[1]["embedded"])

    def test_log_scanner_classifies_hard_and_review_diagnostics(self) -> None:
        hits = scan_log_text(
            "LaTeX Font Warning: Font shape unavailable\n"
            "Missing character: There is no α in font Foo\n"
            "LaTeX Warning: There were undefined references.\n"
            "Overfull \\hbox (3.0pt too wide)\n"
        )
        categories = {hit["category"]: hit["severity"] for hit in hits}
        self.assertEqual(categories["font_warning"], "human_review")
        self.assertEqual(categories["missing_glyph"], "hard_failure")
        self.assertEqual(categories["undefined_reference_or_citation"], "hard_failure")
        self.assertEqual(categories["overfull_box"], "human_review")

    def test_text_scanner_leaves_candidates_for_human_review(self) -> None:
        result = scan_page_text(
            "book",
            17,
            "Chapter 3 Linear Maps\nProof.\nTODO replace ??\n",
        )
        self.assertEqual(len(result["english_hits"]), 2)
        self.assertGreaterEqual(len(result["placeholder_hits"]), 2)
        self.assertTrue(
            all(hit["disposition"] == "human_review_required" for hit in result["english_hits"])
        )

    def test_render_metrics_find_body_bbox_and_gutters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "page.png"
            image = Image.new("L", (100, 120), 255)
            draw = ImageDraw.Draw(image)
            draw.rectangle((20, 20, 79, 99), fill=0)
            image.save(path)
            metrics = inspect_render_png(path)
        self.assertEqual(metrics["body_ink_bbox"], [20, 20, 80, 100])
        self.assertEqual(metrics["left_gutter"], 20)
        self.assertEqual(metrics["right_gutter"], 20)
        self.assertFalse(metrics["body_blank"])

    def test_pdf_geometry_accepts_valid_boxes_and_rotation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "geometry.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            writer.add_blank_page(width=612, height=792).rotate(90)
            with path.open("wb") as stream:
                writer.write(stream)
            geometry = inspect_pdf_geometry(path)
        self.assertEqual(geometry["page_count"], 2)
        self.assertTrue(geometry["all_pages_valid"])
        self.assertEqual(geometry["rotation_variants"], {"0": 1, "90": 1})

    def test_layout_outliers_are_parity_specific(self) -> None:
        rows = []
        for page in range(1, 21):
            rows.append(
                {
                    "pdf": "book",
                    "page": page,
                    "parity": "odd" if page % 2 else "even",
                    "body_blank": False,
                    "body_centroid_x_fraction": 0.50,
                    "body_bbox_width_fraction": 0.70,
                    "body_ink_fraction": 0.10,
                    "inner_gutter_fraction": 0.15,
                    "outer_gutter_fraction": 0.15,
                }
            )
        rows[-2]["body_centroid_x_fraction"] = 0.85  # odd page 19 only
        references, outliers = annotate_layout_outliers(rows)
        self.assertEqual(references["odd"]["body_centroid_x_fraction"]["count"], 10)
        self.assertTrue(
            any(
                row["page"] == 19 and row["metric"] == "body_centroid_x_fraction"
                for row in outliers
            )
        )


if __name__ == "__main__":
    unittest.main()
