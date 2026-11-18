import app.db as db
from fastapi.testclient import TestClient
from app.main import app

def test_business_inventory_and_sale_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    db.init_db()
    client = TestClient(app)

    customer = client.post("/api/business/customers", json={"name":"Test Shop"}).json()
    product = client.post("/api/business/products", json={
        "name":"Notebook","sku":"NB-001","unit_price":50,"stock_qty":10,"low_stock_at":2
    })
    assert product.status_code == 200
    product_id = product.json()["id"]

    sale = client.post("/api/business/sales", json={
        "customer_id":customer["id"],
        "items":[{"product_id":product_id,"quantity":2}]
    })
    assert sale.status_code == 200
    assert sale.json()["status"] == "draft"

    before = client.get("/api/business/products").json()[0]["stock_qty"]
    assert before == 10

    confirmed = client.post(f"/api/business/sales/{sale.json()['sale_id']}/confirm")
    assert confirmed.status_code == 200
    after = client.get("/api/business/products").json()[0]["stock_qty"]
    assert after == 8

    dashboard = client.get("/api/business/dashboard").json()
    assert dashboard["customers"] == 1
    assert dashboard["confirmed_sales_total"] == 100
