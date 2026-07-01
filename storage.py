"""
Unified storage layer for JARVIS.
- SQLite: users, messages (relational / auth)
- ChromaDB: vector embeddings for semantic memory retrieval
- SentenceTransformers: local embedding generation (all-MiniLM-L6-v2)
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

import bcrypt
import chromadb
from chromadb.api.types import EmbeddingFunction
from sentence_transformers import SentenceTransformer

logger = logging.getLogger("jarvis.storage")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str(BASE_DIR / "jarvis.db")
CHROMA_PATH = str(BASE_DIR / "chroma_data")

# ---------------------------------------------------------------------------
# Lazy singletons (loaded on first use, not on import)
# ---------------------------------------------------------------------------

_embedding_model: Optional[SentenceTransformer] = None
_chroma_client: Optional[chromadb.PersistentClient] = None
_message_collection = None


def _get_model() -> SentenceTransformer:
    """Load the embedding model once.  ~80 MB, fast on CPU."""
    global _embedding_model
    if _embedding_model is None:
        logger.info("Loading SentenceTransformer model 'all-MiniLM-L6-v2' ...")
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Embedding model ready (dim=%d)", _embedding_model.get_sentence_embedding_dimension())
    return _embedding_model


def _get_chroma():
    """Return (client, messages_collection)."""
    global _chroma_client, _message_collection
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
        _message_collection = _chroma_client.get_or_create_collection(
            name="jarvis_messages",
            metadata={"hnsw:space": "cosine"},
        )
    return _chroma_client, _message_collection


# ---------------------------------------------------------------------------
# SQLite schema
# ---------------------------------------------------------------------------

def init_db():
    """Create tables if they don't exist.  Idempotent — safe to call on every boot."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    UNIQUE NOT NULL,
            password    TEXT    NOT NULL,
            created_at  TEXT    NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            role        TEXT    NOT NULL,
            content     TEXT    NOT NULL,
            timestamp   TEXT    NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Index for fast per-user history lookups
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)
    """)

    conn.commit()
    conn.close()
    logger.info("SQLite tables ready at %s", DB_PATH)


# ---------------------------------------------------------------------------
# User management (bcrypt)
# ---------------------------------------------------------------------------

def create_user(username: str, password: str) -> dict:
    """Register a new user.  Returns user dict or {'error': ...}."""
    username = username.strip().lower()
    if len(username) < 2:
        return {"error": "Username must be at least 2 characters"}
    if len(password) < 4:
        return {"error": "Password must be at least 4 characters"}

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cur.fetchone():
        conn.close()
        return {"error": "Username already taken"}

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    now = datetime.now().isoformat()
    cur.execute(
        "INSERT INTO users (username, password, created_at) VALUES (?, ?, ?)",
        (username, pw_hash, now),
    )
    user_id = cur.lastrowid
    conn.commit()
    conn.close()

    logger.info("User created: %s (id=%d)", username, user_id)
    return {"id": user_id, "username": username}


def authenticate_user(username: str, password: str) -> dict:
    """Validate credentials.  Returns user dict or {'error': ...}."""
    username = username.strip().lower()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, username, password FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return {"error": "Invalid username or password"}

    if not bcrypt.checkpw(password.encode(), row[2].encode()):
        return {"error": "Invalid username or password"}

    return {"id": row[0], "username": row[1]}


# ---------------------------------------------------------------------------
# Message persistence (SQLite + ChromaDB dual-write)
# ---------------------------------------------------------------------------

def save_message(user_id: int, role: str, content: str):
    """Persist a single message to SQLite and embed+index it in ChromaDB."""
    if not content.strip():
        return

    timestamp = datetime.now().isoformat()

    # 1. SQLite ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO messages (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (user_id, role, content, timestamp),
    )
    msg_id = cur.lastrowid
    conn.commit()
    conn.close()

    # 2. ChromaDB vector store ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    try:
        model = _get_model()
        _, coll = _get_chroma()
        embedding = model.encode(content, show_progress_bar=False).tolist()

        coll.add(
            ids=[f"msg_{user_id}_{msg_id}"],
            embeddings=[embedding],
            metadatas=[{
                "user_id": user_id,
                "role": role,
                "timestamp": timestamp,
                "preview": content[:300],
            }],
            documents=[content],
        )
    except Exception:
        logger.exception("ChromaDB write failed for msg %d — non-fatal", msg_id)


# ---------------------------------------------------------------------------
# History (recency-based, for the LLM context window)
# ---------------------------------------------------------------------------

def get_history(user_id: int, limit: int = 20) -> list[dict]:
    """Return last N messages as [{'role':..., 'content':...}] in chronological order."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [{"role": r, "content": c} for r, c in reversed(rows)]


# ---------------------------------------------------------------------------
# Semantic memory retrieval (the core new feature)
# ---------------------------------------------------------------------------

def retrieve_memories(user_id: int, query: str, top_k: int = 5) -> list[dict]:
    """
    Find past messages that are semantically similar to `query`.
    Returns list of {content, timestamp, relevance} sorted by relevance.
    """
    try:
        model = _get_model()
        _, coll = _get_chroma()
        q_emb = model.encode(query, show_progress_bar=False).tolist()

        results = coll.query(
            query_embeddings=[q_emb],
            n_results=top_k,
            where={"user_id": user_id},
        )

        memories: list[dict] = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                doc = results["documents"][0][i] if results["documents"] else ""
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                dist = results["distances"][0][i] if results["distances"] else 1.0
                memories.append({
                    "content": doc,
                    "timestamp": meta.get("timestamp", ""),
                    "relevance": round(max(0, 1 - dist), 3),
                })

        return memories

    except Exception:
        logger.exception("Memory retrieval failed — returning empty")
        return []


def search_memories(user_id: int, query: str, top_k: int = 10) -> list[dict]:
    """Public alias — same as retrieve_memories, exposed for the /search endpoint."""
    return retrieve_memories(user_id, query, top_k)


def get_user_message_count(user_id: int) -> int:
    """Total number of messages stored for this user."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM messages WHERE user_id = ?", (user_id,))
    count = cur.fetchone()[0]
    conn.close()
    return count


# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------

init_db()
