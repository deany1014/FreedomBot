# cogs/Governace/db_manager.py
import aiosqlite
from datetime import datetime
from typing import Optional, List, Dict, Any

class DBManager:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self):
        """Create tables if they do not exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS proposals (
                    bill_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    text TEXT NOT NULL,
                    proposer_id INTEGER NOT NULL,
                    proposal_message_id INTEGER,
                    debate_message_id INTEGER,
                    vote_message_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'awaiting', -- awaiting, debating, voting, passed, failed, vetoed, archived
                    created_at TEXT NOT NULL,
                    vote_start TEXT,
                    vote_end TEXT,
                    yes_count INTEGER DEFAULT 0,
                    no_count INTEGER DEFAULT 0,
                    abstain_count INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS votes (
                    vote_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    bill_id INTEGER NOT NULL,
                    vote_type TEXT NOT NULL, -- yes/no/abstain
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, bill_id),
                    FOREIGN KEY(bill_id) REFERENCES proposals(bill_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS laws (
                    law_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bill_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    text TEXT NOT NULL,
                    enacted_at TEXT NOT NULL
                );
                """
            )
            await db.commit()

    # ---------- Proposal CRUD ----------
    async def insert_proposal(self, title: str, text: str, proposer_id: int) -> int:
        created_at = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO proposals (title, text, proposer_id, created_at) VALUES (?, ?, ?, ?)",
                (title, text, proposer_id, created_at)
            )
            await db.commit()
            return cursor.lastrowid

    async def update_proposal_message_ids(self, bill_id: int, proposal_message_id: Optional[int] = None,
                                          debate_message_id: Optional[int] = None, vote_message_id: Optional[int] = None):
        async with aiosqlite.connect(self.db_path) as db:
            if proposal_message_id is not None:
                await db.execute("UPDATE proposals SET proposal_message_id = ? WHERE bill_id = ?", (proposal_message_id, bill_id))
            if debate_message_id is not None:
                await db.execute("UPDATE proposals SET debate_message_id = ? WHERE bill_id = ?", (debate_message_id, bill_id))
            if vote_message_id is not None:
                await db.execute("UPDATE proposals SET vote_message_id = ? WHERE bill_id = ?", (vote_message_id, bill_id))
            await db.commit()

    async def set_vote_times(self, bill_id: int, vote_start: datetime, vote_end: datetime):
        await self.update_proposal_times(bill_id, vote_start.isoformat(), vote_end.isoformat())

    async def update_proposal_times(self, bill_id: int, vote_start_iso: Optional[str], vote_end_iso: Optional[str]):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE proposals SET vote_start = ?, vote_end = ?, status = ? WHERE bill_id = ?",
                             (vote_start_iso, vote_end_iso, "voting" if vote_start_iso and vote_end_iso else "debating", bill_id))
            await db.commit()

    async def set_status(self, bill_id: int, status: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE proposals SET status = ? WHERE bill_id = ?", (status, bill_id))
            await db.commit()

    async def get_proposal_by_id(self, bill_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM proposals WHERE bill_id = ?", (bill_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_all_pending_votes(self) -> List[Dict[str, Any]]:
        """Return proposals that have vote_start or vote_end in future or voting ongoing."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM proposals WHERE status IN ('debating','voting') AND (vote_end IS NOT NULL OR vote_start IS NOT NULL)")
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # ---------- Voting ----------
    async def record_vote(self, user_id: int, bill_id: int, vote_type: str) -> bool:
        """Return True if recorded, False if user already voted (and preserved previous)."""
        created_at = datetime.utcnow().isoformat()
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO votes (user_id, bill_id, vote_type, created_at) VALUES (?, ?, ?, ?)",
                    (user_id, bill_id, vote_type, created_at)
                )
                # increment counts
                if vote_type == "yes":
                    await db.execute("UPDATE proposals SET yes_count = yes_count + 1 WHERE bill_id = ?", (bill_id,))
                elif vote_type == "no":
                    await db.execute("UPDATE proposals SET no_count = no_count + 1 WHERE bill_id = ?", (bill_id,))
                else:
                    await db.execute("UPDATE proposals SET abstain_count = abstain_count + 1 WHERE bill_id = ?", (bill_id,))
                await db.commit()
            return True
        except aiosqlite.IntegrityError:
            # Unique constraint: user already voted
            return False

    async def get_user_vote(self, user_id: int, bill_id: int) -> Optional[str]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT vote_type FROM votes WHERE user_id = ? AND bill_id = ?", (user_id, bill_id))
            row = await cursor.fetchone()
            return row["vote_type"] if row else None

    async def get_vote_counts(self, bill_id: int) -> Dict[str, int]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT yes_count, no_count, abstain_count FROM proposals WHERE bill_id = ?", (bill_id,))
            row = await cur.fetchone()
            if not row:
                return {"yes": 0, "no": 0, "abstain": 0}
            return {"yes": row["yes_count"], "no": row["no_count"], "abstain": row["abstain_count"]}

    # ---------- Laws and archival ----------
    async def add_law_from_bill(self, bill_id: int):
        proposal = await self.get_proposal_by_id(bill_id)
        if not proposal:
            return None
        enacted_at = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "INSERT INTO laws (bill_id, title, text, enacted_at) VALUES (?, ?, ?, ?)",
                (bill_id, proposal["title"], proposal["text"], enacted_at)
            )
            await db.commit()
            return cur.lastrowid

    async def get_all_approved_laws(self) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM laws ORDER BY enacted_at DESC")
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # ---------- Staff actions ----------
    async def veto_bill(self, bill_id: int, reason: Optional[str] = None) -> bool:
        prop = await self.get_proposal_by_id(bill_id)
        if not prop:
            return False
        await self.set_status(bill_id, "vetoed")
        # keep vote counts for record but mark as vetoed
        return True

    async def remove_bill(self, bill_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM proposals WHERE bill_id = ?", (bill_id,))
            await db.commit()
            return True
