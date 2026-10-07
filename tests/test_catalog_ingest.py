import pytest
import io
from fastapi.testclient import TestClient
from backend.main import app
from backend.db import get_db, is_postgres

client = TestClient(app)


def test_postgres_active():
    """Verify that PostgreSQL is the active database engine."""
    assert is_postgres() is True


def test_ingest_status_endpoint():
    """Verify the /api/catalog/ingest/status endpoint returns PostgreSQL engine status."""
    res = client.get("/api/catalog/ingest/status")
    assert res.status_code == 200
    data = res.json()
    assert data["database_engine"] == "postgresql"
    assert data["connected"] is True
    assert "cartpilot" in data["database_display"].lower()
    assert isinstance(data["product_count"], int)
    assert isinstance(data["category_count"], int)
    assert isinstance(data["categories"], list)


def test_csv_template_download():
    """Verify that merchants can download the sample CSV template."""
    res = client.get("/api/catalog/ingest/template")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "sku,name,price,stock,category" in res.text


def test_ingest_csv_endpoint():
    """Verify uploading a CSV file ingests products into the PostgreSQL catalog."""
    csv_content = (
        "sku,name,price,stock,category,merchant,description,image_url,tags\n"
        "TEST-INGEST-001,PostgreSQL Unit Test Widget,1299.00,40,electronics,TestMerchant,A high quality testing widget.,https://dummyjson.com/widget.png,\"test,widget\"\n"
        "TEST-INGEST-002,PostgreSQL Organic Apples,250.00,100,groceries,OrganicFarm,Crisp fresh orchard apples.,https://dummyjson.com/apples.png,\"fruit,organic\"\n"
    )

    files = {"file": ("ingest_test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    res = client.post("/api/catalog/ingest/csv", files=files, data={"clear_existing": "false"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["database"] == "PostgreSQL"
    assert data["count"] == 2

    # Verify rows exist in PostgreSQL
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT sku, name, price_paise, category FROM catalog WHERE sku IN ('TEST-INGEST-001', 'TEST-INGEST-002')")
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) == 2
    sku_map = {r["sku"]: r for r in rows}
    assert sku_map["TEST-INGEST-001"]["name"] == "PostgreSQL Unit Test Widget"
    assert sku_map["TEST-INGEST-001"]["price_paise"] == 129900
    assert sku_map["TEST-INGEST-002"]["category"] == "groceries"


def test_ingest_api_key_endpoint():
    """Verify that the API key ingestion endpoint authenticates and ingests catalog items."""
    res = client.post(
        "/api/catalog/ingest/api-key",
        json={"api_key": "test_dummy_key_12345", "provider": "dummyjson", "limit": 10, "clear_existing": False}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["database"] == "PostgreSQL"
    assert data["count"] >= 1
