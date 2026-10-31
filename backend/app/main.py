from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import api_router
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.db.models import Merchant


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure database schema is created on startup
    Base.metadata.create_all(bind=engine)
    
    # Auto-seed initial demo data if database is fresh
    db = SessionLocal()
    try:
        merchant = db.query(Merchant).first()
        if not merchant:
            try:
                from scripts.seed_demo_data import seed_demo_data
                seed_demo_data()
            except Exception as e:
                import logging
                logging.getLogger("uvicorn.error").warning(f"Auto-seed exception: {e}")
    finally:
        db.close()
    
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="Autonomous Multi-Agent AI Teammate for Paytm Merchants",
        lifespan=lifespan,
    )

    # CORS configuration for Merchant Mobile and Employee Web
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_origin_regex=r"https?://.*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/", include_in_schema=False)
    def root():
        return {
            "status": "online",
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "docs": "/docs",
            "health": "/health",
            "merchant_mobile_url": "http://localhost:8081",
            "employee_web_url": "http://127.0.0.1:5173",
        }

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
