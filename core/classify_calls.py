import os
import re
import json
import time
import requests

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

INPUT_DIR = "conversations"
CLASSIFIER_PROVIDER = os.environ.get("AIM_CLASSIFIER_PROVIDER", "ollama").lower()
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_CLASSIFIER_MODEL", "qwen3.5:4b")

CLASSIFIER_PROMPT_TEMPLATE = """You are an audio transcript classifier.
Read the following transcript snippet. Determine if it represents a REAL human conversation or a GARBAGE call (like a voicemail, pocket dial, silent hang-up, or background noise).
Reply ONLY with the exact word "golden" if it is a real conversation.
Reply ONLY with the exact word "garbage" if it is not a real conversation. Do not provide any other explanation.

Transcript:
{transcript}
"""


def ask_ollama(transcript):
    """Classifies the transcript locally using Ollama (100% local / air-gapped default)."""
    prompt = CLASSIFIER_PROMPT_TEMPLATE.format(transcript=transcript)
    data = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0}
    }
    try:
        response = requests.post(OLLAMA_URL, json=data, timeout=30)
        response.raise_for_status()
        result = response.json().get("response", "").strip().lower()
        if "golden" in result:
            return "golden"
        elif "garbage" in result:
            return "garbage"
        else:
            return "unknown"
    except Exception as e:
        print(f"Error querying local Ollama ({OLLAMA_URL}): {e}")
        return "error"


def ask_openai(transcript):
    """Optional cloud fallback: sends the transcript to OpenAI API if OPENAI_API_KEY is set."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is required when using the OpenAI classifier.")
    if OpenAI is None:
        raise RuntimeError("openai package is not installed.")

    client = OpenAI(api_key=api_key)
    prompt = CLASSIFIER_PROMPT_TEMPLATE.format(transcript=transcript)

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

        if "golden" in result:
            return "golden"
        elif "garbage" in result:
            return "garbage"
        else:
            return "unknown"

    except Exception as e:
        print(f"Error querying OpenAI: {e}")
        return "error"


def classify_transcript(transcript):
    """Routes classification to local Ollama by default, or OpenAI if configured."""
    if CLASSIFIER_PROVIDER == "openai":
        return ask_openai(transcript)
    return ask_ollama(transcript)


def classify_files():
    if not os.path.exists(INPUT_DIR):
        print(f"Directory {INPUT_DIR} not found.")
        return

    files = [f for f in os.listdir(INPUT_DIR) if f.endswith('.md')]
    total = len(files)

    provider_desc = f"local Ollama ({OLLAMA_MODEL})" if CLASSIFIER_PROVIDER != "openai" else "OpenAI gpt-4o-mini"
    print(f"Starting classification of {total} files using {provider_desc}...")
    
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
            status = classify_transcript(transcript[:1000])
            
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
