from fastapi import FastAPI

from app.routes import api, web, test


app = FastAPI(title="Button Clicker RPI")

app.include_router(api.router)
app.include_router(web.router)
app.include_router(test.router)
