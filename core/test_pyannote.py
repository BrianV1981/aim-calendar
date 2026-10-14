import os
import sys

HF_TOKEN = os.environ.get("HF_TOKEN")

def main():
    if not HF_TOKEN:
        raise RuntimeError("HF_TOKEN environment variable is required.")
    try:
        from pyannote.audio import Pipeline
        print("Loading pipeline...")
        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=HF_TOKEN)
        
        # Get one audio file
        audio_path = None
        for root, dirs, files in os.walk("benchmark"):
            for f in files:
                if f.endswith(".amr"):
                    audio_path = os.path.join(root, f)
                    break
            if audio_path:
                break
                
        if not audio_path:
            print("No audio file found")
            return
            
        print(f"Running on {audio_path}...")
        diarization = pipeline(audio_path)
        
        print("Type:", type(diarization))
        print("Dir:", dir(diarization))
        
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    main()
