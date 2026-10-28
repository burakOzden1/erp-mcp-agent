# Sample Skill Outputs

Produced by following each `SKILL.md` step by step against the demo database
(default seed, data as of 2026-10-31). All figures come from the MCP tool results.

---

## 1. `weekly-sales-summary` — "Prepare this week's sales summary."

Tool calls: `list_overdue_orders` → `get_kpi(revenue)` → `get_kpi(top_products)` →
`get_stock(below_reorder_only)` → `get_kpi(overdue_receivables)`

# Weekly Sales Summary
**Week:** 2026-10-25 – 2026-10-31 · **Data as of:** 2026-10-31

## Headline
Revenue dipped 4.0% to $33,506 while overdue receivables improved by 5.8%.
The biggest risk is stock: two fast-selling safety glasses lines are almost out, and 12 orders worth $16,011 are past their promised date.

## Revenue
| | This week | Previous week | Change |
|---|---|---|---|
| Revenue | $33,506 | $34,899 | ▼ 4.0% |
| Invoices | 17 | 19 | |
| Avg. invoice | $1,971 | $1,837 | ▲ 7.3% |

## Top 5 Products
| # | Product (SKU) | Units | Revenue | vs prev. week |
|---|---|---|---|---|
| 1 | Wood Screw M12 (FS-0020) | 201 | $2,980 | new |
| 2 | LED Panel 60x60 IP65 (EL-0018) | 50 | $2,758 | ▲ 8.7% |
| 3 | Claw Hammer Compact (HT-0018) | 149 | $2,128 | new |
| 4 | Installation Cable 100m 16A (EL-0001) | 18 | $1,962 | ▲ 63.6% |
| 5 | Void Fill Paper Medium (PK-0012) | 54 | $1,926 | ● 0.0% |

## Stock at Risk
9 products are below reorder level. Most urgent:
| Product (SKU) | In stock | Reorder level | Sold last 90 days |
|---|---|---|---|
| Safety Glasses Economy (SE-0012) | 0 | 75 | 253 |
| Safety Glasses Premium (SE-0003) | 3 | 25 | 1,380 |
| Packing Tape Large (PK-0003) | 13 | 20 | 272 |
| Void Fill Paper Medium (PK-0012) | 9 | 40 | 253 |
| Li-ion Battery Pack 20V (PT-0009) | 5 | 15 | 59 |

## Late Orders
12 orders worth $16,011 are past their promised date. Most late:
| Order | Customer | Days late | Status | Value |
|---|---|---|---|---|
| SO-1509 | Greystone Manufacturing Inc. (C-0027) | 40 | open | $747 |
| SO-1522 | Fairhaven Construction Ltd. (C-0004) | 31 | open | $759 |
| SO-1520 | Stonegate Trading Co. (C-0001) | 24 | open | $552 |
| SO-1539 | Copperfield Building Services (C-0033) | 17 | open | $2,240 |
| SO-1537 | Ashford Building Services (C-0028) | 16 | shipped | $4,550 |

## Overdue Receivables
$26,600 overdue across 6 customers (▼ 5.8% vs $28,244 a week earlier).
Aging: 1–30 days $18,379 · 31–60 $6,355 · 61–90 $1,866 · 90+ $0
Largest: Larkspur Building Services (C-0009) $5,911, Starling Industrial Supply (C-0010) $5,896 (oldest 87 days), Oakhurst Facilities Group (C-0007) $5,877

## This Week's Actions
1. **Purchasing:** reorder SE-0012 Safety Glasses Economy (0 in stock, 253 sold in 90 days) and SE-0003 Safety Glasses Premium (3 in stock, 1,380 sold).
2. **Operations:** ship SO-1509 (40 days late) and SO-1522 (31 days late); Stonegate (C-0001) has three late orders and needs a status call.
3. **Finance:** chase Starling (C-0010, invoice 87 days overdue) and Oakhurst (C-0007, over its credit limit).

---

## 2. `customer-email-draft` — "Draft a payment reminder email for Foxglove."

Tool calls: `get_customer_balance("Foxglove")` → `list_overdue_orders(customer="C-0034")`
Result: 2 overdue, partially paid invoices; no late orders → payment reminder.
Oldest invoice is 33 days overdue → "polite but clear" tone.

**DRAFT – not sent. Please review before sending.**

**To:** Daniel Fenwick <daniel.fenwick@foxglove.example.com>
**Subject:** Payment reminder: 2 overdue invoices ($4,827.85)

Dear Daniel,

Thank you for the partial payments you have made on the invoices below. According to our records, the following balances are now past due:

- INV-10461, due 28 September 2026: $1,478.72 outstanding
- INV-10487, due 18 October 2026: $3,349.13 outstanding

The total overdue amount is $4,827.85. Could you please arrange payment, or let us know the date we can expect it? Our payment details are: [payment details].

If payment is already on its way, please disregard this reminder, and thank you. If you have any questions about either invoice, I will be happy to help.

Kind regards,
[Your name]
[Your company]

---
**Review notes (internal, do not send)**
| Fact | Value |
|---|---|
| Customer | Foxglove Manufacturing Inc. (C-0034), Bristol, United Kingdom |
| Payment terms | 30 days |
| Open balance / credit limit | $10,639.70 / $8,000.00 ⚠️ over limit by $2,639.70 |
| Overdue amount | $4,827.85 across 2 invoices, oldest 33 days |
| Late orders | 0 |
| Data as of | 2026-10-31 |

Before sending: confirm no payment arrived after the data date, fill the placeholders,
and decide whether to mention the credit limit.
