"""
Sentinel X — event logger (Phase 3)

Every event, threat-level change, and command Python issues gets appended
to a JSON-lines file. One event per line, newest at the bottom, so it's
trivially tail-able and greppable, and the dashboard can load it by
reading line-by-line without a DB dependency.

Swap this for SQLite later if the dashboard needs querying/filtering at
scale — the public log_event() interface won't need to change.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone

logger = logging.getLogger("sentinelx.logger")

DEFAULT_LOG_PATH = os.path.join(os.path.dirname(__file__), "data", "events.jsonl")


class EventLogger:
    def __init__(self, log_path: str = DEFAULT_LOG_PATH):
        self._path = log_path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self._path), exist_ok=True)

    def log_event(self, category: str, detail: dict, image_path: str | None = None):
        """
        category: short machine-readable label, e.g. "sensor_event",
                  "threat_level_change", "auth_fail", "command_sent"
        detail:   arbitrary JSON-serializable payload for this entry
        image_path: optional path to an associated captured image
                    (wired up in Phase 6 for failed-match / high-threat captures)
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "category": category,
            "detail": detail,
        }
        if image_path:
            entry["image_path"] = image_path

        line = json.dumps(entry)
        with self._lock:
            with open(self._path, "a") as f:
                f.write(line + "\n")

        logger.debug("Logged event: %s", line)

    def read_recent(self, limit: int = 50) -> list[dict]:
        """Return the most recent `limit` events, oldest-first, for the dashboard."""
        if not os.path.exists(self._path):
            return []
        with self._lock:
            with open(self._path, "r") as f:
                lines = f.readlines()
        recent = lines[-limit:]
        out = []
        for line in recent:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
