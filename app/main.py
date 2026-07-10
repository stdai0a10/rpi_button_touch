from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.config import load_config
from app.gpio import initialize_gpio_service, shutdown_gpio_service
from app.routes import api, web
from app.scheduler import start_job_scheduler, stop_job_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    initialize_gpio_service()
    scheduler = start_job_scheduler()
    try:
        yield
    finally:
        stop_job_scheduler(scheduler)
        shutdown_gpio_service()


config = load_config()

app = FastAPI(
    title=config.name,
    lifespan=lifespan,
    docs_url="/docs" if config.env != "production" else None,
    redoc_url="/redoc" if config.env != "production" else None,
    openapi_url="/openapi.json" if config.env != "production" else None,
)

app.include_router(api.router)
app.include_router(web.router)

if config.env != "production" and config.test_mode:
    from app.routes import test # pylint: disable=import-outside-toplevel
    app.include_router(test.router)
