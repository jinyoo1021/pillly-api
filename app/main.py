import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

# Sentry reset (When DSN)
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        traces_sample_rate=0.2,
    )

app = FastAPI(
    title="Pillly API",
    version="1.0.0",
    # Disable Swagger in Productions
    docs_url="/docs" if settings.APP_ENV == "development" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.APP_ENV == "development" else [settings.API_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "env": settings.APP_ENV}


# Routers registration (v1)
from app.routers import auth, medications, schedules, dose, notifications

app.include_router(auth.router,          prefix="/v1/auth",          tags=["auth"])
app.include_router(medications.router,   prefix="/v1/medications",   tags=["medications"])
app.include_router(schedules.router,     prefix="/v1/schedules",     tags=["schedules"])
app.include_router(dose.router,          prefix="/v1/dose",          tags=["dose"])
app.include_router(notifications.router, prefix="/v1/notifications", tags=["notifications"])