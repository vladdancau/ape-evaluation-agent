import re
import sqlite3
import threading
import time
from pathlib import Path

_STOPWORDS = {
    "the", "and", "that", "this", "with", "what", "which", "your", "you", "have", "from", "please",
    "tell", "check", "memory", "number", "numbers", "previously", "sent", "remember", "pair",
    "paired", "included", "was", "were", "are", "for", "did", "about", "can", "could", "would",
}


class Memory:
    def __init__(self, path, history_limit = 20):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.history_limit = history_limit
        with self.lock:
            self.db.execute("""CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY, context_id TEXT, role TEXT, text TEXT, created REAL)""")
            self.db.commit()

    def add(self, context_id, role, text):
        with self.lock:
            self.db.execute("INSERT INTO messages (context_id, role, text, created) VALUES (?, ?, ?, ?)",
                            (context_id, role, text, time.time()))
            self.db.commit()

    def history(self, context_id):
        """Recent messages of this session, oldest first, in model-message format."""
        with self.lock:
            rows = self.db.execute(
                "SELECT role, text FROM messages WHERE context_id = ? ORDER BY id DESC LIMIT ?",
                (context_id, self.history_limit)).fetchall()
        return [{"role": role, "content": text} for role, text in reversed(rows)]

    def search(self, query, exclude_context = None, limit = 8):
        """User messages from other sessions that share numbers or keywords with the query,
        best matches first."""
        terms = _search_terms(query)
        if not terms:
            return []
        with self.lock:
            rows = self.db.execute(
                "SELECT text, created FROM messages WHERE role = 'user' AND context_id != ? AND ("
                + " OR ".join(["text LIKE ?"] * len(terms)) + ")",
                (exclude_context or "", *[f"%{t}%" for t in terms])).fetchall()

        def score(text):  # count whole-word matches; numbers count double
            return sum((2 if t.isdigit() else 1) for t in terms
                       if re.search(rf"(?<![\w]){re.escape(t)}(?![\w])", text, re.IGNORECASE))

        scored = [(score(text), created, text) for text, created in rows]
        scored = [s for s in scored if s[0] > 0]
        scored.sort(key=lambda s: (s[0], s[1]), reverse=True)  # best score, then most recent
        return [f"[{time.strftime('%Y-%m-%d %H:%M', time.localtime(c))}] {t}" for _, c, t in scored[:limit]]


def _search_terms(text):
    numbers = re.findall(r"\d+", text)
    words = [w for w in re.findall(r"[A-Za-z]{4,}", text.lower()) if w not in _STOPWORDS]
    return list(dict.fromkeys(numbers + words))
