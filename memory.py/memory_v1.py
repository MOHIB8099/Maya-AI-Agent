"""
Maya AI - Advanced Memory System
Single-file module.

Features:
- Short-term conversation memory
- Long-term memory
- Per-user memory
- Preferences
- Search / recall
- Importance scoring
- Duplicate prevention
- Update / delete / forget
- Conservative automatic memory extraction
- Memory context building for brain.py
- SQLite persistence
- Central execute_memory_action() router

External packages: none
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "maya_memory.db"

DEFAULT_USER_ID = "default"
MAX_SHORT_TERM_MESSAGES = 30
DEFAULT_RECALL_LIMIT = 8
DUPLICATE_SIMILARITY = 0.90

VALID_CATEGORIES = {
    "personal", "preference", "project", "work", "routine",
    "goal", "relationship", "location", "device", "technical", "general",
}

VALID_SOURCES = {"manual", "automatic", "chat", "system", "imported"}

SENSITIVE_PATTERNS = [
    r"\bpassword\b",
    r"\bpasscode\b",
    r"\botp\b",
    r"\bpin\b",
    r"\bapi[\s_-]?key\b",
    r"\bsecret\b",
    r"\btoken\b",
    r"\bcredit card\b",
    r"\bdebit card\b",
    r"\bcvv\b",
    r"\bsecurity code\b",
]

_db_lock = threading.RLock()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: int | float, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def normalize_text(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s@.+:/-]", "", text, flags=re.UNICODE)
    return text.strip()


def safe_json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return "{}"


def safe_json_loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return {} if default is None else default
    try:
        return json.loads(value)
    except Exception:
        return {} if default is None else default


def looks_sensitive(text: str) -> bool:
    lowered = (text or "").lower()
    return any(re.search(pattern, lowered, re.IGNORECASE) for pattern in SENSITIVE_PATTERNS)


def text_similarity(a: str, b: str) -> float:
    a_n = normalize_text(a)
    b_n = normalize_text(b)
    if not a_n or not b_n:
        return 0.0
    return SequenceMatcher(None, a_n, b_n).ratio()


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"\b[\w@.+:/-]+\b", normalize_text(text), flags=re.UNICODE)
        if len(token) > 1
    }


def lexical_score(query: str, text: str) -> float:
    q_tokens = tokenize(query)
    t_tokens = tokenize(text)
    if not q_tokens or not t_tokens:
        return 0.0

    overlap = len(q_tokens & t_tokens)
    coverage = overlap / max(1, len(q_tokens))
    jaccard = overlap / max(1, len(q_tokens | t_tokens))
    seq = text_similarity(query, text)
    return min(1.0, coverage * 0.55 + jaccard * 0.25 + seq * 0.20)


def age_decay(updated_at: str, half_life_days: float = 90.0) -> float:
    try:
        dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_days = max(0.0, (now - dt.astimezone(timezone.utc)).total_seconds() / 86400)
        return math.exp(-math.log(2) * age_days / max(1.0, half_life_days))
    except Exception:
        return 0.5


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    if "metadata" in data:
        data["metadata"] = safe_json_loads(data["metadata"], {})
    return data


def init_memory_db() -> None:
    with _db_lock:
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    normalized_content TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'general',
                    importance INTEGER NOT NULL DEFAULT 5,
                    source TEXT NOT NULL DEFAULT 'manual',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_accessed_at TEXT,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1
                );

                CREATE INDEX IF NOT EXISTS idx_memories_user
                    ON memories(user_id);

                CREATE INDEX IF NOT EXISTS idx_memories_user_category
                    ON memories(user_id, category);

                CREATE INDEX IF NOT EXISTS idx_memories_active
                    ON memories(user_id, is_active);

                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL DEFAULT 'default',
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_conv_user_session
                    ON conversation_messages(user_id, session_id, id);

                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    pref_key TEXT NOT NULL,
                    pref_value TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, pref_key)
                );

                CREATE INDEX IF NOT EXISTS idx_preferences_user
                    ON user_preferences(user_id);
                """
            )
            conn.commit()
        finally:
            conn.close()


init_memory_db()


@dataclass
class RecallResult:
    id: int
    content: str
    category: str
    importance: int
    score: float
    source: str
    created_at: str
    updated_at: str
    access_count: int
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "importance": self.importance,
            "score": round(self.score, 4),
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "access_count": self.access_count,
            "metadata": self.metadata,
        }


def find_duplicate_memory(
    user_id: str,
    content: str,
    similarity_threshold: float = DUPLICATE_SIMILARITY,
) -> dict[str, Any] | None:
    user_id = user_id or DEFAULT_USER_ID
    target = normalize_text(content)
    if not target:
        return None

    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM memories
            WHERE user_id = ? AND is_active = 1
            ORDER BY updated_at DESC
            LIMIT 250
            """,
            (user_id,),
        ).fetchall()

        for row in rows:
            existing = row["normalized_content"]
            if existing == target:
                return _row_to_dict(row)

            if SequenceMatcher(None, existing, target).ratio() >= similarity_threshold:
                return _row_to_dict(row)

        return None
    finally:
        conn.close()


def add_memory(
    content: str,
    user_id: str = DEFAULT_USER_ID,
    category: str = "general",
    importance: int = 5,
    source: str = "manual",
    metadata: dict[str, Any] | None = None,
    prevent_duplicates: bool = True,
) -> dict[str, Any]:
    content = (content or "").strip()
    if not content:
        return {"success": False, "error": "Memory content is empty."}

    user_id = user_id or DEFAULT_USER_ID
    category = category if category in VALID_CATEGORIES else "general"
    source = source if source in VALID_SOURCES else "manual"
    importance = clamp(importance, 1, 10)
    metadata = metadata or {}

    if prevent_duplicates:
        duplicate = find_duplicate_memory(user_id, content)
        if duplicate:
            new_importance = max(int(duplicate["importance"]), importance)
            result = update_memory(
                memory_id=int(duplicate["id"]),
                user_id=user_id,
                importance=new_importance,
                metadata={**duplicate.get("metadata", {}), **metadata},
            )
            result["duplicate"] = True
            return result

    now = utc_now_iso()

    with _db_lock:
        conn = _connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO memories (
                    user_id, content, normalized_content, category,
                    importance, source, metadata, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    content,
                    normalize_text(content),
                    category,
                    importance,
                    source,
                    safe_json_dumps(metadata),
                    now,
                    now,
                ),
            )
            conn.commit()
            memory_id = cur.lastrowid
        finally:
            conn.close()

    return {
        "success": True,
        "memory_id": memory_id,
        "content": content,
        "category": category,
        "importance": importance,
        "source": source,
        "duplicate": False,
    }


def get_memory(memory_id: int, user_id: str = DEFAULT_USER_ID) -> dict[str, Any] | None:
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT *
            FROM memories
            WHERE id = ? AND user_id = ? AND is_active = 1
            """,
            (memory_id, user_id or DEFAULT_USER_ID),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def update_memory(
    memory_id: int,
    user_id: str = DEFAULT_USER_ID,
    content: str | None = None,
    category: str | None = None,
    importance: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing = get_memory(memory_id, user_id)
    if not existing:
        return {"success": False, "error": "Memory not found."}

    new_content = existing["content"] if content is None else content.strip()
    if not new_content:
        return {"success": False, "error": "Memory content cannot be empty."}

    new_category = existing["category"]
    if category is not None:
        new_category = category if category in VALID_CATEGORIES else "general"

    new_importance = int(existing["importance"])
    if importance is not None:
        new_importance = clamp(importance, 1, 10)

    new_metadata = existing.get("metadata", {}) if metadata is None else metadata
    now = utc_now_iso()

    with _db_lock:
        conn = _connect()
        try:
            conn.execute(
                """
                UPDATE memories
                SET content = ?,
                    normalized_content = ?,
                    category = ?,
                    importance = ?,
                    metadata = ?,
                    updated_at = ?
                WHERE id = ? AND user_id = ? AND is_active = 1
                """,
                (
                    new_content,
                    normalize_text(new_content),
                    new_category,
                    new_importance,
                    safe_json_dumps(new_metadata),
                    now,
                    memory_id,
                    user_id or DEFAULT_USER_ID,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    return {
        "success": True,
        "memory_id": memory_id,
        "content": new_content,
        "category": new_category,
        "importance": new_importance,
        "metadata": new_metadata,
    }


def delete_memory(
    memory_id: int,
    user_id: str = DEFAULT_USER_ID,
    hard_delete: bool = False,
) -> dict[str, Any]:
    user_id = user_id or DEFAULT_USER_ID

    with _db_lock:
        conn = _connect()
        try:
            if hard_delete:
                cur = conn.execute(
                    "DELETE FROM memories WHERE id = ? AND user_id = ?",
                    (memory_id, user_id),
                )
            else:
                cur = conn.execute(
                    """
                    UPDATE memories
                    SET is_active = 0, updated_at = ?
                    WHERE id = ? AND user_id = ? AND is_active = 1
                    """,
                    (utc_now_iso(), memory_id, user_id),
                )

            conn.commit()

            if cur.rowcount == 0:
                return {"success": False, "error": "Memory not found."}

            return {
                "success": True,
                "memory_id": memory_id,
                "deleted": True,
                "hard_delete": hard_delete,
            }
        finally:
            conn.close()


def forget_by_text(
    text: str,
    user_id: str = DEFAULT_USER_ID,
    similarity_threshold: float = 0.82,
) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {"success": False, "error": "Forget text is empty."}

    user_id = user_id or DEFAULT_USER_ID

    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM memories WHERE user_id = ? AND is_active = 1",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    matches: list[int] = []

    for row in rows:
        sim = text_similarity(text, row["content"])
        lex = lexical_score(text, row["content"])
        if max(sim, lex) >= similarity_threshold:
            matches.append(int(row["id"]))

    for memory_id in matches:
        delete_memory(memory_id, user_id=user_id, hard_delete=False)

    return {
        "success": True,
        "forgotten_count": len(matches),
        "memory_ids": matches,
    }


def list_memories(
    user_id: str = DEFAULT_USER_ID,
    category: str | None = None,
    limit: int = 100,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    user_id = user_id or DEFAULT_USER_ID
    limit = clamp(limit, 1, 500)

    sql = "SELECT * FROM memories WHERE user_id = ?"
    params: list[Any] = [user_id]

    if active_only:
        sql += " AND is_active = 1"

    if category:
        sql += " AND category = ?"
        params.append(category)

    sql += " ORDER BY importance DESC, updated_at DESC LIMIT ?"
    params.append(limit)

    conn = _connect()
    try:
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [_row_to_dict(row) for row in rows if row is not None]
    finally:
        conn.close()


def search_memories(
    query: str,
    user_id: str = DEFAULT_USER_ID,
    category: str | None = None,
    limit: int = DEFAULT_RECALL_LIMIT,
    min_score: float = 0.12,
) -> list[dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return []

    user_id = user_id or DEFAULT_USER_ID
    limit = clamp(limit, 1, 50)

    sql = """
        SELECT *
        FROM memories
        WHERE user_id = ? AND is_active = 1
    """
    params: list[Any] = [user_id]

    if category:
        sql += " AND category = ?"
        params.append(category)

    sql += " ORDER BY importance DESC, updated_at DESC LIMIT 500"

    conn = _connect()
    try:
        rows = conn.execute(sql, tuple(params)).fetchall()
    finally:
        conn.close()

    scored: list[RecallResult] = []

    for row in rows:
        text_score = lexical_score(query, row["content"])
        importance_score = clamp(row["importance"], 1, 10) / 10.0
        recency_score = age_decay(row["updated_at"])

        final_score = (
            text_score * 0.72
            + importance_score * 0.18
            + recency_score * 0.10
        )

        if final_score < min_score:
            continue

        scored.append(
            RecallResult(
                id=int(row["id"]),
                content=row["content"],
                category=row["category"],
                importance=int(row["importance"]),
                score=final_score,
                source=row["source"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                access_count=int(row["access_count"]),
                metadata=safe_json_loads(row["metadata"], {}),
            )
        )

    scored.sort(key=lambda item: item.score, reverse=True)
    selected = scored[:limit]

    if selected:
        ids = [item.id for item in selected]
        placeholders = ",".join("?" for _ in ids)

        with _db_lock:
            conn = _connect()
            try:
                conn.execute(
                    f"""
                    UPDATE memories
                    SET access_count = access_count + 1,
                        last_accessed_at = ?
                    WHERE id IN ({placeholders})
                    """,
                    (utc_now_iso(), *ids),
                )
                conn.commit()
            finally:
                conn.close()

    return [item.to_dict() for item in selected]


def recall_memories(
    query: str,
    user_id: str = DEFAULT_USER_ID,
    limit: int = DEFAULT_RECALL_LIMIT,
) -> list[dict[str, Any]]:
    return search_memories(query=query, user_id=user_id, limit=limit)


def save_conversation_message(
    role: str,
    content: str,
    user_id: str = DEFAULT_USER_ID,
    session_id: str = "default",
) -> dict[str, Any]:
    role = (role or "").strip().lower()
    content = (content or "").strip()

    if role not in {"user", "assistant", "system", "tool"}:
        return {"success": False, "error": "Invalid role."}

    if not content:
        return {"success": False, "error": "Message is empty."}

    with _db_lock:
        conn = _connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO conversation_messages (
                    user_id, session_id, role, content, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user_id or DEFAULT_USER_ID,
                    session_id or "default",
                    role,
                    content,
                    utc_now_iso(),
                ),
            )
            conn.commit()
            message_id = cur.lastrowid
        finally:
            conn.close()

    trim_short_term_memory(
        user_id=user_id,
        session_id=session_id,
        keep_last=MAX_SHORT_TERM_MESSAGES,
    )

    return {"success": True, "message_id": message_id}


def get_recent_conversation(
    user_id: str = DEFAULT_USER_ID,
    session_id: str = "default",
    limit: int = MAX_SHORT_TERM_MESSAGES,
) -> list[dict[str, Any]]:
    limit = clamp(limit, 1, 200)

    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM (
                SELECT *
                FROM conversation_messages
                WHERE user_id = ? AND session_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
            ORDER BY id ASC
            """,
            (
                user_id or DEFAULT_USER_ID,
                session_id or "default",
                limit,
            ),
        ).fetchall()

        return [dict(row) for row in rows]
    finally:
        conn.close()


def trim_short_term_memory(
    user_id: str = DEFAULT_USER_ID,
    session_id: str = "default",
    keep_last: int = MAX_SHORT_TERM_MESSAGES,
) -> None:
    keep_last = clamp(keep_last, 1, 500)

    with _db_lock:
        conn = _connect()
        try:
            conn.execute(
                """
                DELETE FROM conversation_messages
                WHERE user_id = ? AND session_id = ?
                  AND id NOT IN (
                      SELECT id
                      FROM conversation_messages
                      WHERE user_id = ? AND session_id = ?
                      ORDER BY id DESC
                      LIMIT ?
                  )
                """,
                (
                    user_id or DEFAULT_USER_ID,
                    session_id or "default",
                    user_id or DEFAULT_USER_ID,
                    session_id or "default",
                    keep_last,
                ),
            )
            conn.commit()
        finally:
            conn.close()


def clear_short_term_memory(
    user_id: str = DEFAULT_USER_ID,
    session_id: str | None = None,
) -> dict[str, Any]:
    user_id = user_id or DEFAULT_USER_ID

    with _db_lock:
        conn = _connect()
        try:
            if session_id is None:
                cur = conn.execute(
                    "DELETE FROM conversation_messages WHERE user_id = ?",
                    (user_id,),
                )
            else:
                cur = conn.execute(
                    """
                    DELETE FROM conversation_messages
                    WHERE user_id = ? AND session_id = ?
                    """,
                    (user_id, session_id),
                )

            conn.commit()
            return {
                "success": True,
                "deleted_messages": cur.rowcount,
            }
        finally:
            conn.close()


def set_preference(
    key: str,
    value: Any,
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    key = normalize_text(key).replace(" ", "_")
    if not key:
        return {"success": False, "error": "Preference key is empty."}

    now = utc_now_iso()
    serialized = safe_json_dumps(value)

    with _db_lock:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO user_preferences (
                    user_id, pref_key, pref_value, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, pref_key)
                DO UPDATE SET
                    pref_value = excluded.pref_value,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id or DEFAULT_USER_ID,
                    key,
                    serialized,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    return {"success": True, "key": key, "value": value}


def get_preference(
    key: str,
    user_id: str = DEFAULT_USER_ID,
    default: Any = None,
) -> Any:
    key = normalize_text(key).replace(" ", "_")

    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT pref_value
            FROM user_preferences
            WHERE user_id = ? AND pref_key = ?
            """,
            (user_id or DEFAULT_USER_ID, key),
        ).fetchone()

        if not row:
            return default

        return safe_json_loads(row["pref_value"], default)
    finally:
        conn.close()


def get_all_preferences(
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT pref_key, pref_value
            FROM user_preferences
            WHERE user_id = ?
            ORDER BY pref_key ASC
            """,
            (user_id or DEFAULT_USER_ID,),
        ).fetchall()

        return {
            row["pref_key"]: safe_json_loads(row["pref_value"])
            for row in rows
        }
    finally:
        conn.close()


def delete_preference(
    key: str,
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    key = normalize_text(key).replace(" ", "_")

    with _db_lock:
        conn = _connect()
        try:
            cur = conn.execute(
                """
                DELETE FROM user_preferences
                WHERE user_id = ? AND pref_key = ?
                """,
                (user_id or DEFAULT_USER_ID, key),
            )
            conn.commit()

            return {
                "success": True,
                "deleted": cur.rowcount > 0,
                "key": key,
            }
        finally:
            conn.close()


_AUTO_PATTERNS: list[tuple[re.Pattern[str], str, int]] = [
    (
        re.compile(
            r"\b(?:my name is|mera naam|mera name)\s+([A-Za-z][A-Za-z .'-]{1,60})",
            re.IGNORECASE,
        ),
        "personal",
        9,
    ),
    (
        re.compile(
            r"\b(?:i prefer|i like|mujhe pasand hai)\s+(.{2,140})",
            re.IGNORECASE,
        ),
        "preference",
        7,
    ),
    (
        re.compile(
            r"\b(?:remember that|remember this|yaad rakhna|yaad rakho)\s+(.{2,220})",
            re.IGNORECASE,
        ),
        "general",
        9,
    ),
    (
        re.compile(
            r"\b(?:my goal is|mera goal|mera target)\s+(.{2,180})",
            re.IGNORECASE,
        ),
        "goal",
        8,
    ),
]


def extract_memory_candidates(text: str) -> list[dict[str, Any]]:
    text = (text or "").strip()

    if not text or looks_sensitive(text):
        return []

    candidates: list[dict[str, Any]] = []

    for pattern, category, importance in _AUTO_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue

        extracted = match.group(match.lastindex or 0).strip(" .,!?:;")

        if category == "personal" and "name" in pattern.pattern.lower():
            content = f"User's name is {extracted}."
        elif "remember" in pattern.pattern.lower() or "yaad" in pattern.pattern.lower():
            content = extracted
        else:
            content = match.group(0).strip(" .,!?:;")

        if len(content) < 3 or looks_sensitive(content):
            continue

        candidates.append(
            {
                "content": content,
                "category": category,
                "importance": importance,
            }
        )

    return candidates


def auto_save_from_message(
    text: str,
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    candidates = extract_memory_candidates(text)
    saved: list[dict[str, Any]] = []

    for item in candidates:
        saved.append(
            add_memory(
                content=item["content"],
                user_id=user_id,
                category=item["category"],
                importance=item["importance"],
                source="automatic",
                metadata={"original_message": text},
                prevent_duplicates=True,
            )
        )

    return {
        "success": True,
        "candidate_count": len(candidates),
        "saved": saved,
    }


def build_memory_context(
    query: str,
    user_id: str = DEFAULT_USER_ID,
    session_id: str = "default",
    long_term_limit: int = 8,
    short_term_limit: int = 12,
    include_preferences: bool = True,
) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "query": query,
        "long_term_memories": recall_memories(
            query=query,
            user_id=user_id,
            limit=long_term_limit,
        ),
        "recent_conversation": get_recent_conversation(
            user_id=user_id,
            session_id=session_id,
            limit=short_term_limit,
        ),
        "preferences": (
            get_all_preferences(user_id=user_id)
            if include_preferences
            else {}
        ),
    }


def memory_context_as_text(
    query: str,
    user_id: str = DEFAULT_USER_ID,
    session_id: str = "default",
    long_term_limit: int = 8,
    short_term_limit: int = 12,
) -> str:
    context = build_memory_context(
        query=query,
        user_id=user_id,
        session_id=session_id,
        long_term_limit=long_term_limit,
        short_term_limit=short_term_limit,
        include_preferences=True,
    )

    lines: list[str] = []

    memories = context["long_term_memories"]
    if memories:
        lines.append("Relevant long-term memory:")
        for item in memories:
            lines.append(
                f"- [{item['category']}, importance {item['importance']}] "
                f"{item['content']}"
            )

    preferences = context["preferences"]
    if preferences:
        lines.append("\nUser preferences:")
        for key, value in preferences.items():
            lines.append(f"- {key}: {value}")

    recent = context["recent_conversation"]
    if recent:
        lines.append("\nRecent conversation:")
        for item in recent:
            lines.append(f"- {item['role']}: {item['content']}")

    return "\n".join(lines).strip()


def memory_stats(
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    user_id = user_id or DEFAULT_USER_ID
    conn = _connect()

    try:
        total = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM memories
            WHERE user_id = ? AND is_active = 1
            """,
            (user_id,),
        ).fetchone()["c"]

        categories = conn.execute(
            """
            SELECT category, COUNT(*) AS c
            FROM memories
            WHERE user_id = ? AND is_active = 1
            GROUP BY category
            ORDER BY c DESC
            """,
            (user_id,),
        ).fetchall()

        short_count = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM conversation_messages
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()["c"]

        pref_count = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM user_preferences
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()["c"]

        return {
            "success": True,
            "user_id": user_id,
            "long_term_memories": int(total),
            "short_term_messages": int(short_count),
            "preferences": int(pref_count),
            "categories": {
                row["category"]: int(row["c"])
                for row in categories
            },
            "database": str(DB_PATH),
        }
    finally:
        conn.close()


def clear_all_memories(
    user_id: str = DEFAULT_USER_ID,
    include_preferences: bool = False,
    include_short_term: bool = False,
) -> dict[str, Any]:
    user_id = user_id or DEFAULT_USER_ID

    with _db_lock:
        conn = _connect()
        try:
            long_term = conn.execute(
                """
                UPDATE memories
                SET is_active = 0, updated_at = ?
                WHERE user_id = ? AND is_active = 1
                """,
                (utc_now_iso(), user_id),
            ).rowcount

            pref_deleted = 0
            short_deleted = 0

            if include_preferences:
                pref_deleted = conn.execute(
                    "DELETE FROM user_preferences WHERE user_id = ?",
                    (user_id,),
                ).rowcount

            if include_short_term:
                short_deleted = conn.execute(
                    "DELETE FROM conversation_messages WHERE user_id = ?",
                    (user_id,),
                ).rowcount

            conn.commit()

            return {
                "success": True,
                "long_term_forgotten": long_term,
                "preferences_deleted": pref_deleted,
                "short_term_deleted": short_deleted,
            }
        finally:
            conn.close()


def execute_memory_action(
    action: str,
    user_id: str = DEFAULT_USER_ID,
    **kwargs: Any,
) -> Any:
    action = (action or "").strip().lower()

    if action in {"remember", "add", "save"}:
        return add_memory(
            content=kwargs.get("content", ""),
            user_id=user_id,
            category=kwargs.get("category", "general"),
            importance=kwargs.get("importance", 5),
            source=kwargs.get("source", "manual"),
            metadata=kwargs.get("metadata"),
            prevent_duplicates=kwargs.get("prevent_duplicates", True),
        )

    if action in {"recall", "search"}:
        return search_memories(
            query=kwargs.get("query", ""),
            user_id=user_id,
            category=kwargs.get("category"),
            limit=kwargs.get("limit", DEFAULT_RECALL_LIMIT),
            min_score=kwargs.get("min_score", 0.12),
        )

    if action == "get":
        result = get_memory(
            memory_id=int(kwargs.get("memory_id", 0)),
            user_id=user_id,
        )
        return result or {"success": False, "error": "Memory not found."}

    if action == "list":
        return list_memories(
            user_id=user_id,
            category=kwargs.get("category"),
            limit=kwargs.get("limit", 100),
            active_only=kwargs.get("active_only", True),
        )

    if action == "update":
        return update_memory(
            memory_id=int(kwargs.get("memory_id", 0)),
            user_id=user_id,
            content=kwargs.get("content"),
            category=kwargs.get("category"),
            importance=kwargs.get("importance"),
            metadata=kwargs.get("metadata"),
        )

    if action in {"delete", "forget"}:
        return delete_memory(
            memory_id=int(kwargs.get("memory_id", 0)),
            user_id=user_id,
            hard_delete=kwargs.get("hard_delete", False),
        )

    if action == "forget_text":
        return forget_by_text(
            text=kwargs.get("text", ""),
            user_id=user_id,
            similarity_threshold=kwargs.get("similarity_threshold", 0.82),
        )

    if action in {"save_message", "conversation_save"}:
        return save_conversation_message(
            role=kwargs.get("role", "user"),
            content=kwargs.get("content", ""),
            user_id=user_id,
            session_id=kwargs.get("session_id", "default"),
        )

    if action in {"recent", "recent_conversation"}:
        return get_recent_conversation(
            user_id=user_id,
            session_id=kwargs.get("session_id", "default"),
            limit=kwargs.get("limit", MAX_SHORT_TERM_MESSAGES),
        )

    if action == "clear_short_term":
        return clear_short_term_memory(
            user_id=user_id,
            session_id=kwargs.get("session_id"),
        )

    if action == "set_preference":
        return set_preference(
            key=kwargs.get("key", ""),
            value=kwargs.get("value"),
            user_id=user_id,
        )

    if action == "get_preference":
        return {
            "success": True,
            "key": kwargs.get("key", ""),
            "value": get_preference(
                key=kwargs.get("key", ""),
                user_id=user_id,
                default=kwargs.get("default"),
            ),
        }

    if action == "preferences":
        return {
            "success": True,
            "preferences": get_all_preferences(user_id=user_id),
        }

    if action == "delete_preference":
        return delete_preference(
            key=kwargs.get("key", ""),
            user_id=user_id,
        )

    if action == "auto_save":
        return auto_save_from_message(
            text=kwargs.get("text", ""),
            user_id=user_id,
        )

    if action == "context":
        return build_memory_context(
            query=kwargs.get("query", ""),
            user_id=user_id,
            session_id=kwargs.get("session_id", "default"),
            long_term_limit=kwargs.get("long_term_limit", 8),
            short_term_limit=kwargs.get("short_term_limit", 12),
            include_preferences=kwargs.get("include_preferences", True),
        )

    if action == "context_text":
        return memory_context_as_text(
            query=kwargs.get("query", ""),
            user_id=user_id,
            session_id=kwargs.get("session_id", "default"),
            long_term_limit=kwargs.get("long_term_limit", 8),
            short_term_limit=kwargs.get("short_term_limit", 12),
        )

    if action == "stats":
        return memory_stats(user_id=user_id)

    if action == "clear_all":
        if not kwargs.get("confirm", False):
            return {
                "success": False,
                "error": "Confirmation required for clearing all memories.",
            }

        return clear_all_memories(
            user_id=user_id,
            include_preferences=kwargs.get("include_preferences", False),
            include_short_term=kwargs.get("include_short_term", False),
        )

    return {
        "success": False,
        "error": f"Unknown memory action: {action}",
    }


def memory_module_status() -> dict[str, Any]:
    return {
        "module": "memory",
        "ready": True,
        "database": str(DB_PATH),
        "features": [
            "short_term_memory",
            "long_term_memory",
            "preferences",
            "per_user_memory",
            "search_recall",
            "importance_scoring",
            "duplicate_prevention",
            "update_delete_forget",
            "automatic_safe_extraction",
            "context_builder",
            "stats",
            "central_router",
        ],
    }


if __name__ == "__main__":
    print("Maya Memory System")
    print(memory_module_status())

    demo_user = "demo"

    print(
        add_memory(
            "User is building Maya AI.",
            user_id=demo_user,
            category="project",
            importance=9,
        )
    )

    print(
        save_conversation_message(
            "user",
            "I am working on Maya AI.",
            user_id=demo_user,
            session_id="test",
        )
    )

    print(
        recall_memories(
            "What project is the user building?",
            user_id=demo_user,
        )
    )

    print(memory_stats(demo_user))
