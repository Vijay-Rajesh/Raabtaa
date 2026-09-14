from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, family, journeys, locations, notifications, places, safety, schedules, test, users, webhooks
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s in %s mode (WhatsApp mock mode: %s)",
                settings.APP_NAME, settings.ENVIRONMENT, settings.WHATSAPP_MOCK_MODE)
    yield
    logger.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    description="Backend for the SafeReach Automatic Safe Arrival Agent.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception while processing request: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal error occurred. Please try again later."},
    )


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(family.router)
app.include_router(places.router)
app.include_router(locations.router)
app.include_router(journeys.router)
app.include_router(notifications.router)
app.include_router(schedules.router)
app.include_router(webhooks.router)
app.include_router(safety.router)

if not settings.is_production:
    app.include_router(test.router)


@app.get("/", tags=["Health"])
async def root() -> dict:
    return {"app": settings.APP_NAME, "status": "ok", "environment": settings.ENVIRONMENT}


@app.get("/health", tags=["Health"])
async def health() -> dict:
    return {"status": "healthy"}
