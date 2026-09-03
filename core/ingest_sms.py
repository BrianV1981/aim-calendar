import os
import xml.etree.ElementTree as ET
from datetime import datetime
from collections import defaultdict
import glob

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
                f.write(f"---\ndate: {day_key}\ntype: daily_exocortex\n---\n")
                f.write(f"# Daily Log: {day_key}\n\n")
            else:
                f.write(existing_content)
                if not existing_content.endswith("\n"):
                    f.write("\n")
                
            for log in logs:
                # Naive duplicate check
                if log["content"] not in existing_content:
                    f.write(f"- {log['content']}\n")

def parse_large_xml(xml_path, output_dir="conversations/daily_notes", batch_size=50000):
    """
    Parses massive XML files (10GB+) using iterparse to avoid OOM crashes.
    Batches writes to disk every `batch_size` elements.
    """
    if not os.path.exists(xml_path):
        print(f"File {xml_path} does not exist. Skipping.")
        return

    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Streaming parse of {xml_path} (this prevents RAM crashing)...")
    
    buffer = defaultdict(list)
    element_count = 0
    total_processed = 0

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
                contact_display = contact if contact != "(Unknown)" else number
                log_entry = {
                    "timestamp_ms": timestamp_ms,
                    "content": f"**[{time_str}] {call_type}** with {contact_display} (Duration: {duration}s)"
                }
            except:
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
                contact_display = contact if contact != "(Unknown)" else number
                clean_body = body.replace("\n", " ").replace("\r", "")
                log_entry = {
                    "timestamp_ms": timestamp_ms,
                    "content": f"**[{time_str}] {direction}** ({contact_display}): \"{clean_body}\""
                }
            except:
                pass

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
    Since we append files in batches (and mix SMS with Calls), 
    we need a final pass to ensure all bullet points within a day are strictly chronological.
    """
    print("Sorting all Daily Notes chronologically...")
    files = glob.glob(os.path.join(output_dir, "*.md"))
    for file in files:
        with open(file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        header = []
        bullets = []
        in_header = True
        
        for line in lines:
            if in_header:
                header.append(line)
                if line.startswith("# Daily Log:"):
                    in_header = False
            else:
                if line.strip() and line.strip().startswith("- **["):
                    bullets.append(line)
                    
        # Sort bullets based on the time string in the brackets (e.g. [02:02 PM])
        # A proper datetime parse ensures correct AM/PM sorting
        def get_time(bullet):
            try:
                # Extract time string like "02:02 PM"
                time_str = bullet.split("**[")[1].split("]")[0]
                return datetime.strptime(time_str, "%I:%M %p")
            except:
                return datetime.min
                
        bullets.sort(key=get_time)
        
        with open(file, "w", encoding="utf-8") as f:
            for h in header:
                f.write(h)
            f.write("\n")
            for b in bullets:
                f.write(b)

if __name__ == '__main__':
    # Parse the real production files
    parse_large_xml("conversations/sms_raw/calls-20260903012405.xml")
    parse_large_xml("conversations/sms_raw/sms-20260903012405.xml")
    
    # Final pass to interleave and sort everything
    sort_daily_notes()
