"""Wallet store (contracts/wallet_api.md): mock in-memory store seeded from
fixtures/wallet.json, or DynamoDB `wallets` with the atomic conditional debit."""
import json
import logging
import threading
import time

import settings

log = logging.getLogger("server.wallet")


class InsufficientCredits(Exception):
    pass


def _ledger_entry(entry_type: str, amount: int, ref: str) -> dict:
    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "type": entry_type,
        "amount": amount,
        "ref": ref,
    }


class MockWalletStore:
    """In-memory wallet seeded from fixtures/wallet.json (single demo wallet)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._wallets: dict[str, dict] = {}
        self._seed()

    def _seed(self):
        path = settings.FIXTURES_DIR / "wallet.json"
        try:
            data = json.loads(path.read_text())
            uid = data["user_id"].lower()
            self._wallets[uid] = {
                "credits": int(data["credits"]),
                "ledger": list(data.get("ledger", [])),
            }
            log.info("seeded mock wallet: %s = %d credits", uid, data["credits"])
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as e:
            log.warning("could not seed from fixtures/wallet.json (%s); starting empty", e)

    def _wallet(self, user_id: str) -> dict:
        return self._wallets.setdefault(user_id, {"credits": 0, "ledger": []})

    def get_credits(self, user_id: str) -> int:
        return self._wallets.get(user_id, {}).get("credits", 0)

    def credit(self, user_id: str, amount: int, ref: str) -> int:
        with self._lock:
            w = self._wallet(user_id)
            w["credits"] += amount
            w["ledger"].append(_ledger_entry("topup", amount, ref))
            return w["credits"]

    def debit(self, user_id: str, amount: int, ref: str) -> int:
        with self._lock:
            w = self._wallet(user_id)
            if w["credits"] < amount:
                raise InsufficientCredits(user_id)
            w["credits"] -= amount
            w["ledger"].append(_ledger_entry("ask", -amount, ref))
            return w["credits"]


class DynamoWalletStore:
    """DynamoDB `wallets`: PK user_id (S), attrs credits (N), ledger (L)."""

    def __init__(self):
        import boto3

        self._table = boto3.resource("dynamodb", region_name=settings.AWS_REGION).Table(
            settings.WALLETS_TABLE
        )

    def get_credits(self, user_id: str) -> int:
        item = self._table.get_item(Key={"user_id": user_id}).get("Item")
        return int(item["credits"]) if item else 0

    def credit(self, user_id: str, amount: int, ref: str) -> int:
        resp = self._table.update_item(
            Key={"user_id": user_id},
            UpdateExpression=(
                "SET credits = if_not_exists(credits, :zero) + :amt, "
                "ledger = list_append(if_not_exists(ledger, :empty), :entry)"
            ),
            ExpressionAttributeValues={
                ":amt": amount,
                ":zero": 0,
                ":empty": [],
                ":entry": [_ledger_entry("topup", amount, ref)],
            },
            ReturnValues="UPDATED_NEW",
        )
        return int(resp["Attributes"]["credits"])

    def debit(self, user_id: str, amount: int, ref: str) -> int:
        from botocore.exceptions import ClientError

        try:
            resp = self._table.update_item(
                Key={"user_id": user_id},
                UpdateExpression=(
                    "SET credits = credits - :amt, "
                    "ledger = list_append(if_not_exists(ledger, :empty), :entry)"
                ),
                ConditionExpression="credits >= :amt",
                ExpressionAttributeValues={
                    ":amt": amount,
                    ":empty": [],
                    ":entry": [_ledger_entry("ask", -amount, ref)],
                },
                ReturnValues="UPDATED_NEW",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise InsufficientCredits(user_id) from e
            raise
        return int(resp["Attributes"]["credits"])


_store = None
_store_lock = threading.Lock()


def get_store():
    global _store
    with _store_lock:
        if _store is None:
            _store = MockWalletStore() if settings.USE_MOCKS else DynamoWalletStore()
        return _store
