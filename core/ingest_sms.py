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


def parse_large_xml(xml_path, output_dir="conversations/daily_notes", media_dir="conversations/media", batch_size=50000):
    """
    Parses massive XML files (10GB+) using iterparse to avoid OOM crashes.
    Extracts Calls, SMS, and MMS (including Base64 media payloads).
    Batches writes to disk every `batch_size` elements.
    """
    if not os.path.exists(xml_path):
        print(f"File {xml_path} does not exist. Skipping.")
        return

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


def sort_daily_notes(output_dir="conversations/daily_notes"):
    """
    Since we append files in batches (and mix SMS, Calls, and MMS),
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
            f.write("\n")
            for entry in entries:
                f.write(entry)
                if not entry.endswith("\n"):
                    f.write("\n")


if __name__ == '__main__':
    # Parse the real production files
    parse_large_xml("conversations/sms_raw/calls-20260903012405.xml")
    parse_large_xml("conversations/sms_raw/sms-20260903012405.xml")

    # Final pass to interleave and sort everything
    sort_daily_notes()
