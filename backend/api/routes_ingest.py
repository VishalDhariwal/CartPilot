import os
import csv
import io
import json
import uuid
import re
import urllib.request
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query, BackgroundTasks
from fastapi.responses import PlainTextResponse
from backend.db import get_db, is_postgres, get_database_url
from backend.engine.mandates import create_audit_log

router = APIRouter(prefix="/api/catalog", tags=["Catalog Ingestion"])


# ─── Pydantic Request Models ────────────────────────────────────────────────
class ApiKeyIngestRequest(BaseModel):
    api_key: str
    provider: Optional[str] = "dummyjson"  # "dummyjson", "custom_api", "mock_store"
    endpoint_url: Optional[str] = None
    limit: Optional[int] = 200
    clear_existing: Optional[bool] = False


class ClearCatalogRequest(BaseModel):
    confirm: bool = False


# ─── Helper: Compute Embeddings & Compatibility Graph ───────────────────────
def _post_process_catalog(skus: List[str], texts_to_embed: List[str]):
    """
    Computes dense vector embeddings and initializes category compatibility graphs.
    """
    if not skus or not texts_to_embed:
        return

    conn = get_db()
    cursor = conn.cursor()
    try:
        # 1. Dense SentenceTransformer embeddings
        try:
            from backend.recommendations.embedding_engine import get_model
            model = get_model()
            if model is not None:
                embeddings = model.encode(texts_to_embed, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
                updates = [(json.dumps(emb.tolist()), sku) for emb, sku in zip(embeddings, skus)]
                cursor.executemany("UPDATE catalog SET embedding = ? WHERE sku = ?", updates)
                conn.commit()
                print(f"✅ Generated {len(updates)} dense vector embeddings for PostgreSQL catalog.")
        except Exception as emb_err:
            print(f"⚠️ Non-blocking embedding generation error: {emb_err}")

        # 2. Update category compatibility graph if not yet seeded
        try:
            cursor.execute("SELECT COUNT(*) FROM category_compatibility")
            res = cursor.fetchone()
            cc_count = list(res.values())[0] if isinstance(res, dict) else (res[0] if res else 0)
            if cc_count == 0:
                conn.close()
                from backend.recommendations.scalable_engine import generate_category_compatibility
                generate_category_compatibility()
                return
        except Exception as cat_err:
            print(f"⚠️ Category compatibility refresh notice: {cat_err}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ─── 1. Status & Health Check Endpoint ──────────────────────────────────────
@router.get("/ingest/status")
def get_catalog_ingest_status():
    """
    Returns the active database engine (PostgreSQL), connection status,
    catalog size, category breakdown, and whether ingestion is needed.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        db_url = get_database_url()
        # Sanitize password from display
        db_display = "PostgreSQL (localhost:5432/cartpilot)"
        if db_url:
            cleaned_url = re.sub(r':([^@]+)@', ':****@', db_url)
            db_display = f"PostgreSQL ({cleaned_url.split('/')[-1] if '/' in cleaned_url else 'cartpilot'})"

        cursor.execute("SELECT COUNT(*) FROM catalog")
        count_row = cursor.fetchone()
        product_count = list(count_row.values())[0] if isinstance(count_row, dict) else (count_row[0] if count_row else 0)

        cursor.execute("SELECT DISTINCT category FROM catalog WHERE category IS NOT NULL AND category != '' ORDER BY category ASC")
        categories = [r["category"] for r in cursor.fetchall()]

        cursor.execute("SELECT COUNT(*) FROM catalog WHERE embedding IS NOT NULL AND embedding != ''")
        emb_row = cursor.fetchone()
        embedded_count = list(emb_row.values())[0] if isinstance(emb_row, dict) else (emb_row[0] if emb_row else 0)

        return {
            "database_engine": "postgresql" if is_postgres() else "sqlite",
            "database_display": db_display,
            "connected": True,
            "product_count": product_count,
            "category_count": len(categories),
            "categories": categories,
            "embedded_count": embedded_count,
            "is_empty": product_count == 0,
            "requires_ingestion": product_count == 0,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        return {
            "database_engine": "postgresql" if is_postgres() else "sqlite",
            "connected": False,
            "error": str(e),
            "product_count": 0,
            "is_empty": True,
            "requires_ingestion": True
        }
    finally:
        conn.close()


# ─── 2. Ingest Catalog via API Key ──────────────────────────────────────────
@router.post("/ingest/api-key")
def ingest_catalog_from_api_key(req: ApiKeyIngestRequest, background_tasks: BackgroundTasks):
    """
    Ingests store products from an external API using a provided API Key.
    Supports DummyJSON live store, custom REST catalog endpoint, or mock supplier API.
    Inserts products into PostgreSQL, computes embeddings, and logs an immutable audit event.
    """
    if not req.api_key or not req.api_key.strip():
        raise HTTPException(status_code=400, detail="API Key is required to ingest store data.")

    api_key = req.api_key.strip()
    provider = (req.provider or "dummyjson").lower()
    limit = max(10, min(req.limit or 200, 500))

    products = []
    # Route 1: Custom Endpoint
    if req.endpoint_url and req.endpoint_url.startswith("http"):
        try:
            http_req = urllib.request.Request(
                req.endpoint_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "x-api-key": api_key,
                    "User-Agent": "CartPilot-Ingestion-Engine/2.0",
                    "Accept": "application/json"
                }
            )
            with urllib.request.urlopen(http_req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                products = data if isinstance(data, list) else data.get("products", data.get("items", []))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to fetch from custom API endpoint: {str(e)}")
    else:
        # Route 2: DummyJSON Live Catalog with API Key Authentication
        target_url = f"https://dummyjson.com/products?limit={limit}"
        try:
            http_req = urllib.request.Request(
                target_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "x-api-key": api_key,
                    "User-Agent": "CartPilot-Ingestion-Engine/2.0",
                    "Accept": "application/json"
                }
            )
            with urllib.request.urlopen(http_req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                products = data.get("products", [])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to authenticate or fetch catalog from API: {str(e)}")

    if not products:
        raise HTTPException(status_code=404, detail="No products found at the supplied API endpoint.")

    conn = get_db()
    cursor = conn.cursor()
    try:
        if req.clear_existing:
            cursor.execute("DELETE FROM catalog")
            conn.commit()

        items_to_insert = []
        texts_to_embed = []
        skus = []

        for p in products:
            sku = str(p.get("sku") or p.get("id") or f"PRD-{uuid.uuid4().hex[:6].upper()}")
            name = str(p.get("title") or p.get("name") or f"Product {sku}")
            price_val = p.get("price") or p.get("price_rupees") or 10.0
            price_paise = p.get("price_paise") or round(float(price_val) * 100)
            stock = int(p.get("stock") or p.get("quantity") or 25)
            category = str(p.get("category") or "general").strip().lower()
            merchant = str(p.get("brand") or p.get("merchant") or "Store Direct")
            description = str(p.get("description") or "")
            images = p.get("images", [])
            image_url = images[0] if images else (p.get("thumbnail") or p.get("image_url") or "")
            tags = p.get("tags", [])
            tags_str = json.dumps(tags) if isinstance(tags, list) else json.dumps([tags])
            rating = float(p.get("rating", 4.0))
            boosted = 1 if rating >= 4.7 else 0

            prod_metadata = {
                "brand": merchant,
                "rating": rating,
                "weight": p.get("weight"),
                "warranty": p.get("warrantyInformation", "1 Year Warranty"),
                "shipping": p.get("shippingInformation", "Ships in 2-3 business days"),
                "returnPolicy": p.get("returnPolicy", "30 Days Free Return"),
                "images": images[:4] if images else [image_url]
            }

            embed_text = f"{name} | {description} | category: {category} | tags: {tags_str}"
            texts_to_embed.append(embed_text)
            skus.append(sku)

            items_to_insert.append((
                sku, name, price_paise, stock, category, merchant, boosted,
                1.0, "system", "", image_url, description, tags_str, json.dumps(prod_metadata)
            ))

        cursor.executemany(
            """
            INSERT INTO catalog 
            (sku, name, price_paise, stock, category, merchant, boosted, boost_weight, boost_source, boost_reason, image_url, description, tags, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (sku) DO UPDATE SET
                name = EXCLUDED.name,
                price_paise = EXCLUDED.price_paise,
                stock = EXCLUDED.stock,
                category = EXCLUDED.category,
                merchant = EXCLUDED.merchant,
                image_url = EXCLUDED.image_url,
                description = EXCLUDED.description,
                tags = EXCLUDED.tags,
                metadata = EXCLUDED.metadata
            """,
            items_to_insert
        )
        conn.commit()

        # Write immutable audit log event
        create_audit_log(
            cursor,
            ref_type="CATALOG",
            ref_id="INGEST_API",
            event="CATALOG_INGEST_API",
            detail=f"Ingested {len(items_to_insert)} products from provider '{provider}' using API Key into PostgreSQL."
        )
        conn.commit()
    finally:
        conn.close()

    # Precompute vector embeddings and category graph asynchronously
    background_tasks.add_task(_post_process_catalog, skus, texts_to_embed)

    return {
        "success": True,
        "database": "PostgreSQL",
        "provider": provider,
        "count": len(items_to_insert),
        "message": f"Successfully ingested {len(items_to_insert)} products into PostgreSQL catalog via API Key."
    }


# ─── 3. Ingest Catalog via CSV Upload ───────────────────────────────────────
@router.post("/ingest/csv")
async def ingest_catalog_from_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    clear_existing: bool = Form(False)
):
    """
    Parses and ingests an uploaded CSV file into PostgreSQL catalog.
    Supports standard CSV columns:
    sku, name, price, stock, category, merchant, image_url, description, tags
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files (.csv) are supported.")

    content = await file.read()
    try:
        text_stream = io.StringIO(content.decode("utf-8-sig"))
    except UnicodeDecodeError:
        text_stream = io.StringIO(content.decode("latin-1"))

    reader = csv.DictReader(text_stream)
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="Uploaded CSV has no header row.")

    # Normalize header mapping
    header_map = {}
    for h in reader.fieldnames:
        cleaned = h.strip().lower().replace(" ", "_")
        header_map[cleaned] = h

    items_to_insert = []
    texts_to_embed = []
    skus = []

    for row_idx, row in enumerate(reader, start=1):
        def _get(keys, default=""):
            for k in keys:
                actual_key = header_map.get(k)
                if actual_key and row.get(actual_key):
                    return str(row[actual_key]).strip()
            return default

        name = _get(["name", "title", "product_name"])
        if not name:
            continue

        sku = _get(["sku", "product_id", "id", "item_id"])
        if not sku:
            cat_prefix = re.sub(r'[^A-Z0-9]', '', _get(["category", "cat"], "GEN").upper())[:3] or "PRD"
            sku = f"{cat_prefix}-{uuid.uuid4().hex[:6].upper()}"

        # Parse price
        price_str = _get(["price", "price_rupees", "amount", "unit_price", "price_paise"], "0")
        try:
            price_float = float(re.sub(r'[^\d.]', '', price_str) or 0)
            # If price > 100000 and has no decimal, could already be in paise
            if "paise" in header_map or price_float > 100000:
                price_paise = int(price_float)
            else:
                price_paise = round(price_float * 100)
        except Exception:
            price_paise = 100000

        # Parse stock
        stock_str = _get(["stock", "quantity", "inventory", "units"], "25")
        try:
            stock = int(re.sub(r'[^\d]', '', stock_str) or 25)
        except Exception:
            stock = 25

        category = _get(["category", "type", "dept", "department"], "general").lower()
        merchant = _get(["merchant", "brand", "vendor", "seller"], "Store Direct")
        description = _get(["description", "desc", "details"], "")
        image_url = _get(["image_url", "image", "thumbnail", "photo", "img"], "")
        tags_raw = _get(["tags", "keywords", "categories"], "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        prod_metadata = {
            "brand": merchant,
            "source": "csv_import",
            "imported_at": datetime.utcnow().isoformat() + "Z"
        }

        embed_text = f"{name} | {description} | category: {category} | tags: {', '.join(tags)}"
        texts_to_embed.append(embed_text)
        skus.append(sku)

        items_to_insert.append((
            sku, name, price_paise, stock, category, merchant, 0,
            1.0, "system", "", image_url, description, json.dumps(tags), json.dumps(prod_metadata)
        ))

    if not items_to_insert:
        raise HTTPException(status_code=400, detail="No valid product rows could be parsed from the CSV.")

    conn = get_db()
    cursor = conn.cursor()
    try:
        if clear_existing:
            cursor.execute("DELETE FROM catalog")
            conn.commit()

        cursor.executemany(
            """
            INSERT INTO catalog 
            (sku, name, price_paise, stock, category, merchant, boosted, boost_weight, boost_source, boost_reason, image_url, description, tags, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (sku) DO UPDATE SET
                name = EXCLUDED.name,
                price_paise = EXCLUDED.price_paise,
                stock = EXCLUDED.stock,
                category = EXCLUDED.category,
                merchant = EXCLUDED.merchant,
                image_url = EXCLUDED.image_url,
                description = EXCLUDED.description,
                tags = EXCLUDED.tags,
                metadata = EXCLUDED.metadata
            """,
            items_to_insert
        )
        conn.commit()

        create_audit_log(
            cursor,
            ref_type="CATALOG",
            ref_id="INGEST_CSV",
            event="CATALOG_INGEST_CSV",
            detail=f"Imported {len(items_to_insert)} products from file '{file.filename}' into PostgreSQL catalog."
        )
        conn.commit()
    finally:
        conn.close()

    # Precompute vector embeddings and category graph asynchronously
    background_tasks.add_task(_post_process_catalog, skus, texts_to_embed)

    return {
        "success": True,
        "database": "PostgreSQL",
        "filename": file.filename,
        "count": len(items_to_insert),
        "message": f"Successfully parsed and ingested {len(items_to_insert)} products into PostgreSQL catalog."
    }


# ─── 4. Download Sample CSV Template ────────────────────────────────────────
@router.get("/ingest/template")
def download_sample_csv_template():
    """
    Returns a downloadable sample CSV template for merchant store catalog imports.
    """
    sample_csv = (
        "sku,name,price,stock,category,merchant,description,image_url,tags\n"
        "ELEC-LAP-001,MacBook Pro 16 M3 Max,249999.00,15,laptops,Apple Direct,Supercharged by M3 Max chip with 16-core CPU and Liquid Retina XDR display.,https://cdn.dummyjson.com/products/images/laptops/Apple%20MacBook%20Pro%2014%20Inch%20Space%20Grey/1.png,\"apple,laptop,m3,creator\"\n"
        "GROC-TEA-002,Organic Darjeeling Green Tea 250g,499.00,80,groceries,Himalayan Organics,Single estate hand-plucked green tea leaves rich in natural antioxidants.,https://cdn.dummyjson.com/products/images/groceries/Green%20Tea/1.png,\"tea,organic,healthy,beverages\"\n"
        "FASH-SNK-003,Air Jordan Retro High OG,16999.00,25,mens-shoes,Nike Sportswear,Iconic basketball silhouette crafted with premium genuine leather and Air-Sole cushioning.,https://cdn.dummyjson.com/products/images/mens-shoes/Nike%20Air%20Jordan%201%20Retro%20High%20OG/1.png,\"sneakers,nike,jordan,shoes\"\n"
    )
    return PlainTextResponse(
        content=sample_csv,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cartpilot_sample_catalog.csv"}
    )


# ─── 5. 1-Click Demo Seed Endpoint ──────────────────────────────────────────
@router.post("/ingest/sample")
def seed_sample_catalog():
    """
    1-click instant onboarding seed to populate 194 rich catalog products into PostgreSQL.
    """
    from backend.integrations.dummyjson_sync import sync_dummyjson_catalog
    count = sync_dummyjson_catalog()
    return {
        "success": True,
        "database": "PostgreSQL",
        "count": count,
        "message": f"Successfully seeded {count} demo products into PostgreSQL catalog."
    }


# ─── 6. Clear Catalog Endpoint ──────────────────────────────────────────────
@router.delete("/clear")
def clear_catalog(req: ClearCatalogRequest):
    """
    Clears products from the PostgreSQL catalog to allow a fresh import.
    """
    if not req.confirm:
        raise HTTPException(status_code=400, detail="Confirmation required to clear the catalog.")

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM catalog")
        conn.commit()

        create_audit_log(
            cursor,
            ref_type="CATALOG",
            ref_id="RESET",
            event="CATALOG_CLEARED",
            detail="Merchant cleared all products from the catalog table for fresh ingestion."
        )
        conn.commit()
        return {"success": True, "message": "Catalog cleared successfully."}
    finally:
        conn.close()
