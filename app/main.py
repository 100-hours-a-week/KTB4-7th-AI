import logging

from fastapi import FastAPI

from app.core.errors import register_error_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="맴매 AI 서버", version="0.1.0")
register_error_handlers(app)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
