# download_glossary_batch_input.py
#!/usr/bin/env python3
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

AI_DIR = Path("/Users/kamaldivi/Development/Gurudev_Books/SFILES/GLOSSARY/ai_extracted")
OUT = AI_DIR / "uploaded_glossary_requests.jsonl"

def main():
    load_dotenv()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    bid = (AI_DIR / "last_glossary_batch_id.txt").read_text().strip()
    b = client.batches.retrieve(bid)
    in_id = getattr(b, "input_file_id", None)
    if not in_id:
        raise SystemExit("Batch does not expose input_file_id; create a fresh batch and try again.")
    with client.files.with_streaming_response.content(in_id) as r:
        r.stream_to_file(str(OUT))
    print("Saved:", OUT)

if __name__ == "__main__":
    main()
