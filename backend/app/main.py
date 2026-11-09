from fastapi import FastAPI, HTTPException, status, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os
import logging

from .ui import HTML_PAGE

# Import modules để đảm bảo tool đã được đăng ký vào registry
from .db import init_db, get_connection
from .tools import email, calendar, sheets
from .tools.registry import registry
from .confirm.service import (
    confirm_service,
    ActionNotFoundError,
    ActionExpiredError,
    ActionAlreadyProcessedError,
    ValidationError,
)
from .agent.loop import agent_loop

# Auth
from .auth.db_auth import init_auth_tables
from .auth.router import router as auth_router, require_user, _check_csrf
from .auth.config import get_app_base_url

from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_auth_tables()
    yield

app = FastAPI(
    title="Trợ Lý Văn Phòng AI - API",
    description="Backend điều khiển Agent Trợ lý Văn phòng với luồng phê duyệt an toàn (Human-in-the-loop)",
    version="0.1.0",
    lifespan=lifespan,
)

# Cấu hình CORS: chỉ cho phép APP_BASE_URL (không dùng wildcard khi có credentials)
_base_url = get_app_base_url()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_base_url, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Requested-With"],
)

# Mount auth router (/auth/*)
app.include_router(auth_router)

# --- Request / Response Models ---

class ChatMessage(BaseModel):
    role: str = Field(..., description="user hoặc assistant hoặc system")
    content: str = Field(..., description="Nội dung tin nhắn")

class ChatRequest(BaseModel):
    messages: List[ChatMessage]

class ApproveRequest(BaseModel):
    edited_args: Optional[Dict[str, Any]] = Field(
        None,
        description="Tham số chỉnh sửa tùy chọn thay thế tham số gốc trước khi thực thi",
    )

class RejectRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Lý do từ chối hoặc hủy bỏ")

# --- Endpoints ---

@app.get("/health")
def health_check():
    """Route công khai — không cần đăng nhập."""
    return {"status": "ok", "service": "office-assistant-backend"}

@app.get("/api")
def api_info():
    return {
        "service": "Trợ Lý Văn Phòng AI - Backend API",
        "status": "running",
        "docs_url": "/docs",
        "endpoints": {
            "chat": "POST /chat",
            "pending_actions": "GET /actions/pending",
            "approve_action": "POST /actions/{id}/approve",
            "reject_action": "POST /actions/{id}/reject",
            "audit_logs": "GET /audit",
            "health": "GET /health",
            "auth_login": "GET /auth/google/login",
            "auth_me": "GET /auth/me",
            "auth_logout": "POST /auth/logout",
        }
    }

@app.get("/", response_class=HTMLResponse)
@app.get("/ui", response_class=HTMLResponse)
@app.get("/ui/", response_class=HTMLResponse)
def ui_page():
    """
    Giao diện chat tĩnh (server-side HTML cũ).
    Route này vẫn tồn tại nhưng yêu cầu đăng nhập;
    nếu chưa đăng nhập, trả 401 JSON (React frontend đảm nhận hiển thị LoginPage).
    Lưu ý: giao diện chính hiện tại là React SPA trên frontend/,
    route này chỉ giữ lại cho tương thích ngược.
    """
    return HTMLResponse(content=HTML_PAGE)


@app.post("/chat")
def chat(request: ChatRequest, _user=Depends(require_user), req: Request = None):
    """
    Tiếp nhận tin nhắn, kích hoạt vòng lặp agent.
    Yêu cầu: đã đăng nhập (cookie) + header X-Requested-With.
    """
    if req is not None:
        _check_csrf(req)
    raw_messages = [{"role": m.role, "content": m.content} for m in request.messages]
    try:
        response = agent_loop.run(messages=raw_messages)
    except Exception as exc:
        logger.exception("Unexpected error in agent_loop.run")
        return {
            "type": "error",
            "content": f"Lỗi hệ thống: {str(exc)}. Vui lòng thử lại hoặc liên hệ quản trị viên.",
            "pending_action": None,
        }
    return response


@app.get("/actions/pending")
def list_pending(_user=Depends(require_user)):
    """Lấy danh sách tất cả các hành động đang chờ xác nhận."""
    return {"actions": confirm_service.list_pending_actions()}


@app.get("/actions/{action_id}")
def get_action_detail(action_id: str, _user=Depends(require_user)):
    """Lấy chi tiết một pending action."""
    try:
        action = confirm_service.get_action(action_id)
        return action
    except ActionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/actions/{action_id}/approve")
def approve_action(action_id: str, request: Optional[ApproveRequest] = None, _user=Depends(require_user)):
    """
    Duyệt hành động chờ.
    - Chống duyệt đúp (idempotency).
    - Hết hạn sau 10 phút.
    - Hỗ trợ tham số tùy chọn edited_args để ghi đè tham số gốc.
    """
    edited_args = request.edited_args if request else None
    try:
        result = confirm_service.approve_action(action_id=action_id, edited_args=edited_args)
        return {"success": True, "action": result}
    except ActionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ActionExpiredError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ActionAlreadyProcessedError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(e), "status": e.status, "result": e.result},
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/actions/{action_id}/reject")
def reject_action(action_id: str, request: Optional[RejectRequest] = None, _user=Depends(require_user)):
    """Hủy bỏ hoặc từ chối hành động chờ."""
    reason = request.reason if request else None
    try:
        result = confirm_service.reject_action(action_id=action_id, reason=reason)
        return {"success": True, "action": result}
    except ActionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ActionAlreadyProcessedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/audit")
def get_audit_logs(limit: int = 50, _user=Depends(require_user)):
    """Xem vết kiểm toán gần nhất."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return {"logs": [dict(r) for r in rows]}
