from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "data" / "cache"


def normalize_tickers(tickers: Iterable[str]) -> list[str]:
    return sorted({ticker.strip().upper() for ticker in tickers if ticker and ticker.strip()})


def db_signature(db_path: Path | None = None) -> str:
    path = db_path or (PROJECT_ROOT / "data" / "risk_database.duckdb")
    if not path.exists():
        return "missing-db"

    stat = path.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def analysis_cache_key(agent_name: str, tickers: Iterable[str], signature: str) -> str:
    payload = {
        "agent": agent_name,
        "tickers": normalize_tickers(tickers),
        "signature": signature,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_path(cache_key: str) -> Path:
    return CACHE_DIR / f"{cache_key}.json"


def load_json_cache(cache_key: str) -> dict[str, Any] | None:
    path = cache_path(cache_key)
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json_cache(cache_key: str, payload: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(cache_key)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)