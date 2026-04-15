from __future__ import annotations

import json
import time
from pathlib import Path

_LOG_PATH = Path.home() / ".config" / "whisperkey" / "usage_log.jsonl"


def log_usage(mode: str, model: str, input_tokens: int, output_tokens: int) -> None:
    """Append one usage entry to the JSONL log. Silently ignores all errors."""
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": time.time(),
            "mode": mode,
            "model": model,
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
        }
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def query_usage() -> dict:
    """Return token totals for today, this week, and all time."""
    now = time.time()
    today_start = now - (now % 86400)
    week_start = now - 7 * 86400

    result = {
        "today_in": 0,
        "today_out": 0,
        "week_in": 0,
        "week_out": 0,
        "total_in": 0,
        "total_out": 0,
    }

    if not _LOG_PATH.exists():
        return result

    try:
        for raw_line in _LOG_PATH.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                entry = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            ts = entry.get("ts", 0)
            in_tok = entry.get("input_tokens", 0)
            out_tok = entry.get("output_tokens", 0)

            result["total_in"] += in_tok
            result["total_out"] += out_tok
            if ts >= week_start:
                result["week_in"] += in_tok
                result["week_out"] += out_tok
            if ts >= today_start:
                result["today_in"] += in_tok
                result["today_out"] += out_tok
    except Exception:
        pass

    return result
