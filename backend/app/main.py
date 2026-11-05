import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analyses, health
from app.core.config import settings
from app.core.errors import register_exception_handlers

# 앱 로그(비용 추적, 오류 기록)가 보이도록 INFO 수준으로 맞춘다. (기본은 WARNING이라 INFO가 버려진다)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Answer Auditor API")
register_exception_handlers(app)

# CORS: 브라우저는 다른 주소(프론트)의 API 호출을 기본적으로 막습니다.
# 허용할 프론트 주소만 명시적으로 열어 줍니다. ("*"는 쓰지 않음)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(analyses.router)
