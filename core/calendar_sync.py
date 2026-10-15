import os
import re
import glob
import json
import hashlib
import argparse
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
import requests

from core.llm_provider import generate_text, resolve_provider
from core.ingest_to_lancedb import parse_daily_note

DEFAULT_CALENDAR_DIR = "conversations/calendar"
DEFAULT_STATE_FILE = "conversations/calendar/.calendar_state.json"
DEFAULT_ACTIVITY_CALENDAR_NAME = "A.I.M. Activity Log"
DEFAULT_APPOINTMENTS_CALENDAR_NAME = "A.I.M. Appointments"
GCAL_API_BASE = "https://www.googleapis.com/calendar/v3"


def compute_aim_event_id(kind: str, date_or_start: str, summary: str = "") -> str:
    """
    Computes a deterministic 24-hex-char event ID (Guardrail #3) used as both
    the .ics UID prefix and Google Calendar `extendedProperties.private.aim_event_id`.
    """
    norm_summary = " ".join(summary.strip().lower().split())
    seed = f"{kind.strip().lower()}:{date_or_start.strip()[:16]}:{norm_summary}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def load_calendar_state(state_path: str = DEFAULT_STATE_FILE) -> Dict[str, Any]:
    """Loads the canonical local calendar ledger from disk."""
    if state_path and os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("processed_notes", {})
                    data.setdefault("dossiers", {})
                    data.setdefault("appointments", {})
                    data.setdefault("calendar_ids", {})
                    return data
        except Exception:
            pass
    return {
        "processed_notes": {},
        "dossiers": {},
        "appointments": {},
        "calendar_ids": {},
    }


def save_calendar_state(state_path: str, state: Dict[str, Any]) -> None:
    """Persists the canonical local calendar ledger to disk."""
    if not state_path:
        return
    os.makedirs(os.path.dirname(os.path.abspath(state_path)), exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def extract_golden_note_context(filepath: str, max_chars: int = 18000) -> Tuple[str, List[str], str]:
    """
    Guardrail #4 Privacy & Quality Gate:
    Parses a Daily Note and filters out any entries marked as GARBAGE or empty,
    returning `(date_str, clean_entries, formatted_context)`.
    """
    metadata, entries = parse_daily_note(filepath)
    date_str = str(metadata.get("date", "unknown"))
    clean_entries: List[str] = []

    for entry in entries:
        if "status: garbage" in entry.lower() or "[garbage]" in entry.lower():
            continue
        clean_entries.append(entry)

    joined = "\n".join(clean_entries)
    if len(joined) > max_chars:
        joined = joined[:max_chars] + "\n... [truncated]"
    return date_str, clean_entries, joined


def analyze_daily_note(
    filepath: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    min_confidence: float = 0.65,
    llm_fn: Optional[Callable[[str, str], Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Extracts both:
    1. Retrospective Daily Dossier (`dossier`) for 'A.I.M. Activity Log'
    2. Prospective Appointments (`appointments`) for 'A.I.M. Appointments'
    from a single Daily Note (`YYYY-MM-DD.md`).
    """
    date_str, clean_entries, context_text = extract_golden_note_context(filepath)
    if date_str == "unknown" or not clean_entries:
        return None

    try:
        anchor_dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekday_name = anchor_dt.strftime("%A")
    except ValueError:
        weekday_name = "Unknown"

    system_prompt = (
        "You are the A.I.M. Calendar Intelligence Engine. "
        "Analyze the user's chronological Daily Note and return strict JSON with two top-level keys:\n"
        "1. \"dossier\": {\n"
        "     \"headline\": \"Short 5-10 word title summarizing the day\",\n"
        "     \"summary\": \"2-4 sentence executive summary of key calls, texts, work, and decisions\",\n"
        "     \"key_events\": [\"bullet 1\", \"bullet 2\"],\n"
        "     \"media_highlights\": [\"visual context or media highlight if any\"]\n"
        "   }\n"
        "2. \"appointments\": [\n"
        "     {\n"
        "       \"summary\": \"Event title (e.g. Roof Quote - Bob)\",\n"
        "       \"start\": \"YYYY-MM-DDTHH:MM:SS\",\n"
        "       \"end\": \"YYYY-MM-DDTHH:MM:SS\",\n"
        "       \"attendees\": [\"Name or phone\"],\n"
        "       \"location\": \"Address or location if mentioned, else empty string\",\n"
        "       \"confidence\": 0.0 to 1.0,\n"
        "       \"source_quote\": \"Exact quote from the log establishing the appointment\"\n"
        "     }\n"
        "   ]\n"
        "Resolve any relative dates (e.g., 'tomorrow at 10am', 'Thursday at 2pm') strictly relative "
        f"to the note's anchor date: {date_str} ({weekday_name}). "
        "Only extract concrete appointments, meetings, service visits, or scheduled follow-ups."
    )

    user_prompt = f"Anchor Date: {date_str} ({weekday_name})\n\nDaily Log Entries:\n{context_text}"

    if llm_fn is not None:
        raw_result = llm_fn(user_prompt, system_prompt)
    else:
        raw_result = generate_text(
            prompt=user_prompt,
            system_prompt=system_prompt,
            provider=provider,
            model=model,
            json_mode=True,
            temperature=0.1,
        )

    if not isinstance(raw_result, dict):
        return None

    dossier_raw = raw_result.get("dossier") or {}
    if not isinstance(dossier_raw, dict):
        dossier_raw = {}

    headline = str(dossier_raw.get("headline") or f"Daily Activity Log ({date_str})").strip()
    summary = str(dossier_raw.get("summary") or f"Processed {len(clean_entries)} communication entries.").strip()
    key_events = [str(x).strip() for x in (dossier_raw.get("key_events") or []) if str(x).strip()]
    media_highlights = [str(x).strip() for x in (dossier_raw.get("media_highlights") or []) if str(x).strip()]

    dossier_id = compute_aim_event_id("dossier", date_str)
    dossier = {
        "aim_event_id": dossier_id,
        "date": date_str,
        "headline": headline,
        "summary": summary,
        "key_events": key_events,
        "media_highlights": media_highlights,
        "entry_count": len(clean_entries),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    valid_appointments: List[Dict[str, Any]] = []
    for item in raw_result.get("appointments") or []:
        if not isinstance(item, dict):
            continue
        appt_summary = str(item.get("summary") or "").strip()
        start_iso = str(item.get("start") or "").strip()
        end_iso = str(item.get("end") or "").strip()
        if not appt_summary or not start_iso:
            continue

        try:
            conf = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        if conf < min_confidence:
            continue

        # Validate & normalize ISO-8601 start/end
        try:
            start_dt = datetime.fromisoformat(start_iso.replace("Z", ""))
        except ValueError:
            continue

        if end_iso:
            try:
                end_dt = datetime.fromisoformat(end_iso.replace("Z", ""))
                if end_dt <= start_dt:
                    end_dt = start_dt + timedelta(hours=1)
            except ValueError:
                end_dt = start_dt + timedelta(hours=1)
        else:
            end_dt = start_dt + timedelta(hours=1)

        norm_start = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
        norm_end = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
        appt_id = compute_aim_event_id("appt", norm_start, appt_summary)

        attendees = [str(a).strip() for a in (item.get("attendees") or []) if str(a).strip()]
        valid_appointments.append({
            "aim_event_id": appt_id,
            "summary": appt_summary,
            "start": norm_start,
            "end": norm_end,
            "attendees": attendees,
            "location": str(item.get("location") or "").strip(),
            "confidence": round(conf, 3),
            "source_quote": str(item.get("source_quote") or "").strip(),
            "source_date": date_str,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    return {
        "date": date_str,
        "dossier": dossier,
        "appointments": valid_appointments,
    }


def _ics_escape(text: str) -> str:
    """Escapes special characters for RFC-5545 iCalendar fields."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def export_ics_calendars(
    state: Dict[str, Any],
    calendar_dir: str = DEFAULT_CALENDAR_DIR,
) -> Dict[str, str]:
    """
    Writes canonical local RFC-5545 `.ics` feeds for both:
    - `aim_activity_log.ics` (Retrospective all-day Daily Dossiers)
    - `aim_appointments.ics` (Prospective extracted appointments)
    """
    os.makedirs(calendar_dir, exist_ok=True)
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # 1. Retrospective Activity Log (.ics)
    activity_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//A.I.M. Calendar//Activity Log//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{DEFAULT_ACTIVITY_CALENDAR_NAME}",
    ]
    for date_str, dossier in sorted((state.get("dossiers") or {}).items()):
        try:
            dt_start = datetime.strptime(date_str, "%Y-%m-%d")
            dt_end = dt_start + timedelta(days=1)
        except ValueError:
            continue
        uid = f"{dossier['aim_event_id']}@aim-calendar.local"
        title = f"[Dossier] {dossier.get('headline', date_str)}"
        desc_parts = [dossier.get("summary", "")]
        if dossier.get("key_events"):
            desc_parts.append("\nKey Events:\n- " + "\n- ".join(dossier["key_events"]))
        if dossier.get("media_highlights"):
            desc_parts.append("\nVisual Context:\n- " + "\n- ".join(dossier["media_highlights"]))
        desc = "\n".join(p for p in desc_parts if p)

        activity_lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_stamp}",
            f"DTSTART;VALUE=DATE:{dt_start.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{dt_end.strftime('%Y%m%d')}",
            f"SUMMARY:{_ics_escape(title)}",
            f"DESCRIPTION:{_ics_escape(desc)}",
            f"X-AIM-EVENT-ID:{dossier['aim_event_id']}",
            "END:VEVENT",
        ])
    activity_lines.append("END:VCALENDAR")
    activity_ics_path = os.path.join(calendar_dir, "aim_activity_log.ics")
    with open(activity_ics_path, "w", encoding="utf-8") as f:
        f.write("\r\n".join(activity_lines) + "\r\n")

    # 2. Prospective Appointments (.ics)
    appt_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//A.I.M. Calendar//Appointments//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{DEFAULT_APPOINTMENTS_CALENDAR_NAME}",
    ]
    for appt_id, appt in sorted((state.get("appointments") or {}).items()):
        try:
            dt_start = datetime.fromisoformat(appt["start"])
            dt_end = datetime.fromisoformat(appt["end"])
        except (KeyError, ValueError):
            continue
        uid = f"{appt_id}@aim-calendar.local"
        desc_lines = [
            f"Source Note: {appt.get('source_date', '')}",
            f"Confidence: {appt.get('confidence', 0.0)}",
        ]
        if appt.get("attendees"):
            desc_lines.append(f"Participants: {', '.join(appt['attendees'])}")
        if appt.get("source_quote"):
            desc_lines.append(f"Quote: \"{appt['source_quote']}\"")

        appt_lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_stamp}",
            f"DTSTART:{dt_start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{dt_end.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{_ics_escape(appt.get('summary', 'Appointment'))}",
            f"DESCRIPTION:{_ics_escape(chr(10).join(desc_lines))}",
        ])
        if appt.get("location"):
            appt_lines.append(f"LOCATION:{_ics_escape(appt['location'])}")
        appt_lines.extend([
            f"X-AIM-EVENT-ID:{appt_id}",
            "END:VEVENT",
        ])
    appt_lines.append("END:VCALENDAR")
    appt_ics_path = os.path.join(calendar_dir, "aim_appointments.ics")
    with open(appt_ics_path, "w", encoding="utf-8") as f:
        f.write("\r\n".join(appt_lines) + "\r\n")

    return {
        "activity_ics": activity_ics_path,
        "appointments_ics": appt_ics_path,
    }


def _get_gcal_access_token(token_file: Optional[str] = None) -> Optional[str]:
    """
    Loads and refreshes a Google OAuth2 access token from `token.json`
    (or `AIM_GOOGLE_ACCESS_TOKEN` env var) if configured.
    """
    env_token = os.environ.get("AIM_GOOGLE_ACCESS_TOKEN", "").strip()
    if env_token:
        return env_token

    token_path = token_file or os.environ.get("AIM_GOOGLE_TOKEN_FILE", "token.json")
    if not os.path.isfile(token_path):
        return None

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        creds = Credentials.from_authorized_user_file(
            token_path,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        if creds and creds.valid:
            return creds.token
    except Exception as e:
        print(f"[WARN] Could not load/refresh Google OAuth token from {token_path}: {e}")
    return None


def _ensure_secondary_calendar(
    session: requests.Session,
    headers: Dict[str, str],
    calendar_name: str,
    cached_id: Optional[str] = None,
) -> str:
    """Finds or creates a named secondary Google Calendar and returns its calendarId."""
    if cached_id:
        return cached_id

    resp = session.get(f"{GCAL_API_BASE}/users/me/calendarList", headers=headers, timeout=30)
    resp.raise_for_status()
    items = resp.json().get("items") or []
    for item in items:
        if item.get("summary") == calendar_name and item.get("id"):
            return str(item["id"])

    create_resp = session.post(
        f"{GCAL_API_BASE}/calendars",
        headers=headers,
        json={"summary": calendar_name, "description": f"Managed by A.I.M. Calendar ({calendar_name})"},
        timeout=30,
    )
    create_resp.raise_for_status()
    return str(create_resp.json()["id"])


def _upsert_gcal_event(
    session: requests.Session,
    headers: Dict[str, str],
    calendar_id: str,
    aim_event_id: str,
    event_body: Dict[str, Any],
) -> str:
    """
    Idempotently inserts or updates a Google Calendar event using
    `extendedProperties.private.aim_event_id` (Guardrail #3).
    """
    event_body.setdefault("extendedProperties", {}).setdefault("private", {})[
        "aim_event_id"
    ] = aim_event_id

    search_resp = session.get(
        f"{GCAL_API_BASE}/calendars/{ requests.utils.quote(calendar_id, safe='') }/events",
        headers=headers,
        params={"privateExtendedProperty": f"aim_event_id={aim_event_id}"},
        timeout=30,
    )
    search_resp.raise_for_status()
    existing = search_resp.json().get("items") or []

    cal_enc = requests.utils.quote(calendar_id, safe="")
    if existing:
        gcal_event_id = existing[0]["id"]
        ev_enc = requests.utils.quote(str(gcal_event_id), safe="")
        patch_resp = session.patch(
            f"{GCAL_API_BASE}/calendars/{cal_enc}/events/{ev_enc}",
            headers=headers,
            json=event_body,
            timeout=30,
        )
        patch_resp.raise_for_status()
        return str(patch_resp.json().get("id", gcal_event_id))

    post_resp = session.post(
        f"{GCAL_API_BASE}/calendars/{cal_enc}/events",
        headers=headers,
        json=event_body,
        timeout=30,
    )
    post_resp.raise_for_status()
    return str(post_resp.json().get("id", ""))


def sync_state_to_google_calendar(
    state: Dict[str, Any],
    token_file: Optional[str] = None,
    timezone_str: str = "America/New_York",
    dry_run: bool = False,
    http_session: Optional[requests.Session] = None,
) -> Dict[str, int]:
    """
    Pushes unsynced (or updated) Retrospective Dossiers to 'A.I.M. Activity Log'
    and Prospective Appointments to 'A.I.M. Appointments' via Google Calendar API v3.
    """
    if dry_run:
        return {"dossiers_pushed": 0, "appointments_pushed": 0}

    token = _get_gcal_access_token(token_file=token_file)
    if not token:
        return {"dossiers_pushed": 0, "appointments_pushed": 0}

    session = http_session or requests.Session()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    activity_cal_name = os.environ.get("AIM_GCAL_ACTIVITY_CALENDAR", DEFAULT_ACTIVITY_CALENDAR_NAME)
    appt_cal_name = os.environ.get("AIM_GCAL_APPOINTMENTS_CALENDAR", DEFAULT_APPOINTMENTS_CALENDAR_NAME)
    cal_ids = state.setdefault("calendar_ids", {})

    activity_cal_id = _ensure_secondary_calendar(
        session, headers, activity_cal_name, cal_ids.get(activity_cal_name)
    )
    cal_ids[activity_cal_name] = activity_cal_id

    appt_cal_id = _ensure_secondary_calendar(
        session, headers, appt_cal_name, cal_ids.get(appt_cal_name)
    )
    cal_ids[appt_cal_name] = appt_cal_id

    dossiers_pushed = 0
    appointments_pushed = 0

    for date_str, dossier in sorted((state.get("dossiers") or {}).items()):
        if dossier.get("gcal_synced"):
            continue
        try:
            dt_start = datetime.strptime(date_str, "%Y-%m-%d")
            dt_end = dt_start + timedelta(days=1)
        except ValueError:
            continue

        desc_parts = [dossier.get("summary", "")]
        if dossier.get("key_events"):
            desc_parts.append("\nKey Events:\n- " + "\n- ".join(dossier["key_events"]))
        if dossier.get("media_highlights"):
            desc_parts.append("\nVisual Context:\n- " + "\n- ".join(dossier["media_highlights"]))

        body = {
            "summary": f"[Dossier] {dossier.get('headline', date_str)}",
            "description": "\n".join(p for p in desc_parts if p),
            "start": {"date": dt_start.strftime("%Y-%m-%d")},
            "end": {"date": dt_end.strftime("%Y-%m-%d")},
        }
        gcal_id = _upsert_gcal_event(
            session, headers, activity_cal_id, dossier["aim_event_id"], body
        )
        dossier["gcal_event_id"] = gcal_id
        dossier["gcal_synced"] = True
        dossiers_pushed += 1

    for appt_id, appt in sorted((state.get("appointments") or {}).items()):
        if appt.get("gcal_synced"):
            continue
        desc_lines = [
            f"Source Note: {appt.get('source_date', '')}",
            f"Confidence: {appt.get('confidence', 0.0)}",
        ]
        if appt.get("attendees"):
            desc_lines.append(f"Participants: {', '.join(appt['attendees'])}")
        if appt.get("source_quote"):
            desc_lines.append(f"Quote: \"{appt['source_quote']}\"")

        body = {
            "summary": appt.get("summary", "Appointment"),
            "location": appt.get("location", ""),
            "description": "\n".join(desc_lines),
            "start": {"dateTime": appt["start"], "timeZone": timezone_str},
            "end": {"dateTime": appt["end"], "timeZone": timezone_str},
        }
        gcal_id = _upsert_gcal_event(
            session, headers, appt_cal_id, appt_id, body
        )
        appt["gcal_event_id"] = gcal_id
        appt["gcal_synced"] = True
        appointments_pushed += 1

    return {
        "dossiers_pushed": dossiers_pushed,
        "appointments_pushed": appointments_pushed,
    }


def run_calendar_sync(
    notes_dir: str = "conversations/daily_notes",
    calendar_dir: str = DEFAULT_CALENDAR_DIR,
    state_path: Optional[str] = None,
    single_file: Optional[str] = None,
    recent: int = 7,
    limit: int = 0,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    min_confidence: float = 0.65,
    push_gcal: bool = True,
    token_file: Optional[str] = None,
    force: bool = False,
    dry_run: bool = False,
    llm_fn: Optional[Callable[[str, str], Dict[str, Any]]] = None,
    http_session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    """
    End-to-end Phase 2 Calendar Intelligence & Sync pipeline:
    1. Scans Daily Notes (`YYYY-MM-DD.md`) incrementally using canonical local state.
    2. Extracts Retrospective Daily Dossiers and Prospective Appointments.
    3. Saves canonical JSON state (`.calendar_state.json`) and exports RFC-5545 `.ics` feeds.
    4. Optionally syncs to Google Calendar ('A.I.M. Activity Log' & 'A.I.M. Appointments')
       using deterministic `extendedProperties.private.aim_event_id` deduplication.
    """
    if state_path is None:
        state_path = os.path.join(calendar_dir, ".calendar_state.json")

    state = load_calendar_state(state_path)

    if single_file:
        files = [single_file] if os.path.isfile(single_file) else []
    elif os.path.isdir(notes_dir):
        files = sorted(glob.glob(os.path.join(notes_dir, "*.md")))
    else:
        files = []

    if recent > 0 and not single_file:
        files = files[-recent:]
    if limit > 0 and not single_file:
        files = files[:limit]

    notes_analyzed = 0
    new_appointments = 0

    for filepath in files:
        fname = os.path.basename(filepath)
        try:
            file_size = os.path.getsize(filepath)
        except OSError:
            continue

        recorded = state["processed_notes"].get(fname)
        if not force and recorded and recorded.get("size") == file_size:
            continue

        if dry_run:
            print(f"[DRY-RUN] Would analyze Daily Note for calendar sync: {fname}")
            notes_analyzed += 1
            continue

        try:
            result = analyze_daily_note(
                filepath,
                provider=provider,
                model=model,
                min_confidence=min_confidence,
                llm_fn=llm_fn,
            )
        except Exception as e:
            print(f"[WARN] Calendar intelligence extraction failed for {fname}: {e}")
            continue

        if not result:
            continue

        date_str = result["date"]
        state["dossiers"][date_str] = result["dossier"]
        for appt in result["appointments"]:
            state["appointments"][appt["aim_event_id"]] = appt
            new_appointments += 1

        state["processed_notes"][fname] = {
            "size": file_size,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        notes_analyzed += 1

    ics_paths = {"activity_ics": "", "appointments_ics": ""}
    gcal_stats = {"dossiers_pushed": 0, "appointments_pushed": 0}

    if not dry_run:
        save_calendar_state(state_path, state)
        ics_paths = export_ics_calendars(state, calendar_dir=calendar_dir)
        if push_gcal:
            try:
                gcal_stats = sync_state_to_google_calendar(
                    state,
                    token_file=token_file,
                    dry_run=dry_run,
                    http_session=http_session,
                )
                if gcal_stats["dossiers_pushed"] > 0 or gcal_stats["appointments_pushed"] > 0:
                    save_calendar_state(state_path, state)
            except Exception as e:
                print(f"[WARN] Google Calendar push encountered an error: {e}")

    return {
        "notes_analyzed": notes_analyzed,
        "total_dossiers": len(state.get("dossiers", {})),
        "total_appointments": len(state.get("appointments", {})),
        "new_appointments": new_appointments,
        "dossiers_pushed": gcal_stats["dossiers_pushed"],
        "appointments_pushed": gcal_stats["appointments_pushed"],
        "activity_ics": ics_paths["activity_ics"],
        "appointments_ics": ics_paths["appointments_ics"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="A.I.M. Calendar Intelligence & Cloud Synchronization Engine (Issue #14)."
    )
    parser.add_argument("--notes-dir", default="conversations/daily_notes", help="Directory containing Daily Notes.")
    parser.add_argument("--calendar-dir", default=DEFAULT_CALENDAR_DIR, help="Output directory for canonical state and .ics feeds.")
    parser.add_argument("--state-file", default=None, help="Path to .calendar_state.json ledger.")
    parser.add_argument("--file", default=None, help="Analyze a single specific YYYY-MM-DD.md Daily Note.")
    parser.add_argument("--recent", type=int, default=7, help="Analyze the N most recent Daily Notes (default: 7, 0 for all).")
    parser.add_argument("--limit", type=int, default=0, help="Max Daily Notes to process in this run.")
    parser.add_argument("--provider", choices=["auto", "ollama", "gemini"], default=None, help="LLM provider override.")
    parser.add_argument("--model", default=None, help="LLM model override.")
    parser.add_argument("--min-confidence", type=float, default=0.65, help="Minimum confidence threshold for appointments.")
    parser.add_argument("--no-gcal", action="store_true", help="Skip live Google Calendar API push (only update local ledger + .ics).")
    parser.add_argument("--token-file", default=None, help="Path to Google OAuth token.json.")
    parser.add_argument("--force", action="store_true", help="Re-analyze notes even if unchanged in ledger.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate execution without writing files or calling APIs.")
    args = parser.parse_args()

    stats = run_calendar_sync(
        notes_dir=args.notes_dir,
        calendar_dir=args.calendar_dir,
        state_path=args.state_file,
        single_file=args.file,
        recent=args.recent,
        limit=args.limit,
        provider=args.provider,
        model=args.model,
        min_confidence=args.min_confidence,
        push_gcal=not args.no_gcal,
        token_file=args.token_file,
        force=args.force,
        dry_run=args.dry_run,
    )
    print(
        f"[CALENDAR-SYNC] Complete | Notes analyzed: {stats['notes_analyzed']} | "
        f"Dossiers: {stats['total_dossiers']} (GCal pushed: {stats['dossiers_pushed']}) | "
        f"Appointments: {stats['total_appointments']} (GCal pushed: {stats['appointments_pushed']})"
    )


if __name__ == "__main__":
    main()
