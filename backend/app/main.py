"""ChangeGuard Backend Application Entrypoint."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.app.core.config import settings
from backend.app.core.exceptions import ChangeGuardException
from backend.app.api.v1.router import api_v1_router


def create_application() -> FastAPI:
    """Factory creating and configuring the ChangeGuard FastAPI instance."""
    application = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="Intent-Aware Software Change Impact and Regression Analysis Engine",
        docs_url="/docs",
        redoc_url="/redoc",
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

    @application.get("/", tags=["Root"])
    def root():
        return {
            "message": "Welcome to ChangeGuard API",
            "description": "Intent-Aware Software Change Impact and Regression Analysis Engine",
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
