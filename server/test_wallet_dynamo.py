"""D2 verification: DynamoWalletStore against moto (in-process DynamoDB mock).
Proves the atomic conditional debit + ledger behavior before AWS resources exist.

Run: .venv/bin/python3.14 -m pytest server/test_wallet_dynamo.py -q
"""
import concurrent.futures
import os

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

import server.settings as settings  # noqa: E402  (server/__init__ path shim)
import server.wallet as wallet  # noqa: E402


@pytest.fixture()
def store():
    with mock_aws():
        boto3.client("dynamodb", region_name=settings.AWS_REGION).create_table(
            TableName=settings.WALLETS_TABLE,
            KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield wallet.DynamoWalletStore()


def test_unknown_user_is_zero(store):
    assert store.get_credits("nobody@x.com") == 0


def test_credit_creates_wallet_and_ledger(store):
    assert store.credit("a@x.com", 100, "cs_1") == 100
    assert store.credit("a@x.com", 45, "cs_2") == 145
    assert store.get_credits("a@x.com") == 145


def test_debit_decrements(store):
    store.credit("b@x.com", 2, "cs_1")
    assert store.debit("b@x.com", 1, "job-1") == 1
    assert store.debit("b@x.com", 1, "job-2") == 0


def test_debit_insufficient_raises_and_leaves_balance(store):
    store.credit("c@x.com", 1, "cs_1")
    store.debit("c@x.com", 1, "job-1")
    with pytest.raises(wallet.InsufficientCredits):
        store.debit("c@x.com", 1, "job-2")
    assert store.get_credits("c@x.com") == 0


def test_debit_unknown_user_raises(store):
    with pytest.raises(wallet.InsufficientCredits):
        store.debit("ghost@x.com", 1, "job-1")


def test_concurrent_debits_never_oversell(store):
    store.credit("d@x.com", 5, "cs_1")
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(
            lambda i: _try_debit(store, "d@x.com", f"job-{i}"), range(10)
        ))
    assert sum(results) == 5  # exactly 5 of 10 succeed
    assert store.get_credits("d@x.com") == 0


def _try_debit(store, uid, ref):
    try:
        store.debit(uid, 1, ref)
        return 1
    except wallet.InsufficientCredits:
        return 0
