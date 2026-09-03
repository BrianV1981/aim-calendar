import os
import re
import json
import time
from openai import OpenAI

INPUT_DIR = "conversations"

def ask_openai(transcript):
    """Sends the transcript to OpenAI API to classify it."""
    client = OpenAI(api_key="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")
    
    prompt = f"""You are an audio transcript classifier.
Read the following transcript snippet. Determine if it represents a REAL human conversation or a GARBAGE call (like a voicemail, pocket dial, silent hang-up, or background noise).
Reply ONLY with the exact word "golden" if it is a real conversation.
Reply ONLY with the exact word "garbage" if it is not a real conversation. Do not provide any other explanation.

Transcript:
{transcript}
"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=10
        )
        
        result = response.choices[0].message.content.strip().lower()
        
        # Clean up any weird punctuation the LLM might have added
        if "golden" in result:
            return "golden"
        elif "garbage" in result:
            return "garbage"
        else:
            return "unknown"
            
    except Exception as e:
        print(f"Error querying OpenAI: {e}")
        return "error"

def classify_files():
    if not os.path.exists(INPUT_DIR):
        print(f"Directory {INPUT_DIR} not found.")
        return

    files = [f for f in os.listdir(INPUT_DIR) if f.endswith('.md')]
    total = len(files)
    
    print(f"Starting classification of {total} files using OpenAI gpt-4o-mini...")
    
    processed = 0
    golden = 0
    garbage = 0
    skipped = 0
    
    for idx, filename in enumerate(files, 1):
        filepath = os.path.join(INPUT_DIR, filename)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Check if already processed
        if re.search(r'^status:\s*(golden|garbage|unknown)', content, re.MULTILINE):
            print(f"[{idx}/{total}] Skipping {filename} (already classified)")
            skipped += 1
            continue
            
        # Extract transcript for the LLM
        parts = content.split("# Transcript", 1)
        if len(parts) < 2:
            print(f"[{idx}/{total}] Skipping {filename} (no transcript block)")
            skipped += 1
            continue
            
        transcript = parts[1].strip()
        
        # If transcript is extremely short, it's probably garbage
        if len(transcript) < 20:
            status = "garbage"
        else:
            # We don't need to send the whole file, just the first 1000 characters is usually enough to tell
            status = ask_openai(transcript[:1000])
            
        if status in ["error", "unknown"]:
            print(f"[{idx}/{total}] Failed to classify {filename} (returned {status})")
            continue
            
        # Inject the status into the YAML frontmatter
        if "---\n\n# Transcript" in content:
            new_content = content.replace("---\n\n# Transcript", f"status: {status}\n---\n\n# Transcript", 1)
        else:
            new_content = content.replace("---\n", f"---\nstatus: {status}\n", 1)
            
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        print(f"[{idx}/{total}] Classified {filename} -> {status.upper()}")
        
        if status == "golden":
            golden += 1
        elif status == "garbage":
            garbage += 1
            
        processed += 1

    print("\n=== CLASSIFICATION COMPLETE ===")
    print(f"Total newly classified: {processed}")
    print(f"Golden (Real Calls): {golden}")
    print(f"Garbage (Pocket Dials/Noise): {garbage}")
    print(f"Skipped (Already done or invalid): {skipped}")

if __name__ == "__main__":
    classify_files()
