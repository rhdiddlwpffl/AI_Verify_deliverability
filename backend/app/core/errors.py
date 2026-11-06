"""모든 API 오류를 {"error": {"code": ..., "message": ...}} 형식으로 통일한다.

- code: 프로그램이 분기할 때 쓰는 고정 문자열
- message: 사용자에게 그대로 보여 줘도 되는 한국어 문장
메시지에는 내부 정보(키, 주소, 스택)나 사용자가 입력한 원문을 넣지 않는다.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db.session import DatabaseNotConfiguredError

logger = logging.getLogger(__name__)


_HTTP_MESSAGES = {
    400: "요청 형식이 올바르지 않습니다.",
    404: "요청한 주소를 찾을 수 없습니다.",
    405: "허용되지 않는 요청 방식입니다.",
    413: "요청이 너무 큽니다.",
}


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers  # 예: {"Retry-After": "30"}


def _error_response(
    status_code: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": {"code": code, "message": message}}, headers=headers
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # exc.errors()에는 사용자가 보낸 값('input')이 들어 있으므로 응답에 그대로 싣지 않는다.
        for err in exc.errors():
            loc = err.get("loc", ())
            if err.get("type") == "string_too_long" and loc and loc[-1] == "text":
                return _error_response(422, "input_too_long", "입력이 너무 깁니다. 더 짧게 나누어 다시 시도해 주세요.")
            if err.get("type") == "json_invalid":
                return _error_response(400, "invalid_json", "요청 형식이 올바르지 않습니다.")
        return _error_response(422, "invalid_request", "요청 내용이 올바르지 않습니다. 입력을 확인해 주세요.")

    @app.exception_handler(DatabaseNotConfiguredError)
    async def handle_db_not_configured(_: Request, exc: DatabaseNotConfiguredError) -> JSONResponse:
        logger.error("DATABASE_URL이 설정되지 않았습니다.")
        return _error_response(503, "db_not_configured", "기록 기능이 아직 설정되지 않았습니다.")

    @app.exception_handler(SQLAlchemyError)
    async def handle_db_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        # 예외 메시지에는 접속 주소나 쿼리 내용이 섞일 수 있어 응답에 싣지 않는다. 종류만 로그에 남긴다.
        logger.error("DB 오류: %s", type(exc).__name__)
        return _error_response(503, "db_unavailable", "기록 저장소에 문제가 있어 요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.")

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # 프레임워크가 만드는 영어 메시지(Not Found 등)는 그대로 노출하지 않고 상태 코드별 한국어로 바꾼다.
        message = _HTTP_MESSAGES.get(exc.status_code, "요청을 처리할 수 없습니다.")
        return _error_response(exc.status_code, "http_error", message)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("처리되지 않은 오류: %s", type(exc).__name__)
        return _error_response(500, "internal_error", "서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")
