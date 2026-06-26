from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.gpio import initialize_gpio_service, shutdown_gpio_service
from app.routes import api, web, test
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


app = FastAPI(title="Button Clicker RPI", lifespan=lifespan)

app.include_router(api.router)
app.include_router(web.router)
app.include_router(test.router)
