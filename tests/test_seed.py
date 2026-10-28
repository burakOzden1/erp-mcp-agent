"""Tests for the demo database generator."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import seed_db

TABLES = ["customers", "products", "sales_orders", "order_lines", "invoices", "payments"]


def dump(path: Path) -> list[tuple]:
    con = sqlite3.connect(path)
    try:
        return [row for t in ["app_meta", *TABLES] for row in con.execute(f"SELECT * FROM {t} ORDER BY 1")]
    finally:
        con.close()


def test_row_counts(demo_db: Path) -> None:
    summary = seed_db.summarize(demo_db)
    assert summary["customers"] == 40
    assert summary["products"] == 120
    assert summary["sales_orders"] == 600


def test_planted_situations(demo_db: Path) -> None:
    summary = seed_db.summarize(demo_db)
    assert 8 <= summary["products_below_reorder_level"] <= 10
    assert 10 <= summary["overdue_orders (promised date passed, not delivered)"] <= 15
    assert 5 <= summary["customers_with_overdue_partially_paid_invoices"] <= 6
    assert summary["customers_over_credit_limit"] == 2


def test_same_seed_gives_identical_data(demo_db: Path, tmp_path: Path) -> None:
    other = tmp_path / "again.db"
    seed_db.build_database(other)
    assert dump(other) == dump(demo_db)


def test_other_as_of_date_keeps_planted_situations(tmp_path: Path) -> None:
    path = tmp_path / "shifted.db"
    seed_db.build_database(path, as_of=date(2027, 3, 15), seed=7)
    summary = seed_db.summarize(path)
    assert summary["customers_over_credit_limit"] == 2
    assert summary["overdue_orders (promised date passed, not delivered)"] == seed_db.NUM_OVERDUE_ORDERS


def test_data_integrity(demo_db: Path) -> None:
    con = sqlite3.connect(demo_db)
    as_of = con.execute("SELECT value FROM app_meta WHERE key = 'as_of_date'").fetchone()[0]
    checks = {
        "shipped before ordered": "SELECT COUNT(*) FROM sales_orders WHERE shipped_date < order_date",
        "delivered before shipped": "SELECT COUNT(*) FROM sales_orders WHERE delivered_date < shipped_date",
        "dates after as_of": """SELECT COUNT(*) FROM sales_orders WHERE order_date > :as_of
                                OR shipped_date > :as_of OR delivered_date > :as_of""",
        "payment outside invoice..as_of": """SELECT COUNT(*) FROM payments p JOIN invoices i ON i.id = p.invoice_id
                                WHERE p.payment_date < i.invoice_date OR p.payment_date > :as_of""",
        "overpaid invoices": """SELECT COUNT(*) FROM (SELECT i.id FROM invoices i JOIN payments p
                                ON p.invoice_id = i.id GROUP BY i.id HAVING SUM(p.amount) > i.total_amount + 0.005)""",
        "invoice total != order lines": """SELECT COUNT(*) FROM invoices i JOIN (
                                SELECT order_id, SUM(ROUND(qty * unit_price * (1 - discount_pct / 100), 2)) AS t
                                FROM order_lines GROUP BY order_id) o ON o.order_id = i.order_id
                                WHERE ABS(i.total_amount - o.t) > 0.01""",
        "unbilled shipped/delivered orders": """SELECT COUNT(*) FROM sales_orders o
                                WHERE status IN ('shipped', 'delivered')
                                AND NOT EXISTS (SELECT 1 FROM invoices i WHERE i.order_id = o.id)""",
    }
    try:
        failures = {name: n for name, sql in checks.items()
                    if (n := con.execute(sql, {"as_of": as_of}).fetchone()[0])}
    finally:
        con.close()
    assert failures == {}
