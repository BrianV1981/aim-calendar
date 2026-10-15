import os
import json
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.calendar_sync import (
    compute_aim_event_id,
    extract_golden_note_context,
    analyze_daily_note,
    export_ics_calendars,
    sync_state_to_google_calendar,
    run_calendar_sync,
)


class TestCalendarSync(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="aim_test_cal_sync_")
        self.notes_dir = os.path.join(self.test_dir, "daily_notes")
        self.cal_dir = os.path.join(self.test_dir, "calendar")
        os.makedirs(self.notes_dir, exist_ok=True)
        os.makedirs(self.cal_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_deterministic_aim_event_id(self):
        """Verify Guardrail #3: deterministic 24-hex event IDs."""
        id1 = compute_aim_event_id("appt", "2026-10-15T10:00:00", "Roof Quote - Bob")
        id2 = compute_aim_event_id("appt", "2026-10-15T10:00:59", "  roof quote -   bob ")
        self.assertEqual(len(id1), 24)
        self.assertEqual(id1, id2)

    def test_privacy_gate_strips_garbage_entries(self):
        """Verify Guardrail #4: GARBAGE entries are stripped before cloud LLM analysis."""
        note_path = os.path.join(self.notes_dir, "2026-10-14.md")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(
                "---\ndate: 2026-10-14\ntype: daily_exocortex\n---\n# Daily Log: 2026-10-14\n\n"
                "- **[09:00 AM] Incoming Call** [GARBAGE] Spam robocall\n"
                "- **[10:15 AM] Received Text** (Alice): \"Let's meet tomorrow at 10am for the roof quote.\"\n"
            )

        date_str, clean_entries, joined = extract_golden_note_context(note_path)
        self.assertEqual(date_str, "2026-10-14")
        self.assertEqual(len(clean_entries), 1)
        self.assertNotIn("Spam robocall", joined)
        self.assertIn("Alice", joined)

    def test_analyze_daily_note_retrospective_and_prospective(self):
        """Verify Guardrail #2: separates Retrospective Dossier from Prospective Appointments."""
        note_path = os.path.join(self.notes_dir, "2026-10-14.md")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(
                "---\ndate: 2026-10-14\ntype: daily_exocortex\n---\n# Daily Log: 2026-10-14\n\n"
                "- **[10:15 AM] Received Text** (Alice): \"I'll swing by Thursday at 10am for the roof quote.\"\n"
            )

        def fake_llm(prompt: str, sys_prompt: str):
            return {
                "dossier": {
                    "headline": "Roof Quote Scheduling with Alice",
                    "summary": "Coordinated Thursday 10am roof quote with Alice.",
                    "key_events": ["Confirmed Thursday 10am estimate with Alice"],
                    "media_highlights": ["72ft perimeter measurement photo"],
                },
                "appointments": [
                    {
                        "summary": "Roof Quote - Alice",
                        "start": "2026-10-15T10:00:00",
                        "end": "2026-10-15T11:00:00",
                        "attendees": ["Alice"],
                        "location": "123 Oak St",
                        "confidence": 0.92,
                        "source_quote": "I'll swing by Thursday at 10am for the roof quote.",
                    },
                    {
                        "summary": "Vague Maybe Call",
                        "start": "2026-10-16T12:00:00",
                        "end": "2026-10-16T13:00:00",
                        "attendees": [],
                        "location": "",
                        "confidence": 0.30,
                        "source_quote": "Maybe talk Friday",
                    },
                ],
            }

        res = analyze_daily_note(note_path, min_confidence=0.65, llm_fn=fake_llm)
        self.assertIsNotNone(res)
        self.assertEqual(res["dossier"]["headline"], "Roof Quote Scheduling with Alice")
        # Low-confidence appointment (0.30 < 0.65) must be filtered out
        self.assertEqual(len(res["appointments"]), 1)
        self.assertEqual(res["appointments"][0]["summary"], "Roof Quote - Alice")
        self.assertEqual(res["appointments"][0]["start"], "2026-10-15T10:00:00")

    def test_canonical_local_ledger_and_ics_export(self):
        """Verify Guardrail #3: canonical .calendar_state.json + dual .ics feed generation & idempotency."""
        note_path = os.path.join(self.notes_dir, "2026-10-14.md")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(
                "---\ndate: 2026-10-14\ntype: daily_exocortex\n---\n# Daily Log: 2026-10-14\n\n"
                "- **[10:15 AM] Received Text** (Alice): \"See you tomorrow at 10am.\"\n"
            )

        calls = {"count": 0}

        def fake_llm(prompt: str, sys_prompt: str):
            calls["count"] += 1
            return {
                "dossier": {
                    "headline": "Alice Estimate Confirmed",
                    "summary": "Scheduled Alice estimate.",
                    "key_events": ["Alice estimate set"],
                    "media_highlights": [],
                },
                "appointments": [
                    {
                        "summary": "Estimate - Alice",
                        "start": "2026-10-15T10:00:00",
                        "end": "2026-10-15T11:00:00",
                        "attendees": ["Alice"],
                        "location": "Tampa, FL",
                        "confidence": 0.95,
                        "source_quote": "See you tomorrow at 10am.",
                    }
                ],
            }

        stats1 = run_calendar_sync(
            notes_dir=self.notes_dir,
            calendar_dir=self.cal_dir,
            push_gcal=False,
            llm_fn=fake_llm,
        )
        self.assertEqual(stats1["notes_analyzed"], 1)
        self.assertEqual(stats1["total_dossiers"], 1)
        self.assertEqual(stats1["total_appointments"], 1)
        self.assertTrue(os.path.isfile(stats1["activity_ics"]))
        self.assertTrue(os.path.isfile(stats1["appointments_ics"]))

        with open(stats1["activity_ics"], "r", encoding="utf-8") as f:
            act_ics = f.read()
        self.assertIn("X-WR-CALNAME:A.I.M. Activity Log", act_ics)
        self.assertIn("SUMMARY:[Dossier] Alice Estimate Confirmed", act_ics)
        self.assertIn("X-AIM-EVENT-ID:", act_ics)

        with open(stats1["appointments_ics"], "r", encoding="utf-8") as f:
            appt_ics = f.read()
        self.assertIn("X-WR-CALNAME:A.I.M. Appointments", appt_ics)
        self.assertIn("SUMMARY:Estimate - Alice", appt_ics)
        self.assertIn("LOCATION:Tampa\\, FL", appt_ics)

        # Second run should skip unchanged Daily Note without calling LLM
        stats2 = run_calendar_sync(
            notes_dir=self.notes_dir,
            calendar_dir=self.cal_dir,
            push_gcal=False,
            llm_fn=fake_llm,
        )
        self.assertEqual(stats2["notes_analyzed"], 0)
        self.assertEqual(calls["count"], 1)

    def test_google_calendar_idempotent_upsert(self):
        """Verify Guardrail #3: Google Calendar push uses extendedProperties.private.aim_event_id to prevent duplicates."""
        state = {
            "processed_notes": {},
            "dossiers": {
                "2026-10-14": {
                    "aim_event_id": "dossier1234567890abcdef12",
                    "date": "2026-10-14",
                    "headline": "Test Dossier",
                    "summary": "Summary text",
                    "key_events": ["Call 1"],
                    "media_highlights": [],
                }
            },
            "appointments": {
                "appt1234567890abcdef1234": {
                    "aim_event_id": "appt1234567890abcdef1234",
                    "summary": "Roof Wash",
                    "start": "2026-10-15T10:00:00",
                    "end": "2026-10-15T11:00:00",
                    "attendees": ["Bob"],
                    "location": "456 Pine Rd",
                    "confidence": 0.9,
                    "source_quote": "Thursday 10am",
                    "source_date": "2026-10-14",
                }
            },
            "calendar_ids": {
                "A.I.M. Activity Log": "cal_activity_id",
                "A.I.M. Appointments": "cal_appt_id",
            },
        }

        mock_session = MagicMock()

        # Simulate: dossier already exists in Google Calendar (returns 1 item -> PATCH),
        # appointment does not exist yet (returns 0 items -> POST).
        def side_effect_get(url, headers=None, params=None, timeout=30):
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            if "cal_activity_id/events" in url:
                resp.json.return_value = {"items": [{"id": "existing_gcal_dossier_99"}]}
            else:
                resp.json.return_value = {"items": []}
            return resp

        mock_session.get.side_effect = side_effect_get

        patch_resp = MagicMock()
        patch_resp.raise_for_status.return_value = None
        patch_resp.json.return_value = {"id": "existing_gcal_dossier_99"}
        mock_session.patch.return_value = patch_resp

        post_resp = MagicMock()
        post_resp.raise_for_status.return_value = None
        post_resp.json.return_value = {"id": "new_gcal_appt_77"}
        mock_session.post.return_value = post_resp

        with patch.dict(os.environ, {"AIM_GOOGLE_ACCESS_TOKEN": "mock_oauth_token"}, clear=False):
            push_stats = sync_state_to_google_calendar(state, http_session=mock_session)

        self.assertEqual(push_stats["dossiers_pushed"], 1)
        self.assertEqual(push_stats["appointments_pushed"], 1)
        self.assertTrue(mock_session.patch.called, "Existing event with matching aim_event_id should be PATCHed.")
        self.assertTrue(mock_session.post.called, "New event without matching aim_event_id should be POSTed.")

        # Verify extendedProperties.private.aim_event_id was sent on POST
        posted_body = mock_session.post.call_args.kwargs["json"]
        self.assertEqual(
            posted_body["extendedProperties"]["private"]["aim_event_id"],
            "appt1234567890abcdef1234",
        )


if __name__ == "__main__":
    unittest.main()
