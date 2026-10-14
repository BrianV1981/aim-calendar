import os
import unittest
from unittest.mock import patch, MagicMock
import requests
import json
from core.classify_calls import classify_transcript, ask_ollama, ask_openai

INPUT_DIR = "conversations"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3.5:4b"


class TestClassifier(unittest.TestCase):
    """Offline unit tests for local-first call classification (CAL-001, CAL-007)."""

    @patch("core.classify_calls.requests.post")
    def test_ask_ollama_golden(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "golden"}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        verdict = ask_ollama("Speaker 1: Hi, are we meeting at noon? Speaker 2: Yes, see you there.")
        self.assertEqual(verdict, "golden")

    @patch("core.classify_calls.requests.post")
    def test_ask_ollama_garbage(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "garbage"}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        verdict = ask_ollama("Please leave a message after the tone.")
        self.assertEqual(verdict, "garbage")

    def test_ask_openai_requires_env_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                ask_openai("Sample transcript")


def run_accuracy_benchmark():
    print(f"Testing {MODEL_NAME} accuracy on 5 sample calls...\n")
    if not os.path.exists(INPUT_DIR):
        print(f"Directory {INPUT_DIR} not found.")
        return
    files = [f for f in os.listdir(INPUT_DIR) if f.endswith('.md')]
    
    count = 0
    for filename in files:
        if count >= 5:
            break
            
        filepath = os.path.join(INPUT_DIR, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        parts = content.split("# Transcript", 1)
        if len(parts) < 2:
            continue
        
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
    unittest.main()
