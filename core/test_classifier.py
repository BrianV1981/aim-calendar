import os
import requests
import json

INPUT_DIR = "conversations"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3.5:4b"

def ask_ollama(transcript):
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
        "options": {"temperature": 0.0}
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=data, timeout=30)
        response.raise_for_status()
        result = response.json().get("response", "").strip().lower()
        if "golden" in result: return "golden"
        elif "garbage" in result: return "garbage"
        else: return f"unknown: {result}"
    except Exception as e:
        return f"error: {e}"

def test_accuracy():
    print(f"Testing {MODEL_NAME} accuracy on 5 sample calls...\n")
    files = [f for f in os.listdir(INPUT_DIR) if f.endswith('.md')]
    
    count = 0
    for filename in files:
        if count >= 5:
            break
            
        filepath = os.path.join(INPUT_DIR, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        parts = content.split("# Transcript", 1)
        if len(parts) < 2: continue
        
        transcript = parts[1].strip()
        
        print(f"--- FILE: {filename} ---")
        print(f"Transcript Snippet (First 200 chars):\n{transcript[:200]}...")
        
        if len(transcript) < 20:
            status = "garbage (due to short length)"
        else:
            status = ask_ollama(transcript[:1000])
            
        print(f"\n=> MODEL VERDICT: {status.upper()}")
        print("-" * 50 + "\n")
        count += 1

if __name__ == "__main__":
    test_accuracy()
