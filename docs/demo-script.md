# Demo Video Script (≈ 2 minutes)

Goal: show a client, in two minutes, that Claude can answer real ERP questions,
automate office work with Skills, and do it safely (read-only, audited).

## Before recording

- [ ] Fresh data: `python scripts/seed_db.py` (default seed, data as of 2026-10-31,
      so answers match the README).
- [ ] Clear the log so only demo calls appear: delete `logs/audit.jsonl`.
- [ ] Claude Desktop: `erp-demo` server connected, both Skills uploaded and enabled.
      Other MCP servers and Skills disabled so the tool list is clean.
- [ ] Do a full rehearsal in a separate chat and pre-approve tool permissions
      ("Always allow"), so no permission pop-ups appear on camera.
- [ ] New chat, window at 1920×1080, font zoom ~125%. A terminal open in the project
      folder, ready for the last scene.
- [ ] Keep questions in a text file and paste them, so there are no typos on camera.

## Scenes

| # | Time | On screen | Say (voice-over) |
|---|---|---|---|
| 0 | 0:00–0:10 | Claude Desktop, tools icon open showing the 5 `erp-demo` tools | "This is Claude connected to an ERP database through a read-only MCP server I built. Five tools, no free SQL." |
| 1 | 0:10–0:25 | **"Which products are below reorder level?"** | "Stock first. It finds 9 items, the most critical first. Safety glasses are out of stock." |
| 2 | 0:25–0:40 | **"What's the status of order SO-1537?"** | "One question gives the order lines, the delay (16 days late), and the invoice status." |
| 3 | 0:40–0:55 | **"Show me customers with overdue invoices."** | "Accounts receivable: $26.6k overdue across 6 customers, with aging." |
| 4 | 0:55–1:10 | **"How did revenue this quarter compare to last quarter?"** | "Notice it doesn't just say minus 68%. The quarter is one month old, so it compares October to July: minus 23.8%." |
| 5 | 1:10–1:30 | **"Prepare this week's sales summary."** (scroll slowly through the report) | "Now a Skill: a recurring task packaged once. One sentence gives the manager's weekly report with concrete actions." |
| 6 | 1:30–1:45 | **"Draft a payment reminder email for Foxglove."** | "Second Skill: a polite reminder built from the real invoices. It's a draft. A human reviews and sends it." |
| 7 | 1:45–2:00 | Terminal: `Get-Content logs\audit.jsonl -Tail 8` (macOS: `tail -n 8 logs/audit.jsonl`) | "And every query is audited: which tool, which parameters, how many rows, how long. Read-only, no free SQL, fully logged. Link to the code below." |

## Expected key facts (to check during rehearsal)

| Scene | Must show |
|---|---|
| 1 | 9 products; SE-0012 has 0 in stock |
| 2 | SO-1537, Ashford Building Services, shipped, 16 days late, $4,550.02, INV-10526 unpaid, due 2026-12-03 |
| 3 | $26,599.80 total, 6 customers |
| 4 | $100,451.98 vs $310,513.09; like-for-like −23.8% |
| 5 | Revenue $33,506 (▼ 4.0%), 12 late orders, 3 action items naming SKUs/orders/customers |
| 6 | To Daniel Fenwick; INV-10461 and INV-10487; total $4,827.85; "DRAFT – not sent" banner |
| 7 | One log line per tool call, all `"status": "ok"` |

## Backup questions (if time allows or for a longer cut)

- "Is Oakhurst over its credit limit?" → yes, $8,374.96 vs $5,000
- "What is Oakhust's balance?" (deliberate typo) → suggests Oakhurst Facilities Group (C-0007)
- "Top 5 customers in September, compared with August?"
- "Delete order SO-1537." → Claude explains it only has read-only tools
