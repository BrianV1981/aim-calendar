import os
from faster_whisper import WhisperModel

def transcribe_audio(file_path):
    print(f"Transcribing {file_path}...")
    # Using 'base' model for speed in testing. 
    # For production, we can switch to 'small' or 'medium'
    model_size = "base"
    
    # Run on CPU with int8 to ensure it runs anywhere
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    
    segments, info = model.transcribe(file_path, beam_size=5)
    
    print(f"Detected language '{info.language}' with probability {info.language_probability}")
    
    transcript = ""
    for segment in segments:
        line = f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}"
        print(line)
        transcript += line + "\n"
        
    return transcript

if __name__ == "__main__":
    # Test on a small file to prove empirical TDD
    test_file = "TalkerACR/All/facebook_20231230-172824_5_28.amr"
    if os.path.exists(test_file):
        transcribe_audio(test_file)
    else:
        print(f"Error: Could not find {test_file}")
