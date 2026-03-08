from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from database import query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Optional
import os
import uuid
from PIL import Image

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads/logos"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────

class LoginRequest(BaseModel):
    password: str

class ResetPasswordRequest(BaseModel):
    current_password: str
    new_password: str

class SupplierRequest(BaseModel):
    name: str
    phone: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None

class SupplierPurchaseRequest(BaseModel):
    supplier_id: int
    item_name: str          # e.g. "Rubber Rolls", "Ink", "Tape", "Cones"
    quantity: float         # kg, units, rolls — whatever applies
    unit: str               # "kg", "pcs", "rolls", etc.
    unit_cost: float        # cost per unit
    purchase_date: str
    notes: Optional[str] = None

class SupplierPaymentRequest(BaseModel):
    supplier_id: int
    amount: float
    payment_method: str     # Cash / Mobile Money / Bank Transfer
    payment_date: str
    notes: Optional[str] = None

class CycleRequest(BaseModel):
    start_date: str
    total_weight_kg: float
    cost_per_kg: float
    supplier_id: Optional[int] = None  # now references suppliers table

class OrderRequest(BaseModel):
    client_id: int
    cycle_id: int
    total_weight_kg: float
    price_per_kg: float
    num_rolls: int
    order_date: str
    delivery_date: Optional[str] = None
    status: Optional[str] = "Pending"

class RollRequest(BaseModel):
    order_id: int
    rolls: list[dict]  # [{ "roll_number": 1, "weight_kg": 20 }, ...]

class ReceiptRequest(BaseModel):
    order_id: int
    payment_method: str
    amount_paid: float
    transport_cost: Optional[float] = 0
    balance: Optional[float] = 0


# ─────────────────────────────────────────────
# SETUP — creates all tables and seeds password
# ─────────────────────────────────────────────

@app.get("/setup", status_code=200)
def setup():
    query("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            phone VARCHAR(20),
            location VARCHAR(255),
            notes TEXT,
            createdate DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    query("""
        CREATE TABLE IF NOT EXISTS supplier_purchases (
            id INT AUTO_INCREMENT PRIMARY KEY,
            supplier_id INT NOT NULL,
            item_name VARCHAR(255) NOT NULL,
            quantity DECIMAL(10,2) NOT NULL,
            unit VARCHAR(50) NOT NULL,
            unit_cost DECIMAL(10,2) NOT NULL,
            total_cost DECIMAL(10,2) NOT NULL,
            purchase_date DATE NOT NULL,
            reference_type VARCHAR(50) DEFAULT 'manual',  -- 'cycle' or 'manual'
            reference_id INT DEFAULT NULL,                -- cycle id if from a cycle
            notes TEXT,
            createdate DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
        )
    """)

    query("""
        CREATE TABLE IF NOT EXISTS supplier_payments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            supplier_id INT NOT NULL,
            amount DECIMAL(10,2) NOT NULL,
            payment_method VARCHAR(50),
            payment_date DATE NOT NULL,
            notes TEXT,
            createdate DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
        )
    """)

    query("""
        CREATE TABLE IF NOT EXISTS credentials (
            id INT AUTO_INCREMENT PRIMARY KEY,
            password VARCHAR(255) NOT NULL,
            createdate DATETIME DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) DEFAULT 'active'
        )
    """)

    query("""
        CREATE TABLE IF NOT EXISTS clients (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            phone VARCHAR(20),
            location VARCHAR(255) NOT NULL,
            description VARCHAR(255),
            logo VARCHAR(255),
            createdate DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    query("""
        CREATE TABLE IF NOT EXISTS cycles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            start_date DATE NOT NULL,
            end_date DATE,
            total_weight_kg DECIMAL(10,2) NOT NULL,
            cost_per_kg DECIMAL(10,2) NOT NULL,
            supplier_id INT DEFAULT NULL,
            status VARCHAR(20) DEFAULT 'Open',
            createdate DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
        )
    """)

    query("""
        CREATE TABLE IF NOT EXISTS orders (
            id INT AUTO_INCREMENT PRIMARY KEY,
            client_id INT NOT NULL,
            cycle_id INT NOT NULL,
            total_weight_kg DECIMAL(10,2) NOT NULL,
            price_per_kg DECIMAL(10,2) NOT NULL,
            num_rolls INT NOT NULL,
            order_date DATE NOT NULL,
            delivery_date DATE,
            status VARCHAR(20) DEFAULT 'Pending',
            createdate DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(id),
            FOREIGN KEY (cycle_id) REFERENCES cycles(id)
        )
    """)

    query("""
        CREATE TABLE IF NOT EXISTS order_rolls (
            id INT AUTO_INCREMENT PRIMARY KEY,
            order_id INT NOT NULL,
            roll_number INT NOT NULL,
            weight_kg DECIMAL(10,2) NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id)
        )
    """)

    query("""
        CREATE TABLE IF NOT EXISTS receipts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            order_id INT NOT NULL,
            receipt_number VARCHAR(50) UNIQUE NOT NULL,
            payment_method VARCHAR(50),
            amount_paid DECIMAL(10,2),
            transport_cost DECIMAL(10,2) DEFAULT 0,
            balance DECIMAL(10,2) DEFAULT 0,
            createdate DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id)
        )
    """)

    existing = query("SELECT COUNT(*) as count FROM credentials", fetchone=True)
    if existing["count"] == 0:
        query(
            "INSERT INTO credentials (password, status) VALUES (%s, 'active')",
            ("alwajud2024",)
        )

    return {"message": "Database setup complete"}


# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────

@app.post("/login", status_code=200)
def login(body: LoginRequest):
    row = query("SELECT * FROM credentials WHERE status = 'active'", fetchone=True)
    if not row:
        raise HTTPException(status_code=404, detail="No credentials found")
    if body.password != row["password"]:
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"message": "Login successful"}


@app.post("/resetPassword", status_code=200)
def reset_password(body: ResetPasswordRequest):
    row = query("SELECT * FROM credentials WHERE status = 'active'", fetchone=True)
    if not row:
        raise HTTPException(status_code=404, detail="No active credentials found")
    if body.current_password != row["password"]:
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    query("UPDATE credentials SET status = 'inactive'")
    query(
        "INSERT INTO credentials (password, status) VALUES (%s, 'active')",
        (body.new_password,)
    )
    return {"message": "Password reset successful"}


# ─────────────────────────────────────────────
# CLIENTS
# ─────────────────────────────────────────────

@app.get("/clients", status_code=200)
def get_clients():
    return query("""
        SELECT c.*,
            COUNT(o.id) AS total_orders,
            MAX(o.order_date) AS last_order_date,
            COALESCE(SUM(o.total_weight_kg), 0) AS total_weight,
            COALESCE(SUM(o.total_weight_kg * o.price_per_kg), 0) AS total_revenue
        FROM clients c
        LEFT JOIN orders o ON o.client_id = c.id
        GROUP BY c.id
        ORDER BY c.name ASC
    """)


@app.get("/clients/{client_id}", status_code=200)
def get_client(client_id: int):
    client = query("SELECT * FROM clients WHERE id = %s", (client_id,), fetchone=True)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    orders = query("""
        SELECT o.*, r.receipt_number
        FROM orders o
        LEFT JOIN receipts r ON r.order_id = o.id
        WHERE o.client_id = %s
        ORDER BY o.order_date DESC
    """, (client_id,))

    stats = query("""
        SELECT
            COALESCE(SUM(total_weight_kg), 0) AS total_weight,
            COALESCE(SUM(total_weight_kg * price_per_kg), 0) AS total_revenue,
            COUNT(*) AS total_orders
        FROM orders WHERE client_id = %s
    """, (client_id,), fetchone=True)

    return { **client, "orders": orders, "stats": stats }


@app.post("/client", status_code=201)
async def create_client(
    name: str = Form(...),
    phone: str = Form(None),
    location: str = Form(...),
    description: str = Form(None),
    logo: UploadFile = File(None),
):
    logo_filename = None
    if logo:
        if not logo.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")
        ext = logo.filename.split(".")[-1]
        logo_filename = f"{uuid.uuid4()}.{ext}"
        image = Image.open(logo.file)
        image.thumbnail((300, 300))
        image.save(os.path.join(UPLOAD_DIR, logo_filename))

    query(
        "INSERT INTO clients (name, phone, location, description, logo) VALUES (%s, %s, %s, %s, %s)",
        (name, phone, location, description, logo_filename)
    )
    return {"message": "Client created"}


@app.put("/client/{client_id}", status_code=200)
async def update_client(
    client_id: int,
    name: str = Form(...),
    phone: str = Form(None),
    location: str = Form(...),
    description: str = Form(None),
    logo: UploadFile = File(None),
):
    client = query("SELECT * FROM clients WHERE id = %s", (client_id,), fetchone=True)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    logo_filename = client["logo"]
    if logo:
        if not logo.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")
        ext = logo.filename.split(".")[-1]
        logo_filename = f"{uuid.uuid4()}.{ext}"
        image = Image.open(logo.file)
        image.thumbnail((300, 300))
        image.save(os.path.join(UPLOAD_DIR, logo_filename))

    query(
        "UPDATE clients SET name=%s, phone=%s, location=%s, description=%s, logo=%s WHERE id=%s",
        (name, phone, location, description, logo_filename, client_id)
    )
    return {"message": "Client updated"}


@app.delete("/client/{client_id}", status_code=200)
def delete_client(client_id: int):
    client = query("SELECT * FROM clients WHERE id = %s", (client_id,), fetchone=True)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    query("DELETE FROM clients WHERE id = %s", (client_id,))
    return {"message": "Client deleted"}


# ─────────────────────────────────────────────
# CYCLES
# ─────────────────────────────────────────────

@app.get("/cycles", status_code=200)
def get_cycles():
    return query("""
        SELECT cy.*,
            s.name AS supplier_name,
            COALESCE(SUM(o.total_weight_kg), 0) AS weight_distributed,
            cy.total_weight_kg - COALESCE(SUM(o.total_weight_kg), 0) AS weight_remaining,
            COALESCE(SUM(o.total_weight_kg * o.price_per_kg), 0) AS revenue
        FROM cycles cy
        LEFT JOIN suppliers s ON s.id = cy.supplier_id
        LEFT JOIN orders o ON o.cycle_id = cy.id
        GROUP BY cy.id
        ORDER BY cy.start_date DESC
    """)


@app.get("/cycles/{cycle_id}", status_code=200)
def get_cycle(cycle_id: int):
    cycle = query("""
        SELECT cy.*,
            s.name AS supplier_name,
            COALESCE(SUM(o.total_weight_kg), 0) AS weight_distributed,
            cy.total_weight_kg - COALESCE(SUM(o.total_weight_kg), 0) AS weight_remaining,
            COALESCE(SUM(o.total_weight_kg * o.price_per_kg), 0) AS revenue
        FROM cycles cy
        LEFT JOIN suppliers s ON s.id = cy.supplier_id
        LEFT JOIN orders o ON o.cycle_id = cy.id
        WHERE cy.id = %s
        GROUP BY cy.id
    """, (cycle_id,), fetchone=True)

    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")

    orders = query("""
        SELECT o.*, c.name AS client_name
        FROM orders o
        JOIN clients c ON c.id = o.client_id
        WHERE o.cycle_id = %s
        ORDER BY o.order_date DESC
    """, (cycle_id,))

    # Client distribution for pie chart
    distribution = query("""
        SELECT c.name AS client_name, SUM(o.total_weight_kg) AS total_weight
        FROM orders o
        JOIN clients c ON c.id = o.client_id
        WHERE o.cycle_id = %s
        GROUP BY c.id
        ORDER BY total_weight DESC
    """, (cycle_id,))

    return { **cycle, "orders": orders, "distribution": distribution }


@app.post("/cycle", status_code=201)
def create_cycle(body: CycleRequest):
    query(
        """INSERT INTO cycles (start_date, total_weight_kg, cost_per_kg, supplier_id, status)
           VALUES (%s, %s, %s, %s, 'Open')""",
        (body.start_date, body.total_weight_kg, body.cost_per_kg, body.supplier_id)
    )

    new_cycle = query("SELECT id FROM cycles ORDER BY id DESC LIMIT 1", fetchone=True)

    # Auto-create a supplier purchase entry for the rubber rolls
    if body.supplier_id:
        total_cost = body.total_weight_kg * body.cost_per_kg
        query(
            """INSERT INTO supplier_purchases 
               (supplier_id, item_name, quantity, unit, unit_cost, total_cost, purchase_date, reference_type, reference_id)
               VALUES (%s, 'Rubber Rolls', %s, 'kg', %s, %s, %s, 'cycle', %s)""",
            (body.supplier_id, body.total_weight_kg, body.cost_per_kg, total_cost,
             body.start_date, new_cycle["id"])
        )

    return {"message": "Cycle created", "cycle_id": new_cycle["id"]}


@app.put("/cycle/{cycle_id}/close", status_code=200)
def close_cycle(cycle_id: int):
    cycle = query("SELECT * FROM cycles WHERE id = %s", (cycle_id,), fetchone=True)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")
    if cycle["status"] == "Closed":
        raise HTTPException(status_code=400, detail="Cycle is already closed")

    query(
        "UPDATE cycles SET status = 'Closed', end_date = CURDATE() WHERE id = %s",
        (cycle_id,)
    )
    return {"message": "Cycle closed"}


@app.delete("/cycle/{cycle_id}", status_code=200)
def delete_cycle(cycle_id: int):
    cycle = query("SELECT * FROM cycles WHERE id = %s", (cycle_id,), fetchone=True)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")
    query("DELETE FROM cycles WHERE id = %s", (cycle_id,))
    return {"message": "Cycle deleted"}


# ─────────────────────────────────────────────
# ORDERS
# ─────────────────────────────────────────────

@app.get("/orders", status_code=200)
def get_orders(
    client_id: Optional[int] = None,
    cycle_id: Optional[int] = None,
    status: Optional[str] = None,
):
    filters = []
    params = []

    if client_id:
        filters.append("o.client_id = %s")
        params.append(client_id)
    if cycle_id:
        filters.append("o.cycle_id = %s")
        params.append(cycle_id)
    if status:
        filters.append("o.status = %s")
        params.append(status)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""

    return query(f"""
        SELECT o.*, c.name AS client_name, cy.start_date AS cycle_start
        FROM orders o
        JOIN clients c ON c.id = o.client_id
        JOIN cycles cy ON cy.id = o.cycle_id
        {where}
        ORDER BY o.order_date DESC
    """, tuple(params))


@app.get("/orders/{order_id}", status_code=200)
def get_order(order_id: int):
    order = query("""
        SELECT o.*, c.name AS client_name, c.location AS client_location,
               c.phone AS client_phone, c.logo AS client_logo,
               cy.start_date AS cycle_start
        FROM orders o
        JOIN clients c ON c.id = o.client_id
        JOIN cycles cy ON cy.id = o.cycle_id
        WHERE o.id = %s
    """, (order_id,), fetchone=True)

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    rolls = query("SELECT * FROM order_rolls WHERE order_id = %s ORDER BY roll_number", (order_id,))
    receipt = query("SELECT * FROM receipts WHERE order_id = %s", (order_id,), fetchone=True)

    return { **order, "rolls": rolls, "receipt": receipt }


@app.post("/order", status_code=201)
def create_order(body: OrderRequest):
    # Check cycle has enough weight remaining
    cycle = query("""
        SELECT cy.total_weight_kg - COALESCE(SUM(o.total_weight_kg), 0) AS weight_remaining
        FROM cycles cy
        LEFT JOIN orders o ON o.cycle_id = cy.id
        WHERE cy.id = %s
        GROUP BY cy.id
    """, (body.cycle_id,), fetchone=True)

    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")
    if cycle["weight_remaining"] < body.total_weight_kg:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough weight in cycle. Available: {cycle['weight_remaining']}kg"
        )

    query(
        """INSERT INTO orders (client_id, cycle_id, total_weight_kg, price_per_kg,
           num_rolls, order_date, delivery_date, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (body.client_id, body.cycle_id, body.total_weight_kg, body.price_per_kg,
         body.num_rolls, body.order_date, body.delivery_date, body.status)
    )

    # Get the new order id
    new_order = query("SELECT id FROM orders ORDER BY id DESC LIMIT 1", fetchone=True)

    # Auto-generate rolls with equal weight distribution
    weight_per_roll = round(body.total_weight_kg / body.num_rolls, 2)
    for i in range(1, body.num_rolls + 1):
        query(
            "INSERT INTO order_rolls (order_id, roll_number, weight_kg) VALUES (%s, %s, %s)",
            (new_order["id"], i, weight_per_roll)
        )

    return {"message": "Order created", "order_id": new_order["id"]}


@app.put("/order/{order_id}/status", status_code=200)
def update_order_status(order_id: int, status: str = Form(...)):
    order = query("SELECT * FROM orders WHERE id = %s", (order_id,), fetchone=True)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    query("UPDATE orders SET status = %s WHERE id = %s", (status, order_id))
    return {"message": "Order status updated"}


@app.delete("/order/{order_id}", status_code=200)
def delete_order(order_id: int):
    order = query("SELECT * FROM orders WHERE id = %s", (order_id,), fetchone=True)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    query("DELETE FROM order_rolls WHERE order_id = %s", (order_id,))
    query("DELETE FROM orders WHERE id = %s", (order_id,))
    return {"message": "Order deleted"}


# ─────────────────────────────────────────────
# RECEIPTS
# ─────────────────────────────────────────────

@app.get("/receipts", status_code=200)
def get_receipts():
    return query("""
        SELECT r.*, o.total_weight_kg, o.price_per_kg, o.order_date,
               c.name AS client_name, c.location AS client_location
        FROM receipts r
        JOIN orders o ON o.id = r.order_id
        JOIN clients c ON c.id = o.client_id
        ORDER BY r.createdate DESC
    """)


@app.get("/receipts/{receipt_id}", status_code=200)
def get_receipt(receipt_id: int):
    receipt = query("""
        SELECT r.*, o.total_weight_kg, o.price_per_kg, o.num_rolls, o.order_date,
               c.name AS client_name, c.location AS client_location, c.phone AS client_phone
        FROM receipts r
        JOIN orders o ON o.id = r.order_id
        JOIN clients c ON c.id = o.client_id
        WHERE r.id = %s
    """, (receipt_id,), fetchone=True)

    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    rolls = query(
        "SELECT * FROM order_rolls WHERE order_id = %s ORDER BY roll_number",
        (receipt["order_id"],)
    )

    return { **receipt, "rolls": rolls }


@app.post("/receipt", status_code=201)
def create_receipt(body: ReceiptRequest):
    order = query("SELECT * FROM orders WHERE id = %s", (body.order_id,), fetchone=True)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    existing = query("SELECT id FROM receipts WHERE order_id = %s", (body.order_id,), fetchone=True)
    if existing:
        raise HTTPException(status_code=400, detail="Receipt already exists for this order")

    # Generate receipt number: RCP-YYYYMMDD-XXXX
    from datetime import date
    count = query("SELECT COUNT(*) as count FROM receipts", fetchone=True)
    receipt_number = f"RCP-{date.today().strftime('%Y%m%d')}-{str(count['count'] + 1).zfill(4)}"

    query(
        """INSERT INTO receipts (order_id, receipt_number, payment_method, amount_paid, transport_cost, balance)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (body.order_id, receipt_number, body.payment_method,
         body.amount_paid, body.transport_cost, body.balance)
    )

    # Auto mark order as completed
    query("UPDATE orders SET status = 'Completed' WHERE id = %s", (body.order_id,))

    return {"message": "Receipt created", "receipt_number": receipt_number}




# ─────────────────────────────────────────────
# SUPPLIERS
# ─────────────────────────────────────────────

@app.get("/suppliers", status_code=200)
def get_suppliers():
    return query("""
        SELECT s.*,
            COALESCE(SUM(sp.total_cost), 0) AS total_purchased,
            COALESCE(SUM(pay.amount), 0) AS total_paid,
            COALESCE(SUM(sp.total_cost), 0) - COALESCE(SUM(pay.amount), 0) AS balance_due
        FROM suppliers s
        LEFT JOIN supplier_purchases sp ON sp.supplier_id = s.id
        LEFT JOIN supplier_payments pay ON pay.supplier_id = s.id
        GROUP BY s.id
        ORDER BY s.name ASC
    """)


@app.get("/suppliers/{supplier_id}", status_code=200)
def get_supplier(supplier_id: int):
    supplier = query("SELECT * FROM suppliers WHERE id = %s", (supplier_id,), fetchone=True)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    # All purchases from this supplier (rubber rolls from cycles + manual items)
    purchases = query("""
        SELECT sp.*, 
            CASE WHEN sp.reference_type = 'cycle' THEN CONCAT('Cycle #', sp.reference_id)
                 ELSE NULL END AS cycle_ref
        FROM supplier_purchases sp
        WHERE sp.supplier_id = %s
        ORDER BY sp.purchase_date DESC
    """, (supplier_id,))

    # All payments made to this supplier
    payments = query("""
        SELECT * FROM supplier_payments
        WHERE supplier_id = %s
        ORDER BY payment_date DESC
    """, (supplier_id,))

    # Summary stats
    stats = query("""
        SELECT
            COALESCE(SUM(sp.total_cost), 0) AS total_purchased,
            COALESCE(SUM(pay.amount), 0) AS total_paid,
            COALESCE(SUM(sp.total_cost), 0) - COALESCE(SUM(pay.amount), 0) AS balance_due
        FROM suppliers s
        LEFT JOIN supplier_purchases sp ON sp.supplier_id = s.id
        LEFT JOIN supplier_payments pay ON pay.supplier_id = s.id
        WHERE s.id = %s
        GROUP BY s.id
    """, (supplier_id,), fetchone=True)

    # Breakdown by item type
    item_breakdown = query("""
        SELECT item_name,
            SUM(quantity) AS total_quantity,
            unit,
            SUM(total_cost) AS total_cost
        FROM supplier_purchases
        WHERE supplier_id = %s
        GROUP BY item_name, unit
        ORDER BY total_cost DESC
    """, (supplier_id,))

    return {
        **supplier,
        "purchases": purchases,
        "payments": payments,
        "stats": stats,
        "item_breakdown": item_breakdown
    }


@app.post("/supplier", status_code=201)
def create_supplier(body: SupplierRequest):
    query(
        "INSERT INTO suppliers (name, phone, location, notes) VALUES (%s, %s, %s, %s)",
        (body.name, body.phone, body.location, body.notes)
    )
    return {"message": "Supplier created"}


@app.put("/supplier/{supplier_id}", status_code=200)
def update_supplier(supplier_id: int, body: SupplierRequest):
    supplier = query("SELECT * FROM suppliers WHERE id = %s", (supplier_id,), fetchone=True)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    query(
        "UPDATE suppliers SET name=%s, phone=%s, location=%s, notes=%s WHERE id=%s",
        (body.name, body.phone, body.location, body.notes, supplier_id)
    )
    return {"message": "Supplier updated"}


@app.delete("/supplier/{supplier_id}", status_code=200)
def delete_supplier(supplier_id: int):
    supplier = query("SELECT * FROM suppliers WHERE id = %s", (supplier_id,), fetchone=True)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    query("DELETE FROM suppliers WHERE id = %s", (supplier_id,))
    return {"message": "Supplier deleted"}


# ─── Supplier Purchases (ink, tape, cones, etc.) ───

@app.post("/supplier/purchase", status_code=201)
def add_supplier_purchase(body: SupplierPurchaseRequest):
    supplier = query("SELECT * FROM suppliers WHERE id = %s", (body.supplier_id,), fetchone=True)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    total_cost = body.quantity * body.unit_cost
    query(
        """INSERT INTO supplier_purchases 
           (supplier_id, item_name, quantity, unit, unit_cost, total_cost, purchase_date, reference_type, notes)
           VALUES (%s, %s, %s, %s, %s, %s, %s, 'manual', %s)""",
        (body.supplier_id, body.item_name, body.quantity, body.unit,
         body.unit_cost, total_cost, body.purchase_date, body.notes)
    )
    return {"message": "Purchase recorded"}


@app.delete("/supplier/purchase/{purchase_id}", status_code=200)
def delete_supplier_purchase(purchase_id: int):
    purchase = query("SELECT * FROM supplier_purchases WHERE id = %s", (purchase_id,), fetchone=True)
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    if purchase["reference_type"] == "cycle":
        raise HTTPException(status_code=400, detail="Cannot delete a cycle-linked purchase. Delete the cycle instead.")
    query("DELETE FROM supplier_purchases WHERE id = %s", (purchase_id,))
    return {"message": "Purchase deleted"}


# ─── Supplier Payments ───

@app.post("/supplier/payment", status_code=201)
def add_supplier_payment(body: SupplierPaymentRequest):
    supplier = query("SELECT * FROM suppliers WHERE id = %s", (body.supplier_id,), fetchone=True)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    query(
        """INSERT INTO supplier_payments (supplier_id, amount, payment_method, payment_date, notes)
           VALUES (%s, %s, %s, %s, %s)""",
        (body.supplier_id, body.amount, body.payment_method, body.payment_date, body.notes)
    )
    return {"message": "Payment recorded"}


@app.delete("/supplier/payment/{payment_id}", status_code=200)
def delete_supplier_payment(payment_id: int):
    payment = query("SELECT * FROM supplier_payments WHERE id = %s", (payment_id,), fetchone=True)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    query("DELETE FROM supplier_payments WHERE id = %s", (payment_id,))
    return {"message": "Payment deleted"}




@app.get("/dashboard", status_code=200)
def dashboard():
    active_cycles = query(
        "SELECT COUNT(*) as count FROM cycles WHERE status = 'Open'", fetchone=True
    )
    total_clients = query("SELECT COUNT(*) as count FROM clients", fetchone=True)

    monthly_revenue = query("""
        SELECT COALESCE(SUM(o.total_weight_kg * o.price_per_kg), 0) AS revenue
        FROM orders o
        WHERE MONTH(o.order_date) = MONTH(CURDATE())
        AND YEAR(o.order_date) = YEAR(CURDATE())
    """, fetchone=True)

    total_stock = query("""
        SELECT COALESCE(SUM(cy.total_weight_kg) - SUM(COALESCE(o_sum.distributed, 0)), 0) AS stock
        FROM cycles cy
        LEFT JOIN (
            SELECT cycle_id, SUM(total_weight_kg) AS distributed
            FROM orders GROUP BY cycle_id
        ) o_sum ON o_sum.cycle_id = cy.id
        WHERE cy.status = 'Open'
    """, fetchone=True)

    return {
        "active_cycles": active_cycles["count"],
        "total_clients": total_clients["count"],
        "monthly_revenue": monthly_revenue["revenue"],
        "total_stock_kg": total_stock["stock"],
    }


@app.get("/analytics", status_code=200)
def analytics():
    # Revenue per month (last 12 months)
    monthly_revenue = query("""
        SELECT DATE_FORMAT(order_date, '%Y-%m') AS month,
               SUM(total_weight_kg * price_per_kg) AS revenue,
               SUM(total_weight_kg) AS weight_sold,
               COUNT(*) AS order_count
        FROM orders
        WHERE order_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
        GROUP BY month
        ORDER BY month ASC
    """)

    # Top clients by weight this month
    top_clients_weight = query("""
        SELECT c.name, SUM(o.total_weight_kg) AS total_weight
        FROM orders o
        JOIN clients c ON c.id = o.client_id
        WHERE MONTH(o.order_date) = MONTH(CURDATE())
        AND YEAR(o.order_date) = YEAR(CURDATE())
        GROUP BY c.id
        ORDER BY total_weight DESC
        LIMIT 10
    """)

    # Top clients by revenue this month
    top_clients_revenue = query("""
        SELECT c.name, SUM(o.total_weight_kg * o.price_per_kg) AS total_revenue
        FROM orders o
        JOIN clients c ON c.id = o.client_id
        WHERE MONTH(o.order_date) = MONTH(CURDATE())
        AND YEAR(o.order_date) = YEAR(CURDATE())
        GROUP BY c.id
        ORDER BY total_revenue DESC
        LIMIT 10
    """)

    # Inventory summary
    inventory = query("""
        SELECT
            COALESCE(SUM(cy.total_weight_kg), 0) AS total_purchased,
            COALESCE(SUM(COALESCE(o_sum.distributed, 0)), 0) AS total_sold,
            COALESCE(SUM(cy.total_weight_kg) - SUM(COALESCE(o_sum.distributed, 0)), 0) AS current_stock
        FROM cycles cy
        LEFT JOIN (
            SELECT cycle_id, SUM(total_weight_kg) AS distributed
            FROM orders GROUP BY cycle_id
        ) o_sum ON o_sum.cycle_id = cy.id
    """, fetchone=True)

    return {
        "monthly_revenue": monthly_revenue,
        "top_clients_weight": top_clients_weight,
        "top_clients_revenue": top_clients_revenue,
        "inventory": inventory,
    }