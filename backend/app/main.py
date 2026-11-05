from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health
from app.core.config import settings

app = FastAPI(title="Answer Auditor API")

# CORS: 브라우저는 다른 주소(프론트)의 API 호출을 기본적으로 막습니다.
# 허용할 프론트 주소만 명시적으로 열어 줍니다. ("*"는 쓰지 않음)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health.router)
