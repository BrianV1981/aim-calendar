import os
import xml.etree.ElementTree as ET
from datetime import datetime
from collections import defaultdict
import glob
import base64
import hashlib
import mimetypes

MIME_MAP = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "video/mp4": ".mp4",
    "video/3gpp": ".3gp",
    "video/3gp": ".3gp",
    "audio/amr": ".amr",
    "audio/3gpp": ".3gp",
    "audio/aac": ".aac",
    "audio/mp3": ".mp3",
    "audio/mpeg": ".mp3",
    "audio/m4a": ".m4a",
    "application/pdf": ".pdf",
    "text/x-vcard": ".vcf",
    "text/vcard": ".vcf",
}


def append_to_daily_files(buffer, output_dir):
    """Flushes the buffered logs to their respective daily markdown files."""
    for day_key, logs in buffer.items():
        md_path = os.path.join(output_dir, f"{day_key}.md")

        existing_content = ""
        if os.path.exists(md_path):
            with open(md_path, "r", encoding="utf-8") as f:
                existing_content = f.read()

        with open(md_path, "w", encoding="utf-8") as f:
            if not existing_content:
                f.write(
                    f"---\n"
                    f"date: {day_key}\n"
                    f"type: daily_exocortex\n"
                    f"tags:\n"
                    f"  - daily-note\n"
                    f"  - calendar\n"
                    f"  - timeline\n"
                    f"  - exocortex\n"
                    f"---\n"
                )
                f.write(f"# Daily Log: {day_key}\n\n")
            else:
                f.write(existing_content)
                if not existing_content.endswith("\n"):
                    f.write("\n")

            for log in logs:
                if log["content"] not in existing_content:
                    f.write(f"- {log['content']}\n")


def extract_mms_parts(elem, timestamp_ms, media_dir, output_dir, md5_cache):
    """
    Extracts text captions and decodes Base64 media payloads from <part> tags.
    Saves media to media_dir with MD5-based deduplication and returns relative markdown links.
    """
    os.makedirs(media_dir, exist_ok=True)
    parts = elem.find("parts")
    text_pieces = []
    media_links = []

    if parts is not None:
        for part in parts:
            ct = part.get("ct", "").lower()
            if ct == "application/smil":
                continue

            # Text body parts
            if ct == "text/plain":
                t = part.get("text") or part.text or ""
                if t and t != "null":
                    clean_t = t.replace("\r\n", " ").replace("\n", " ").replace("\r", "").strip()
                    if clean_t:
                        text_pieces.append(clean_t)

            # Rich media payload parts (Base64)
            data_b64 = part.get("data")
            if data_b64 and data_b64 != "null":
                try:
                    raw_bytes = base64.b64decode(data_b64)
                except Exception:
                    raw_bytes = None

                if raw_bytes:
                    md5_hex = hashlib.md5(raw_bytes).hexdigest()
                    ext = MIME_MAP.get(ct)
                    if not ext:
                        ext = mimetypes.guess_extension(ct) or ".bin"
                        if ext == ".jpe":
                            ext = ".jpg"

                    if md5_hex in md5_cache:
                        saved_name = md5_cache[md5_hex]
                    else:
                        saved_name = f"mms_{timestamp_ms}_{md5_hex[:8]}{ext}"
                        dest_path = os.path.join(media_dir, saved_name)
                        if not os.path.exists(dest_path):
                            with open(dest_path, "wb") as f_out:
                                f_out.write(raw_bytes)
                        md5_cache[md5_hex] = saved_name

                    dest_path = os.path.join(media_dir, saved_name)
                    rel_path = os.path.relpath(dest_path, output_dir)

                    if ct.startswith("image/"):
                        media_links.append(f"  ![MMS Image]({rel_path})")
                    elif ct.startswith("video/"):
                        media_links.append(f"  [MMS Video]({rel_path})")
                    elif ct.startswith("audio/"):
                        media_links.append(f"  [MMS Audio]({rel_path})")
                    else:
                        media_links.append(f"  [MMS Attachment]({rel_path})")

                    caption = part.get("text")
                    if caption and caption != "null":
                        clean_cap = caption.strip()
                        if clean_cap and clean_cap not in text_pieces:
                            media_links.append(f"  > {clean_cap}")

    text_body = " ".join(text_pieces).strip()
    return text_body, media_links


def parse_large_xml(xml_path, output_dir="conversations/daily_notes", media_dir="conversations/media", batch_size=50000, dry_run=False):
    """
    Parses massive XML files (10GB+) using iterparse to avoid OOM crashes.
    Extracts Calls, SMS, and MMS (including Base64 media payloads).
    Batches writes to disk every `batch_size` elements.
    """
    if not os.path.exists(xml_path):
        print(f"File {xml_path} does not exist. Skipping.")
        return 0

    if dry_run:
        print(f"[DRY-RUN] Would parse XML file: {xml_path}")
        return 0

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(media_dir, exist_ok=True)

    print(f"Streaming parse of {xml_path} (this prevents RAM crashing)...")

    buffer = defaultdict(list)
    element_count = 0
    total_processed = 0
    md5_cache = {}

    context = ET.iterparse(xml_path, events=("end",))

    for event, elem in context:
        tag = elem.tag
        log_entry = None
        day_key = None

        if tag == "call":
            number = elem.get("number", "Unknown")
            contact = elem.get("contact_name", "(Unknown)")
            duration = elem.get("duration", "0")
            call_type_code = elem.get("type", "0")
            timestamp_ms = int(elem.get("date", "0"))

            call_type = "Unknown Call"
            if call_type_code == "1": call_type = "Incoming Call"
            elif call_type_code == "2": call_type = "Outgoing Call"
            elif call_type_code == "3": call_type = "Missed Call"
            elif call_type_code == "5": call_type = "Rejected Call"

            try:
                dt_obj = datetime.fromtimestamp(timestamp_ms / 1000.0)
                day_key = dt_obj.strftime("%Y-%m-%d")
                time_str = dt_obj.strftime("%I:%M %p")
                contact_display = contact if contact not in ("(Unknown)", "~", "null", "") else number
                log_entry = {
                    "timestamp_ms": timestamp_ms,
                    "content": f"**[{time_str}] {call_type}** with {contact_display} (Duration: {duration}s)"
                }
            except Exception:
                pass

        elif tag == "sms":
            number = elem.get("address", "Unknown")
            contact = elem.get("contact_name", "(Unknown)")
            body = elem.get("body", "")
            sms_type_code = elem.get("type", "1")
            timestamp_ms = int(elem.get("date", "0"))

            direction = "Received Text" if sms_type_code == "1" else "Sent Text"

            try:
                dt_obj = datetime.fromtimestamp(timestamp_ms / 1000.0)
                day_key = dt_obj.strftime("%Y-%m-%d")
                time_str = dt_obj.strftime("%I:%M %p")
                contact_display = contact if contact not in ("(Unknown)", "~", "null", "") else number
                clean_body = body.replace("\r\n", " ").replace("\n", " ").replace("\r", "")
                log_entry = {
                    "timestamp_ms": timestamp_ms,
                    "content": f"**[{time_str}] {direction}** ({contact_display}): \"{clean_body}\""
                }
            except Exception:
                pass

        elif tag == "mms":
            number = elem.get("address", "Unknown")
            contact = elem.get("contact_name", "(Unknown)")
            msg_box = elem.get("msg_box", "1")
            timestamp_ms = int(elem.get("date", "0"))

            direction = "Received MMS" if msg_box == "1" else "Sent MMS"

            # If address or contact is empty or "~", resolve from <addrs>
            if not contact or contact in ("(Unknown)", "~", "null") or not number or number in ("~", "null"):
                addrs = elem.find("addrs")
                if addrs is not None:
                    for addr in addrs:
                        addr_type = addr.get("type")
                        addr_val = addr.get("address", "")
                        if addr_val and addr_val != "~":
                            if msg_box == "1" and addr_type == "137":  # FROM
                                number = addr_val
                                break
                            elif msg_box == "2" and addr_type == "151":  # TO
                                number = addr_val
                                break

            try:
                dt_obj = datetime.fromtimestamp(timestamp_ms / 1000.0)
                day_key = dt_obj.strftime("%Y-%m-%d")
                time_str = dt_obj.strftime("%I:%M %p")
                contact_display = contact if contact not in ("(Unknown)", "~", "null", "") else (number if number and number != "~" else "Unknown")

                text_body, media_links = extract_mms_parts(elem, timestamp_ms, media_dir, output_dir, md5_cache)

                if text_body:
                    header = f"**[{time_str}] {direction}** ({contact_display}): \"{text_body}\""
                else:
                    header = f"**[{time_str}] {direction}** ({contact_display})"

                entry_lines = [header] + media_links
                full_content = "\n".join(entry_lines)

                log_entry = {
                    "timestamp_ms": timestamp_ms,
                    "content": full_content
                }
            except Exception:
                pass

        if tag in ("call", "sms", "mms"):
            if log_entry and day_key:
                buffer[day_key].append(log_entry)
                element_count += 1
                total_processed += 1

            # Clear the element from memory to prevent RAM bloat
            elem.clear()

        # Periodically flush the buffer to disk
        if element_count >= batch_size:
            append_to_daily_files(buffer, output_dir)
            buffer.clear()
            element_count = 0
            print(f"  ...processed {total_processed} records.")

    # Flush any remaining logs
    if buffer:
        append_to_daily_files(buffer, output_dir)
        print(f"  ...processed {total_processed} total records.")

    print(f"Finished parsing {xml_path}!")
    return total_processed


def load_manifest(manifest_path):
    """Loads the incremental ingestion manifest from disk."""
    import json
    if manifest_path and os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("xml_files", {})
                    data.setdefault("transcripts", {})
                    return data
        except Exception:
            pass
    return {"xml_files": {}, "transcripts": {}}


def save_manifest(manifest_path, manifest_data):
    """Persists the incremental ingestion manifest to disk."""
    import json
    if not manifest_path:
        return
    os.makedirs(os.path.dirname(os.path.abspath(manifest_path)), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, sort_keys=True)


def prune_superseded_backups(
    input_dir="conversations/sms_raw",
    manifest_path=None,
    keep_latest=1,
    dry_run=False
):
    """
    Prunes superseded cumulative SMS/Call XML backups (`sms-*.xml`, `calls-*.xml`),
    already-ingested unpacked archive XMLs (`calls.xml`, `messages.xml`), and
    already-extracted `.zip` archives (preserving `.zip.extracted` markers and
    `.processed_xml_manifest.json` so rclone/sync_daemon never re-downloads them).
    """
    if not os.path.exists(input_dir):
        return {"pruned_files": 0, "bytes_freed": 0}

    if manifest_path is None:
        manifest_path = os.path.join(input_dir, ".processed_xml_manifest.json")

    manifest = load_manifest(manifest_path)
    recorded_xmls = manifest.get("xml_files", {})

    pruned_files = 0
    bytes_freed = 0

    for pattern in ("calls-*.xml", "sms-*.xml"):
        matched = sorted(glob.glob(os.path.join(input_dir, pattern)))
        superseded = matched[:-keep_latest] if keep_latest > 0 else matched
        for fpath in superseded:
            fname = os.path.basename(fpath)
            if fname not in recorded_xmls:
                continue
            try:
                sz = os.path.getsize(fpath)
                if dry_run:
                    print(f"[DRY-RUN] Would prune superseded XML: {fname} ({sz} bytes)")
                else:
                    os.remove(fpath)
                    print(f"Pruned superseded XML: {fname} ({sz / (1024**3):.2f} GB)")
                pruned_files += 1
                bytes_freed += sz
            except OSError:
                pass

    for unpacked_name in ("calls.xml", "messages.xml"):
        upath = os.path.join(input_dir, unpacked_name)
        if os.path.exists(upath) and unpacked_name in recorded_xmls:
            try:
                sz = os.path.getsize(upath)
                if dry_run:
                    print(f"[DRY-RUN] Would prune unpacked XML: {unpacked_name} ({sz} bytes)")
                else:
                    os.remove(upath)
                    print(f"Pruned unpacked XML: {unpacked_name} ({sz / (1024**2):.2f} MB)")
                pruned_files += 1
                bytes_freed += sz
            except OSError:
                pass

    for zpath in sorted(glob.glob(os.path.join(input_dir, "*.zip"))):
        marker = zpath + ".extracted"
        if os.path.exists(marker):
            zname = os.path.basename(zpath)
            try:
                sz = os.path.getsize(zpath)
                if dry_run:
                    print(f"[DRY-RUN] Would prune extracted archive: {zname} ({sz} bytes)")
                else:
                    os.remove(zpath)
                    print(f"Pruned extracted archive: {zname} ({sz / (1024**2):.2f} MB)")
                pruned_files += 1
                bytes_freed += sz
            except OSError:
                pass

    return {"pruned_files": pruned_files, "bytes_freed": bytes_freed}


def ingest_xml_directory(
    input_dir="conversations/sms_raw",
    output_dir="conversations/daily_notes",
    media_dir="conversations/media",
    manifest_path=None,
    force=False,
    dry_run=False,
    batch_size=50000,
    prune=True,
    keep_latest=1
):
    """
    Globs all calls-*.xml and sms-*.xml files in input_dir chronologically
    and parses only newly added or modified XML backups using a manifest ledger.
    Automatically prunes superseded raw backups after recording them in the manifest.
    """
    if not os.path.exists(input_dir):
        print(f"Input directory {input_dir} does not exist. Skipping XML directory ingestion.")
        return 0

    if manifest_path is None:
        manifest_path = os.path.join(input_dir, ".processed_xml_manifest.json")

    manifest_existed = os.path.exists(manifest_path)
    manifest = load_manifest(manifest_path)

    call_xmls = sorted(glob.glob(os.path.join(input_dir, "calls-*.xml")))
    sms_xmls = sorted(glob.glob(os.path.join(input_dir, "sms-*.xml")))
    unpacked_xmls = [
        os.path.join(input_dir, name)
        for name in ("calls.xml", "messages.xml")
        if os.path.exists(os.path.join(input_dir, name))
    ]
    all_xmls = call_xmls + sms_xmls + unpacked_xmls

    # Bootstrap legacy baseline: if manifest didn't exist yet but 2026-09-02.md is already built,
    # mark the legacy 20260903012405 baseline XMLs as processed so we don't re-parse 11GB redundantly.
    if not manifest_existed and not force and os.path.exists(os.path.join(output_dir, "2026-09-02.md")):
        for legacy_name in ("calls-20260903012405.xml", "sms-20260903012405.xml"):
            legacy_path = os.path.join(input_dir, legacy_name)
            if os.path.exists(legacy_path):
                st = os.stat(legacy_path)
                manifest["xml_files"][legacy_name] = {
                    "size": st.st_size,
                    "mtime": int(st.st_mtime)
                }
        if not dry_run and manifest["xml_files"]:
            save_manifest(manifest_path, manifest)

    # Mark unpacked calls.xml / messages.xml as already superseded if a newer cumulative XML is already ingested
    latest_ingested_mtime = max(
        (v.get("mtime", 0) for k, v in manifest["xml_files"].items() if k.startswith(("sms-", "calls-"))),
        default=0
    )
    for upath in unpacked_xmls:
        uname = os.path.basename(upath)
        if not force and uname not in manifest["xml_files"]:
            try:
                st = os.stat(upath)
                if latest_ingested_mtime >= int(st.st_mtime):
                    manifest["xml_files"][uname] = {
                        "size": st.st_size,
                        "mtime": int(st.st_mtime)
                    }
                    if not dry_run:
                        save_manifest(manifest_path, manifest)
            except OSError:
                pass

    files_parsed = 0
    for xml_path in all_xmls:
        fname = os.path.basename(xml_path)
        try:
            st = os.stat(xml_path)
        except OSError:
            continue

        recorded = manifest["xml_files"].get(fname)
        if not force and recorded and recorded.get("size") == st.st_size:
            print(f"Skipping already ingested XML: {fname}")
            continue

        if dry_run:
            print(f"[DRY-RUN] Would parse XML backup: {fname} ({st.st_size} bytes)")
            files_parsed += 1
            continue

        parse_large_xml(xml_path, output_dir=output_dir, media_dir=media_dir, batch_size=batch_size, dry_run=False)
        manifest["xml_files"][fname] = {
            "size": st.st_size,
            "mtime": int(st.st_mtime)
        }
        save_manifest(manifest_path, manifest)
        files_parsed += 1

    if prune:
        prune_superseded_backups(
            input_dir=input_dir,
            manifest_path=manifest_path,
            keep_latest=keep_latest,
            dry_run=dry_run
        )

    return files_parsed


def ingest_diarized_transcripts(
    transcripts_dir="conversations_diarized",
    output_dir="conversations/daily_notes",
    manifest_path=None,
    force=False,
    dry_run=False,
    max_preview_lines=4
):
    """
    Chronologically links and interleaves diarized call transcripts from
    `conversations_diarized/*.md` into `conversations/daily_notes/YYYY-MM-DD.md`.
    """
    import re
    if not os.path.exists(transcripts_dir):
        return 0

    if manifest_path is None:
        manifest_path = os.path.join(output_dir, ".processed_transcripts_manifest.json")

    manifest = load_manifest(manifest_path)
    recorded_transcripts = manifest.get("transcripts", {})

    md_files = sorted(glob.glob(os.path.join(transcripts_dir, "*.md")))
    if not md_files:
        return 0

    os.makedirs(output_dir, exist_ok=True)
    buffer = defaultdict(list)
    linked_count = 0

    for t_path in md_files:
        fname = os.path.basename(t_path)
        if not force and fname in recorded_transcripts:
            continue

        try:
            with open(t_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue

        # Extract frontmatter fields
        date_raw = None
        contact_raw = None
        duration_raw = "unknown"
        platform_raw = "phone"

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm_text = parts[1]
                for line in fm_text.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k == "date":
                            date_raw = v
                        elif k == "contact":
                            contact_raw = v
                        elif k == "duration":
                            duration_raw = v
                        elif k == "platform":
                            platform_raw = v

        # Fallback to filename pattern: <platform>_<YYYYMMDD-HHMMSS>_<contact>.md
        base_no_ext = os.path.splitext(fname)[0]
        m = re.match(r"^([a-zA-Z0-9]+)_(\d{8}-\d{6})(?:_(.*))?$", base_no_ext)
        if m:
            if not platform_raw or platform_raw == "unknown":
                platform_raw = m.group(1)
            if not date_raw or date_raw == "unknown":
                date_raw = m.group(2)
            if not contact_raw or contact_raw in ("unknown", ""):
                contact_raw = (m.group(3) or "Unknown").lstrip("_")

        if not date_raw:
            continue

        try:
            dt_obj = datetime.strptime(date_raw, "%Y%m%d-%H%M%S")
            day_key = dt_obj.strftime("%Y-%m-%d")
            time_str = dt_obj.strftime("%I:%M %p")
            timestamp_ms = int(dt_obj.timestamp() * 1000)
        except Exception:
            continue

        contact_display = contact_raw if contact_raw and contact_raw != "unknown" else "Unknown"

        # Extract speaker dialogue preview lines
        transcript_body = content.split("# Transcript", 1)[-1].strip() if "# Transcript" in content else ""
        preview_lines = []
        if transcript_body:
            for line in transcript_body.splitlines():
                line_s = line.strip()
                if line_s.startswith("[SPEAKER_") or line_s.startswith("[Unknown]"):
                    preview_lines.append(f"  > {line_s}")
                    if len(preview_lines) >= max_preview_lines:
                        break

        rel_path = os.path.relpath(t_path, output_dir)
        header = (
            f"**[{time_str}] Audio Call Transcript** ({contact_display}) "
            f"(Duration: {duration_raw}) — [Full Transcript]({rel_path})"
        )
        entry_lines = [header] + preview_lines
        full_content = "\n".join(entry_lines)

        if not dry_run:
            buffer[day_key].append({
                "timestamp_ms": timestamp_ms,
                "content": full_content
            })
            recorded_transcripts[fname] = day_key

        linked_count += 1

    if dry_run:
        print(f"[DRY-RUN] Would interleave {linked_count} audio transcripts into Daily Notes.")
        return linked_count

    if buffer:
        append_to_daily_files(buffer, output_dir)
        manifest["transcripts"] = recorded_transcripts
        save_manifest(manifest_path, manifest)
        print(f"Interleaved {linked_count} audio transcripts across {len(buffer)} Daily Notes.")

    return linked_count


def sort_daily_notes(output_dir="conversations/daily_notes"):
    """
    Since we append files in batches (and mix SMS, Calls, MMS, and Audio Transcripts),
    we perform a final pass to ensure all log blocks within a day are strictly chronological
    while preserving multi-line attachments and markdown images.
    """
    print("Sorting all Daily Notes chronologically...")
    files = glob.glob(os.path.join(output_dir, "*.md"))
    for file in files:
        with open(file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        header = []
        entries = []
        current_entry = []
        in_header = True

        for line in lines:
            if in_header:
                header.append(line)
                if line.startswith("# Daily Log:"):
                    in_header = False
            else:
                if line.startswith("- **["):
                    if current_entry:
                        entries.append("".join(current_entry))
                        current_entry = []
                    current_entry.append(line)
                elif current_entry:
                    current_entry.append(line)

        if current_entry:
            entries.append("".join(current_entry))

        # Deduplicate identical entries while preserving order
        seen = set()
        unique_entries = []
        for entry in entries:
            norm = entry.strip()
            if norm not in seen:
                seen.add(norm)
                unique_entries.append(entry)
        entries = unique_entries

        # Sort entries based on the time string in the brackets (e.g. [02:02 PM])
        def get_time(entry):
            try:
                time_str = entry.split("**[")[1].split("]")[0]
                return datetime.strptime(time_str, "%I:%M %p")
            except Exception:
                return datetime.min

        entries.sort(key=get_time)

        with open(file, "w", encoding="utf-8") as f:
            for h in header:
                f.write(h)
            if header and not header[-1].endswith("\n\n"):
                f.write("\n")
            for entry in entries:
                f.write(entry)
                if not entry.endswith("\n"):
                    f.write("\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Ingest Android SMS/MMS/Call XML backups and audio transcripts into chronological Daily Notes.")
    parser.add_argument("--input-dir", default="conversations/sms_raw", help="Directory containing calls-*.xml and sms-*.xml files.")
    parser.add_argument("--file", default=None, help="Parse a single specific XML file instead of globbing --input-dir.")
    parser.add_argument("--output-dir", default="conversations/daily_notes", help="Directory for output YYYY-MM-DD.md Daily Notes.")
    parser.add_argument("--media-dir", default="conversations/media", help="Directory for extracted MMS media attachments.")
    parser.add_argument("--transcripts-dir", default="conversations_diarized", help="Directory containing diarized audio call transcripts.")
    parser.add_argument("--no-transcripts", action="store_true", help="Skip interleaving diarized audio transcripts into Daily Notes.")
    parser.add_argument("--manifest", default=None, help="Path to incremental XML manifest JSON file.")
    parser.add_argument("--force", action="store_true", help="Force re-parsing of all XML and transcript files regardless of manifest state.")
    parser.add_argument("--no-prune", action="store_true", help="Do not prune superseded XML backups and extracted ZIP archives after ingestion.")
    parser.add_argument("--keep-latest", type=int, default=1, help="Number of newest calls-*.xml and sms-*.xml files to retain when pruning (default: 1).")
    parser.add_argument("--dry-run", action="store_true", help="Simulate ingestion without writing files.")
    args = parser.parse_args()

    changed = False
    if args.file:
        count = parse_large_xml(args.file, output_dir=args.output_dir, media_dir=args.media_dir, dry_run=args.dry_run)
        if count > 0:
            changed = True
    else:
        xml_count = ingest_xml_directory(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            media_dir=args.media_dir,
            manifest_path=args.manifest,
            force=args.force,
            dry_run=args.dry_run,
            prune=not args.no_prune,
            keep_latest=args.keep_latest
        )
        if xml_count > 0:
            changed = True

    if not args.no_transcripts:
        t_manifest = args.manifest or os.path.join(args.input_dir, ".processed_xml_manifest.json")
        t_count = ingest_diarized_transcripts(
            transcripts_dir=args.transcripts_dir,
            output_dir=args.output_dir,
            manifest_path=t_manifest,
            force=args.force,
            dry_run=args.dry_run
        )
        if t_count > 0:
            changed = True

    if not args.dry_run and (changed or args.force or args.file):
        sort_daily_notes(output_dir=args.output_dir)


if __name__ == '__main__':
    main()
