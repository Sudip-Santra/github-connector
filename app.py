from fastapi import FastAPI
from api.health import router as health_router

app = FastAPI(title="GitHub Connector")

app.include_router(health_router)
