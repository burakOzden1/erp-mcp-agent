"""Create the demo ERP database and fill it with fake but realistic data.

All names, companies and numbers are invented. A fixed random seed and a fixed
reference date ("as of" date) make every run produce the same database.

Usage:
    python scripts/seed_db.py                    # as_of = 2026-10-31, seed = 42
    python scripts/seed_db.py --as-of today      # anchor the data to today's date
    python scripts/seed_db.py --as-of 2026-12-15 --seed 7 --db data/other.db
"""

from __future__ import annotations

import argparse
import math
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "erp_demo.db"
DEFAULT_AS_OF = date(2026, 10, 31)
DEFAULT_SEED = 42
SCHEMA_VERSION = "1"

NUM_CUSTOMERS = 40
PRODUCTS_PER_CATEGORY = 20
NUM_ORDERS = 600
NUM_BESTSELLERS = 10

# Deliberately planted situations that the demo questions will surface.
NUM_LOW_STOCK = 9
NUM_OVERDUE_ORDERS = 12
NUM_SLOW_PAYERS = 6
NUM_OVER_CREDIT_LIMIT = 2

SCHEMA = """
CREATE TABLE app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE customers (
    id                 INTEGER PRIMARY KEY,
    code               TEXT    NOT NULL UNIQUE,
    name               TEXT    NOT NULL,
    contact_name       TEXT    NOT NULL,
    email              TEXT    NOT NULL,
    country            TEXT    NOT NULL,
    city               TEXT    NOT NULL,
    credit_limit       REAL    NOT NULL CHECK (credit_limit >= 0),
    payment_terms_days INTEGER NOT NULL CHECK (payment_terms_days > 0)
);

CREATE TABLE products (
    id            INTEGER PRIMARY KEY,
    sku           TEXT    NOT NULL UNIQUE,
    name          TEXT    NOT NULL,
    category      TEXT    NOT NULL,
    unit          TEXT    NOT NULL,
    unit_price    REAL    NOT NULL CHECK (unit_price >= 0),
    stock_qty     INTEGER NOT NULL CHECK (stock_qty >= 0),
    reorder_level INTEGER NOT NULL CHECK (reorder_level >= 0)
);

CREATE TABLE sales_orders (
    id             INTEGER PRIMARY KEY,
    order_no       TEXT    NOT NULL UNIQUE,
    customer_id    INTEGER NOT NULL REFERENCES customers (id),
    order_date     TEXT    NOT NULL,
    promised_date  TEXT    NOT NULL,
    shipped_date   TEXT,
    delivered_date TEXT,
    status         TEXT    NOT NULL
        CHECK (status IN ('open', 'shipped', 'delivered', 'cancelled'))
);

CREATE TABLE order_lines (
    id           INTEGER PRIMARY KEY,
    order_id     INTEGER NOT NULL REFERENCES sales_orders (id),
    line_no      INTEGER NOT NULL,
    product_id   INTEGER NOT NULL REFERENCES products (id),
    qty          INTEGER NOT NULL CHECK (qty > 0),
    unit_price   REAL    NOT NULL CHECK (unit_price >= 0),
    discount_pct REAL    NOT NULL DEFAULT 0 CHECK (discount_pct BETWEEN 0 AND 100),
    UNIQUE (order_id, line_no)
);

CREATE TABLE invoices (
    id           INTEGER PRIMARY KEY,
    invoice_no   TEXT    NOT NULL UNIQUE,
    order_id     INTEGER NOT NULL UNIQUE REFERENCES sales_orders (id),
    customer_id  INTEGER NOT NULL REFERENCES customers (id),
    invoice_date TEXT    NOT NULL,
    due_date     TEXT    NOT NULL,
    total_amount REAL    NOT NULL CHECK (total_amount >= 0)
);

CREATE TABLE payments (
    id           INTEGER PRIMARY KEY,
    invoice_id   INTEGER NOT NULL REFERENCES invoices (id),
    payment_date TEXT    NOT NULL,
    amount       REAL    NOT NULL CHECK (amount > 0),
    method       TEXT    NOT NULL CHECK (method IN ('bank_transfer', 'card', 'check'))
);

CREATE INDEX ix_orders_customer   ON sales_orders (customer_id);
CREATE INDEX ix_orders_date       ON sales_orders (order_date);
CREATE INDEX ix_orders_status     ON sales_orders (status, promised_date);
CREATE INDEX ix_lines_order       ON order_lines (order_id);
CREATE INDEX ix_lines_product     ON order_lines (product_id);
CREATE INDEX ix_invoices_customer ON invoices (customer_id);
CREATE INDEX ix_invoices_due      ON invoices (due_date);
CREATE INDEX ix_payments_invoice  ON payments (invoice_id);
"""

# --- Reference data (all invented) -------------------------------------------

COMPANY_STEMS = [
    "Bluepeak", "Ironvale", "Crestline", "Harborview", "Silverbrook", "Redmoor",
    "Oakhurst", "Stonegate", "Brightwater", "Westfield", "Pinecrest", "Copperfield",
    "Lakemont", "Granite Ridge", "Summitway", "Fairhaven", "Northgate", "Riverbend",
    "Greystone", "Maplewood", "Eastbrook", "Highland", "Clearwater", "Ashford",
    "Kingsbridge", "Sandhill", "Thornbury", "Larkspur", "Ridgeway", "Elmstead",
    "Foxglove", "Hawthorne", "Millbrook", "Seabright", "Windmere", "Cedarline",
    "Goldcrest", "Ravenhill", "Starling", "Wolfbridge",
]
COMPANY_SUFFIXES = [
    "Trading Co.", "Industrial Supply", "Construction Ltd.", "Manufacturing Inc.",
    "Facilities Group", "Logistics LLC", "Building Services", "Engineering GmbH",
    "Maintenance Co.", "Contractors Ltd.",
]
LOCATIONS = [
    ("United States", ["Chicago", "Houston", "Denver", "Atlanta", "Phoenix", "Columbus"]),
    ("United Kingdom", ["Manchester", "Leeds", "Bristol", "Birmingham"]),
    ("Germany", ["Hamburg", "Cologne", "Stuttgart", "Leipzig"]),
    ("Netherlands", ["Rotterdam", "Utrecht", "Eindhoven"]),
    ("Canada", ["Toronto", "Calgary", "Ottawa"]),
    ("Ireland", ["Dublin", "Cork"]),
]
FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Jamie", "Avery",
    "Quinn", "Robin", "Dana", "Sam", "Chris", "Kim", "Lee", "Noa", "Elena",
    "Marco", "Sofia", "Lukas", "Hannah", "Daniel", "Priya", "Omar",
]
LAST_NAMES = [
    "Whitfield", "Carver", "Lindqvist", "Brennan", "Okafor", "Moreau", "Hartley",
    "Visser", "Novak", "Castillo", "Fenwick", "Albrecht", "Delaney", "Sato",
    "Kowalski", "Ramsey", "Bauer", "Ellison", "Marsh", "Quintero",
]

# category -> (sku prefix, [(base name, unit, min price, max price)], [variants])
CATALOG: dict[str, tuple[str, list[tuple[str, str, float, float]], list[str]]] = {
    "Fasteners": ("FS", [
        ("Hex Bolt", "box", 8, 35), ("Wood Screw", "box", 5, 25),
        ("Wall Anchor", "box", 6, 22), ("Flat Washer", "box", 3, 12),
        ("Lock Nut", "box", 4, 18), ("Threaded Rod", "pcs", 3, 15),
    ], ["M6", "M8", "M10", "M12", "Stainless", "Zinc Plated"]),
    "Hand Tools": ("HT", [
        ("Claw Hammer", "pcs", 12, 40), ("Screwdriver Set", "set", 15, 60),
        ("Combination Wrench Set", "set", 30, 95), ("Locking Pliers", "pcs", 10, 35),
        ("Tape Measure", "pcs", 8, 30), ("Utility Knife", "pcs", 6, 20),
    ], ["Standard", "Pro", "Heavy Duty", "Compact", "Insulated"]),
    "Power Tools": ("PT", [
        ("Cordless Drill", "pcs", 90, 260), ("Angle Grinder", "pcs", 70, 210),
        ("Circular Saw", "pcs", 120, 380), ("Impact Driver", "pcs", 110, 300),
        ("Jigsaw", "pcs", 80, 220), ("Li-ion Battery Pack", "pcs", 45, 140),
    ], ["18V", "20V", "Brushless", "Kit", "Pro Series"]),
    "Safety Equipment": ("SE", [
        ("Work Gloves", "pair", 3, 14), ("Safety Helmet", "pcs", 12, 45),
        ("Safety Glasses", "pcs", 4, 18), ("Hi-Vis Vest", "pcs", 5, 20),
        ("Ear Defenders", "pcs", 9, 35), ("FFP2 Respirator Mask", "box", 15, 45),
    ], ["Size M", "Size L", "Size XL", "Premium", "Economy"]),
    "Electrical": ("EL", [
        ("Installation Cable 100m", "roll", 45, 150), ("LED Panel 60x60", "pcs", 25, 70),
        ("Junction Box", "pcs", 4, 15), ("Circuit Breaker", "pcs", 8, 40),
        ("Extension Cord", "pcs", 10, 45), ("Cable Ties", "box", 3, 12),
    ], ["IP44", "IP65", "16A", "32A", "Outdoor"]),
    "Packaging": ("PK", [
        ("Stretch Film Roll", "roll", 9, 28), ("Corrugated Box", "bundle", 12, 40),
        ("Packing Tape", "roll", 2, 6), ("Bubble Wrap Roll", "roll", 15, 45),
        ("Pallet Strap Kit", "set", 25, 80), ("Void Fill Paper", "box", 18, 50),
    ], ["Small", "Medium", "Large", "Heavy Duty", "Recycled"]),
}

# Relative order volume per calendar month (construction/industrial seasonality).
MONTH_SEASONALITY = {
    1: 0.75, 2: 0.85, 3: 1.05, 4: 1.15, 5: 1.20, 6: 1.10,
    7: 0.90, 8: 0.80, 9: 1.10, 10: 1.20, 11: 1.05, 12: 0.70,
}

PAYMENT_METHODS = ["bank_transfer", "bank_transfer", "bank_transfer", "card", "check"]


# --- In-memory model -----------------------------------------------------------

@dataclass
class Customer:
    id: int
    code: str
    name: str
    contact_name: str
    email: str
    country: str
    city: str
    credit_limit: float
    payment_terms_days: int
    weight: float


@dataclass
class Product:
    id: int
    sku: str
    name: str
    category: str
    unit: str
    unit_price: float
    stock_qty: int
    reorder_level: int
    weight: float


@dataclass
class Order:
    id: int
    order_no: str
    customer: Customer
    order_date: date
    promised_date: date
    shipped_date: date | None = None
    delivered_date: date | None = None
    status: str = "open"
    lines: list[tuple[int, int, int, float, float]] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(sum(line_total(qty, price, disc) for _, _, qty, price, disc in self.lines), 2)


@dataclass
class Invoice:
    id: int
    invoice_no: str
    order: Order
    invoice_date: date
    due_date: date
    total_amount: float
    payments: list[tuple[date, float, str]] = field(default_factory=list)

    @property
    def paid(self) -> float:
        return round(sum(amount for _, amount, _ in self.payments), 2)


def line_total(qty: int, unit_price: float, discount_pct: float) -> float:
    """Net amount of an order line after discount, rounded to cents."""
    return round(qty * unit_price * (1 - discount_pct / 100), 2)


# --- Generators -----------------------------------------------------------------

def make_customers(rng: random.Random) -> list[Customer]:
    stems = rng.sample(COMPANY_STEMS, NUM_CUSTOMERS)
    customers = []
    for i, stem in enumerate(stems, start=1):
        country, cities = rng.choice(LOCATIONS)
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        slug = stem.lower().replace(" ", "")
        customers.append(Customer(
            id=i,
            code=f"C-{i:04d}",
            name=f"{stem} {rng.choice(COMPANY_SUFFIXES)}",
            contact_name=f"{first} {last}",
            email=f"{first.lower()}.{last.lower()}@{slug}.example.com",
            country=country,
            city=rng.choice(cities),
            credit_limit=float(rng.choice([10, 15, 20, 25, 30, 40, 50, 75, 100]) * 1000),
            payment_terms_days=rng.choice([30, 30, 45, 60]),
            # Pareto weights: a handful of large accounts, a long tail of small ones.
            weight=rng.paretovariate(1.3),
        ))
    return customers


def make_products(rng: random.Random) -> list[Product]:
    products: list[Product] = []
    for category, (prefix, bases, variants) in CATALOG.items():
        combos = [(base, variant) for base in bases for variant in variants]
        for n, ((base_name, unit, lo, hi), variant) in enumerate(
            rng.sample(combos, PRODUCTS_PER_CATEGORY), start=1
        ):
            reorder = rng.choice([10, 15, 20, 25, 30, 40, 50, 75, 100])
            products.append(Product(
                id=len(products) + 1,
                sku=f"{prefix}-{n:04d}",
                name=f"{base_name} {variant}",
                category=category,
                unit=unit,
                unit_price=round(rng.uniform(lo, hi), 2),
                stock_qty=int(reorder * rng.uniform(1.3, 5.0)) + 1,
                reorder_level=reorder,
                weight=rng.uniform(0.5, 1.5),
            ))
    for p in rng.sample(products, NUM_BESTSELLERS):
        p.weight *= 8
    return products


def sample_order_dates(rng: random.Random, as_of: date) -> list[date]:
    """Spread orders over the last 12 months with seasonality, weekdays and mild growth."""
    days = [as_of - timedelta(days=d) for d in range(364, -1, -1)]
    weights = []
    for i, d in enumerate(days):
        weekday_factor = 1.0 if d.weekday() < 5 else 0.15
        growth = 1 + 0.2 * i / len(days)
        weights.append(MONTH_SEASONALITY[d.month] * weekday_factor * growth)
    return sorted(rng.choices(days, weights=weights, k=NUM_ORDERS))


def make_order_lines(rng: random.Random, products: list[Product]) -> list[tuple[int, int, int, float, float]]:
    n_lines = rng.choices([1, 2, 3, 4, 5, 6], weights=[20, 25, 22, 15, 10, 8])[0]
    chosen: list[Product] = []
    while len(chosen) < n_lines:
        p = rng.choices(products, weights=[p.weight for p in products])[0]
        if p not in chosen:
            chosen.append(p)
    lines = []
    for line_no, p in enumerate(chosen, start=1):
        if p.unit_price < 20:
            qty = rng.randint(10, 150)
        elif p.unit_price < 100:
            qty = rng.randint(2, 30)
        else:
            qty = rng.randint(1, 8)
        discount = rng.choices([0, 5, 10, 15], weights=[75, 13, 9, 3])[0]
        lines.append((line_no, p.id, qty, p.unit_price, float(discount)))
    return lines


def make_orders(rng: random.Random, customers: list[Customer], products: list[Product],
                as_of: date) -> list[Order]:
    orders = []
    for i, order_date in enumerate(sample_order_dates(rng, as_of), start=1):
        customer = rng.choices(customers, weights=[c.weight for c in customers])[0]
        order = Order(
            id=i,
            order_no=f"SO-{1000 + i}",
            customer=customer,
            order_date=order_date,
            promised_date=order_date + timedelta(days=rng.randint(5, 14)),
            lines=make_order_lines(rng, products),
        )
        set_natural_status(rng, order, as_of)
        orders.append(order)
    return orders


def set_natural_status(rng: random.Random, order: Order, as_of: date) -> None:
    """Assign a 'healthy' lifecycle: nothing is overdue unless planted later."""
    if order.promised_date < as_of:
        if rng.random() < 0.03:
            order.status = "cancelled"
            return
        shipped = order.promised_date + timedelta(days=rng.randint(-4, 2))
        delivered = shipped + timedelta(days=rng.randint(1, 4))
        delivered = min(delivered, as_of)
        order.shipped_date = max(order.order_date + timedelta(days=1), min(shipped, delivered))
        order.delivered_date = max(delivered, order.shipped_date)
        order.status = "delivered"
        return
    # Promise still in the future: order is open, shipped or already delivered.
    if order.order_date >= as_of - timedelta(days=2) or rng.random() < 0.5:
        order.status = "open"
        return
    order.shipped_date = order.order_date + timedelta(
        days=rng.randint(1, max(1, (as_of - order.order_date).days)))
    transit_done = order.shipped_date + timedelta(days=rng.randint(1, 4))
    if transit_done <= as_of:
        order.delivered_date = transit_done
        order.status = "delivered"
    else:
        order.status = "shipped"


def plant_overdue_orders(rng: random.Random, orders: list[Order], as_of: date) -> list[Order]:
    """Turn some recent orders into 'promised date passed, not delivered'."""
    candidates = [
        o for o in orders
        if o.status != "cancelled" and 1 <= (as_of - o.promised_date).days <= 45
    ]
    picked = rng.sample(candidates, NUM_OVERDUE_ORDERS)
    for n, o in enumerate(picked):
        o.delivered_date = None
        if n < NUM_OVERDUE_ORDERS * 0.6:
            o.status, o.shipped_date = "open", None
        else:
            o.status = "shipped"
            o.shipped_date = o.promised_date + timedelta(
                days=rng.randint(0, max(0, (as_of - o.promised_date).days - 1)))
    return picked


def make_invoices(orders: list[Order]) -> list[Invoice]:
    invoices = []
    billable = sorted(
        (o for o in orders if o.status in ("shipped", "delivered")),
        key=lambda o: (o.shipped_date, o.id),
    )
    for i, o in enumerate(billable, start=1):
        assert o.shipped_date is not None
        invoices.append(Invoice(
            id=i,
            invoice_no=f"INV-{10000 + i}",
            order=o,
            invoice_date=o.shipped_date,
            due_date=o.shipped_date + timedelta(days=o.customer.payment_terms_days),
            total_amount=o.total,
        ))
    return invoices


def make_payments(rng: random.Random, invoices: list[Invoice], customers: list[Customer],
                  as_of: date) -> list[Customer]:
    """Pay invoices on time, except for a few planted slow payers. Returns those payers."""
    def pay_date(inv: Invoice, target: date) -> date:
        return min(max(target, inv.invoice_date), as_of)

    for inv in invoices:
        method = rng.choice(PAYMENT_METHODS)
        if inv.due_date < as_of:
            when = pay_date(inv, inv.due_date + timedelta(days=rng.randint(-15, 8)))
            if rng.random() < 0.1:  # occasionally settled in two instalments
                first = round(inv.total_amount * rng.uniform(0.3, 0.7), 2)
                inv.payments += [
                    (pay_date(inv, when - timedelta(days=rng.randint(5, 20))), first, method),
                    (when, round(inv.total_amount - first, 2), method),
                ]
            else:
                inv.payments.append((when, inv.total_amount, method))
        elif rng.random() < 0.35:  # some customers pay before the due date
            inv.payments.append((pay_date(inv, inv.invoice_date + timedelta(
                days=rng.randint(3, inv.order.customer.payment_terms_days))), inv.total_amount, method))

    # Slow payers: customers with several past-due invoices in the last 120 days.
    recent_past_due: dict[int, list[Invoice]] = {}
    for inv in invoices:
        if inv.due_date < as_of and (as_of - inv.due_date).days <= 120:
            recent_past_due.setdefault(inv.order.customer.id, []).append(inv)
    candidates = [c for c in customers if len(recent_past_due.get(c.id, [])) >= 3]
    slow_payers = rng.sample(candidates, NUM_SLOW_PAYERS)

    for c in slow_payers:
        overdue = sorted(recent_past_due[c.id], key=lambda inv: inv.due_date, reverse=True)
        for n, inv in enumerate(overdue[: rng.randint(2, 3)]):
            method = inv.payments[0][2] if inv.payments else rng.choice(PAYMENT_METHODS)
            if n == 0 or rng.random() < 0.5:  # partially paid (at least one per customer)
                share = round(inv.total_amount * rng.uniform(0.25, 0.6), 2)
                inv.payments = [(pay_date(inv, inv.due_date - timedelta(days=rng.randint(0, 10))),
                                 share, method)]
            else:  # not paid at all
                inv.payments = []
    return slow_payers


def set_credit_limits(rng: random.Random, customers: list[Customer], invoices: list[Invoice],
                      slow_payers: list[Customer]) -> list[Customer]:
    """Keep everyone within limit except two planted over-limit slow payers."""
    balance = {c.id: 0.0 for c in customers}
    for inv in invoices:
        balance[inv.order.customer.id] += inv.total_amount - inv.paid

    over_limit = sorted(slow_payers, key=lambda c: balance[c.id], reverse=True)[:NUM_OVER_CREDIT_LIMIT]
    for c in customers:
        if c in over_limit:
            c.credit_limit = float(max(5000, math.floor(balance[c.id] * rng.uniform(0.6, 0.85) / 1000) * 1000))
        else:
            headroom = math.ceil(balance[c.id] * 1.4 / 5000) * 5000
            c.credit_limit = float(max(c.credit_limit, headroom))
    return over_limit


def plant_low_stock(rng: random.Random, products: list[Product]) -> list[Product]:
    """Push a few products (some of them bestsellers) below their reorder level."""
    by_weight = sorted(products, key=lambda p: p.weight, reverse=True)
    picked = rng.sample(by_weight[:NUM_BESTSELLERS], 3)
    picked += rng.sample([p for p in products if p not in picked], NUM_LOW_STOCK - 3)
    for p in picked:
        p.stock_qty = rng.randint(0, p.reorder_level - 1)
    return picked


# --- Persistence -----------------------------------------------------------------

def write_database(db_path: Path, as_of: date, seed: int, customers: list[Customer],
                   products: list[Product], orders: list[Order], invoices: list[Invoice]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)

    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    con = sqlite3.connect(db_path)
    try:
        con.executescript(SCHEMA)
        con.executemany("INSERT INTO app_meta VALUES (?, ?)", [
            ("as_of_date", as_of.isoformat()),
            ("seed", str(seed)),
            ("currency", "USD"),
            ("schema_version", SCHEMA_VERSION),
        ])
        con.executemany(
            "INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(c.id, c.code, c.name, c.contact_name, c.email, c.country, c.city,
              c.credit_limit, c.payment_terms_days) for c in customers],
        )
        con.executemany(
            "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(p.id, p.sku, p.name, p.category, p.unit, p.unit_price, p.stock_qty,
              p.reorder_level) for p in products],
        )
        con.executemany(
            "INSERT INTO sales_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(o.id, o.order_no, o.customer.id, iso(o.order_date), iso(o.promised_date),
              iso(o.shipped_date), iso(o.delivered_date), o.status) for o in orders],
        )
        con.executemany(
            "INSERT INTO order_lines (order_id, line_no, product_id, qty, unit_price, discount_pct)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [(o.id, *line) for o in orders for line in o.lines],
        )
        con.executemany(
            "INSERT INTO invoices VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(i.id, i.invoice_no, i.order.id, i.order.customer.id, iso(i.invoice_date),
              iso(i.due_date), i.total_amount) for i in invoices],
        )
        con.executemany(
            "INSERT INTO payments (invoice_id, payment_date, amount, method) VALUES (?, ?, ?, ?)",
            [(i.id, iso(d), amount, method) for i in invoices for d, amount, method in i.payments],
        )
        con.commit()
    finally:
        con.close()


def build_database(db_path: Path = DEFAULT_DB_PATH, as_of: date = DEFAULT_AS_OF,
                   seed: int = DEFAULT_SEED) -> None:
    """Generate all data deterministically and write it to ``db_path`` (overwrites)."""
    rng = random.Random(seed)
    customers = make_customers(rng)
    products = make_products(rng)
    orders = make_orders(rng, customers, products, as_of)
    plant_overdue_orders(rng, orders, as_of)
    invoices = make_invoices(orders)
    slow_payers = make_payments(rng, invoices, customers, as_of)
    set_credit_limits(rng, customers, invoices, slow_payers)
    plant_low_stock(rng, products)
    write_database(db_path, as_of, seed, customers, products, orders, invoices)


# --- Verification (reads back from the database, not from memory) ----------------

PLANTED_CHECKS = {
    "products_below_reorder_level":
        "SELECT COUNT(*) FROM products WHERE stock_qty < reorder_level",
    "overdue_orders (promised date passed, not delivered)":
        "SELECT COUNT(*) FROM sales_orders WHERE status IN ('open', 'shipped') AND promised_date < :as_of",
    "customers_with_overdue_partially_paid_invoices": """
        SELECT COUNT(DISTINCT i.customer_id)
        FROM invoices i
        JOIN (SELECT invoice_id, SUM(amount) AS paid FROM payments GROUP BY invoice_id) p
          ON p.invoice_id = i.id
        WHERE i.due_date < :as_of AND p.paid < i.total_amount - 0.005""",
    "customers_over_credit_limit": """
        SELECT COUNT(*) FROM (
            SELECT c.id
            FROM customers c
            JOIN invoices i ON i.customer_id = c.id
            LEFT JOIN (SELECT invoice_id, SUM(amount) AS paid FROM payments GROUP BY invoice_id) p
              ON p.invoice_id = i.id
            GROUP BY c.id
            HAVING SUM(i.total_amount - COALESCE(p.paid, 0)) > c.credit_limit)""",
}


def summarize(db_path: Path) -> dict[str, int]:
    """Return row counts per table and counts of the planted demo situations."""
    con = sqlite3.connect(db_path)
    try:
        as_of = con.execute("SELECT value FROM app_meta WHERE key = 'as_of_date'").fetchone()[0]
        tables = ["customers", "products", "sales_orders", "order_lines", "invoices", "payments"]
        summary = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
        for label, sql in PLANTED_CHECKS.items():
            summary[label] = con.execute(sql, {"as_of": as_of}).fetchone()[0]
        return summary
    finally:
        con.close()


def print_report(db_path: Path) -> None:
    summary = summarize(db_path)
    con = sqlite3.connect(db_path)
    try:
        as_of = con.execute("SELECT value FROM app_meta WHERE key = 'as_of_date'").fetchone()[0]
        overdue = con.execute(
            "SELECT order_no FROM sales_orders WHERE status IN ('open','shipped') "
            "AND promised_date < ? ORDER BY promised_date LIMIT 3", (as_of,)).fetchall()
        delivered = con.execute(
            "SELECT order_no FROM sales_orders WHERE status = 'delivered' ORDER BY id LIMIT 1 OFFSET 41"
        ).fetchone()
    finally:
        con.close()

    print(f"Database written to {db_path} (as_of {as_of})\n")
    print("Rows per table")
    for key in ["customers", "products", "sales_orders", "order_lines", "invoices", "payments"]:
        print(f"  {key:<14} {summary[key]:>6}")
    print("\nPlanted demo situations")
    for key in PLANTED_CHECKS:
        print(f"  {key:<55} {summary[key]:>3}")
    print("\nSample order numbers for the demo")
    print(f"  overdue:   {', '.join(r[0] for r in overdue)}")
    print(f"  delivered: {delivered[0] if delivered else '-'}")


def parse_as_of(value: str) -> date:
    return date.today() if value == "today" else date.fromisoformat(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the demo ERP SQLite database.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="output database path")
    parser.add_argument("--as-of", type=parse_as_of, default=DEFAULT_AS_OF,
                        help="reference date: YYYY-MM-DD or 'today' (default: %(default)s)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed")
    args = parser.parse_args()

    build_database(args.db, args.as_of, args.seed)
    print_report(args.db)


if __name__ == "__main__":
    main()
