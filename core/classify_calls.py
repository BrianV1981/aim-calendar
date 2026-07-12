import os
import requests
import re
import json
import time

INPUT_DIR = "conversations"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3.5:4b"

def ask_ollama(transcript):
    """Sends the transcript to the local Ollama LLM to classify it."""
    prompt = f"""You are an audio transcript classifier.
Read the following transcript snippet. Determine if it represents a REAL human conversation or a GARBAGE call (like a voicemail, pocket dial, silent hang-up, or background noise).
Reply ONLY with the exact word "golden" if it is a real conversation.
Reply ONLY with the exact word "garbage" if it is not a real conversation. Do not provide any other explanation.

Transcript:
{transcript}
"""
    
    data = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0
        }
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=data, timeout=30)
        response.raise_for_status()
        result = response.json().get("response", "").strip().lower()
        
        # Clean up any weird punctuation the LLM might have added
        if "golden" in result:
            return "golden"
        elif "garbage" in result:
            return "garbage"
        else:
            return "unknown"
            
    except Exception as e:
        print(f"Error querying Ollama: {e}")
        return "error"

def classify_files():
    if not os.path.exists(INPUT_DIR):
        print(f"Directory {INPUT_DIR} not found.")
        return

    files = [f for f in os.listdir(INPUT_DIR) if f.endswith('.md')]
    total = len(files)
    
    print(f"Starting classification of {total} files using {MODEL_NAME}...")
    
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
            status = ask_ollama(transcript[:1000])
            
        if status in ["error", "unknown"]:
            print(f"[{idx}/{total}] Failed to classify {filename} (returned {status})")
            continue
            
        # Inject the status into the YAML frontmatter
        # We replace the closing '---' of the frontmatter with our new tag + closing
        if "---\n\n# Transcript" in content:
            new_content = content.replace("---\n\n# Transcript", f"status: {status}\n---\n\n# Transcript", 1)
        else:
            # Fallback if format is slightly different
            new_content = content.replace("---\n", f"---\nstatus: {status}\n", 1)
            
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        print(f"[{idx}/{total}] Classified {filename} -> {status.upper()}")
        
        if status == "golden":
            golden += 1
        elif status == "garbage":
            garbage += 1
            
        processed += 1
        
        # Small delay to prevent overloading CPU/Ollama
        time.sleep(0.1)

    print("\n=== CLASSIFICATION COMPLETE ===")
    print(f"Total newly classified: {processed}")
    print(f"Golden (Real Calls): {golden}")
    print(f"Garbage (Pocket Dials/Noise): {garbage}")
    print(f"Skipped (Already done or invalid): {skipped}")

if __name__ == "__main__":
    classify_files()
