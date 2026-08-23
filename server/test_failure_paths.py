"""Failure-path tests: zero-credit 402 shape + wallet safety under concurrent debits.

Runs against the local SQLite wallet backend (server/wallet.py only routes to
modal.Dict when MODAL_TASK_ID is set — never in local pytest).

Run: .venv/bin/python -m pytest server/test_failure_paths.py -q
"""
import pathlib
import sys
import threading

import pytest
from fastapi.testclient import TestClient

_HERE = pathlib.Path(__file__).resolve().parent
for p in (str(_HERE), str(_HERE.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

import settings
import wallet
from app import app


@pytest.fixture()
def fresh_wallet(tmp_path, monkeypatch):
    """Point the wallet at a throwaway SQLite file and force the SQLite backend."""
    monkeypatch.delenv("MODAL_TASK_ID", raising=False)
    monkeypatch.setattr(settings, "WALLET_DB", str(tmp_path / "wallet.db"))
    wallet._reset_for_tests()
    yield
    wallet._reset_for_tests()


@pytest.fixture()
def client(fresh_wallet):
    # raise_server_exceptions default True is fine; we never expect a 500 here.
    with TestClient(app) as c:
        yield c


def test_zero_credit_ask_returns_402_no_credits(client):
    """Frontend contract (web/js/wallet.js liveAsk): status must be exactly 402;
    body standardized as {"error": "no_credits"}."""
    r = client.post(
        "/api/ask",
        json={"user_id": "broke@example.com", "episode_id": "ep1", "question": "hi?"},
    )
    assert r.status_code == 402
    assert r.json() == {"error": "no_credits"}
    # Wallet untouched (no negative balance created by the failed ask).
    assert wallet.get_credits("broke@example.com") == 0


def test_wallet_endpoint_shape(client):
    """Frontend fetchWallet() reads .credits as a number."""
    wallet.credit("shape@example.com", 3)
    r = client.get("/api/wallet/shape@example.com")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["credits"], int)
    assert body["credits"] == 3


def test_concurrent_debits_never_oversell(fresh_wallet):
    """Credit 5, fire 20 concurrent debits: exactly 5 succeed, balance never < 0."""
    user = "race@example.com"
    n_threads = 20
    wallet.credit(user, 5)

    barrier = threading.Barrier(n_threads)
    results = []
    results_lock = threading.Lock()

    def attempt():
        barrier.wait()  # maximize contention: all debits released at once
        ok = wallet.debit(user, 1)
        with results_lock:
            results.append(ok)

    threads = [threading.Thread(target=attempt) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(results) == 5, f"expected exactly 5 successful debits, got {sum(results)}"
    assert wallet.get_credits(user) == 0


def test_wallet_read_stays_nonnegative_during_debits(client):
    """GET /api/wallet must return an int >= 0 at every point while debits race."""
    user = "reader@example.com"
    n_threads = 12
    wallet.credit(user, 5)

    start = threading.Barrier(n_threads + 1)
    done = threading.Event()
    remaining = [n_threads]
    count_lock = threading.Lock()

    def attempt():
        start.wait()
        wallet.debit(user, 1)
        with count_lock:
            remaining[0] -= 1
            if remaining[0] == 0:
                done.set()

    threads = [threading.Thread(target=attempt) for _ in range(n_threads)]
    for t in threads:
        t.start()
    start.wait()  # release the debit horde, then hammer reads until they finish

    observed = []
    while not done.is_set():
        r = client.get(f"/api/wallet/{user}")
        assert r.status_code == 200
        c = r.json()["credits"]
        assert isinstance(c, int)
        assert c >= 0, f"wallet read went negative: {c}"
        observed.append(c)
    for t in threads:
        t.join()

    # Final state: 12 attempted, only 5 could succeed.
    final = client.get(f"/api/wallet/{user}").json()["credits"]
    assert final == 0
    assert all(v >= 0 for v in observed)
