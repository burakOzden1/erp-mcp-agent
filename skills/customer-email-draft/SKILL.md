---
name: customer-email-draft
description: Drafts a polite, professional English email to a customer based on live ERP data - a payment reminder for overdue invoices, an update on late orders, or both. The email is only a draft for human review and is never sent. Use when the user asks to draft, write or prepare an email, payment reminder, dunning letter or order-delay notice for a named customer. Requires the erp-demo MCP tools (get_customer_balance, list_overdue_orders).
---

# Customer Email Draft

Write an email **draft** for a person to review. Never send email, never call any
email or messaging tool, and never present the draft as sent.

## Workflow

**1. Find the customer.** Call `get_customer_balance` with the name or code the user gave.
If the tool says the name is ambiguous or not found, show the suggested customers
and ask the user which one they mean. Do not guess.

**2. Late orders.** Call `list_overdue_orders` with `customer` set to the customer
code from step 1.

**3. Choose the email type:**

| Situation | Email type |
|---|---|
| Overdue invoices only | Payment reminder |
| Late orders only | Order delay update |
| Both | Order update first, then the payment reminder, in one email |
| Neither | No email needed: tell the user the account is in good standing and stop |

**4. Choose the tone** for a payment reminder from the oldest `days_overdue`:
- 1–30 days: friendly reminder ("may have been overlooked")
- 31–60 days: polite but clear; ask for a payment date
- over 60 days: firm and courteous; ask for payment or a call this week

Never threaten legal action, late fees or account suspension. Those are business
decisions for the reviewer.

**5. Write the draft** using the template below, then add the review notes.

## Content rules

- Address the contact by first name (`contact_name`), sent to their `email`.
- List each overdue invoice: invoice number, due date, outstanding amount.
- If an invoice is partially paid, thank them for the payment received.
- State the total overdue amount. Use USD, e.g. `$3,349.13`. Write dates as `18 October 2026`.
- For late orders, list the order number and original promised date, and apologise
  briefly. Do not invent a new delivery date: use the placeholder `[new expected date]`.
- Do not mention the credit limit in the email. Put it in the review notes instead.
- Use placeholders for unknown details: `[Your name]`, `[Your company]`, `[payment details]`.
- Keep the body under 200 words.

## Output template

```markdown
**DRAFT – not sent. Please review before sending.**

**To:** {contact_name} <{email}>
**Subject:** {e.g. "Payment reminder: 2 overdue invoices ($4,827.85)" or "Update on your order SO-1509"}

Dear {first name},

{Body}

Kind regards,
[Your name]
[Your company]

---
**Review notes (internal, do not send)**
| Fact | Value |
|---|---|
| Customer | {name} ({code}), {city}, {country} |
| Payment terms | {n} days |
| Open balance / credit limit | $… / $… {⚠️ over limit by $… if over_credit_limit} |
| Overdue amount | $… across {n} invoices, oldest {n} days |
| Late orders | {n} ({order numbers}) |
| Data as of | {as_of_date} |

Before sending: confirm no payment arrived after the data date, fill the placeholders,
and decide whether to mention the credit limit.
```
