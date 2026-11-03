from __future__ import annotations

import json
from datetime import datetime, timezone


class ShadowRecorder:
    """Prospective decisions only; records no fills and submits no orders."""

    def __init__(self, db):
        self.db = db

    def record(self, *, decision_time: datetime, variant: str, asset: str, baseline_action: str, llm_output, effective_action: str):
        if decision_time.tzinfo is None:
            raise ValueError("Decision time must be timezone-aware")
        if decision_time > datetime.now(timezone.utc):
            raise ValueError("Cannot record a future shadow decision")
        with self.db.connect() as c:
            cursor = c.execute(
                """INSERT INTO llm_shadow(created,decision_time,variant,asset,baseline_action,llm_output,effective_action,status)
                   VALUES(?,?,?,?,?,?,?,'pending')""",
                (
                    datetime.now(timezone.utc).isoformat(), decision_time.isoformat(), variant,
                    asset, baseline_action, json.dumps(llm_output), effective_action,
                ),
            )
        return cursor.lastrowid

    def settle(self, decision_id: int, pnl: float):
        with self.db.connect() as c:
            row = c.execute("SELECT status FROM llm_shadow WHERE id=?", (decision_id,)).fetchone()
            if not row or row["status"] != "pending":
                raise ValueError("Shadow decision absent or already settled")
            c.execute(
                "UPDATE llm_shadow SET settled_pnl=?,status='settled' WHERE id=?",
                (float(pnl), decision_id),
            )

    def rows(self):
        return self.db.rows("SELECT * FROM llm_shadow ORDER BY id DESC")
