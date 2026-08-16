"""Seed a realistic e-commerce warehouse with intentionally injected data issues,
then register datasets, checks and lineage in the control plane.

Run with:  python -m app.seed
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from .db import SessionLocal, init_db
from .models import Check, Dataset, LineageEdge
from .warehouse import warehouse_engine

RNG = random.Random(42)


def _reset_warehouse() -> None:
    ddl = [
        "DROP TABLE IF EXISTS order_items",
        "DROP TABLE IF EXISTS orders",
        "DROP TABLE IF EXISTS products",
        "DROP TABLE IF EXISTS customers",
        "DROP TABLE IF EXISTS daily_revenue",
        """CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            email TEXT,
            country TEXT,
            created_at TEXT
        )""",
        """CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            sku TEXT,
            category TEXT,
            price REAL,
            created_at TEXT
        )""",
        """CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            status TEXT,
            total REAL,
            created_at TEXT
        )""",
        """CREATE TABLE order_items (
            id INTEGER PRIMARY KEY,
            order_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            unit_price REAL
        )""",
        """CREATE TABLE daily_revenue (
            day TEXT PRIMARY KEY,
            revenue REAL,
            created_at TEXT
        )""",
    ]
    with warehouse_engine().begin() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _seed_warehouse_rows() -> None:
    now = datetime.now(timezone.utc)
    countries = ["US", "GB", "BD", "DE", "IN", "CA"]
    categories = ["electronics", "apparel", "home", "beauty"]
    statuses = ["pending", "paid", "shipped", "delivered", "cancelled"]

    customers, products, orders, items = [], [], [], []

    for cid in range(1, 401):
        # Inject issues: ~4% NULL emails and a handful of duplicates.
        email = f"user{cid}@shop.example"
        if RNG.random() < 0.04:
            email = None
        elif cid in (12, 88, 205):
            email = "user1@shop.example"  # duplicate of customer 1
        customers.append(
            {
                "id": cid,
                "email": email,
                "country": RNG.choice(countries),
                "created_at": _iso(now - timedelta(days=RNG.randint(1, 400))),
            }
        )

    for pid in range(1, 121):
        price = round(RNG.uniform(5, 900), 2)
        category = RNG.choice(categories)
        if pid in (7, 34):  # invalid category (schema/domain drift)
            category = "misc"
        if pid in (19, 58):  # negative price (range violation)
            price = -round(RNG.uniform(1, 50), 2)
        products.append(
            {
                "id": pid,
                "sku": f"SKU-{pid:04d}",
                "category": category,
                "price": price,
                "created_at": _iso(now - timedelta(days=RNG.randint(1, 500))),
            }
        )

    for oid in range(1, 901):
        status = RNG.choice(statuses)
        if oid in (3, 77, 512):  # invalid status (accepted_values violation)
            status = "refunded?"
        orders.append(
            {
                "id": oid,
                "customer_id": RNG.randint(1, 400),
                "status": status,
                "total": round(RNG.uniform(10, 1500), 2),
                "created_at": _iso(now - timedelta(hours=RNG.randint(0, 72))),
            }
        )

    item_id = 1
    for oid in range(1, 901):
        for _ in range(RNG.randint(1, 4)):
            qty = RNG.randint(1, 5)
            if item_id in (10, 250, 999):  # negative quantity (range violation)
                qty = -1
            items.append(
                {
                    "id": item_id,
                    "order_id": oid,
                    "product_id": RNG.randint(1, 120),
                    "quantity": qty,
                    "unit_price": round(RNG.uniform(5, 900), 2),
                }
            )
            item_id += 1

    # daily_revenue is intentionally stale (newest row is 5 days old) to trip freshness.
    daily = [
        {
            "day": (now - timedelta(days=d)).date().isoformat(),
            "revenue": round(RNG.uniform(5000, 20000), 2),
            "created_at": _iso(now - timedelta(days=d + 5)),
        }
        for d in range(30)
    ]

    with warehouse_engine().begin() as conn:
        conn.execute(
            text("INSERT INTO customers (id,email,country,created_at) VALUES (:id,:email,:country,:created_at)"),
            customers,
        )
        conn.execute(
            text("INSERT INTO products (id,sku,category,price,created_at) VALUES (:id,:sku,:category,:price,:created_at)"),
            products,
        )
        conn.execute(
            text("INSERT INTO orders (id,customer_id,status,total,created_at) VALUES (:id,:customer_id,:status,:total,:created_at)"),
            orders,
        )
        conn.execute(
            text("INSERT INTO order_items (id,order_id,product_id,quantity,unit_price) VALUES (:id,:order_id,:product_id,:quantity,:unit_price)"),
            items,
        )
        conn.execute(
            text("INSERT INTO daily_revenue (day,revenue,created_at) VALUES (:day,:revenue,:created_at)"),
            daily,
        )


def _register_control_plane() -> None:
    with SessionLocal() as session:
        session.query(Check).delete()
        session.query(Dataset).delete()
        session.query(LineageEdge).delete()
        session.flush()

        datasets = {
            "customers": Dataset(name="customers", source_table="customers", domain="crm", owner="growth", description="Registered shoppers", freshness_sla_minutes=1440),
            "products": Dataset(name="products", source_table="products", domain="catalog", owner="merchandising", description="Product catalog", freshness_sla_minutes=2880),
            "orders": Dataset(name="orders", source_table="orders", domain="commerce", owner="orders", description="Placed orders", freshness_sla_minutes=180),
            "order_items": Dataset(name="order_items", source_table="order_items", domain="commerce", owner="orders", description="Order line items", freshness_sla_minutes=180),
            "daily_revenue": Dataset(name="daily_revenue", source_table="daily_revenue", domain="finance", owner="analytics", description="Daily revenue rollup", freshness_sla_minutes=1440),
        }
        for ds in datasets.values():
            session.add(ds)
        session.flush()

        checks = [
            Check(dataset_id=datasets["customers"].id, name="customers.email not null", check_type="not_null", column_name="email", config={"max_failure_rate": 0.0}, severity="high"),
            Check(dataset_id=datasets["customers"].id, name="customers.email unique", check_type="unique", column_name="email", config={}, severity="high"),
            Check(dataset_id=datasets["customers"].id, name="customers.id unique", check_type="unique", column_name="id", config={}, severity="high"),
            Check(dataset_id=datasets["products"].id, name="products.price >= 0", check_type="range", column_name="price", config={"min": 0}, severity="high"),
            Check(dataset_id=datasets["products"].id, name="products.category allowed", check_type="accepted_values", column_name="category", config={"values": ["electronics", "apparel", "home", "beauty"]}, severity="medium"),
            Check(dataset_id=datasets["orders"].id, name="orders.status allowed", check_type="accepted_values", column_name="status", config={"values": ["pending", "paid", "shipped", "delivered", "cancelled"]}, severity="high"),
            Check(dataset_id=datasets["orders"].id, name="orders freshness (3h)", check_type="freshness", column_name="created_at", config={"sla_minutes": 180}, severity="high"),
            Check(dataset_id=datasets["orders"].id, name="orders.total >= 0", check_type="range", column_name="total", config={"min": 0}, severity="medium"),
            Check(dataset_id=datasets["order_items"].id, name="order_items.quantity >= 1", check_type="range", column_name="quantity", config={"min": 1}, severity="high"),
            Check(dataset_id=datasets["daily_revenue"].id, name="daily_revenue freshness (24h)", check_type="freshness", column_name="created_at", config={"sla_minutes": 1440}, severity="high"),
            Check(dataset_id=datasets["orders"].id, name="orders schema", check_type="schema", column_name=None, config={"columns": ["id", "customer_id", "status", "total", "created_at"]}, severity="low"),
        ]
        session.add_all(checks)

        lineage = [
            LineageEdge(upstream="customers", downstream="orders", transformation="customer_id FK"),
            LineageEdge(upstream="orders", downstream="order_items", transformation="order_id FK"),
            LineageEdge(upstream="products", downstream="order_items", transformation="product_id FK"),
            LineageEdge(upstream="orders", downstream="daily_revenue", transformation="SUM(total) GROUP BY day"),
        ]
        session.add_all(lineage)
        session.commit()


def seed_all() -> None:
    init_db()
    _reset_warehouse()
    _seed_warehouse_rows()
    _register_control_plane()
    print("Seeded warehouse + control plane. Injected issues across 5 datasets and 11 checks.")


if __name__ == "__main__":
    seed_all()
