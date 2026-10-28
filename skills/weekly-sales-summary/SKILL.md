---
name: weekly-sales-summary
description: Prepares a one-page weekly sales summary for a manager from live ERP data - revenue vs the previous week, top 5 products, stock at risk, late orders, overdue receivables and three action items. Use when the user asks for a weekly sales summary, weekly report, sales recap, "how did we do this week" or a Monday management update. Requires the erp-demo MCP tools (get_kpi, get_stock, list_overdue_orders).
---

# Weekly Sales Summary

Produce a one-page management summary from the ERP tools. Every number must come
from a tool result in this conversation; never estimate or invent figures.

## Workflow

Copy this checklist and tick it off as you go:

```
- [ ] 1. Find the data date and late orders
- [ ] 2. Revenue this week vs previous week
- [ ] 3. Top 5 products
- [ ] 4. Stock at risk
- [ ] 5. Overdue receivables
- [ ] 6. Write the summary
```

**1. Data date and late orders.** Call `list_overdue_orders` with no arguments.
Take `as_of_date` from the result: this is "today" for the data.
The week is the 7 days ending on `as_of_date` (`week_start` = as_of_date - 6 days).
If the user names a specific week, use those dates instead.

**2. Revenue.** Call `get_kpi` with `metric="revenue"`, `period_start=week_start`,
`period_end=as_of_date`, `compare_previous=true`.

**3. Top products.** Call `get_kpi` with `metric="top_products"`, the same period,
`compare_previous=true`, `limit=5`. An item with `previous_rank: null` was not sold
in the previous week: label it "new".

**4. Stock at risk.** Call `get_stock` with `below_reorder_only=true`. Rank by
urgency: zero stock first, then the highest `sold_last_90_days` (fast movers run out first).

**5. Overdue receivables.** Call `get_kpi` with `metric="overdue_receivables"`,
the same period, `compare_previous=true`.

**6. Write the summary** using the template below.

If a tool call fails, keep going and write "Data unavailable" in that section.

## Output template

Keep it to one page. Use USD with thousands separators (`$33,506`), percentages
with one decimal and an arrow (▲ 4.0% / ▼ 4.0% / ● 0.0%).

```markdown
# Weekly Sales Summary
**Week:** {week_start} – {as_of_date} · **Data as of:** {as_of_date}

## Headline
{Two sentences: the most important change this week and the biggest risk.}

## Revenue
| | This week | Previous week | Change |
|---|---|---|---|
| Revenue | $… | $… | ▲/▼ …% |
| Invoices | … | … | |
| Avg. invoice | $… | $… | |

## Top 5 Products
| # | Product (SKU) | Units | Revenue | vs prev. week |
|---|---|---|---|---|

## Stock at Risk
{n} products are below reorder level. Most urgent (max 5):
| Product (SKU) | In stock | Reorder level | Sold last 90 days |
|---|---|---|---|

## Late Orders
{n} orders worth $… are past their promised date. Most late (max 5):
| Order | Customer | Days late | Status | Value |
|---|---|---|---|---|

## Overdue Receivables
$… overdue across {n} customers ({change vs previous week}).
Aging: 1–30 days $… · 31–60 $… · 61–90 $… · 90+ $…
Largest: {customer (code) $…}, {…}, {…}

## This Week's Actions
1. {Specific action with owner area, e.g. "Purchasing: reorder SE-0012 Safety Glasses Economy (0 in stock, 253 sold in 90 days)."}
2. {…}
3. {…}
```

## Writing the actions

Pick the three items with the biggest business impact, one line each, naming the
exact SKU, order number or customer code. Good sources, in order:
out-of-stock fast movers → orders late more than 14 days → customers over their
credit limit or with the oldest overdue invoices → a notable revenue swing.

Avoid generic advice ("monitor sales", "improve collections").
