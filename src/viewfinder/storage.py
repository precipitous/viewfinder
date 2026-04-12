"""SQLite persistence layer for Viewfinder.

Stores videos, transcripts, screenshots, and summaries. Uses stdlib sqlite3
(no extra dependencies). The DB file defaults to ~/.viewfinder/viewfinder.db.
"""

import json
import sqlite3
from pathlib import Path

from .models import (
    ScreenshotResult,
    SummaryResult,
    TranscriptResult,
    TranscriptSnippet,
    TranscriptSource,
    VideoMeta,
)

DEFAULT_DB_DIR = Path.home() / ".viewfinder"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "viewfinder.db"

SCHEMA_VERSION = 1

SCHEMA = """\
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    title TEXT,
    channel TEXT,
    duration_seconds INTEGER,
    upload_date TEXT,
    description TEXT,
    url TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    source TEXT NOT NULL,
    language TEXT NOT NULL,
    translated_from TEXT,
    is_generated INTEGER NOT NULL DEFAULT 0,
    full_text TEXT NOT NULL,
    snippets_json TEXT NOT NULL,
    word_count INTEGER NOT NULL,
    fetched_at TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(video_id, language, source)
);

CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    transcript_id INTEGER NOT NULL REFERENCES transcripts(id),
    summary TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_template TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    generated_at TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS screenshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    interval_seconds INTEGER NOT NULL,
    output_dir TEXT NOT NULL,
    paths_json TEXT NOT NULL,
    count INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_transcripts_video ON transcripts(video_id);
CREATE INDEX IF NOT EXISTS idx_summaries_video ON summaries(video_id);
CREATE INDEX IF NOT EXISTS idx_screenshots_video ON screenshots(video_id);
"""


class Storage:
    """SQLite storage for Viewfinder data."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = DEFAULT_DB_PATH
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._init_schema()
        return self._conn

    def _init_schema(self):
        self.conn.executescript(SCHEMA)
        row = self.conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            self.conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
            self.conn.commit()

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------------
    # Videos
    # ------------------------------------------------------------------

    def save_video(self, meta: VideoMeta):
        """Insert or update video metadata."""
        self.conn.execute(
            """INSERT INTO videos (video_id, title, channel, duration_seconds,
               upload_date, description, url)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(video_id) DO UPDATE SET
                 title = COALESCE(excluded.title, title),
                 channel = COALESCE(excluded.channel, channel),
                 duration_seconds = COALESCE(excluded.duration_seconds, duration_seconds),
                 upload_date = COALESCE(excluded.upload_date, upload_date),
                 description = COALESCE(excluded.description, description)
            """,
            (
                meta.video_id,
                meta.title,
                meta.channel,
                meta.duration_seconds,
                meta.upload_date,
                meta.description,
                meta.url,
            ),
        )
        self.conn.commit()

    def get_video(self, video_id: str) -> VideoMeta | None:
        """Fetch video metadata by ID."""
        row = self.conn.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,)).fetchone()
        if row is None:
            return None
        return VideoMeta(
            video_id=row["video_id"],
            title=row["title"],
            channel=row["channel"],
            duration_seconds=row["duration_seconds"],
            upload_date=row["upload_date"],
            description=row["description"],
            url=row["url"],
        )

    # ------------------------------------------------------------------
    # Transcripts
    # ------------------------------------------------------------------

    def save_transcript(self, result: TranscriptResult) -> int:
        """Save a transcript result. Returns the transcript row ID."""
        self.save_video(result.meta)

        snippets_json = json.dumps(
            [{"text": s.text, "start": s.start, "duration": s.duration} for s in result.snippets]
        )

        cursor = self.conn.execute(
            """INSERT INTO transcripts
               (video_id, source, language, translated_from, is_generated,
                full_text, snippets_json, word_count, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(video_id, language, source) DO UPDATE SET
                 full_text = excluded.full_text,
                 snippets_json = excluded.snippets_json,
                 word_count = excluded.word_count,
                 fetched_at = excluded.fetched_at
            """,
            (
                result.meta.video_id,
                result.source.value,
                result.language,
                result.translated_from,
                int(result.is_generated),
                result.full_text,
                snippets_json,
                result.word_count,
                result.fetched_at,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_transcript(
        self,
        video_id: str,
        language: str = "en",
        source: str | None = None,
    ) -> TranscriptResult | None:
        """Fetch a cached transcript. Returns None if not found."""
        if source:
            row = self.conn.execute(
                "SELECT * FROM transcripts WHERE video_id = ? AND language = ? AND source = ?",
                (video_id, language, source),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT * FROM transcripts WHERE video_id = ? AND language = ? ORDER BY id DESC",
                (video_id, language),
            ).fetchone()

        if row is None:
            return None

        meta = self.get_video(video_id) or VideoMeta(video_id=video_id)
        snippets = [
            TranscriptSnippet(text=s["text"], start=s["start"], duration=s["duration"])
            for s in json.loads(row["snippets_json"])
        ]

        return TranscriptResult(
            meta=meta,
            snippets=snippets,
            source=TranscriptSource(row["source"]),
            language=row["language"],
            translated_from=row["translated_from"],
            is_generated=bool(row["is_generated"]),
            fetched_at=row["fetched_at"],
        )

    def has_transcript(self, video_id: str, language: str = "en") -> bool:
        """Check if a transcript exists for this video and language."""
        row = self.conn.execute(
            "SELECT 1 FROM transcripts WHERE video_id = ? AND language = ?",
            (video_id, language),
        ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Summaries
    # ------------------------------------------------------------------

    def save_summary(self, result: SummaryResult, transcript_id: int) -> int:
        """Save a summary result. Returns the summary row ID."""
        cursor = self.conn.execute(
            """INSERT INTO summaries
               (video_id, transcript_id, summary, model, prompt_template,
                input_tokens, output_tokens, generated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.transcript.meta.video_id,
                transcript_id,
                result.summary,
                result.model,
                result.prompt_template,
                result.input_tokens,
                result.output_tokens,
                result.generated_at,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_summaries(self, video_id: str) -> list[dict]:
        """Fetch all summaries for a video."""
        rows = self.conn.execute(
            "SELECT * FROM summaries WHERE video_id = ? ORDER BY id DESC",
            (video_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Screenshots
    # ------------------------------------------------------------------

    def save_screenshots(self, result: ScreenshotResult) -> int:
        """Save screenshot result metadata. Returns the row ID."""
        self.save_video(result.meta)

        paths_json = json.dumps(
            [{"path": s.path, "timestamp": s.timestamp} for s in result.screenshots]
        )

        cursor = self.conn.execute(
            """INSERT INTO screenshots
               (video_id, interval_seconds, output_dir, paths_json, count)
               VALUES (?, ?, ?, ?, ?)
            """,
            (
                result.meta.video_id,
                result.interval_seconds,
                result.output_dir,
                paths_json,
                len(result.screenshots),
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    # ------------------------------------------------------------------
    # Cost tracking
    # ------------------------------------------------------------------

    def get_cost_summary(self) -> dict:
        """Return cumulative token usage across all summaries."""
        row = self.conn.execute(
            """SELECT
                 COUNT(*) as total_summaries,
                 COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                 COALESCE(SUM(output_tokens), 0) as total_output_tokens
               FROM summaries
            """
        ).fetchone()
        return {
            "total_summaries": row["total_summaries"],
            "total_input_tokens": row["total_input_tokens"],
            "total_output_tokens": row["total_output_tokens"],
            "total_tokens": row["total_input_tokens"] + row["total_output_tokens"],
        }

    def get_cost_by_model(self) -> list[dict]:
        """Return token usage grouped by model."""
        rows = self.conn.execute(
            """SELECT
                 model,
                 COUNT(*) as count,
                 COALESCE(SUM(input_tokens), 0) as input_tokens,
                 COALESCE(SUM(output_tokens), 0) as output_tokens
               FROM summaries
               GROUP BY model
               ORDER BY count DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------

    def list_videos(self, limit: int = 50) -> list[dict]:
        """List stored videos with transcript/summary counts."""
        rows = self.conn.execute(
            """SELECT
                 v.video_id, v.title, v.channel, v.duration_seconds,
                 (SELECT COUNT(*) FROM transcripts t
                  WHERE t.video_id = v.video_id) as transcript_count,
                 (SELECT COUNT(*) FROM summaries s
                  WHERE s.video_id = v.video_id) as summary_count
               FROM videos v
               ORDER BY v.created_at DESC
               LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def video_count(self) -> int:
        """Return total number of stored videos."""
        row = self.conn.execute("SELECT COUNT(*) as n FROM videos").fetchone()
        return row["n"]
