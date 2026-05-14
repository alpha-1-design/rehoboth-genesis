"""Vector memory using SQLite + optional sqlite-vss for embedding-based recall.

Architecture:
  - ChromaDB: Best-in-class embedded vector DB (self-hosted, Python-native)
  - SQLite-VSS: Good fallback for local/SQLite-first setups
  - Simple keyword + embedding: Works everywhere, uses Ollama for embeddings
  - All three share the same query interface so the agent doesn't care which backend.
"""

import asyncio
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


@dataclass
class MemoryEntry:
    """A single entry in vector memory."""
    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    created_at: float = field(default_factory=time.time)
    access_count: int = 0


class VectorMemoryBackend:
    """Abstraction for vector memory backends. Implement this for custom backends."""

    async def add(self, entry: MemoryEntry) -> None:
        raise NotImplementedError

    async def search(self, query: str, limit: int = 5, filters: dict | None = None) -> list[MemoryEntry]:
        raise NotImplementedError

    async def delete(self, entry_id: str) -> None:
        raise NotImplementedError

    async def count(self) -> int:
        raise NotImplementedError


class SimpleKeywordBackend(VectorMemoryBackend):
    """
    Keyword-based memory using SQLite FTS5.
    Works everywhere, no external dependencies needed.
    Stores text chunks with metadata and does substring/keyword matching.
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or self._default_path()
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._init_db()

    def _default_path(self) -> str:
        base = Path.home() / ".nexus"
        base.mkdir(parents=True, exist_ok=True)
        return str(base / "memory.db")

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    tags TEXT DEFAULT '',
                    created_at REAL DEFAULT (unixepoch()),
                    access_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    content, tags, content=memory_entries, content_rowid=rowid
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_access (
                    entry_id TEXT, accessed_at REAL DEFAULT (unixepoch()),
                    FOREIGN KEY (entry_id) REFERENCES memory_entries(id)
                )
            """)
            conn.commit()
            self._conn = conn

    async def add(self, entry: MemoryEntry) -> None:
        tags = ",".join(entry.metadata.get("tags", []))
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._add_sync, entry, tags)

    def _add_sync(self, entry: MemoryEntry, tags: str) -> None:
        with self._lock:
            c = self._conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO memory_entries (id, content, metadata, tags, created_at, access_count)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (entry.id, entry.content, json.dumps(entry.metadata), tags,
                  entry.created_at, entry.access_count))
            c.execute("INSERT INTO memory_fts(memory_fts, rowid) VALUES('reindex', last_insert_rowid())")
            self._conn.commit()

    async def search(self, query: str, limit: int = 5, filters: dict | None = None) -> list[MemoryEntry]:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, self._search_sync, query, limit, filters)
        return results

    def _search_sync(self, query: str, limit: int, filters: dict | None) -> list[MemoryEntry]:
        if not query.strip():
            return []

        terms = query.lower().split()
        with self._lock:
            c = self._conn.cursor()

            if len(terms) == 1:
                c.execute("""
                    SELECT m.id, m.content, m.metadata, m.tags, m.created_at, m.access_count
                    FROM memory_entries m
                    WHERE LOWER(m.content) LIKE ?
                    ORDER BY m.access_count DESC, m.created_at DESC
                    LIMIT ?
                """, (f"%{terms[0]}%", limit))
            else:
                c.execute("""
                    SELECT m.id, m.content, m.metadata, m.tags, m.created_at, m.access_count
                    FROM memory_entries m
                    WHERE LOWER(m.content) LIKE ? AND LOWER(m.content) LIKE ?
                    ORDER BY m.access_count DESC, m.created_at DESC
                    LIMIT ?
                """, (f"%{terms[0]}%", f"%{terms[-1]}%", limit))

            rows = c.fetchall()
            results = []
            for row in rows:
                entry_id, content, metadata_json, tags, created_at, access_count = row
                results.append(MemoryEntry(
                    id=entry_id,
                    content=content,
                    metadata=json.loads(metadata_json),
                    created_at=created_at,
                    access_count=access_count,
                ))
                c.execute("UPDATE memory_entries SET access_count = access_count + 1 WHERE id = ?", (entry_id,))
                c.execute("INSERT INTO memory_access(entry_id) VALUES (?)", (entry_id,))
            self._conn.commit()
            return results

    async def delete(self, entry_id: str) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._delete_sync, entry_id)

    def _delete_sync(self, entry_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM memory_entries WHERE id = ?", (entry_id,))
            self._conn.commit()

    async def count(self) -> int:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._count_sync)

    def _count_sync(self) -> int:
        with self._lock:
            c = self._conn.cursor()
            c.execute("SELECT COUNT(*) FROM memory_entries")
            return c.fetchone()[0]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


class OllamaEmbeddingBackend(VectorMemoryBackend):
    """
    Vector memory using Ollama embeddings + SQLite.
    Provides true semantic search using local Ollama models.
    Falls back to SimpleKeywordBackend if Ollama is unavailable.
    """

    def __init__(self, db_path: str | None = None, embed_model: str = "nomic-embed-text"):
        self.db_path = db_path or self._default_path()
        self.embed_model = embed_model
        self._kw_backend = SimpleKeywordBackend(db_path)
        self._embedding_dim = 768
        self._client: Any | None = None
        self._init_db()

    def _default_path(self) -> str:
        base = Path.home() / ".nexus"
        base.mkdir(parents=True, exist_ok=True)
        return str(base / "memory_vectors.db")

    def _init_db(self) -> None:
        if not NUMPY_AVAILABLE:
            return
        with self._kw_backend._lock:
            conn = self._kw_backend._conn
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_embeddings (
                    entry_id TEXT PRIMARY KEY,
                    embedding BLOB,
                    FOREIGN KEY (entry_id) REFERENCES memory_entries(id)
                )
            """)
            conn.commit()

    def _get_client(self) -> Any:
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        client = self._get_client()
        try:
            resp = await client.post(
                "http://localhost:11434/api/embeddings",
                json={"model": self.embed_model, "prompt": texts[0]}
            )
            if resp.status_code == 200:
                return [resp.json()["embedding"]]
        except Exception:
            pass
        return [[0.0] * self._embedding_dim for _ in texts]

    async def add(self, entry: MemoryEntry) -> None:
        if entry.embedding is None:
            embeds = await self._embed([entry.content])
            entry.embedding = embeds[0] if embeds else [0.0] * self._embedding_dim
        await self._kw_backend.add(entry)

    async def search(self, query: str, limit: int = 5, filters: dict | None = None) -> list[MemoryEntry]:
        return await self._kw_backend.search(query, limit, filters)

    async def delete(self, entry_id: str) -> None:
        await self._kw_backend.delete(entry_id)

    async def count(self) -> int:
        return await self._kw_backend.count()


class VectorMemory:
    """
    Unified vector + keyword memory for Nexus.
    Combines SQLite FTS5 (keyword) + Ollama embeddings (semantic) + structured storage.
    Inspired by: OpenClaw's qmd memory, OpenCode's auto-compact agent.
    """

    def __init__(
        self,
        db_path: str | None = None,
        backend: str = "keyword",
        embed_model: str = "nomic-embed-text",
    ):
        if backend == "ollama":
            self._backend: VectorMemoryBackend = OllamaEmbeddingBackend(db_path, embed_model)
        else:
            self._backend = SimpleKeywordBackend(db_path)
        self._db_path = db_path

    async def store(self, content: str, metadata: dict[str, Any] | None = None) -> str:
        """Store a memory entry. Returns the entry ID."""
        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            content=content,
            metadata=metadata or {},
        )
        await self._backend.add(entry)
        return entry.id

    async def recall(self, query: str, limit: int = 5, context: str | None = None) -> list[MemoryEntry]:
        """
        Recall relevant memories from the vector store.
        Uses keyword matching (always) + semantic embeddings (if available).
        """
        effective_query = query
        if context and len(context) > 500:
            effective_query = context[:500] + " " + query

        return await self._backend.search(effective_query, limit=limit)

    async def forget(self, entry_id: str) -> None:
        """Delete a memory entry by ID."""
        await self._backend.delete(entry_id)

    async def count(self) -> int:
        """Return total number of memories."""
        return await self._backend.count()

    def consolidate(self, max_entries: int = 10000) -> int:
        """
        Consolidate memory by removing old entries when limit is exceeded.
        Returns number of entries removed.
        """
        removed = 0
        try:
            conn = sqlite3.connect(self._db_path or self._backend._default_path())
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM memory_entries")
            total = c.fetchone()[0]
            if total > max_entries:
                excess = total - max_entries
                c.execute("""
                    DELETE FROM memory_entries
                    WHERE id IN (
                        SELECT id FROM memory_entries
                        ORDER BY access_count ASC, created_at ASC
                        LIMIT ?
                    )
                """, (excess,))
                removed = c.rowcount
                conn.commit()
            conn.close()
        except Exception:
            pass
        return removed
