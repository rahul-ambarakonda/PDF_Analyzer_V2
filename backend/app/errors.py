"""Uniform error handling — every failure leaves as ``{error, detail, request_id}``."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .logging import request_id_var

log = logging.getLogger("app.error")


class ApiError(Exception):
    """Raise to return a controlled error response."""

    def __init__(self, status_code: int, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.detail = detail


def _body(error: str, detail: str | None) -> dict:
    return {"error": error, "detail": detail, "request_id": request_id_var.get()}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_body(exc.message, exc.detail))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_body(str(exc.detail), None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content=_body("Invalid request.", str(exc.errors())))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled exception")
        return JSONResponse(status_code=500, content=_body("Internal server error.", None))
