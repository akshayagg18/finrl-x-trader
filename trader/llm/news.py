from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from .schemas import NewsEvent


class NewsStore:
    def __init__(self, db):
        self.db = db

    def ingest(self, event: NewsEvent):
        digest = hashlib.sha256(event.content.encode()).hexdigest()
        with self.db.connect() as c:
            c.execute(
                """INSERT OR IGNORE INTO news_events(source_id,publisher,source_url,published_at,updated_at,available_at,retrieved_at,assets,title,content,content_hash)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event.source_id, event.publisher, event.source_url, event.published_at.isoformat(),
                    event.updated_at.isoformat() if event.updated_at else None,
                    event.earliest_available_at.isoformat(), event.retrieved_at.isoformat(),
                    ",".join(event.assets), event.title, event.content, digest,
                ),
            )
        return digest

    def as_of(self, decision_time: datetime, assets: list[str] | None = None):
        if decision_time.tzinfo is None:
            decision_time = decision_time.replace(tzinfo=timezone.utc)
        rows = self.db.rows(
            "SELECT * FROM news_events WHERE available_at<=? ORDER BY available_at,source_id",
            (decision_time.isoformat(),),
        )
        if assets:
            wanted = set(assets)
            rows = [r for r in rows if wanted.intersection(r["assets"].split(","))]
        return rows
