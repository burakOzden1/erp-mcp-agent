"""End-to-end tests through the MCP protocol (in-process client) and the audit log."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from mcp import Client

from erp_mcp.server import mcp

EXPECTED_TOOLS = {"get_stock", "get_order_status", "get_customer_balance", "list_overdue_orders", "get_kpi"}


def call(name: str, args: dict[str, Any]) -> Any:
    async def run() -> Any:
        async with Client(mcp) as client:
            return await client.call_tool(name, args)
    return asyncio.run(run())


def read_log(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_lists_five_read_only_tools() -> None:
    async def run() -> Any:
        async with Client(mcp) as client:
            return (await client.list_tools()).tools
    tools = asyncio.run(run())
    assert {t.name for t in tools} == EXPECTED_TOOLS
    for tool in tools:
        assert tool.description and len(tool.description) > 50
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False


def test_no_tool_accepts_raw_sql() -> None:
    async def run() -> Any:
        async with Client(mcp) as client:
            return (await client.list_tools()).tools
    for tool in asyncio.run(run()):
        assert not {"sql", "query_sql", "statement"} & set(tool.input_schema["properties"])


def test_successful_call_is_audited(erp_env: Path) -> None:
    result = call("list_overdue_orders", {"min_days_late": 5})
    assert not result.is_error
    assert result.structured_content["total_matches"] > 0

    [record] = read_log(erp_env)
    assert record["tool"] == "list_overdue_orders"
    assert record["params"] == {"customer": None, "min_days_late": 5}
    assert record["row_count"] == result.structured_content["row_count"]
    assert record["status"] == "ok"
    assert record["duration_ms"] >= 0 and record["ts"]


def test_failed_lookup_returns_helpful_error_and_is_audited(erp_env: Path) -> None:
    result = call("get_customer_balance", {"customer": "Oakhust"})
    assert result.is_error
    assert "Did you mean: Oakhurst" in result.content[0].text

    [record] = read_log(erp_env)
    assert record["status"] == "error" and "Oakhurst" in record["error"]


def test_invalid_metric_is_rejected_by_schema(erp_env: Path) -> None:
    result = call("get_kpi", {"metric": "DROP TABLE invoices", "period_start": "2026-01-01",
                              "period_end": "2026-01-31"})
    assert result.is_error


def test_each_tool_answers_over_protocol(erp_env: Path) -> None:
    calls = {
        "get_stock": {"below_reorder_only": True},
        "get_order_status": {"order_no": "SO-1042"},
        "get_customer_balance": {"customer": "C-0034"},
        "list_overdue_orders": {},
        "get_kpi": {"metric": "revenue", "period_start": "2026-07-01", "period_end": "2026-09-30",
                    "compare_previous": True},
    }
    for name, args in calls.items():
        result = call(name, args)
        assert not result.is_error, (name, result.content)
        assert result.structured_content["as_of_date"] == "2026-10-31"
    assert [r["tool"] for r in read_log(erp_env)] == list(calls)
