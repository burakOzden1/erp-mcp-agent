"""Tests for the query layer, one group per tool (default seed, as_of 2026-10-31)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from erp_mcp import queries
from erp_mcp.db import connect_readonly


@pytest.fixture
def con(demo_db: Path) -> Iterator[sqlite3.Connection]:
    connection = connect_readonly(demo_db)
    yield connection
    connection.close()


# --- read-only guarantee -----------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "DELETE FROM customers",
    "UPDATE products SET stock_qty = 0",
    "INSERT INTO app_meta VALUES ('x', 'y')",
    "DROP TABLE payments",
])
def test_connection_rejects_writes(con: sqlite3.Connection, sql: str) -> None:
    with pytest.raises(sqlite3.OperationalError):
        con.execute(sql)


def test_missing_database_gives_clear_message(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="seed_db.py"):
        connect_readonly(tmp_path / "nope.db")


# --- get_stock -------------------------------------------------------------------------

def test_stock_below_reorder(con: sqlite3.Connection) -> None:
    result = queries.get_stock(con, below_reorder_only=True)
    assert result["total_matches"] == 9
    assert all(p["below_reorder_level"] and p["shortfall_qty"] > 0 for p in result["products"])


def test_stock_search_matches_all_words(con: sqlite3.Connection) -> None:
    result = queries.get_stock(con, query="drill 18v")
    assert result["products"]
    assert all("Drill" in p["name"] and "18V" in p["name"] for p in result["products"])


def test_stock_caps_rows(con: sqlite3.Connection) -> None:
    result = queries.get_stock(con)
    assert result["total_matches"] == 120
    assert result["row_count"] == queries.MAX_ROWS and result["truncated"]


def test_stock_unknown_category_lists_options(con: sqlite3.Connection) -> None:
    with pytest.raises(queries.LookupFailed, match="Power Tools"):
        queries.get_stock(con, category="Garden")


# --- get_order_status -----------------------------------------------------------------

def test_order_status_with_invoice(con: sqlite3.Connection) -> None:
    result = queries.get_order_status(con, "so-1042")
    assert result["order_no"] == "SO-1042"
    assert result["status"] == "delivered"
    assert result["lines"]
    assert result["invoice"]["total_amount"] == result["order_total"]


def test_order_status_overdue_order_is_late(con: sqlite3.Connection) -> None:
    late = queries.list_overdue_orders(con)["orders"][0]
    result = queries.get_order_status(con, late["order_no"])
    assert result["delivery"] == {"is_late": True, "days_late": late["days_late"]}


def test_order_status_not_found_suggests_nearby(con: sqlite3.Connection) -> None:
    with pytest.raises(queries.LookupFailed, match="SO-1600"):
        queries.get_order_status(con, "SO-9999")


# --- get_customer_balance -----------------------------------------------------------------

def test_balance_over_credit_limit(con: sqlite3.Connection) -> None:
    result = queries.get_customer_balance(con, "C-0007")
    assert result["over_credit_limit"]
    assert result["open_balance"] == pytest.approx(result["total_invoiced"] - result["total_paid"], abs=0.01)
    assert result["overdue_amount"] == pytest.approx(
        sum(i["outstanding_amount"] for i in result["overdue_invoices"]), abs=0.01)


@pytest.mark.parametrize("text", ["C-0007", "c7", "7", "oakhurst", "Oakhurst Facilities Group"])
def test_customer_lookup_variants(con: sqlite3.Connection, text: str) -> None:
    assert queries.get_customer_balance(con, text)["customer"]["code"] == "C-0007"


def test_customer_typo_suggests_close_match(con: sqlite3.Connection) -> None:
    with pytest.raises(queries.LookupFailed, match="Did you mean: Oakhurst"):
        queries.get_customer_balance(con, "Oakhust")


def test_ambiguous_customer_asks_to_be_specific(con: sqlite3.Connection) -> None:
    with pytest.raises(queries.LookupFailed, match="more specific"):
        queries.get_customer_balance(con, "Trading")


# --- list_overdue_orders ---------------------------------------------------------------------

def test_overdue_orders(con: sqlite3.Connection) -> None:
    result = queries.list_overdue_orders(con)
    assert result["total_matches"] == 12
    days = [o["days_late"] for o in result["orders"]]
    assert days == sorted(days, reverse=True) and min(days) >= 1


def test_overdue_orders_filters(con: sqlite3.Connection) -> None:
    all_late = queries.list_overdue_orders(con)["orders"]
    assert len(queries.list_overdue_orders(con, min_days_late=20)["orders"]) == sum(
        o["days_late"] >= 20 for o in all_late)
    code = all_late[0]["customer"]["code"]
    filtered = queries.list_overdue_orders(con, customer=code)["orders"]
    assert filtered and all(o["customer"]["code"] == code for o in filtered)


# --- get_kpi ---------------------------------------------------------------------------------

def test_kpi_revenue_months_add_up_to_year(con: sqlite3.Connection) -> None:
    year = queries.get_kpi(con, "revenue", "2025-11-01", "2026-10-31")["value"]
    month_starts = [date(2025, 11, 1), date(2025, 12, 1)] + [date(2026, m, 1) for m in range(1, 11)]
    month_ends = [queries.previous_period(s, s)[1] for s in month_starts[1:]] + [date(2026, 10, 31)]
    months = sum(
        queries.get_kpi(con, "revenue", s.isoformat(), e.isoformat())["value"]
        for s, e in zip(month_starts, month_ends, strict=True)
    )
    total = con.execute("SELECT ROUND(SUM(total_amount), 2) FROM invoices").fetchone()[0]
    assert year == total
    assert months == pytest.approx(year, abs=0.05)


def test_kpi_partial_quarter_has_like_for_like(con: sqlite3.Connection) -> None:
    result = queries.get_kpi(con, "revenue", "2026-10-01", "2026-12-31", compare_previous=True)
    assert result["previous_period"]["start"] == "2026-07-01"
    assert result["previous_period"]["end"] == "2026-09-30"
    assert result["previous_period_to_date"]["end"] == "2026-07-31"
    assert result["change_pct_to_date"] is not None


@pytest.mark.parametrize(("start", "end", "prev"), [
    ("2026-09-01", "2026-09-30", ("2026-08-01", "2026-08-31")),
    ("2026-04-01", "2026-06-30", ("2026-01-01", "2026-03-31")),
    ("2026-01-01", "2026-12-31", ("2025-01-01", "2025-12-31")),
    ("2026-10-19", "2026-10-25", ("2026-10-12", "2026-10-18")),
])
def test_previous_period(start: str, end: str, prev: tuple[str, str]) -> None:
    got = queries.previous_period(date.fromisoformat(start), date.fromisoformat(end))
    assert tuple(d.isoformat() for d in got) == prev


def test_kpi_top_lists(con: sqlite3.Connection) -> None:
    products = queries.get_kpi(con, "top_products", "2026-07-01", "2026-09-30", limit=5)["items"]
    customers = queries.get_kpi(con, "top_customers", "2026-07-01", "2026-09-30", limit=3)["items"]
    assert len(products) == 5 and len(customers) == 3
    revenues = [p["revenue"] for p in products]
    assert revenues == sorted(revenues, reverse=True)


def test_kpi_avg_order_value(con: sqlite3.Connection) -> None:
    result = queries.get_kpi(con, "avg_order_value", "2026-09-01", "2026-09-30")
    assert result["value"] == pytest.approx(result["revenue"] / result["order_count"], abs=0.01)


def test_kpi_overdue_receivables(con: sqlite3.Connection) -> None:
    result = queries.get_kpi(con, "overdue_receivables", "2026-10-01", "2026-10-31")
    assert result["customer_count"] == 6
    assert result["value"] == pytest.approx(sum(result["aging_buckets_days"].values()), abs=0.01)


@pytest.mark.parametrize(("args", "message"), [
    (("profit", "2026-01-01", "2026-01-31"), "Unknown metric"),
    (("revenue", "2026-13-01", "2026-01-31"), "YYYY-MM-DD"),
    (("revenue", "2026-02-01", "2026-01-31"), "on or before"),
])
def test_kpi_rejects_bad_input(con: sqlite3.Connection, args: tuple[str, str, str], message: str) -> None:
    with pytest.raises(queries.LookupFailed, match=message):
        queries.get_kpi(con, *args)
