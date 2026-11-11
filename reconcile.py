#!/usr/bin/env python3
"""Payment reconciliation.

Reads payments.jsonl and works out how much money we actually collected.
Run:  python3 reconcile.py

Rules implemented (see README.md):
  * Lines that cannot be parsed, and events without a `txn_id`, are ignored.
  * A payment may be attempted several times; only the latest attempt for each
    `txn_id` counts. "Latest" is decided by the event `ts`, not by line order,
    because the export is not sorted chronologically.
  * A payment counts as collected only if its latest attempt is `success`.
  * Amounts are summed exactly, with Decimal, so no float drift sneaks in.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

DATA_FILE = "payments.jsonl"
EXPECTED_FILE = "expected.txt"


def parse_ts(value):
    """Return a sortable timestamp, or None if `value` is not a usable time."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_amount(value):
    """Return the amount as a Decimal, or None if it cannot be read.

    Amounts are usually JSON numbers, but some rows carry them as strings with
    thousands separators (for example "4,804.15"), so those are normalised too.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("\u20a6", "").replace("NGN", "").strip()
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    return None


def load_latest_attempts(path):
    """Read the export and keep only the latest attempt per `txn_id`."""
    latest = {}
    skipped_malformed = 0
    skipped_no_txn = 0

    with open(path, encoding="utf-8", errors="replace") as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():
                continue

            try:
                event = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                skipped_malformed += 1
                continue

            if not isinstance(event, dict):
                skipped_malformed += 1
                continue

            txn_id = event.get("txn_id")
            if not isinstance(txn_id, str) or not txn_id.strip():
                skipped_no_txn += 1
                continue

            ts = parse_ts(event.get("ts"))
            # An unreadable timestamp cannot establish that this attempt is the
            # latest one, so the event is dropped rather than guessed at.
            if ts is None:
                skipped_malformed += 1
                continue

            candidate = (ts, line_number, event)
            current = latest.get(txn_id)
            if current is None or candidate[:2] > current[:2]:
                latest[txn_id] = candidate

    return latest, skipped_malformed, skipped_no_txn


def main():
    latest, skipped_malformed, skipped_no_txn = load_latest_attempts(DATA_FILE)

    total = Decimal(0)
    count = 0
    skipped_amounts = 0

    for _ts, _line_number, event in latest.values():
        if event.get("status") != "success":
            continue

        amount = parse_amount(event.get("amount"))
        if amount is None:
            skipped_amounts += 1
            continue

        total += amount
        count += 1

    with open(EXPECTED_FILE, encoding="utf-8") as f:
        expected = int(f.read().strip())

    if skipped_malformed or skipped_no_txn or skipped_amounts:
        print(
            "Ignored {0} unreadable lines, {1} events without a txn_id and "
            "{2} events with an unreadable amount.".format(
                skipped_malformed, skipped_no_txn, skipped_amounts
            ),
            file=sys.stderr,
        )

    if count != expected:
        print(
            "Check failed: counted {0} successful payments, expected {1}.".format(
                count, expected
            )
        )
        print("Something in the data isn't being handled the way the README describes.")
        return 1

    print("Check passed: {0} successful payments.".format(count))
    print("Collected: NGN {0}".format(total))
    print("Your code: KOYA-{0}".format(int(total.to_integral_value(ROUND_HALF_UP))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
