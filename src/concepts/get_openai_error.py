#!/usr/bin/env python3
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

def main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY not set.")

    client = OpenAI(api_key=api_key)

    bid_path = Path("last_batch_id.txt")
    if not bid_path.exists():
        raise SystemExit("last_batch_id.txt not found in this folder.")

    batch_id = bid_path.read_text().strip()
    b = client.batches.retrieve(batch_id)
    print("status:", b.status, "counts:", getattr(b, "request_counts", None))
    err_id = getattr(b, "error_file_id", None)
    print("error_file_id:", err_id)

    if not err_id:
        print("No error file present for this batch.")
        return

    out_path = Path("batch_errors.jsonl")
    # ✅ stream to file (works across SDK versions)
    with client.files.with_streaming_response.content(err_id) as r:
        r.stream_to_file(str(out_path))
    print("Saved:", out_path.resolve())

if __name__ == "__main__":
    main()
