"""
backend/app/auth/router.py
Routes xác thực Google OAuth 2.0 (chỉ scope danh tính: openid, email, profile).
Tuyệt đối không log token, code, state, nonce, cookie hay nội dung thư.
"""
import logging
import secrets
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from .config import (
    IDENTITY_SCOPES,
    get_allowed_emails,
    get_app_base_url,
    get_session_days,
    get_web_client_file,
)
from .db_auth import (
    create_session,
    delete_session,
    get_session_user,
    init_auth_tables,
    upsert_user,
)
from .state_store import consume_state, consume_state_with_status, create_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "session_id"


# ---------------------------------------------------------------------------
# Cookie helper
# ---------------------------------------------------------------------------

def _set_session_cookie(response: Response, token: str, session_days: int, secure: bool) -> None:
    """Đặt cookie HttpOnly, SameSite=Lax. Secure chỉ khi APP_BASE_URL là https."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


def _clear_session_cookie(response: Response, secure: bool) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/", secure=secure, httponly=True, samesite="lax")


# ---------------------------------------------------------------------------
# Dependency: require_user
# ---------------------------------------------------------------------------

def get_current_user(session_id: Optional[str] = Cookie(default=None, alias=COOKIE_NAME)):
    """
    Trả về dict user nếu cookie hợp lệ và phiên chưa hết hạn.
    Dùng làm dependency cho các route cần đăng nhập.
    Raise NOT phải ở đây — route gọi sẽ kiểm tra None hoặc dùng require_user.
    """
    if not session_id:
        return None
    return get_session_user(session_id)


def require_user(user=Depends(get_current_user)):
    """Dependency bắt buộc đăng nhập; trả 401 JSON nếu chưa đăng nhập hoặc phiên hết hạn."""
    from fastapi import HTTPException, status
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "unauthenticated", "message": "Vui lòng đăng nhập để tiếp tục."},
        )
    return user


# ---------------------------------------------------------------------------
# CSRF check for POST requests
# ---------------------------------------------------------------------------

def _check_csrf(request: Request) -> None:
    """
    Kiểm tra CSRF đơn giản cho các POST mutation:
    - Header X-Requested-With phải có mặt.
    - Origin phải khớp APP_BASE_URL (hoặc không có Origin từ same-origin).
    """
    from fastapi import HTTPException, status

    xrw = request.headers.get("X-Requested-With", "")
    if not xrw:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "csrf", "message": "Thiếu header X-Requested-With."},
        )
    origin = request.headers.get("Origin", "")
    base = get_app_base_url()
    if origin and origin.rstrip("/") != base:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "csrf", "message": "Origin không hợp lệ."},
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/google/login")
def google_login():
    """
    Chuyển hướng người dùng tới Google OAuth consent screen.
    Tạo state ngẫu nhiên + PKCE + nonce, lưu trong bộ nhớ 10 phút.
    """
    client_file = get_web_client_file()
    if not client_file.exists():
        logger.warning("GOOGLE_WEB_CLIENT_FILE không tồn tại tại %s — Google login không khả dụng.", client_file)
        base = get_app_base_url()
        return RedirectResponse(url=f"{base}/?error=no_client_config", status_code=302)

    try:
        from google_auth_oauthlib.flow import Flow

        nonce = secrets.token_urlsafe(32)
        state, code_verifier, code_challenge = create_state(nonce)

        base = get_app_base_url()
        redirect_uri = f"{base}/auth/google/callback"

        flow = Flow.from_client_secrets_file(
            str(client_file),
            scopes=IDENTITY_SCOPES,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            autogenerate_code_verifier=False,
        )

        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="false",
            state=state,
            nonce=nonce,
            prompt="select_account",
        )
        return RedirectResponse(url=auth_url, status_code=302)
    except Exception as exc:
        logger.exception("Lỗi khi tạo URL đăng nhập Google: %s", type(exc).__name__)
        base = get_app_base_url()
        return RedirectResponse(url=f"{base}/?error=login_failed", status_code=302)


@router.get("/google/callback")
def google_callback(request: Request, state: str = "", code: str = ""):
    """
    Callback từ Google sau khi người dùng đồng ý.
    1. Kiểm tra state (dùng 1 lần duy nhất) → lấy code_verifier + nonce.
    2. Đổi code lấy id_token (fetch_token kèm code_verifier).
    3. Xác minh id_token qua google-auth.
    4. Kiểm tra ALLOWED_EMAILS.
    5. Upsert user, tạo phiên, đặt cookie, chuyển hướng.
    """
    base = get_app_base_url()
    secure = base.startswith("https")
    session_days = get_session_days()

    # 1. Kiểm tra state
    state_data, state_status = consume_state_with_status(state)
    if state_status == "state_invalid":
        logger.warning("OAuth callback thất bại [state_invalid]: state không hợp lệ hoặc đã dùng.")
        return RedirectResponse(url=f"{base}/?error=state_invalid", status_code=302)
    elif state_status == "state_expired":
        logger.warning("OAuth callback thất bại [state_expired]: state đã hết hạn.")
        return RedirectResponse(url=f"{base}/?error=state_expired", status_code=302)

    if not code:
        logger.warning("OAuth callback thất bại [code_missing]: thiếu authorization code.")
        return RedirectResponse(url=f"{base}/?error=code_missing", status_code=302)

    client_file = get_web_client_file()
    if not client_file.exists():
        logger.warning("OAuth callback thất bại [no_client_config]: không tìm thấy client file.")
        return RedirectResponse(url=f"{base}/?error=no_client_config", status_code=302)

    code_verifier = state_data["code_verifier"]

    try:
        from google_auth_oauthlib.flow import Flow
        import google.oauth2.id_token
        from google.auth.transport import requests as google_requests
        import json as _json

        redirect_uri = f"{base}/auth/google/callback"
        flow = Flow.from_client_secrets_file(
            str(client_file),
            scopes=IDENTITY_SCOPES,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            autogenerate_code_verifier=False,
            state=state,
        )

        client_config = _json.loads(client_file.read_text(encoding="utf-8"))
        client_id = (
            client_config.get("web", {}).get("client_id")
            or client_config.get("installed", {}).get("client_id")
            or ""
        )

        # 2. Đổi code lấy token với code_verifier
        try:
            flow.fetch_token(code=code, code_verifier=code_verifier)
        except Exception as exc:
            logger.exception("OAuth callback thất bại [token_exchange_failed]: %s", type(exc).__name__)
            return RedirectResponse(url=f"{base}/?error=token_exchange_failed", status_code=302)

        credentials = flow.credentials
        id_token_str = credentials.id_token

        # Kiểm tra scope nếu bị thay đổi (chỉ khi scopes là danh sách cụ thể)
        scopes_granted = getattr(credentials, "scopes", None)
        if isinstance(scopes_granted, (list, tuple, set)) and scopes_granted:
            if not set(IDENTITY_SCOPES).issubset(set(scopes_granted)):
                logger.warning("OAuth callback thất bại [scope_changed]: scopes cấp không đủ.")
                return RedirectResponse(url=f"{base}/?error=scope_changed", status_code=302)

        # 3. Xác minh id_token
        try:
            http_request = google_requests.Request()
            id_info = google.oauth2.id_token.verify_oauth2_token(
                id_token_str,
                http_request,
                audience=client_id,
            )
        except Exception as exc:
            logger.exception("OAuth callback thất bại [id_token_invalid]: %s", type(exc).__name__)
            return RedirectResponse(url=f"{base}/?error=id_token_invalid", status_code=302)

        # Xác minh nonce
        if id_info.get("nonce") != state_data["nonce"]:
            logger.warning("OAuth callback thất bại [nonce_mismatch]: nonce không khớp.")
            return RedirectResponse(url=f"{base}/?error=nonce_mismatch", status_code=302)

        email_addr = id_info.get("email", "").lower().strip()
        google_sub = id_info.get("sub", "")
        name = id_info.get("name", email_addr)
        picture = id_info.get("picture")

        # 4. Kiểm tra ALLOWED_EMAILS
        allowed = get_allowed_emails()
        if allowed and email_addr not in allowed:
            logger.warning("OAuth callback thất bại [email_not_allowed]: email không trong danh sách cho phép.")
            return RedirectResponse(url=f"{base}/?error=email_not_allowed", status_code=302)

        if not google_sub or not email_addr:
            logger.warning("OAuth callback thất bại [id_token_invalid]: thiếu sub hoặc email.")
            return RedirectResponse(url=f"{base}/?error=id_token_invalid", status_code=302)

        # 5. Upsert user và tạo phiên
        init_auth_tables()
        user = upsert_user(google_sub=google_sub, email=email_addr, name=name, picture=picture)
        token = create_session(user_id=user["id"], session_days=session_days)

        redirect_response = RedirectResponse(url=base, status_code=302)
        _set_session_cookie(redirect_response, token, session_days, secure)
        return redirect_response

    except Exception as exc:
        logger.exception("OAuth callback thất bại [auth_failed]: %s", type(exc).__name__)
        return RedirectResponse(url=f"{base}/?error=auth_failed", status_code=302)


@router.get("/me")
def me(user=Depends(get_current_user)):
    """Trả về thông tin user đang đăng nhập, hoặc 401 nếu chưa đăng nhập."""
    from fastapi import HTTPException, status
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "unauthenticated", "message": "Chưa đăng nhập."},
        )
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "picture": user.get("picture"),
    }


@router.post("/logout")
def logout(request: Request, session_id: Optional[str] = Cookie(default=None, alias=COOKIE_NAME)):
    """Xóa phiên phía server và xóa cookie. Yêu cầu header X-Requested-With."""
    _check_csrf(request)
    base = get_app_base_url()
    secure = base.startswith("https")

    if session_id:
        try:
            delete_session(session_id)
        except Exception:
            logger.exception("Lỗi khi xóa phiên (chi tiết ẩn)")

    response = JSONResponse(content={"success": True, "message": "Đã đăng xuất thành công."})
    _clear_session_cookie(response, secure)
    return response
