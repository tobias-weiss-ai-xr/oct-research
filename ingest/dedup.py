"""Deduplication state store (JSON-backed history of seen items)."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime


class DedupStore:
    def __init__(self, path: str, retention_days: int = 14):
        self.path = path
        self.retention_days = retention_days
        self.data: dict[str, dict] = {}
        self._load()
        self._prune()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as fh:
                    self.data = json.load(fh)
            except (json.JSONDecodeError, OSError):
                self.data = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=1)
        os.replace(tmp, self.path)

    def _prune(self):
        cutoff = time.time() - self.retention_days * 86400
        self.data = {k: v for k, v in self.data.items() if v.get("t", 0) >= cutoff}

    def seen(self, digest: str) -> bool:
        return digest in self.data

    def mark_seen(self, digest: str, title: str = "", url: str = ""):
        self.data[digest] = {"t": time.time(), "title": title[:200], "url": url[:300]}

    def save(self):
        self._save()

    def stats(self) -> dict:
        return {"tracked": len(self.data)}