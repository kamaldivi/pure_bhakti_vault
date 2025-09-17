#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Parse an OpenAI Batch /v1/responses output JSONL and write per-book JSON + CSV.

Defaults:
  --input  = /Users/kamaldivi/Development/Python/bhakti_vault/batch_output.jsonl
  --outdir = /Users/kamaldivi/Development/Gurudev_Books/SFILES/TOC/ai_extracted

Usage:
  python parse_batch_jsonl.py
  # or override paths:
  python parse_batch_jsonl.py --input /path/to/batch_output.jsonl --outdir /some/outdir
  # extra diagnostics:
  python parse_batch_jsonl.py --debug 5
"""

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List, Tuple, Any

DEFAULT_INPUT = Path("/Users/kamaldivi/Development/Python/bhakti_vault/batch_output.jsonl")
DEFAULT_OUTDIR = Path("/Users/kamaldivi/Development/Gurudev_Books/SFILES/TOC/ai_extracted")

def _first(it):
    return it[0] if it else None

def extract_structured_json(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Robustly extract the model's structured JSON from a Responses object.
    Priority:
      1) output[].content[].type == 'output_json' -> content['json']  (already parsed)
      2) body['output_text'] -> json.loads(text)
      3) output[].content[].type == 'output_text' -> json.loads(content['text'])
      4) legacy: choices[0].message.content (JSON string) -> json.loads(...)
    """
    # 1) Newer structured path: output -> content -> output_json
    out = body.get("output")
    if isinstance(out, list) and out:
        for msg in out:
            contents = msg.get("content", [])
            if isinstance(contents, list):
                for c in contents:
                    t = c.get("type")
                    if t in ("output_json", "json", "json_object"):
                        payload = c.get("json")
                        if isinstance(payload, dict):
                            return payload
                    if t in ("output_text", "text"):
                        txt = c.get("text")
                        if isinstance(txt, str):
                            try:
                                return json.loads(txt)
                            except Exception:
                                pass  # try other paths

    # 2) output_text at top level
    if isinstance(body.get("output_text"), str):
        try:
            return json.loads(body["output_text"])
        except Exception:
            pass

    # 3) legacy 'choices'
    ch = body.get("choices")
    if isinstance(ch, list) and ch:
        content = ch[0].get("message", {}).get("content")
        if isinstance(content, str):
            return json.loads(content)

    raise RuntimeError("Could not find structured JSON in response body")

def assign_ids_and_parents(items: List[Dict]) -> List[Dict]:
    """
    Compute toc_id (1..N) and parent_toc_id from 'level' using a simple stack.
    Assumes items are in reading order from the model output.
    """
    out = []
    stack: List[Tuple[int, int]] = []  # (level, toc_id)
    for idx, it in enumerate(items, start=1):
        lvl = int(it.get("level", 1) or 1)
        if lvl < 1:
            lvl = 1
        # pop until parent is strictly shallower
        while stack and stack[-1][0] >= lvl:
            stack.pop()
        parent = stack[-1][1] if stack else None

        row = {
            "toc_id": idx,
            "parent_toc_id": parent,
            "level": lvl,
            "label": (it.get("label") or "").strip(),
            "page_label": (it.get("page_label") or "").strip(),
            "notes": (it.get("notes") or "").strip(),
        }
        out.append(row)
        stack.append((lvl, idx))
    return out

def main():
    ap = argparse.ArgumentParser(description="Parse batch output JSONL into per-book CSV/JSON")
    ap.add_argument("--input", default=str(DEFAULT_INPUT), help="Path to batch_output.jsonl (downloaded from dashboard)")
    ap.add_argument("--outdir", default=str(DEFAULT_OUTDIR), help="Directory to write per-book files")
    ap.add_argument("--debug", type=int, default=0, help="Print details for the first N failures")
    args = ap.parse_args()

    inp = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if not inp.exists():
        alt = Path("batch_output.jsonl")
        if alt.exists():
            inp = alt
        else:
            raise SystemExit(f"[FATAL] Input JSONL not found: {args.input}")

    ok_ids, failed_ids = [], []
    total = 0
    last_model = None
    debug_left = args.debug

    with inp.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            total += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                if debug_left > 0:
                    print(f"[DEBUG] Line {total}: invalid JSON: {e}")
                    debug_left -= 1
                failed_ids.append(f"<invalid-json-line-{total}>")
                continue

            cid = obj.get("custom_id")  # original PDF filename you set in the batch
            resp = obj.get("response", {})
            status = resp.get("status_code", 0)

            if status != 200:
                if debug_left > 0:
                    print(f"[DEBUG] {cid or f'<unknown-{total}>'}: status_code={status}, skipping")
                    body = resp.get("body")
                    if body:
                        print("[DEBUG] body keys:", list(body.keys()))
                    debug_left -= 1
                failed_ids.append(cid or f"<unknown-{total}>")
                continue

            body = resp.get("body", {})
            if isinstance(body, dict) and body.get("model"):
                last_model = body["model"]

            try:
                data = extract_structured_json(body)
            except Exception as e:
                if debug_left > 0:
                    print(f"[DEBUG] {cid or f'<unknown-{total}>'}: extract_structured_json failed: {e}")
                    print("[DEBUG] body keys:", list(body.keys()))
                    debug_left -= 1
                failed_ids.append(cid or f"<unknown-{total}>")
                continue

            # Enforce ground-truth pdf name from custom_id
            pdf_name = cid or data.get("pdf_name") or "unknown.pdf"
            base = Path(pdf_name).stem

            # Validate minimal shape
            toc_items = data.get("toc", [])
            if not isinstance(toc_items, list) or not toc_items:
                if debug_left > 0:
                    print(f"[DEBUG] {pdf_name}: no 'toc' array or empty toc")
                    debug_left -= 1
                failed_ids.append(pdf_name)
                continue

            rows = assign_ids_and_parents(toc_items)

            # Write JSON (with tiny provenance)
            payload = {
                "pdf_name": pdf_name,
                "model": last_model or "unknown",
                "toc": rows
            }
            (outdir / f"{base}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            # Write CSV
            fieldnames = ["pdf_name", "toc_id", "parent_toc_id", "level", "label", "page_label", "notes"]
            with (outdir / f"{base}.csv").open("w", encoding="utf-8", newline="") as cf:
                w = csv.DictWriter(cf, fieldnames=fieldnames)
                w.writeheader()
                for r in rows:
                    w.writerow({
                        "pdf_name": pdf_name,
                        **{k: r.get(k, "") for k in ["toc_id", "parent_toc_id", "level", "label", "page_label", "notes"]}
                    })

            ok_ids.append(pdf_name)

    # Summary lists
    (outdir / "ok_ids.txt").write_text("\n".join(ok_ids), encoding="utf-8")
    (outdir / "failed_ids.txt").write_text("\n".join(failed_ids), encoding="utf-8")

    print(f"[SUMMARY] total_lines={total}  ok={len(ok_ids)}  failed={len(failed_ids)}")
    if failed_ids:
        print(f"[INFO] Wrote failed_ids.txt in {outdir}")
        if args.debug == 0:
            print("[HINT] Re-run with --debug 5 to see sample failure reasons.")

if __name__ == "__main__":
    main()
