# Calendar Intelligence & Cloud Synchronization (`core/calendar_sync.py`)

## Overview
Implemented in **Issue #14**, the Calendar Intelligence Engine (`core/calendar_sync.py`) bridges the local chronological Daily Notes (`conversations/daily_notes/YYYY-MM-DD.md`) with standard RFC-5545 `.ics` feeds and Google Calendar API v3.

---

## The 4 Architectural Guardrails

### Guardrail #1: Unified Hybrid LLM Provider (`core/llm_provider.py`)
All structured event extraction routes through `core/llm_provider.py` (`AIM_LLM_PROVIDER=auto|ollama|gemini`):
* **`auto` (default):** Uses Google `gemini-2.5-flash` when `GEMINI_API_KEY` is present in the environment or `.env`, otherwise falls back to local Ollama (`qwen3.5:4b`).
* **`ollama`:** Enforces 100% air-gapped local inference.
* **`gemini`:** Enforces structured JSON generation via `google-genai` SDK or REST v1beta.

### Guardrail #2: Dual-Track Extraction (`A.I.M. Activity Log` vs. `A.I.M. Appointments`)
To prevent daily retrospective summaries from cluttering time-bounded schedule slots, each Daily Note is synthesized into two distinct tracks:
1. **Retrospective Daily Dossiers (`A.I.M. Activity Log`):**
   * One all-day summary event per `YYYY-MM-DD` Daily Note (`headline`, executive `summary`, `key_events`, and `media_highlights`).
2. **Prospective Appointments (`A.I.M. Appointments`):**
   * Time-bounded future commitments, meetings, and service appointments extracted from calls and texts, anchored against the note's `YYYY-MM-DD` date to resolve relative phrases (e.g., *"tomorrow at 9am"*, *"this Friday"*).
   * Filtered by a minimum confidence threshold (`--min-confidence`, default `0.65`).

### Guardrail #3: Canonical Local Ledger & Deterministic Deduplication
* **Canonical State (`conversations/calendar/.calendar_state.json`):** Tracks processed Daily Note mtimes/sizes, extracted dossiers, appointments, and remote Google Calendar IDs.
* **Deterministic 24-Hex Hash (`aim_event_id`):** Every dossier and appointment computes `compute_aim_event_id(kind, date_or_start, summary)` via SHA-256.
* **RFC-5545 `.ics` Feeds:** Exports `conversations/calendar/aim_activity_log.ics` and `conversations/calendar/aim_appointments.ics` with `UID:aim-<aim_event_id>@aim-calendar.local`.
* **Idempotent Google Calendar Upsert:** Queries `privateExtendedProperty=aim_event_id=<hash>` before inserting; updates existing events in-place via `PATCH`/`PUT` and creates new events via `POST`, preventing duplicate calendar entries across repeated runs.

### Guardrail #4: Privacy & Quality Gate
`extract_golden_note_context()` parses each Daily Note and strips any entry marked `Status: GARBAGE` or `[GARBAGE]` before LLM analysis or cloud synchronization.

---

## CLI Operations

```bash
# Analyze the 10 most recent Daily Notes and export local .ics feeds
python3 core/calendar_sync.py --recent 10 --export-ics

# Process a single Daily Note in dry-run mode
python3 core/calendar_sync.py --file conversations/daily_notes/2026-09-04.md --dry-run

# Run full analysis, .ics export, and Google Calendar API v3 upsert
python3 core/calendar_sync.py --recent 30 --export-ics --gcal-sync
```
