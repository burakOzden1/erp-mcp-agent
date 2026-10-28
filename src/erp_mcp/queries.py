"""Pre-written, parameterized queries behind the MCP tools.

Every function takes an open (read-only) connection, validates its inputs and
returns a JSON-ready dict with a ``row_count`` key used by the audit log.
No function accepts SQL from the caller.
"""

from __future__ import annotations

import calendar
import difflib
import re
import sqlite3
from datetime import date, timedelta
from typing import Any, Literal

MAX_ROWS = 50

Metric = Literal["revenue", "top_products", "top_customers", "avg_order_value", "overdue_receivables"]
METRICS: tuple[str, ...] = Metric.__args__  # type: ignore[attr-defined]

# Amount paid per invoice, counting only payments received up to :as_of.
PAID_SUBQUERY = """
    SELECT invoice_id, SUM(amount) AS paid
    FROM payments
    WHERE payment_date <= :as_of
    GROUP BY invoice_id
"""


class LookupFailed(Exception):
    """An expected, user-facing failure (unknown customer, bad date, ...)."""


# --- Helpers -----------------------------------------------------------------------

def money(value: float | None) -> float:
    return round(value or 0.0, 2)


def get_as_of(con: sqlite3.Connection) -> date:
    """The reference date the demo data is anchored to ('today' for the data)."""
    row = con.execute("SELECT value FROM app_meta WHERE key = 'as_of_date'").fetchone()
    return date.fromisoformat(row[0])


def parse_date(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except (ValueError, AttributeError):
        raise LookupFailed(f"{name} must be a date in YYYY-MM-DD format, got {value!r}.") from None


def page(rows: list[dict[str, Any]], limit: int = MAX_ROWS) -> tuple[list[dict[str, Any]], bool]:
    return rows[:limit], len(rows) > limit


def resolve_customer(con: sqlite3.Connection, text: str) -> sqlite3.Row:
    """Find one customer by code (``C-0007``, ``c7``, ``7``) or (partial) name."""
    needle = (text or "").strip()
    if not needle:
        raise LookupFailed("Please provide a customer code (e.g. C-0007) or name.")

    if m := re.fullmatch(r"(?i)c?-?\s*0*(\d{1,4})", needle):
        row = con.execute("SELECT * FROM customers WHERE code = ?", (f"C-{int(m[1]):04d}",)).fetchone()
        if row:
            return row

    row = con.execute("SELECT * FROM customers WHERE lower(name) = lower(?)", (needle,)).fetchone()
    if row:
        return row

    matches = con.execute(
        "SELECT * FROM customers WHERE name LIKE ? ORDER BY name", (f"%{needle}%",)
    ).fetchall()
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        options = ", ".join(f"{r['name']} ({r['code']})" for r in matches[:10])
        raise LookupFailed(f"'{needle}' matches {len(matches)} customers: {options}. Please be more specific.")

    rows = con.execute("SELECT code, name FROM customers").fetchall()
    by_key = {r["name"].lower(): r for r in rows}
    by_key.update({r["name"].split()[0].lower(): r for r in rows})
    close = difflib.get_close_matches(needle.lower(), by_key, n=3, cutoff=0.6)
    hint = ""
    if close:
        unique = list(dict.fromkeys(f"{by_key[k]['name']} ({by_key[k]['code']})" for k in close))
        hint = f" Did you mean: {', '.join(unique)}?"
    raise LookupFailed(f"No customer found for '{needle}'.{hint}")


def customer_ref(row: sqlite3.Row) -> dict[str, str]:
    return {"code": row["code"], "name": row["name"]}


# --- get_stock -------------------------------------------------------------------------

def get_stock(
    con: sqlite3.Connection,
    query: str = "",
    category: str | None = None,
    below_reorder_only: bool = False,
) -> dict[str, Any]:
    as_of = get_as_of(con)
    categories = [r[0] for r in con.execute("SELECT DISTINCT category FROM products ORDER BY 1")]

    where, params = ["1 = 1"], {"as_of": as_of.isoformat(), "since": (as_of - timedelta(days=90)).isoformat()}
    if category:
        canonical = next((c for c in categories if c.lower() == category.strip().lower()), None)
        if canonical is None:
            raise LookupFailed(f"Unknown category '{category}'. Available: {', '.join(categories)}.")
        where.append("p.category = :category")
        params["category"] = canonical
    for i, token in enumerate((query or "").split()):
        where.append(f"(p.name || ' ' || p.sku || ' ' || p.category) LIKE :t{i}")
        params[f"t{i}"] = f"%{token}%"
    if below_reorder_only:
        where.append("p.stock_qty < p.reorder_level")

    rows = con.execute(
        f"""
        SELECT p.sku, p.name, p.category, p.unit, p.unit_price, p.stock_qty, p.reorder_level,
               COALESCE(s.qty, 0) AS sold_last_90_days
        FROM products p
        LEFT JOIN (
            SELECT l.product_id, SUM(l.qty) AS qty
            FROM order_lines l JOIN sales_orders o ON o.id = l.order_id
            WHERE o.status != 'cancelled' AND o.order_date > :since AND o.order_date <= :as_of
            GROUP BY l.product_id
        ) s ON s.product_id = p.id
        WHERE {' AND '.join(where)}
        ORDER BY (p.stock_qty < p.reorder_level) DESC,
                 CAST(p.stock_qty AS REAL) / MAX(p.reorder_level, 1),
                 p.sku
        """,
        params,
    ).fetchall()

    products = [
        {
            "sku": r["sku"],
            "name": r["name"],
            "category": r["category"],
            "unit": r["unit"],
            "unit_price": r["unit_price"],
            "stock_qty": r["stock_qty"],
            "reorder_level": r["reorder_level"],
            "below_reorder_level": r["stock_qty"] < r["reorder_level"],
            "shortfall_qty": max(r["reorder_level"] - r["stock_qty"], 0),
            "sold_last_90_days": r["sold_last_90_days"],
        }
        for r in rows
    ]
    shown, truncated = page(products)
    result: dict[str, Any] = {
        "as_of_date": as_of.isoformat(),
        "total_matches": len(products),
        "truncated": truncated,
        "row_count": len(shown),
        "products": shown,
    }
    if truncated:
        result["note"] = f"Showing first {MAX_ROWS} of {len(products)}. Narrow the search with query or category."
    if not products:
        result["note"] = f"No products matched. Categories: {', '.join(categories)}."
    return result


# --- get_order_status --------------------------------------------------------------------

def get_order_status(con: sqlite3.Connection, order_no: str) -> dict[str, Any]:
    as_of = get_as_of(con)
    m = re.search(r"(\d+)", order_no or "")
    if not m:
        raise LookupFailed(f"'{order_no}' is not a valid order number. Expected a format like SO-1042.")
    number = int(m[1])
    normalized = f"SO-{number}"

    order = con.execute(
        """
        SELECT o.*, c.code AS customer_code, c.name AS customer_name
        FROM sales_orders o JOIN customers c ON c.id = o.customer_id
        WHERE o.order_no = ?
        """,
        (normalized,),
    ).fetchone()
    if order is None:
        nearby = con.execute(
            "SELECT order_no FROM sales_orders "
            "ORDER BY ABS(CAST(substr(order_no, 4) AS INTEGER) - ?) LIMIT 3",
            (number,),
        ).fetchall()
        bounds = con.execute("SELECT MIN(order_no), MAX(order_no) FROM sales_orders").fetchone()
        raise LookupFailed(
            f"Order {normalized} not found. Orders range from {bounds[0]} to {bounds[1]}. "
            f"Closest existing: {', '.join(r[0] for r in nearby)}."
        )

    lines = [
        {
            "line_no": r["line_no"],
            "sku": r["sku"],
            "product": r["name"],
            "qty": r["qty"],
            "unit_price": r["unit_price"],
            "discount_pct": r["discount_pct"],
            "line_total": money(r["qty"] * r["unit_price"] * (1 - r["discount_pct"] / 100)),
        }
        for r in con.execute(
            """
            SELECT l.line_no, p.sku, p.name, l.qty, l.unit_price, l.discount_pct
            FROM order_lines l JOIN products p ON p.id = l.product_id
            WHERE l.order_id = ? ORDER BY l.line_no
            """,
            (order["id"],),
        )
    ]

    promised = date.fromisoformat(order["promised_date"])
    delivery: dict[str, Any] = {}
    if order["status"] in ("open", "shipped"):
        days_late = (as_of - promised).days
        delivery = {"is_late": days_late > 0, "days_late": max(days_late, 0)}
    elif order["status"] == "delivered":
        late_by = (date.fromisoformat(order["delivered_date"]) - promised).days
        delivery = {"delivered_on_time": late_by <= 0, "days_late_at_delivery": max(late_by, 0)}

    invoice = con.execute(
        f"""
        SELECT i.*, COALESCE(p.paid, 0) AS paid
        FROM invoices i LEFT JOIN ({PAID_SUBQUERY}) p ON p.invoice_id = i.id
        WHERE i.order_id = :order_id
        """,
        {"order_id": order["id"], "as_of": as_of.isoformat()},
    ).fetchone()
    invoice_info: dict[str, Any] | None = None
    if invoice:
        outstanding = money(invoice["total_amount"] - invoice["paid"])
        days_past_due = (as_of - date.fromisoformat(invoice["due_date"])).days
        invoice_info = {
            "invoice_no": invoice["invoice_no"],
            "invoice_date": invoice["invoice_date"],
            "due_date": invoice["due_date"],
            "total_amount": invoice["total_amount"],
            "paid_amount": money(invoice["paid"]),
            "outstanding_amount": outstanding,
            "payment_status": "paid" if outstanding <= 0 else ("partially_paid" if invoice["paid"] else "unpaid"),
            "is_overdue": outstanding > 0 and days_past_due > 0,
            "days_overdue": max(days_past_due, 0) if outstanding > 0 else 0,
            "payments": [
                dict(r)
                for r in con.execute(
                    "SELECT payment_date, amount, method FROM payments "
                    "WHERE invoice_id = ? AND payment_date <= ? ORDER BY payment_date",
                    (invoice["id"], as_of.isoformat()),
                )
            ],
        }

    return {
        "as_of_date": as_of.isoformat(),
        "order_no": order["order_no"],
        "status": order["status"],
        "customer": {"code": order["customer_code"], "name": order["customer_name"]},
        "order_date": order["order_date"],
        "promised_date": order["promised_date"],
        "shipped_date": order["shipped_date"],
        "delivered_date": order["delivered_date"],
        "delivery": delivery,
        "order_total": money(sum(line["line_total"] for line in lines)),
        "lines": lines,
        "invoice": invoice_info,
        "row_count": 1,
    }


# --- get_customer_balance ----------------------------------------------------------------

def get_customer_balance(con: sqlite3.Connection, customer: str) -> dict[str, Any]:
    as_of = get_as_of(con)
    c = resolve_customer(con, customer)
    params = {"cid": c["id"], "as_of": as_of.isoformat()}

    invoices = con.execute(
        f"""
        SELECT i.invoice_no, i.invoice_date, i.due_date, i.total_amount, COALESCE(p.paid, 0) AS paid
        FROM invoices i LEFT JOIN ({PAID_SUBQUERY}) p ON p.invoice_id = i.id
        WHERE i.customer_id = :cid AND i.invoice_date <= :as_of
        ORDER BY i.due_date
        """,
        params,
    ).fetchall()

    total_invoiced = sum(r["total_amount"] for r in invoices)
    total_paid = sum(r["paid"] for r in invoices)
    open_invoices, overdue_invoices = [], []
    for r in invoices:
        outstanding = money(r["total_amount"] - r["paid"])
        if outstanding <= 0:
            continue
        days_overdue = (as_of - date.fromisoformat(r["due_date"])).days
        item = {
            "invoice_no": r["invoice_no"],
            "invoice_date": r["invoice_date"],
            "due_date": r["due_date"],
            "total_amount": r["total_amount"],
            "paid_amount": money(r["paid"]),
            "outstanding_amount": outstanding,
        }
        open_invoices.append(item)
        if days_overdue > 0:
            overdue_invoices.append({**item, "days_overdue": days_overdue})

    open_balance = money(total_invoiced - total_paid)
    overdue_amount = money(sum(i["outstanding_amount"] for i in overdue_invoices))
    orders = con.execute(
        """
        SELECT
            SUM(status IN ('open', 'shipped')) AS open_orders,
            SUM(status IN ('open', 'shipped') AND promised_date < :as_of) AS overdue_orders
        FROM sales_orders WHERE customer_id = :cid
        """,
        params,
    ).fetchone()

    return {
        "as_of_date": as_of.isoformat(),
        "customer": {
            **customer_ref(c),
            "contact_name": c["contact_name"],
            "email": c["email"],
            "country": c["country"],
            "city": c["city"],
            "payment_terms_days": c["payment_terms_days"],
        },
        "currency": "USD",
        "credit_limit": c["credit_limit"],
        "total_invoiced": money(total_invoiced),
        "total_paid": money(total_paid),
        "open_balance": open_balance,
        "overdue_amount": overdue_amount,
        "available_credit": money(c["credit_limit"] - open_balance),
        "over_credit_limit": open_balance > c["credit_limit"],
        "open_invoice_count": len(open_invoices),
        "overdue_invoices": overdue_invoices,
        "open_orders": orders["open_orders"] or 0,
        "overdue_orders": orders["overdue_orders"] or 0,
        "row_count": 1,
    }


# --- list_overdue_orders -----------------------------------------------------------------

def list_overdue_orders(
    con: sqlite3.Connection,
    customer: str | None = None,
    min_days_late: int = 1,
) -> dict[str, Any]:
    as_of = get_as_of(con)
    params: dict[str, Any] = {"as_of": as_of.isoformat(), "min_days": max(int(min_days_late), 1)}
    customer_filter = ""
    resolved = None
    if customer:
        resolved = resolve_customer(con, customer)
        customer_filter = "AND o.customer_id = :cid"
        params["cid"] = resolved["id"]

    rows = con.execute(
        f"""
        SELECT o.order_no, o.status, o.order_date, o.promised_date, o.shipped_date,
               c.code, c.name,
               CAST(julianday(:as_of) - julianday(o.promised_date) AS INTEGER) AS days_late,
               (SELECT ROUND(SUM(ROUND(l.qty * l.unit_price * (1 - l.discount_pct / 100), 2)), 2)
                FROM order_lines l WHERE l.order_id = o.id) AS order_total
        FROM sales_orders o JOIN customers c ON c.id = o.customer_id
        WHERE o.status IN ('open', 'shipped')
          AND julianday(:as_of) - julianday(o.promised_date) >= :min_days
          {customer_filter}
        ORDER BY days_late DESC, o.order_no
        """,
        params,
    ).fetchall()

    orders = [
        {
            "order_no": r["order_no"],
            "customer": {"code": r["code"], "name": r["name"]},
            "status": r["status"],
            "order_date": r["order_date"],
            "promised_date": r["promised_date"],
            "shipped_date": r["shipped_date"],
            "days_late": r["days_late"],
            "order_total": r["order_total"],
        }
        for r in rows
    ]
    shown, truncated = page(orders)
    return {
        "as_of_date": as_of.isoformat(),
        "definition": "Promised date has passed and the order is not delivered (status open or shipped).",
        "filters": {
            "customer": customer_ref(resolved) if resolved else None,
            "min_days_late": params["min_days"],
        },
        "total_matches": len(orders),
        "total_value": money(sum(o["order_total"] or 0 for o in orders)),
        "truncated": truncated,
        "row_count": len(shown),
        "orders": shown,
    }


# --- get_kpi -----------------------------------------------------------------------------------

def previous_period(start: date, end: date) -> tuple[date, date]:
    """Previous calendar year/quarter/month when the period is one; else the same-length window before."""
    last_day = lambda d: d.replace(day=calendar.monthrange(d.year, d.month)[1])  # noqa: E731
    prev_end = start - timedelta(days=1)
    if start.day == 1:
        if start.month == 1 and end == date(start.year, 12, 31):
            return date(start.year - 1, 1, 1), prev_end
        if start.month in (1, 4, 7, 10) and end == last_day(date(start.year, start.month + 2, 1)):
            return date(prev_end.year, prev_end.month - 2, 1), prev_end
        if end == last_day(start):
            return prev_end.replace(day=1), prev_end
    return prev_end - (end - start), prev_end


def _scalar_kpi(con: sqlite3.Connection, metric: str, start: date, end: date) -> dict[str, Any]:
    row = con.execute(
        "SELECT COALESCE(SUM(total_amount), 0) AS revenue, COUNT(*) AS invoices "
        "FROM invoices WHERE invoice_date BETWEEN ? AND ?",
        (start.isoformat(), end.isoformat()),
    ).fetchone()
    if metric == "revenue":
        return {"value": money(row["revenue"]), "invoice_count": row["invoices"]}
    avg = row["revenue"] / row["invoices"] if row["invoices"] else 0.0
    return {"value": money(avg), "order_count": row["invoices"], "revenue": money(row["revenue"])}


def _top_products(con: sqlite3.Connection, start: date, end: date, limit: int | None) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT p.sku, p.name, p.category, SUM(l.qty) AS qty,
               ROUND(SUM(ROUND(l.qty * l.unit_price * (1 - l.discount_pct / 100), 2)), 2) AS revenue
        FROM invoices i
        JOIN order_lines l ON l.order_id = i.order_id
        JOIN products p ON p.id = l.product_id
        WHERE i.invoice_date BETWEEN ? AND ?
        GROUP BY p.id ORDER BY revenue DESC, p.sku
        """ + ("LIMIT ?" if limit else ""),
        (start.isoformat(), end.isoformat(), *([limit] if limit else [])),
    ).fetchall()
    return [{"key": r["sku"], "sku": r["sku"], "name": r["name"], "category": r["category"],
             "qty_sold": r["qty"], "revenue": r["revenue"]} for r in rows]


def _top_customers(con: sqlite3.Connection, start: date, end: date, limit: int | None) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT c.code, c.name, c.country, COUNT(*) AS invoices, ROUND(SUM(i.total_amount), 2) AS revenue
        FROM invoices i JOIN customers c ON c.id = i.customer_id
        WHERE i.invoice_date BETWEEN ? AND ?
        GROUP BY c.id ORDER BY revenue DESC, c.code
        """ + ("LIMIT ?" if limit else ""),
        (start.isoformat(), end.isoformat(), *([limit] if limit else [])),
    ).fetchall()
    return [{"key": r["code"], "code": r["code"], "name": r["name"], "country": r["country"],
             "invoice_count": r["invoices"], "revenue": r["revenue"]} for r in rows]


def _overdue_receivables(con: sqlite3.Connection, ref: date, limit: int) -> dict[str, Any]:
    rows = con.execute(
        f"""
        SELECT c.code, c.name, i.total_amount - COALESCE(p.paid, 0) AS outstanding,
               CAST(julianday(:as_of) - julianday(i.due_date) AS INTEGER) AS days_overdue
        FROM invoices i
        JOIN customers c ON c.id = i.customer_id
        LEFT JOIN ({PAID_SUBQUERY}) p ON p.invoice_id = i.id
        WHERE i.invoice_date <= :as_of AND i.due_date < :as_of
          AND i.total_amount - COALESCE(p.paid, 0) > 0.005
        """,
        {"as_of": ref.isoformat()},
    ).fetchall()
    buckets = {"1-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    per_customer: dict[str, dict[str, Any]] = {}
    for r in rows:
        d = r["days_overdue"]
        bucket = "1-30" if d <= 30 else "31-60" if d <= 60 else "61-90" if d <= 90 else "90+"
        buckets[bucket] += r["outstanding"]
        entry = per_customer.setdefault(r["code"], {"key": r["code"], "code": r["code"], "name": r["name"],
                                                    "overdue_amount": 0.0, "invoice_count": 0,
                                                    "oldest_days_overdue": 0})
        entry["overdue_amount"] += r["outstanding"]
        entry["invoice_count"] += 1
        entry["oldest_days_overdue"] = max(entry["oldest_days_overdue"], d)
    customers = sorted(per_customer.values(), key=lambda e: -e["overdue_amount"])
    for e in customers:
        e["overdue_amount"] = money(e["overdue_amount"])
    return {
        "value": money(sum(r["outstanding"] for r in rows)),
        "invoice_count": len(rows),
        "customer_count": len(customers),
        "aging_buckets_days": {k: money(v) for k, v in buckets.items()},
        "items": customers[:limit],
    }


def _change_pct(current: float, previous: float) -> float | None:
    return round((current - previous) / previous * 100, 1) if previous else None


def get_kpi(
    con: sqlite3.Connection,
    metric: str,
    period_start: str,
    period_end: str,
    compare_previous: bool = False,
    limit: int = 5,
) -> dict[str, Any]:
    if metric not in METRICS:
        raise LookupFailed(f"Unknown metric '{metric}'. Available: {', '.join(METRICS)}.")
    as_of = get_as_of(con)
    start, end = parse_date(period_start, "period_start"), parse_date(period_end, "period_end")
    if start > end:
        raise LookupFailed("period_start must be on or before period_end.")
    limit = min(max(int(limit), 1), 20)
    notes: list[str] = []
    effective_end = min(end, as_of)
    if end > as_of:
        notes.append(f"Data is available up to {as_of.isoformat()}; the period is counted up to that date.")
    if start > as_of:
        notes.append("The whole period is after the data date, so values are zero.")

    result: dict[str, Any] = {
        "metric": metric,
        "as_of_date": as_of.isoformat(),
        "currency": "USD",
        "period": {"start": start.isoformat(), "end": end.isoformat()},
    }
    prev_start, prev_end = previous_period(start, end)

    if metric in ("revenue", "avg_order_value"):
        result.update(_scalar_kpi(con, metric, start, effective_end))
        result["definition"] = ("Invoiced amount by invoice date." if metric == "revenue"
                                else "Invoiced revenue divided by number of invoiced orders.")
        row_count = 1
        if compare_previous:
            prev = _scalar_kpi(con, metric, prev_start, prev_end)
            result["previous_period"] = {"start": prev_start.isoformat(), "end": prev_end.isoformat(), **prev}
            result["change_pct"] = _change_pct(result["value"], prev["value"])
            if effective_end < end and start <= as_of:
                # Like-for-like: same number of elapsed days at the start of the previous period.
                elapsed = (effective_end - start).days
                same_end = min(prev_start + timedelta(days=elapsed), prev_end)
                same = _scalar_kpi(con, metric, prev_start, same_end)
                result["previous_period_to_date"] = {"start": prev_start.isoformat(),
                                                     "end": same_end.isoformat(), **same}
                result["change_pct_to_date"] = _change_pct(result["value"], same["value"])
                notes.append("The current period is partial. Use change_pct_to_date for a like-for-like comparison.")
            row_count = 2

    elif metric in ("top_products", "top_customers"):
        fetch = _top_products if metric == "top_products" else _top_customers
        items = fetch(con, start, effective_end, limit)
        result["definition"] = "Ranked by invoiced net revenue (after line discounts) in the period."
        if compare_previous:
            previous = {i["key"]: i for i in fetch(con, prev_start, prev_end, None)}
            ranks = {k: n for n, k in enumerate(previous, start=1)}
            result["previous_period"] = {"start": prev_start.isoformat(), "end": prev_end.isoformat()}
            for item in items:
                prev_item = previous.get(item["key"])
                item["previous_revenue"] = prev_item["revenue"] if prev_item else 0.0
                item["previous_rank"] = ranks.get(item["key"])
                item["change_pct"] = _change_pct(item["revenue"], item["previous_revenue"])
        result["items"] = [{k: v for k, v in i.items() if k != "key"} for i in items]
        row_count = len(items)

    else:  # overdue_receivables
        ref = effective_end
        notes.append(f"Snapshot of unpaid invoices past due on {ref.isoformat()}; period_start is not used.")
        snap = _overdue_receivables(con, ref, limit)
        result["definition"] = "Outstanding amount of invoices whose due date has passed."
        result["snapshot_date"] = ref.isoformat()
        result.update({k: v for k, v in snap.items() if k != "items"})
        result["top_customers"] = [{k: v for k, v in i.items() if k != "key"} for i in snap["items"]]
        if compare_previous:
            prev_ref = min(prev_end, as_of)
            prev = _overdue_receivables(con, prev_ref, limit)
            result["previous_snapshot"] = {"snapshot_date": prev_ref.isoformat(), "value": prev["value"],
                                           "invoice_count": prev["invoice_count"]}
            result["change_pct"] = _change_pct(result["value"], prev["value"])
        row_count = snap["invoice_count"]

    if notes:
        result["notes"] = notes
    result["row_count"] = row_count
    return result
