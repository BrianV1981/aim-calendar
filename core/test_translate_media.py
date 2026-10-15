import os
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import lancedb

from core.llm_provider import resolve_provider, describe_media, generate_text
from core.translate_media import translate_daily_notes_media
from core.ingest_to_lancedb import ingest_daily_notes, LANCEDB_SCHEMA


class TestLLMProviderAndTranslateMedia(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="aim_test_locomo_")
        self.notes_dir = os.path.join(self.test_dir, "daily_notes")
        self.media_dir = os.path.join(self.test_dir, "media")
        self.db_dir = os.path.join(self.test_dir, "test_cartridge.lance")
        os.makedirs(self.notes_dir, exist_ok=True)
        os.makedirs(self.media_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_resolve_provider_hybrid_autodetect(self):
        """Verify Guardrail #1: hybrid auto-detect between ollama and gemini."""
        with patch.dict(os.environ, {"AIM_LLM_PROVIDER": "auto", "GEMINI_API_KEY": ""}, clear=False):
            self.assertEqual(resolve_provider(), "ollama")

        with patch.dict(os.environ, {"AIM_LLM_PROVIDER": "auto", "GEMINI_API_KEY": "AIzaSyDummyKey"}, clear=False):
            self.assertEqual(resolve_provider(), "gemini")

        with patch.dict(os.environ, {"AIM_LLM_PROVIDER": "ollama", "GEMINI_API_KEY": "AIzaSyDummyKey"}, clear=False):
            self.assertEqual(resolve_provider(), "ollama")

    def test_describe_vcard_and_text_attachments(self):
        """Verify .vcf and .txt MMS attachments are summarized deterministically."""
        vcf_path = os.path.join(self.media_dir, "contact.vcf")
        with open(vcf_path, "w", encoding="utf-8") as f:
            f.write("BEGIN:VCARD\nFN:Alice Smith\nORG:Apex Roofing;\nTEL:+15550199999\nEND:VCARD\n")

        desc = describe_media(vcf_path, provider="ollama")
        self.assertIn("Alice Smith", desc)
        self.assertIn("Apex Roofing", desc)
        self.assertIn("+15550199999", desc)

        txt_path = os.path.join(self.media_dir, "note.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("Gate code is #4421")
        txt_desc = describe_media(txt_path, provider="ollama")
        self.assertIn("Gate code is #4421", txt_desc)

    @patch("core.llm_provider.requests.post")
    def test_describe_media_ollama_vision(self, mock_post):
        """Verify local Ollama vision request sends base64 image to qwen2.5vl:3b."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "Invoice #1042 for roof wash totaling $450.00."}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        img_path = os.path.join(self.media_dir, "mms_100_abcd.jpg")
        with open(img_path, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0dummyjpeg")

        caption = describe_media(img_path, provider="ollama")
        self.assertEqual(caption, "Invoice #1042 for roof wash totaling $450.00.")
        self.assertTrue(mock_post.called)
        sent_json = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_json["model"], "qwen2.5vl:3b")
        self.assertEqual(len(sent_json["images"]), 1)

    def test_translate_daily_notes_injects_blockquote_and_uses_cache(self):
        """Verify Daily Notes media translation, blockquote injection, and cache hits."""
        img_path = os.path.join(self.media_dir, "mms_1672581600000_abcd1234.jpg")
        with open(img_path, "wb") as f:
            f.write(b"dummy image bytes")

        note1 = os.path.join(self.notes_dir, "2026-09-02.md")
        with open(note1, "w", encoding="utf-8") as f:
            f.write(
                "---\ndate: 2026-09-02\ntype: daily_exocortex\n---\n# Daily Log: 2026-09-02\n\n"
                "- **[01:00 PM] Received MMS** (Client):\n"
                "  ![MMS Image](../media/mms_1672581600000_abcd1234.jpg)\n"
                "- **[02:00 PM] Sent Text** (Client): \"Looks good!\"\n"
            )

        call_counter = {"count": 0}

        def fake_describe(path: str) -> str:
            call_counter["count"] += 1
            return "Two-story stucco house with mildew on north fascia."

        # 1. Dry-run should not modify files
        dry_stats = translate_daily_notes_media(
            notes_dir=self.notes_dir,
            media_dir=self.media_dir,
            dry_run=True,
            describe_fn=fake_describe,
        )
        self.assertEqual(dry_stats["notes_updated"], 0)
        self.assertEqual(call_counter["count"], 0)

        # 2. Live run should inject > [Visual Context: ...] and write cache
        stats1 = translate_daily_notes_media(
            notes_dir=self.notes_dir,
            media_dir=self.media_dir,
            describe_fn=fake_describe,
        )
        self.assertEqual(stats1["notes_updated"], 1)
        self.assertEqual(stats1["media_translated"], 1)
        self.assertEqual(call_counter["count"], 1)

        with open(note1, "r", encoding="utf-8") as f:
            updated_md = f.read()
        self.assertIn(
            "  > [Visual Context: Two-story stucco house with mildew on north fascia.]\n",
            updated_md,
        )

        # 3. Second run on same note should be a no-op (already has Visual Context)
        stats2 = translate_daily_notes_media(
            notes_dir=self.notes_dir,
            media_dir=self.media_dir,
            describe_fn=fake_describe,
        )
        self.assertEqual(stats2["notes_updated"], 0)
        self.assertEqual(call_counter["count"], 1)

        # 4. New Daily Note referencing the same media file should hit cache without calling describe_fn
        note2 = os.path.join(self.notes_dir, "2026-09-03.md")
        with open(note2, "w", encoding="utf-8") as f:
            f.write(
                "---\ndate: 2026-09-03\ntype: daily_exocortex\n---\n# Daily Log: 2026-09-03\n\n"
                "- **[09:00 AM] Sent MMS** (Client):\n"
                "  ![MMS Image](../media/mms_1672581600000_abcd1234.jpg)\n"
            )

        stats3 = translate_daily_notes_media(
            notes_dir=self.notes_dir,
            media_dir=self.media_dir,
            describe_fn=fake_describe,
        )
        self.assertEqual(stats3["notes_updated"], 1)
        self.assertEqual(stats3["cache_hits"], 1)
        self.assertEqual(call_counter["count"], 1)

    def test_lancedb_reindexes_note_after_visual_translation(self):
        """Verify LanceDB automatically re-indexes a Daily Note after Visual Context is injected."""
        db = lancedb.connect(self.db_dir)
        db.create_table("fragments", schema=LANCEDB_SCHEMA)

        img_path = os.path.join(self.media_dir, "mms_roof.jpg")
        with open(img_path, "wb") as f:
            f.write(b"roofimage")

        note_path = os.path.join(self.notes_dir, "2026-09-05.md")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(
                "---\ndate: 2026-09-05\ntype: daily_exocortex\n---\n# Daily Log: 2026-09-05\n\n"
                "- **[10:00 AM] Received MMS** (Customer):\n"
                "  ![MMS Image](../media/mms_roof.jpg)\n"
            )

        mock_vec = [0.2] * 768
        c1 = ingest_daily_notes(db_path=self.db_dir, input_dir=self.notes_dir, embed_fn=lambda t: mock_vec)
        self.assertEqual(c1, 1)

        # Now inject Visual Context via translate_daily_notes_media
        translate_daily_notes_media(
            notes_dir=self.notes_dir,
            media_dir=self.media_dir,
            describe_fn=lambda p: " terracotta barrel tile roof with driveway stain ",
        )

        # Re-run ingest_daily_notes WITHOUT force=True; size change should trigger automatic re-index
        c2 = ingest_daily_notes(db_path=self.db_dir, input_dir=self.notes_dir, embed_fn=lambda t: mock_vec)
        self.assertEqual(c2, 1)

        tbl = db.open_table("fragments")
        df = tbl.search().where("type = 'daily_note'").to_pandas()
        self.assertEqual(len(df), 1)
        self.assertIn("terracotta barrel tile roof", df.iloc[0]["content"])


if __name__ == "__main__":
    unittest.main()
