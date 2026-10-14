import unittest
import os
import tempfile
import shutil
import base64
import hashlib
from core.ingest_sms import (
    parse_large_xml,
    sort_daily_notes,
    extract_mms_parts,
    ingest_xml_directory,
    ingest_diarized_transcripts,
    prune_superseded_backups
)

# 1x1 transparent GIF base64 string
DUMMY_GIF_B64 = "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
DUMMY_GIF_BYTES = base64.b64decode(DUMMY_GIF_B64)
DUMMY_GIF_MD5 = hashlib.md5(DUMMY_GIF_BYTES).hexdigest()

# 1x1 PNG base64 string
DUMMY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
DUMMY_PNG_BYTES = base64.b64decode(DUMMY_PNG_B64)
DUMMY_PNG_MD5 = hashlib.md5(DUMMY_PNG_BYTES).hexdigest()


class TestIngestSMS(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="aim_test_sms_")
        self.notes_dir = os.path.join(self.test_dir, "daily_notes")
        self.media_dir = os.path.join(self.test_dir, "media")
        os.makedirs(self.notes_dir, exist_ok=True)
        os.makedirs(self.media_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_parse_sms_and_call(self):
        """Test standard SMS and Call log parsing."""
        xml_content = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<smses count="2">
  <call number="5550101234" duration="45" type="1" date="1672574400000" contact_name="Alice" />
  <sms protocol="0" address="5550105678" date="1672578000000" type="1" subject="null" body="Hello from test!" contact_name="Bob" />
</smses>"""
        xml_path = os.path.join(self.test_dir, "test_basic.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(xml_content)

        parse_large_xml(xml_path, output_dir=self.notes_dir, media_dir=self.media_dir)

        # Date 1672574400000 ms is 2023-01-01
        daily_note = os.path.join(self.notes_dir, "2023-01-01.md")
        self.assertTrue(os.path.exists(daily_note), "Daily note was not created.")

        with open(daily_note, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Incoming Call", content)
        self.assertIn("Alice", content)
        self.assertIn("Hello from test!", content)
        self.assertIn("Bob", content)

    def test_parse_mms_base64_image_extraction(self):
        """Test MMS base64 image decoding, file writing, and markdown linking."""
        xml_content = f"""<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<smses count="1">
  <mms date="1672581600000" msg_box="1" address="5550109999" contact_name="Charlie">
    <parts>
      <part seq="-1" ct="application/smil" name="smil.xml" text="&lt;smil&gt;&lt;/smil&gt;" />
      <part seq="0" ct="text/plain" name="text_0.txt" text="Here is the estimate screenshot" />
      <part seq="1" ct="image/gif" name="estimate.gif" data="{DUMMY_GIF_B64}" text="null" />
    </parts>
    <addrs>
      <addr address="5550109999" type="137" />
      <addr address="5550100100" type="151" />
    </addrs>
  </mms>
</smses>"""
        xml_path = os.path.join(self.test_dir, "test_mms.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(xml_content)

        parse_large_xml(xml_path, output_dir=self.notes_dir, media_dir=self.media_dir)

        # 1. Verify image file was written to media_dir
        media_files = os.listdir(self.media_dir)
        self.assertEqual(len(media_files), 1, "Expected exactly 1 extracted image in media directory.")

        saved_file = os.path.join(self.media_dir, media_files[0])
        with open(saved_file, "rb") as f:
            saved_bytes = f.read()
        self.assertEqual(saved_bytes, DUMMY_GIF_BYTES, "Saved image bytes do not match original.")

        # 2. Verify daily note contains link to media file
        daily_note = os.path.join(self.notes_dir, "2023-01-01.md")
        self.assertTrue(os.path.exists(daily_note))
        with open(daily_note, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Received MMS", content)
        self.assertIn("Charlie", content)
        self.assertIn("Here is the estimate screenshot", content)
        self.assertIn(media_files[0], content)
        self.assertIn("![MMS Image](", content)

    def test_mms_deduplication(self):
        """Test that identical payloads are not duplicated on disk."""
        xml_content = f"""<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<smses count="2">
  <mms date="1672581600000" msg_box="1" address="5550109999" contact_name="Charlie">
    <parts>
      <part seq="0" ct="image/png" name="pic1.png" data="{DUMMY_PNG_B64}" />
    </parts>
  </mms>
  <mms date="1672585200000" msg_box="2" address="5550109999" contact_name="Charlie">
    <parts>
      <part seq="0" ct="image/png" name="pic1_copy.png" data="{DUMMY_PNG_B64}" />
    </parts>
  </mms>
</smses>"""
        xml_path = os.path.join(self.test_dir, "test_dedup.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(xml_content)

        parse_large_xml(xml_path, output_dir=self.notes_dir, media_dir=self.media_dir)

        # Only 1 unique file should exist in media_dir
        media_files = os.listdir(self.media_dir)
        self.assertEqual(len(media_files), 1, "Duplicate payload should not produce a second file.")

    def test_sort_daily_notes_preserves_multiline_mms(self):
        """Test sort_daily_notes sorts chronologically and preserves media markdown links."""
        note_content = """---
date: 2023-01-01
type: daily_exocortex
---
# Daily Log: 2023-01-01

- **[03:00 PM] Received Text** (Bob): "Later message"
- **[01:00 PM] Received MMS** (Charlie): "Earlier message with image"
  ![MMS Image](../media/test_pic.jpg)
  > Caption note
"""
        note_path = os.path.join(self.notes_dir, "2023-01-01.md")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(note_content)

        sort_daily_notes(output_dir=self.notes_dir)

        with open(note_path, "r", encoding="utf-8") as f:
            sorted_content = f.read()

        # [01:00 PM] must appear before [03:00 PM]
        idx_earlier = sorted_content.find("[01:00 PM]")
        idx_later = sorted_content.find("[03:00 PM]")
        self.assertNotEqual(idx_earlier, -1)
        self.assertNotEqual(idx_later, -1)
        self.assertLess(idx_earlier, idx_later, "01:00 PM should be sorted before 03:00 PM.")

        # Ensure attachment lines were NOT dropped
        self.assertIn("![MMS Image](../media/test_pic.jpg)", sorted_content)
        self.assertIn("> Caption note", sorted_content)

    def test_multimodal_mime_types(self):
        """Test video, audio, and pdf attachment links."""
        dummy_data = base64.b64encode(b"binary content").decode("ascii")
        xml_content = f"""<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<smses count="3">
  <mms date="1672581600000" msg_box="1" address="5550101111" contact_name="Dana">
    <parts>
      <part seq="0" ct="video/mp4" name="video.mp4" data="{dummy_data}" />
    </parts>
  </mms>
  <mms date="1672585200000" msg_box="1" address="5550101111" contact_name="Dana">
    <parts>
      <part seq="0" ct="audio/amr" name="voice.amr" data="{dummy_data}" />
    </parts>
  </mms>
  <mms date="1672588800000" msg_box="1" address="5550101111" contact_name="Dana">
    <parts>
      <part seq="0" ct="application/pdf" name="doc.pdf" data="{dummy_data}" />
    </parts>
  </mms>
</smses>"""
        xml_path = os.path.join(self.test_dir, "test_types.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(xml_content)

        parse_large_xml(xml_path, output_dir=self.notes_dir, media_dir=self.media_dir)

        daily_note = os.path.join(self.notes_dir, "2023-01-01.md")
        with open(daily_note, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("[MMS Video]", content)
        self.assertIn("[MMS Audio]", content)
        self.assertIn("[MMS Attachment]", content)

    def test_mms_address_resolution_fallback(self):
        """Test address fallback from <addrs> when address attribute is '~'."""
        xml_content = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<smses count="1">
  <mms date="1672581600000" msg_box="1" address="~" contact_name="(Unknown)">
    <parts>
      <part seq="0" ct="text/plain" text="Message from unknown sender" />
    </parts>
    <addrs>
      <addr address="5550108888" type="137" />
    </addrs>
  </mms>
</smses>"""
        xml_path = os.path.join(self.test_dir, "test_addr_fallback.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(xml_content)

        parse_large_xml(xml_path, output_dir=self.notes_dir, media_dir=self.media_dir)

        daily_note = os.path.join(self.notes_dir, "2023-01-01.md")
        with open(daily_note, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("5550108888", content)
        self.assertIn("Message from unknown sender", content)

    def test_incremental_xml_directory_globbing(self):
        """Test directory globbing and manifest-based incremental skipping (CAL-002)."""
        raw_dir = os.path.join(self.test_dir, "sms_raw")
        os.makedirs(raw_dir, exist_ok=True)
        manifest_path = os.path.join(raw_dir, ".processed_xml_manifest.json")

        calls_xml = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<calls count="1">
  <call number="5550101234" duration="30" type="1" date="1672574400000" contact_name="Alice" />
</calls>"""
        sms_xml = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<smses count="1">
  <sms protocol="0" address="5550105678" date="1672578000000" type="1" body="Incremental SMS!" contact_name="Bob" />
</smses>"""

        with open(os.path.join(raw_dir, "calls-20261001000000.xml"), "w", encoding="utf-8") as f:
            f.write(calls_xml)
        with open(os.path.join(raw_dir, "sms-20261001000000.xml"), "w", encoding="utf-8") as f:
            f.write(sms_xml)

        # First run should parse both files
        count1 = ingest_xml_directory(
            input_dir=raw_dir,
            output_dir=self.notes_dir,
            media_dir=self.media_dir,
            manifest_path=manifest_path
        )
        self.assertEqual(count1, 2)
        self.assertTrue(os.path.exists(manifest_path))

        # Second incremental run should skip both already-ingested files
        count2 = ingest_xml_directory(
            input_dir=raw_dir,
            output_dir=self.notes_dir,
            media_dir=self.media_dir,
            manifest_path=manifest_path
        )
        self.assertEqual(count2, 0)

        # Force run should re-parse both files
        count3 = ingest_xml_directory(
            input_dir=raw_dir,
            output_dir=self.notes_dir,
            media_dir=self.media_dir,
            manifest_path=manifest_path,
            force=True
        )
        self.assertEqual(count3, 2)

    def test_ingest_diarized_transcripts(self):
        """Test interleaving diarized audio transcripts into Daily Notes (CAL-005)."""
        t_dir = os.path.join(self.test_dir, "conversations_diarized")
        os.makedirs(t_dir, exist_ok=True)
        manifest_path = os.path.join(self.test_dir, ".manifest.json")

        t_content = """---
platform: phone
date: 20230101-143000
contact: "+15550100100"
duration: 120.50s
tags: [phone-call, talker-acr]
status: golden
model: large-v3 + pyannote
---

# Transcript

[SPEAKER_00] [0.40s -> 5.86s] Hello, checking on the schedule.
[SPEAKER_01] [6.24s -> 9.80s] We are all set for tomorrow morning.
"""
        t_path = os.path.join(t_dir, "phone_20230101-143000__15550100100.md")
        with open(t_path, "w", encoding="utf-8") as f:
            f.write(t_content)

        linked = ingest_diarized_transcripts(
            transcripts_dir=t_dir,
            output_dir=self.notes_dir,
            manifest_path=manifest_path
        )
        self.assertEqual(linked, 1)

        daily_note = os.path.join(self.notes_dir, "2023-01-01.md")
        self.assertTrue(os.path.exists(daily_note))
        with open(daily_note, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Audio Call Transcript", content)
        self.assertIn("+15550100100", content)
        self.assertIn("[SPEAKER_00]", content)
        self.assertIn("Full Transcript", content)

    def test_prune_superseded_backups(self):
        """Test pruning of superseded cumulative XMLs and extracted ZIP archives (CAL-012)."""
        raw_dir = os.path.join(self.test_dir, "sms_raw_prune")
        os.makedirs(raw_dir, exist_ok=True)
        manifest_path = os.path.join(raw_dir, ".processed_xml_manifest.json")

        calls_xml = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<calls count="1">
  <call number="5550101234" duration="30" type="1" date="1672574400000" contact_name="Alice" />
</calls>"""
        sms_xml = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<smses count="1">
  <sms protocol="0" address="5550105678" date="1672578000000" type="1" body="Prune test!" contact_name="Bob" />
</smses>"""

        for name in ("calls-20261001000000.xml", "calls-20261002000000.xml", "calls.xml"):
            with open(os.path.join(raw_dir, name), "w", encoding="utf-8") as f:
                f.write(calls_xml)

        for name in ("sms-20261001000000.xml", "sms-20261002000000.xml", "messages.xml"):
            with open(os.path.join(raw_dir, name), "w", encoding="utf-8") as f:
                f.write(sms_xml)

        zip_path = os.path.join(raw_dir, "sms_backup_100.zip")
        marker_path = zip_path + ".extracted"
        with open(zip_path, "wb") as f:
            f.write(b"PK\x03\x04dummyzip")
        with open(marker_path, "w", encoding="utf-8") as f:
            f.write("")

        ingest_xml_directory(
            input_dir=raw_dir,
            output_dir=self.notes_dir,
            media_dir=self.media_dir,
            manifest_path=manifest_path,
            prune=True,
            keep_latest=1
        )

        # Older cumulative XMLs, unpacked calls.xml/messages.xml, and extracted .zip should be pruned
        self.assertFalse(os.path.exists(os.path.join(raw_dir, "calls-20261001000000.xml")))
        self.assertFalse(os.path.exists(os.path.join(raw_dir, "sms-20261001000000.xml")))
        self.assertFalse(os.path.exists(os.path.join(raw_dir, "calls.xml")))
        self.assertFalse(os.path.exists(os.path.join(raw_dir, "messages.xml")))
        self.assertFalse(os.path.exists(zip_path))

        # Newest cumulative XMLs, .zip.extracted marker, and manifest must be preserved
        self.assertTrue(os.path.exists(os.path.join(raw_dir, "calls-20261002000000.xml")))
        self.assertTrue(os.path.exists(os.path.join(raw_dir, "sms-20261002000000.xml")))
        self.assertTrue(os.path.exists(marker_path))
        self.assertTrue(os.path.exists(manifest_path))


if __name__ == '__main__':
    unittest.main()
