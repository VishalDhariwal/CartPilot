import uvicorn
from fastapi import FastAPI
from backend.db import init_db
from backend.api import routes_checkout, routes_webhook, routes_resolution

app = FastAPI(title="CartPilot API")

# Setup database on startup
@app.on_event("startup")
def startup_event():
    print("Initializing Database...")
    init_db()

# Include routers
app.include_router(routes_checkout.router, prefix="/checkout", tags=["Checkout"])
app.include_router(routes_webhook.router, prefix="/webhook", tags=["Webhook"])
app.include_router(routes_resolution.router, prefix="/resolution", tags=["Resolution"])

if __name__ == "__main__":
    print("Starting Phase 2 Server...")
    print("Endpoints:")
    print("  POST /checkout/hardcoded-checkout")
    print("  POST /webhook/razorpay")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
