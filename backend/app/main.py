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
from .auth.config import get_app_base_url, validate_demo_mode_or_raise

from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_demo_mode_or_raise()
    init_db()
    init_auth_tables()
    # Cảnh báo an toàn Gmail nếu có nhiều hơn 1 user mà chưa cấu hình GMAIL_OWNER_EMAIL
    if os.getenv("EMAIL_PROVIDER", "mock").strip().lower() == "google" and not os.getenv("GMAIL_OWNER_EMAIL", "").strip():
        try:
            with get_connection() as conn:
                user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                if user_count > 1:
                    logger.warning(
                        "⚠️  CẢNH BÁO BẢO MẬT: EMAIL_PROVIDER=google nhưng chưa thiết lập GMAIL_OWNER_EMAIL "
                        "trong khi hệ thống có %d người dùng. Các tài khoản đều sẽ dùng chung token Gmail!",
                        user_count,
                    )
        except Exception:
            pass
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
            "chat_clear": "POST /chat/clear",
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


def _extract_user(user: Any) -> Optional[Dict[str, Any]]:
    if isinstance(user, dict):
        return user
    if hasattr(user, "id"):
        return {"id": getattr(user, "id"), "email": getattr(user, "email", "")}
    return None

def _extract_user_id(user: Any) -> Optional[int]:
    u = _extract_user(user)
    return u["id"] if u and "id" in u else None


@app.post("/chat")
def chat(request: ChatRequest, _user=Depends(require_user), req: Request = None):
    """
    Tiếp nhận tin nhắn, kích hoạt vòng lặp agent.
    Yêu cầu: đã đăng nhập (cookie) + header X-Requested-With.
    """
    if req is not None:
        _check_csrf(req)
    user_info = _extract_user(_user)
    raw_messages = [{"role": m.role, "content": m.content} for m in request.messages]
    try:
        response = agent_loop.run(messages=raw_messages, user=user_info)
    except Exception as exc:
        logger.exception("Unexpected error in agent_loop.run")
        return {
            "type": "error",
            "content": f"Lỗi hệ thống: {str(exc)}. Vui lòng thử lại hoặc liên hệ quản trị viên.",
            "pending_action": None,
        }
    return response


@app.post("/chat/clear")
@app.post("/chat/new")
def clear_chat(_user=Depends(require_user), req: Request = None):
    """
    Xóa lịch sử hội thoại của chính người dùng hiện tại trong bộ nhớ.
    """
    if req is not None:
        _check_csrf(req)
    user_id = _extract_user_id(_user)
    if user_id is not None:
        agent_loop.clear_history(user_id=user_id)
    return {"success": True, "message": "Đã làm mới cuộc trò chuyện."}


@app.get("/actions/pending")
def list_pending(_user=Depends(require_user)):
    """Lấy danh sách các hành động đang chờ xác nhận của người dùng hiện tại."""
    user_id = _extract_user_id(_user)
    return {"actions": confirm_service.list_pending_actions(user_id=user_id)}


@app.get("/actions/{action_id}")
def get_action_detail(action_id: str, _user=Depends(require_user)):
    """Lấy chi tiết một pending action của người dùng hiện tại."""
    user_id = _extract_user_id(_user)
    try:
        action = confirm_service.get_action(action_id, user_id=user_id)
        return action
    except ActionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/actions/{action_id}/approve")
def approve_action(action_id: str, request: Optional[ApproveRequest] = None, _user=Depends(require_user)):
    """
    Duyệt hành động chờ.
    - Chỉ chủ sở hữu mới có quyền duyệt.
    - Chống duyệt đúp (idempotency).
    - Hết hạn sau 10 phút.
    - Hỗ trợ tham số tùy chọn edited_args để ghi đè tham số gốc.
    """
    user_id = _extract_user_id(_user)
    edited_args = request.edited_args if request else None
    try:
        result = confirm_service.approve_action(action_id=action_id, edited_args=edited_args, user_id=user_id)
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
    """Hủy bỏ hoặc từ chối hành động chờ (chỉ chủ sở hữu)."""
    user_id = _extract_user_id(_user)
    reason = request.reason if request else None
    try:
        result = confirm_service.reject_action(action_id=action_id, reason=reason, user_id=user_id)
        return {"success": True, "action": result}
    except ActionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ActionAlreadyProcessedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/audit")
def get_audit_logs(limit: int = 50, _user=Depends(require_user)):
    """Xem vết kiểm toán của người dùng hiện tại."""
    user_id = _extract_user_id(_user)
    with get_connection() as conn:
        cursor = conn.cursor()
        if user_id is not None:
            cursor.execute("SELECT * FROM audit_log WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
        else:
            cursor.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return {"logs": [dict(r) for r in rows]}
