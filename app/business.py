from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
from .config import SAFWAN_APP_TOKEN
from .db import connect

router = APIRouter(prefix="/api/business", tags=["business"])

def guard(authorization: Optional[str]):
    if SAFWAN_APP_TOKEN and authorization != f"Bearer {SAFWAN_APP_TOKEN}":
        raise HTTPException(401, "Unauthorized")

class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=160)
    notes: str = Field(default="", max_length=2000)

class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    sku: str = Field(min_length=1, max_length=80)
    unit_price: float = Field(ge=0)
    stock_qty: float = Field(default=0, ge=0)
    low_stock_at: float = Field(default=5, ge=0)

class SaleLine(BaseModel):
    product_id: int
    quantity: float = Field(gt=0)

class SaleIn(BaseModel):
    customer_id: Optional[int] = None
    items: list[SaleLine] = Field(min_length=1, max_length=100)

@router.get("/dashboard")
def dashboard(authorization: Optional[str] = Header(default=None)):
    guard(authorization)
    with connect() as con:
        products = con.execute("SELECT COUNT(*) n, COALESCE(SUM(stock_qty*unit_price),0) value FROM products").fetchone()
        customers = con.execute("SELECT COUNT(*) n FROM customers").fetchone()["n"]
        low = con.execute("SELECT COUNT(*) n FROM products WHERE stock_qty <= low_stock_at").fetchone()["n"]
        sales = con.execute("SELECT COUNT(*) n, COALESCE(SUM(total),0) total FROM sales WHERE status='confirmed'").fetchone()
        return {"products":products["n"],"inventory_value":round(products["value"],2),
                "customers":customers,"low_stock_products":low,
                "confirmed_sales_count":sales["n"],"confirmed_sales_total":round(sales["total"],2)}

@router.get("/customers")
def customers(authorization: Optional[str] = Header(default=None)):
    guard(authorization)
    with connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM customers ORDER BY id DESC LIMIT 500")]

@router.post("/customers")
def add_customer(body: CustomerIn, authorization: Optional[str] = Header(default=None)):
    guard(authorization)
    with connect() as con:
        cur=con.execute("INSERT INTO customers(name,phone,email,notes) VALUES(?,?,?,?)",
                        (body.name,body.phone,body.email,body.notes))
        return {"id":cur.lastrowid,"message":"Customer saved"}

@router.get("/products")
def products(authorization: Optional[str] = Header(default=None)):
    guard(authorization)
    with connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM products ORDER BY name LIMIT 1000")]

@router.post("/products")
def add_product(body: ProductIn, authorization: Optional[str] = Header(default=None)):
    guard(authorization)
    with connect() as con:
        try:
            cur=con.execute("INSERT INTO products(name,sku,unit_price,stock_qty,low_stock_at) VALUES(?,?,?,?,?)",
                (body.name,body.sku,body.unit_price,body.stock_qty,body.low_stock_at))
        except Exception as exc:
            if "UNIQUE" in str(exc): raise HTTPException(409,"SKU already exists")
            raise
        return {"id":cur.lastrowid,"message":"Product saved"}

@router.post("/sales")
def create_sale(body: SaleIn, authorization: Optional[str] = Header(default=None)):
    guard(authorization)
    with connect() as con:
        if body.customer_id is not None and not con.execute("SELECT id FROM customers WHERE id=?",(body.customer_id,)).fetchone():
            raise HTTPException(404,"Customer not found")
        total=0.0
        resolved=[]
        for line in body.items:
            p=con.execute("SELECT id,name,unit_price,stock_qty FROM products WHERE id=?",(line.product_id,)).fetchone()
            if not p: raise HTTPException(404,f"Product {line.product_id} not found")
            if p["stock_qty"] < line.quantity:
                raise HTTPException(409,f"Insufficient stock for {p['name']}")
            amount=round(p["unit_price"]*line.quantity,2)
            total+=amount
            resolved.append((p["id"],line.quantity,p["unit_price"],amount))
        ref=f"SA-{__import__('uuid').uuid4().hex[:10].upper()}"
        cur=con.execute("INSERT INTO sales(customer_id,reference,status,total) VALUES(?,?,?,?)",
                        (body.customer_id,ref,"draft",round(total,2)))
        sale_id=cur.lastrowid
        for pid,qty,price,amount in resolved:
            con.execute("INSERT INTO sale_items(sale_id,product_id,quantity,unit_price,line_total) VALUES(?,?,?,?,?)",
                        (sale_id,pid,qty,price,amount))
        return {"sale_id":sale_id,"reference":ref,"status":"draft","total":round(total,2),
                "message":"Draft created; stock has not been reduced"}

@router.post("/sales/{sale_id}/confirm")
def confirm_sale(sale_id: int, authorization: Optional[str] = Header(default=None)):
    guard(authorization)
    with connect() as con:
        sale=con.execute("SELECT * FROM sales WHERE id=?",(sale_id,)).fetchone()
        if not sale: raise HTTPException(404,"Sale not found")
        if sale["status"]!="draft": raise HTTPException(409,"Only draft sales can be confirmed")
        items=con.execute("SELECT product_id,quantity FROM sale_items WHERE sale_id=?",(sale_id,)).fetchall()
        for item in items:
            p=con.execute("SELECT name,stock_qty FROM products WHERE id=?",(item["product_id"],)).fetchone()
            if p["stock_qty"] < item["quantity"]:
                raise HTTPException(409,f"Insufficient stock for {p['name']}")
        for item in items:
            con.execute("UPDATE products SET stock_qty=stock_qty-?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (item["quantity"],item["product_id"]))
        con.execute("UPDATE sales SET status='confirmed' WHERE id=?",(sale_id,))
        return {"sale_id":sale_id,"status":"confirmed","total":sale["total"],"message":"Sale confirmed and stock deducted"}

@router.get("/sales")
def sales(authorization: Optional[str] = Header(default=None)):
    guard(authorization)
    with connect() as con:
        rows=con.execute("""SELECT s.id,s.reference,s.status,s.total,s.created_at,c.name customer
            FROM sales s LEFT JOIN customers c ON c.id=s.customer_id ORDER BY s.id DESC LIMIT 500""").fetchall()
        return [dict(r) for r in rows]


def get_business_context_data():
    """Return a compact, privacy-conscious snapshot for the AI prompt."""
    with connect() as con:
        products = con.execute("SELECT COUNT(*) n, COALESCE(SUM(stock_qty*unit_price),0) value FROM products").fetchone()
        customers = con.execute("SELECT COUNT(*) n FROM customers").fetchone()["n"]
        low_stock = [dict(r) for r in con.execute(
            "SELECT name,sku,stock_qty,low_stock_at FROM products WHERE stock_qty <= low_stock_at ORDER BY stock_qty ASC LIMIT 15"
        )]
        sales = con.execute("SELECT COUNT(*) n, COALESCE(SUM(total),0) total FROM sales WHERE status='confirmed'").fetchone()
        recent = [dict(r) for r in con.execute(
            "SELECT reference,status,total,created_at FROM sales ORDER BY id DESC LIMIT 5"
        )]
        low_count = con.execute("SELECT COUNT(*) n FROM products WHERE stock_qty <= low_stock_at").fetchone()["n"]
        return {
            "product_count": products["n"],
            "inventory_value": round(products["value"], 2),
            "customer_count": customers,
            "low_stock_count": low_count,
            "low_stock_products": low_stock,
            "confirmed_sales_count": sales["n"],
            "confirmed_sales_total": round(sales["total"], 2),
            "recent_sales": recent,
        }

@router.get("/context")
def business_context(authorization: Optional[str] = Header(default=None)):
    guard(authorization)
    return get_business_context_data()
