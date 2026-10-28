"""MCP server exposing read-only ERP tools to Claude.

Run with ``erp-mcp`` (stdio transport) or ``python -m erp_mcp.server``.
"""

import sqlite3
import time
from collections.abc import Callable
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from erp_mcp import __version__, audit, queries
from erp_mcp.db import connect_readonly

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


def _data_date() -> str:
    try:
        con = connect_readonly()
        try:
            return queries.get_as_of(con).isoformat()
        finally:
            con.close()
    except Exception:  # database not created yet; tools will report it clearly
        return "unknown"


INSTRUCTIONS = f"""\
Read-only access to a demo ERP (wholesale industrial supplies, USD).
Data is current as of {_data_date()}: treat that date as "today" for relative periods
such as "this week", "this month" or "this quarter".
Tools never modify data. Prefer get_kpi for totals and rankings, and quote order
numbers (SO-xxxx), customer codes (C-xxxx) and invoice numbers in answers.
"""

mcp = MCPServer("erp-demo", version=__version__, instructions=INSTRUCTIONS)


def _run(tool: str, params: dict[str, Any], fn: Callable[[sqlite3.Connection], dict[str, Any]]) -> dict[str, Any]:
    """Execute a query on a fresh read-only connection and write the audit record."""
    started = time.perf_counter()

    def elapsed() -> float:
        return (time.perf_counter() - started) * 1000

    try:
        con = connect_readonly()
        try:
            result = fn(con)
        finally:
            con.close()
    except (queries.LookupFailed, FileNotFoundError) as exc:
        audit.log_call(tool, params, row_count=0, duration_ms=elapsed(), status="error", error=str(exc))
        raise ToolError(str(exc)) from None
    except Exception as exc:
        audit.log_call(tool, params, row_count=0, duration_ms=elapsed(), status="error",
                       error=type(exc).__name__)
        raise
    audit.log_call(tool, params, row_count=result.get("row_count", 0), duration_ms=elapsed())
    return result


@mcp.tool(title="Stock lookup", annotations=READ_ONLY)
def get_stock(
    query: Annotated[str, Field(description=(
        "Words to match in product name, SKU or category, e.g. 'drill 18V' or 'PT-0004'. "
        "Empty = all products."))] = "",
    category: Annotated[str | None, Field(description="Exact category filter, e.g. 'Power Tools'.")] = None,
    below_reorder_only: Annotated[bool, Field(
        description="Only products whose stock is below their reorder level.")] = False,
) -> dict[str, Any]:
    """Look up product stock levels.

    Use for questions like "How many cordless drills do we have?", "Which products
    are below reorder level?" or "Show stock for Safety Equipment". Returns stock
    quantity, reorder level, shortfall and units sold in the last 90 days.
    Results are sorted with the most critical stock first (max 50 rows).
    """
    params = {"query": query, "category": category, "below_reorder_only": below_reorder_only}
    return _run("get_stock", params, lambda con: queries.get_stock(con, **params))


@mcp.tool(title="Order status", annotations=READ_ONLY)
def get_order_status(
    order_no: Annotated[str, Field(description="Sales order number, e.g. 'SO-1042' (also accepts '1042').")],
) -> dict[str, Any]:
    """Get the full status of one sales order.

    Use for "What's the status of order SO-1042?" or "Has SO-1509 been invoiced
    or paid?". Returns header (customer, dates, status, lateness), order lines,
    and the invoice with payments and outstanding amount.
    """
    return _run("get_order_status", {"order_no": order_no},
                lambda con: queries.get_order_status(con, order_no))


@mcp.tool(title="Customer balance", annotations=READ_ONLY)
def get_customer_balance(
    customer: Annotated[str, Field(
        description="Customer code (e.g. 'C-0007') or name, full or partial (e.g. 'Oakhurst').")],
) -> dict[str, Any]:
    """Get a customer's account balance (accounts receivable).

    Use for "What is Oakhurst's open balance?", "Is C-0034 over its credit limit?"
    or before drafting a payment reminder. Returns contact details, credit limit,
    invoiced, paid, open and overdue amounts, each overdue invoice with days
    overdue, and counts of open/overdue orders.
    """
    return _run("get_customer_balance", {"customer": customer},
                lambda con: queries.get_customer_balance(con, customer))


@mcp.tool(title="Overdue orders", annotations=READ_ONLY)
def list_overdue_orders(
    customer: Annotated[str | None, Field(description="Optional customer code or name to filter by.")] = None,
    min_days_late: Annotated[int, Field(
        ge=1, description="Only orders at least this many days past the promised date.")] = 1,
) -> dict[str, Any]:
    """List sales orders that are late: promised date passed but not yet delivered.

    Use for "Which orders are late?", "Show orders more than 14 days late" or
    "Does Foxglove have any delayed orders?". Sorted by days late, max 50 rows,
    with total value of the late orders.
    """
    params = {"customer": customer, "min_days_late": min_days_late}
    return _run("list_overdue_orders", params, lambda con: queries.list_overdue_orders(con, **params))


@mcp.tool(title="Business KPIs", annotations=READ_ONLY)
def get_kpi(
    metric: Annotated[queries.Metric, Field(description=(
        "revenue = invoiced sales; top_products / top_customers = ranking by revenue; "
        "avg_order_value = revenue per invoiced order; overdue_receivables = unpaid past-due "
        "invoices as of period_end, with aging buckets."))],
    period_start: Annotated[str, Field(description="First day of the period, YYYY-MM-DD.")],
    period_end: Annotated[str, Field(description="Last day of the period, YYYY-MM-DD (inclusive).")],
    compare_previous: Annotated[bool, Field(description=(
        "Also return the previous period and % change. Calendar months, quarters and years "
        "compare with the previous calendar month/quarter/year; "
        "other ranges with the same-length window before."))] = False,
    limit: Annotated[int, Field(ge=1, le=20, description="Number of items for top_* metrics.")] = 5,
) -> dict[str, Any]:
    """Calculate a business KPI for a date range from a fixed list of metrics.

    Use for "How did revenue this quarter compare to last quarter?", "Top 5
    products last month", "Average order value in 2026" or "How much is overdue?".
    Example: metric='revenue', period_start='2026-10-01', period_end='2026-12-31',
    compare_previous=true. Partial periods include a like-for-like comparison.
    """
    params = {"metric": metric, "period_start": period_start, "period_end": period_end,
              "compare_previous": compare_previous, "limit": limit}
    return _run("get_kpi", params, lambda con: queries.get_kpi(con, **params))


def main() -> None:
    """Entry point: serve over stdio (the transport Claude Desktop uses)."""
    mcp.run()


if __name__ == "__main__":
    main()
