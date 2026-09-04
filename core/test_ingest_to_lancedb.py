import unittest
import os
import tempfile
import shutil
import json
import pyarrow as pa
import lancedb
from core.ingest_to_lancedb import (
    parse_daily_note,
    chunk_daily_note,
    ingest_daily_notes,
    LANCEDB_SCHEMA
)


class TestIngestToLanceDB(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="aim_test_lancedb_")
        self.notes_dir = os.path.join(self.test_dir, "daily_notes")
        self.db_dir = os.path.join(self.test_dir, "test_cartridge.lance")
        os.makedirs(self.notes_dir, exist_ok=True)

        # Create a mock LanceDB with the fragments table
        db = lancedb.connect(self.db_dir)
        db.create_table("fragments", schema=LANCEDB_SCHEMA)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_parse_daily_note(self):
        """Verify YAML frontmatter and multiline entries are parsed accurately."""
        sample_md = """---
date: 2026-09-02
type: daily_exocortex
---
# Daily Log: 2026-09-02

- **[07:22 AM] Received Text** (+13238701595): "Hey Tampa Bay Soft Wash, need an estimate."
- **[07:23 AM] Sent Text** (+13238701595): "Sure, what is the address?"
- **[01:00 PM] Received MMS** (Jessica): "Here is the roof photo"
  ![MMS Image](../media/roof.jpg)
  > Steep pitch tile roof
"""
        note_path = os.path.join(self.notes_dir, "2026-09-02.md")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(sample_md)

        metadata, entries = parse_daily_note(note_path)
        self.assertEqual(metadata["date"], "2026-09-02")
        self.assertEqual(metadata["type"], "daily_exocortex")
        self.assertEqual(len(entries), 3)
        self.assertIn("roof.jpg", entries[2])
        self.assertIn("> Steep pitch tile roof", entries[2])

    def test_chunk_daily_note_temporal_anchor(self):
        """Verify chunks include temporal date anchor and respect sliding window."""
        entries = [
            "- **[09:00 AM] Incoming Call** with Client A (Duration: 30s)",
            "- **[10:00 AM] Received Text** (Client B): 'Can you come at 2pm?'",
            "- **[10:05 AM] Sent Text** (Client B): 'Yes, 2pm works.'",
            "- **[02:00 PM] Received Text** (Client C): 'Are you on your way?'"
        ]
        chunks = chunk_daily_note(entries, date_str="2026-09-02", target_chunk_chars=150, overlap_entries=1)
        self.assertGreater(len(chunks), 1)

        for chunk_text, meta in chunks:
            self.assertTrue(chunk_text.startswith("[Date: 2026-09-02]"), "Chunk must include temporal anchor header.")
            self.assertIn("date", meta)
            self.assertEqual(meta["date"], "2026-09-02")

    def test_ingest_daily_notes_mock_embed(self):
        """Verify end-to-end ingestion into LanceDB table using mock embedding function."""
        sample_md = """---
date: 2026-09-03
type: daily_exocortex
---
# Daily Log: 2026-09-03

- **[08:00 AM] Received Text** (Brian): "Schedule the house wash for Friday."
- **[08:05 AM] Sent Text** (Brian): "Confirmed for 9am."
"""
        note_path = os.path.join(self.notes_dir, "2026-09-03.md")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(sample_md)

        # Mock embedding function returning 768-dim float vector
        mock_vec = [0.1] * 768
        def mock_embed_fn(text, task_type="RETRIEVAL_DOCUMENT"):
            return mock_vec

        ingest_count = ingest_daily_notes(
            db_path=self.db_dir,
            input_dir=self.notes_dir,
            embed_fn=mock_embed_fn
        )
        self.assertGreater(ingest_count, 0)

        # Verify records in LanceDB
        db = lancedb.connect(self.db_dir)
        tbl = db.open_table("fragments")
        self.assertGreater(tbl.count_rows(), 0)

        df = tbl.search().where("type = 'daily_note'").to_pandas()
        self.assertEqual(len(df), ingest_count)
        self.assertEqual(df.iloc[0]["session_id"], "2026-09-03.md")
        self.assertEqual(df.iloc[0]["type"], "daily_note")
        self.assertIn("house wash", df.iloc[0]["content"])

        # Test idempotency: re-running should skip already ingested file
        second_run_count = ingest_daily_notes(
            db_path=self.db_dir,
            input_dir=self.notes_dir,
            embed_fn=mock_embed_fn
        )
        self.assertEqual(second_run_count, 0, "Second run should skip already indexed files.")


if __name__ == '__main__':
    unittest.main()
