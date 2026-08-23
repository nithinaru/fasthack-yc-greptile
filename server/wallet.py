"""Wallet store — SQLite (PRD §3.4/§5.4: "Wallet = SQLite on a Modal Volume").

Single table `wallets(user_id TEXT PRIMARY KEY, credits INTEGER NOT NULL DEFAULT 0)`.
user_id = lowercase email. Debit is a single atomic UPDATE with a WHERE guard —
no read-then-write race, works fine under sqlite3's own connection-level lock too.

DB file path: settings.WALLET_DB (default DATA_DIR/"wallet.db"; on Modal that's
a path on the mounted Volume so balances survive container restarts).
"""
import logging
import sqlite3
import threading

import settings

log = logging.getLogger("server.wallet")

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            db_path = settings.WALLET_DB
            # Ensure the parent dir exists (DATA_DIR may not have been created yet).
            try:
                import pathlib
                pathlib.Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                log.warning("could not create wallet DB parent dir: %s", e)
            _conn = sqlite3.connect(db_path, check_same_thread=False)
            _conn.execute(
                "CREATE TABLE IF NOT EXISTS wallets ("
                "  user_id TEXT PRIMARY KEY,"
                "  credits INTEGER NOT NULL DEFAULT 0"
                ")"
            )
            _conn.commit()
            log.info("wallet DB ready at %s", db_path)
            _maybe_seed_mock_wallet(_conn)
        return _conn


def _maybe_seed_mock_wallet(conn: sqlite3.Connection) -> None:
    """Mock-mode convenience: give the demo wallet a starting balance the first
    time the DB is created, from fixtures/wallet.json. No-op if the table
    already has rows, or outside mock mode."""
    if not settings.USE_MOCKS:
        return
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM wallets").fetchone()
        if count:
            return
        import json
        data = json.loads((settings.FIXTURES_DIR / "wallet.json").read_text())
        uid = data["user_id"].lower()
        conn.execute(
            "INSERT INTO wallets (user_id, credits) VALUES (?, ?)",
            (uid, int(data["credits"])),
        )
        conn.commit()
        log.info("seeded mock wallet: %s = %d credits", uid, data["credits"])
    except (OSError, KeyError, ValueError, LookupError) as e:
        log.warning("could not seed mock wallet from fixtures/wallet.json (%s)", e)


def get_credits(user_id: str) -> int:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            "SELECT credits FROM wallets WHERE user_id = ?", (user_id,)
        ).fetchone()
    return int(row[0]) if row else 0


def credit(user_id: str, credits: int) -> int:
    """Add `credits` to user_id's balance (creating the row if needed). Returns
    the new balance."""
    conn = _get_conn()
    with _lock:
        conn.execute(
            "INSERT INTO wallets (user_id, credits) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET credits = credits + excluded.credits",
            (user_id, credits),
        )
        conn.commit()
        row = conn.execute(
            "SELECT credits FROM wallets WHERE user_id = ?", (user_id,)
        ).fetchone()
    return int(row[0])


def debit(user_id: str, n: int = 1) -> bool:
    """Atomically subtract n credits if the balance covers it. Returns True on
    success, False if there were insufficient credits (or no wallet at all —
    the UPDATE simply matches zero rows)."""
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "UPDATE wallets SET credits = credits - ? WHERE user_id = ? AND credits >= ?",
            (n, user_id, n),
        )
        conn.commit()
        return cur.rowcount > 0


def _reset_for_tests() -> None:
    """Test helper: drop the cached connection so a fresh settings.WALLET_DB
    (e.g. an in-memory or tmp-file DB) takes effect on the next call."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None
