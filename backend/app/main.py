"""ChangeGuard Backend Application Entrypoint."""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from backend.app.core.config import settings
from backend.app.core.exceptions import ChangeGuardException
from backend.app.api.v1.router import api_v1_router
from backend.app.monitoring.poller import get_polling_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start background monitoring if enabled by default
    worker = get_polling_worker()
    if settings.MONITORING_ENABLED_BY_DEFAULT:
        worker.start()
    yield
    # Shutdown: Stop worker cleanly
    worker.stop()


def create_application() -> FastAPI:
    """Factory creating and configuring the ChangeGuard FastAPI instance."""
    application = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="Intent-Aware Software Change Impact and Regression Analysis Engine",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS configuration
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global Exception Handlers
    @application.exception_handler(ChangeGuardException)
    async def changeguard_exception_handler(request: Request, exc: ChangeGuardException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.message,
                "status_code": exc.status_code,
                "details": exc.details,
            },
        )

    # Health Checks
    @application.get("/health", tags=["Health"])
    @application.get(f"{settings.API_V1_PREFIX}/health", tags=["Health"])
    def health_check():
        return {
            "status": "healthy",
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
        }

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    index_html = os.path.join(static_dir, "index.html")

    if os.path.exists(static_dir):
        application.mount("/static", StaticFiles(directory=static_dir), name="static")

    @application.get("/dashboard", tags=["Dashboard"])
    @application.get("/", tags=["Dashboard"])
    def get_dashboard():
        if os.path.exists(index_html):
            return FileResponse(index_html)
        return {
            "message": "ChangeGuard API is running. Dashboard HTML not found in static directory.",
            "docs": "/docs",
            "health": "/health",
        }

    # Mount API routers
    application.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)

    return application


app = create_application()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
