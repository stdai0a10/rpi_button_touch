from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.config import load_config
from app.gpio import (
    execute_state,
    initialize_gpio_service,
    shutdown_gpio_service,
)
from app.routes import api, web
from app.scheduler import start_job_scheduler, stop_job_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    initialize_gpio_service()
    scheduler = None
    try:
        scheduler = start_job_scheduler()
        execute_state("ready")
        yield
    finally:
        try:
            stop_job_scheduler(scheduler)
        finally:
            try:
                execute_state("stop")
            finally:
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
