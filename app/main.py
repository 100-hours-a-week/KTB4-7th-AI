import logging

from fastapi import FastAPI

from app.api import chat, forecast, insights, solutions
from app.core.config import missing_required, settings
from app.core.errors import register_error_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="맴매 AI 서버", version="0.1.0")

_missing = missing_required(settings)
if _missing:
    logging.getLogger(__name__).error(
        "환경변수가 비어 있다 — 배포 설정을 확인한다: %s", ", ".join(_missing)
    )
register_error_handlers(app)
app.include_router(chat.router)
app.include_router(forecast.router)
app.include_router(insights.router)
app.include_router(solutions.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
