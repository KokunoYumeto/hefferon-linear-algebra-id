"""Focused offline tests for terminology and production-provenance gates."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from backend import build_index as builder
from backend import validate_backend as validator


EXPECTED_PROVENANCE = "OpenAI Codex gpt-5.6-sol, Ultra."


def read_rows() -> list[dict[str, str]]:
    with validator.TERMINOLOGY_LEDGER.open(
        "r", encoding="utf-8", newline=""
    ) as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == validator.TERM_FIELDS
        return list(reader)


def projected_terms(rows: list[dict[str, str]], payload: bytes) -> list[dict]:
    ledger_sha = hashlib.sha256(payload).hexdigest()
    result: list[dict] = []
    for row_number, row in enumerate(rows, 2):
        local_id = row["term_id"]
        result.append(
            {
                "evidence": row["evidence"],
                "id": (
                    "r005.hefferon-linear-algebra.term."
                    f"{local_id.lower()}.locale.id-id"
                ),
                "language": "id",
                "ledger_status": row["status"],
                "locale": "id-ID",
                "notes": row["notes"],
                "preferred": row["preferred_id"],
                "record_type": "term",
                "rejected": validator.split_semicolon(row["rejected"]),
                "scope": row["scope"],
                "source_ledger_row": row_number,
                "source_ledger_sha256": ledger_sha,
                "source_local_id": local_id,
                "source_locator": f"00_control/TERMINOLOGY.csv#row-{row_number}",
                "source_sha256": ledger_sha,
                "source_term": row["english"],
                "target_edition_id": validator.TARGET_EDITION_ID,
                "translation_state": "translated",
                "variants": validator.split_semicolon(row["variants"]),
            }
        )
    return result


class TerminologyLedgerTests(unittest.TestCase):
    def test_live_ledger_is_canonical_contiguous_and_exact(self) -> None:
        rows, payload = validator.load_terminology_ledger()
        self.assertEqual(114, len(rows))
        self.assertEqual("HLA-T0001", rows[0]["term_id"])
        self.assertEqual("HLA-T0114", rows[-1]["term_id"])
        self.assertTrue(payload.endswith(b"\n"))
        self.assertNotIn(b"\r", payload)
        builder.validate_terminology_rows(rows, validator.TERMINOLOGY_LEDGER)

    def test_required_decisions_have_exact_semantics(self) -> None:
        rows, _payload = validator.load_terminology_ledger()
        row_by_id = {row["term_id"]: row for row in rows}
        for local_id, expected in validator.REQUIRED_TERMINOLOGY_DECISIONS.items():
            self.assertEqual(expected, {field: row_by_id[local_id][field] for field in expected})

    def test_builder_rejects_a_gap(self) -> None:
        rows = read_rows()
        rows[112]["term_id"] = "HLA-T0999"
        with self.assertRaisesRegex(RuntimeError, "noncontiguous term_id"):
            builder.validate_terminology_rows(rows, Path("TERMINOLOGY.csv"))

    def test_validator_rejects_preferred_rejected_collision(self) -> None:
        rows = read_rows()
        rows[112]["rejected"] = rows[112]["preferred_id"]
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(
            stream, fieldnames=validator.TERM_FIELDS, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "TERMINOLOGY.csv"
            path.write_bytes(stream.getvalue().encode("utf-8"))
            with self.assertRaisesRegex(RuntimeError, "rejects its preferred form"):
                validator.load_terminology_ledger(path)

    def test_projection_round_trips_every_live_row(self) -> None:
        rows, payload = validator.load_terminology_ledger()
        validator.validate_terminology_projection(
            rows, payload, projected_terms(rows, payload)
        )

    def test_projection_rejects_changed_null_space_preference(self) -> None:
        rows, payload = validator.load_terminology_ledger()
        terms = projected_terms(rows, payload)
        term = next(
            item for item in terms if item["source_local_id"] == "HLA-T0113"
        )
        term["preferred"] = "ruang kosong"
        with self.assertRaisesRegex(RuntimeError, "round-trip mismatch in preferred"):
            validator.validate_terminology_projection(rows, payload, terms)


class ProductionProvenanceTests(unittest.TestCase):
    def test_builder_and_validator_share_exact_provenance(self) -> None:
        self.assertEqual(EXPECTED_PROVENANCE, builder.PRODUCTION_PROVENANCE)
        self.assertEqual(EXPECTED_PROVENANCE, validator.PRODUCTION_PROVENANCE)
        validator.validate_derivative_provenance(
            {"production_provenance": EXPECTED_PROVENANCE}
        )

    def test_near_match_provenance_is_rejected(self) -> None:
        for value in (
            None,
            EXPECTED_PROVENANCE.removesuffix("."),
            EXPECTED_PROVENANCE.replace("Ultra", "ultra"),
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError, "inexact production provenance"):
                    validator.validate_derivative_provenance(
                        {"production_provenance": value}
                    )


if __name__ == "__main__":
    unittest.main()
