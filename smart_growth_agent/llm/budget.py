"""Cross-process request cap and usage ledger. Never stores messages or credentials."""

import fcntl
import json
from pathlib import Path
from time import time


def update(path: Path, operation):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        value = json.loads(stream.read() or '{"calls":[]}')
        result = operation(value)
        stream.seek(0)
        stream.truncate()
        stream.write(json.dumps(value, ensure_ascii=False))
        stream.flush()
        return result


def reserve(path: Path, limit: int, model: str):
    def operation(value):
        if len(value["calls"]) >= limit:
            raise RuntimeError("local_model_request_budget_exhausted")
        number = len(value["calls"])
        value["calls"].append(
            {"number": number, "model": model, "started": time(), "status": "reserved"}
        )
        return number

    return update(path, operation)


def complete(path: Path, number: int, status: int, body: dict | None):
    def operation(value):
        row = value["calls"][number]
        row["http_status"] = status
        row["status"] = "response_received" if status else "outcome_unknown"
        usage = (body or {}).get("usage") or {}
        for key in (
            "prompt_tokens",
            "completion_tokens",
            "prompt_cache_hit_tokens",
            "prompt_cache_miss_tokens",
        ):
            count = usage.get(key)
            if type(count) is int and count >= 0:
                row[key] = count
        row["returned_model"] = (body or {}).get("model")

    update(path, operation)
