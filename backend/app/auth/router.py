"""
backend/app/auth/router.py
Routes xác thực Google OAuth 2.0 (chỉ scope danh tính: openid, email, profile).
Tuyệt đối không log token, code, state, nonce, cookie hay nội dung thư.
"""
import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from .config import (
    IDENTITY_SCOPES,
    get_allowed_emails,
    get_app_base_url,
    get_session_days,
    get_web_client_file,
    is_demo_mode,
)
from .db_auth import (
    create_session,
    delete_session,
    delete_user_google_token,
    get_or_create_demo_user,
    get_session_user,
    get_user_by_id,
    get_user_google_token,
    init_auth_tables,
    upsert_user,
    upsert_user_google_token,
)
from .state_store import consume_state, consume_state_with_status, create_state, save_state

logger = logging.getLogger(__name__)


def _sanitize_oauth_log(text: str, code: str = "") -> str:
    """Loại bỏ thông tin nhạy cảm (token, code, secret) khỏi log."""
    if not text:
        return ""
    if code and len(code) > 3:
        text = text.replace(code, "[REDACTED_CODE]")
    text = re.sub(r'ya29\.[a-zA-Z0-9_\-]+', '[REDACTED_ACCESS_TOKEN]', text)
    text = re.sub(r'1//[a-zA-Z0-9_\-]+', '[REDACTED_REFRESH_TOKEN]', text)
    text = re.sub(r'Bearer\s+[a-zA-Z0-9_\-\.]+', 'Bearer [REDACTED_TOKEN]', text, flags=re.IGNORECASE)
    text = re.sub(r'GOCSPX-[a-zA-Z0-9_\-]+', '[REDACTED_CLIENT_SECRET]', text)
    text = re.sub(r'client_secret=[a-zA-Z0-9_\-\.]+', 'client_secret=[REDACTED_SECRET]', text, flags=re.IGNORECASE)
    text = re.sub(r'access_token=[a-zA-Z0-9_\-\.]+', 'access_token=[REDACTED_TOKEN]', text, flags=re.IGNORECASE)
    return text

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
    - Nếu có session_id hợp lệ, trả về user tương ứng (bảo toàn cô lập đa người dùng).
    - Ở chế độ demo (AUTH_MODE=demo), nếu chưa có cookie hoặc phiên không tìm thấy, trả về demo user mặc định.
    - Ở chế độ google, không có session_id trả về None (kích hoạt 401).
    """
    if session_id:
        user = get_session_user(session_id)
        if user:
            return user
    if is_demo_mode():
        return get_or_create_demo_user()
    return None


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
    Ở chế độ demo, chuyển thẳng về trang chủ (không cần Google).
    """
    if is_demo_mode():
        base = get_app_base_url()
        return RedirectResponse(url=f"{base}/", status_code=302)

    client_file = get_web_client_file()
    if not client_file.exists():
        logger.exception("GOOGLE_WEB_CLIENT_FILE không tồn tại tại %s — Google login không khả dụng.", client_file, exc_info=False)
        base = get_app_base_url()
        return RedirectResponse(url=f"{base}/?error=no_client_config", status_code=302)

    try:
        from google_auth_oauthlib.flow import Flow

        nonce = secrets.token_urlsafe(32)
        state = secrets.token_urlsafe(32)
        base = get_app_base_url()
        redirect_uri = f"{base}/auth/google/callback"

        flow = Flow.from_client_secrets_file(
            str(client_file),
            scopes=IDENTITY_SCOPES,
            redirect_uri=redirect_uri,
        )

        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="false",
            state=state,
            nonce=nonce,
            prompt="select_account",
        )

        # Lấy đúng code_verifier mà flow đã sinh lúc tạo authorization URL
        code_verifier = getattr(flow, "code_verifier", None)
        if not isinstance(code_verifier, str) or not code_verifier:
            code_verifier = secrets.token_urlsafe(64)
            flow.code_verifier = code_verifier

        save_state(state=state, nonce=nonce, code_verifier=code_verifier, purpose="login")
        return RedirectResponse(url=auth_url, status_code=302)
    except Exception as exc:
        sanitized = _sanitize_oauth_log(str(exc))
        logger.exception("Lỗi khi tạo URL đăng nhập Google [%s]: %s", type(exc).__name__, sanitized, exc_info=False)
        base = get_app_base_url()
        return RedirectResponse(url=f"{base}/?error=login_failed", status_code=302)


@router.get("/google/connect-gmail")
def connect_gmail(user=Depends(require_user)):
    """
    Tạo URL cấp quyền bổ sung (Incremental Authorization) để đọc Gmail.
    Scope: IDENTITY_SCOPES + https://www.googleapis.com/auth/gmail.readonly.
    Lưu state kèm purpose='connect_gmail' và user_id.
    Ở chế độ demo, từ chối và chuyển hướng về trang chủ.
    """
    base = get_app_base_url()
    if is_demo_mode():
        return RedirectResponse(url=f"{base}/?error=demo_mode_no_gmail", status_code=302)

    client_file = get_web_client_file()
    if not client_file.exists():
        logger.exception("GOOGLE_WEB_CLIENT_FILE không tồn tại tại %s — Connect Gmail không khả dụng.", client_file, exc_info=False)
        return RedirectResponse(url=f"{base}/?error=no_client_config", status_code=302)

    try:
        from google_auth_oauthlib.flow import Flow

        nonce = secrets.token_urlsafe(32)
        state = secrets.token_urlsafe(32)
        redirect_uri = f"{base}/auth/google/callback"
        connect_scopes = list(IDENTITY_SCOPES) + ["https://www.googleapis.com/auth/gmail.readonly"]

        flow = Flow.from_client_secrets_file(
            str(client_file),
            scopes=connect_scopes,
            redirect_uri=redirect_uri,
        )

        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
            nonce=nonce,
            login_hint=user.get("email"),
        )

        code_verifier = getattr(flow, "code_verifier", None)
        if not isinstance(code_verifier, str) or not code_verifier:
            code_verifier = secrets.token_urlsafe(64)
            flow.code_verifier = code_verifier

        save_state(
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
            purpose="connect_gmail",
            user_id=user["id"],
        )
        return RedirectResponse(url=auth_url, status_code=302)
    except Exception as exc:
        sanitized = _sanitize_oauth_log(str(exc))
        logger.exception("Lỗi khi tạo URL kết nối Gmail [%s]: %s", type(exc).__name__, sanitized, exc_info=False)
        return RedirectResponse(url=f"{base}/?error=connect_failed", status_code=302)


@router.get("/google/callback")
def google_callback(
    request: Request,
    state: str = "",
    code: str = "",
    session_id: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
):
    """
    Callback từ Google sau khi người dùng đồng ý:
    - purpose == 'login': Xác thực danh tính, tạo session, chuyển hướng về trang chủ.
    - purpose == 'connect_gmail': Cấp quyền Gmail cho tài khoản hiện tại, lưu token vào DB.
    """
    base = get_app_base_url()
    secure = base.startswith("https")
    session_days = get_session_days()

    # 1. Kiểm tra state (xóa ngay lập tức, dùng một lần)
    state_data, state_status = consume_state_with_status(state)
    if state_status == "state_invalid":
        logger.exception("OAuth callback thất bại [state_invalid]: state không hợp lệ hoặc đã dùng.", exc_info=False)
        return RedirectResponse(url=f"{base}/?error=state_invalid", status_code=302)
    elif state_status == "state_expired":
        logger.exception("OAuth callback thất bại [state_expired]: state đã hết hạn.", exc_info=False)
        return RedirectResponse(url=f"{base}/?error=state_expired", status_code=302)

    if not code:
        logger.exception("OAuth callback thất bại [code_missing]: thiếu authorization code.", exc_info=False)
        return RedirectResponse(url=f"{base}/?error=code_missing", status_code=302)

    client_file = get_web_client_file()
    if not client_file.exists():
        logger.exception("OAuth callback thất bại [no_client_config]: không tìm thấy client file.", exc_info=False)
        return RedirectResponse(url=f"{base}/?error=no_client_config", status_code=302)

    code_verifier = state_data["code_verifier"]
    purpose = state_data.get("purpose", "login")

    try:
        from google_auth_oauthlib.flow import Flow
        import google.oauth2.id_token
        from google.auth.transport import requests as google_requests
        import json as _json

        redirect_uri = f"{base}/auth/google/callback"
        flow_scopes = list(IDENTITY_SCOPES)
        if purpose == "connect_gmail":
            flow_scopes.append("https://www.googleapis.com/auth/gmail.readonly")

        flow = Flow.from_client_secrets_file(
            str(client_file),
            scopes=flow_scopes,
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
            sanitized = _sanitize_oauth_log(str(exc), code)
            logger.exception("OAuth callback thất bại [token_exchange_failed]: %s - %s", type(exc).__name__, sanitized, exc_info=False)
            return RedirectResponse(url=f"{base}/?error=token_exchange_failed", status_code=302)

        credentials = flow.credentials
        id_token_str = credentials.id_token

        # Kiểm tra scope nếu bị thay đổi (chỉ khi scopes là danh sách cụ thể)
        scopes_granted = getattr(credentials, "scopes", None)
        if isinstance(scopes_granted, (list, tuple, set)) and scopes_granted:
            if purpose == "connect_gmail":
                if "https://www.googleapis.com/auth/gmail.readonly" not in scopes_granted:
                    logger.exception("OAuth callback thất bại [scope_changed]: thiếu quyền gmail.readonly.", exc_info=False)
                    return RedirectResponse(url=f"{base}/?error=scope_changed", status_code=302)
            else:
                if not set(IDENTITY_SCOPES).issubset(set(scopes_granted)):
                    logger.exception("OAuth callback thất bại [scope_changed]: scopes cấp không đủ.", exc_info=False)
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
            sanitized = _sanitize_oauth_log(str(exc), code)
            logger.exception("OAuth callback thất bại [id_token_invalid]: %s - %s", type(exc).__name__, sanitized, exc_info=False)
            return RedirectResponse(url=f"{base}/?error=id_token_invalid", status_code=302)

        # Xác minh nonce
        if id_info.get("nonce") != state_data["nonce"]:
            logger.exception("OAuth callback thất bại [nonce_mismatch]: nonce không khớp.", exc_info=False)
            return RedirectResponse(url=f"{base}/?error=nonce_mismatch", status_code=302)

        email_addr = id_info.get("email", "").lower().strip()
        google_sub = id_info.get("sub", "")
        name = id_info.get("name", email_addr)
        picture = id_info.get("picture")

        # Phân nhánh theo purpose
        if purpose == "connect_gmail":
            # 1. Kiểm tra phiên đăng nhập hiện tại từ cookie phải khớp user_id trong state
            current_session_user = get_session_user(session_id) if session_id else None
            state_user_id = state_data.get("user_id")
            if not current_session_user or current_session_user["id"] != state_user_id:
                logger.warning("OAuth callback thất bại [session_mismatch]: phiên đăng nhập hiện tại không khớp user_id trong state.")
                return RedirectResponse(url=f"{base}/?error=session_mismatch", status_code=302)

            # 2. Kiểm tra scope gmail.readonly
            if isinstance(scopes_granted, (list, tuple, set)) and scopes_granted:
                if "https://www.googleapis.com/auth/gmail.readonly" not in scopes_granted:
                    logger.warning("OAuth callback thất bại [scope_changed]: thiếu quyền gmail.readonly.")
                    return RedirectResponse(url=f"{base}/?error=scope_changed", status_code=302)

            # 3. Kiểm tra email kết nối phải khớp với email của user đang đăng nhập
            if current_session_user["email"].lower().strip() != email_addr:
                logger.warning("OAuth callback thất bại [email_mismatch]: email kết nối không khớp với tài khoản hiện tại.")
                return RedirectResponse(url=f"{base}/?error=email_mismatch", status_code=302)

            init_auth_tables()
            scopes_str = " ".join(scopes_granted) if isinstance(scopes_granted, (list, tuple, set)) else str(scopes_granted or " ".join(flow_scopes))
            expiry_str = credentials.expiry.replace(tzinfo=timezone.utc).isoformat() if getattr(credentials, "expiry", None) else None

            # 4. Lưu token mã hóa vào DB (TUYỆT ĐỐI KHÔNG lưu client_secret)
            try:
                upsert_user_google_token(
                    user_id=current_session_user["id"],
                    access_token=credentials.token or "",
                    refresh_token=getattr(credentials, "refresh_token", None),
                    token_uri=getattr(credentials, "token_uri", "https://oauth2.googleapis.com/token"),
                    client_id=client_id,
                    scopes=scopes_str,
                    expiry=expiry_str,
                )
                logger.info("Kết nối Gmail thành công cho user_id=%s (%s).", current_session_user["id"], email_addr)
                return RedirectResponse(url=f"{base}/?gmail_connected=1", status_code=302)
            except Exception as token_err:
                sanitized = _sanitize_oauth_log(str(token_err))
                logger.exception("Lỗi khi lưu token mã hóa [%s]: %s", type(token_err).__name__, sanitized, exc_info=False)
                return RedirectResponse(url=f"{base}/?error=token_storage_error", status_code=302)

        # 4. Kiểm tra ALLOWED_EMAILS (cho login)
        allowed = get_allowed_emails()
        if allowed and email_addr not in allowed:
            logger.exception("OAuth callback thất bại [email_not_allowed]: email không trong danh sách cho phép.", exc_info=False)
            return RedirectResponse(url=f"{base}/?error=email_not_allowed", status_code=302)

        if not google_sub or not email_addr:
            logger.exception("OAuth callback thất bại [id_token_invalid]: thiếu sub hoặc email.", exc_info=False)
            return RedirectResponse(url=f"{base}/?error=id_token_invalid", status_code=302)

        # 5. Upsert user và tạo phiên (cho login)
        init_auth_tables()
        user = upsert_user(google_sub=google_sub, email=email_addr, name=name, picture=picture)
        token = create_session(user_id=user["id"], session_days=session_days)

        redirect_response = RedirectResponse(url=base, status_code=302)
        _set_session_cookie(redirect_response, token, session_days, secure)
        return redirect_response

    except Exception as exc:
        sanitized = _sanitize_oauth_log(str(exc), code)
        logger.exception("OAuth callback thất bại [auth_failed]: %s - %s", type(exc).__name__, sanitized, exc_info=False)
        return RedirectResponse(url=f"{base}/?error=auth_failed", status_code=302)


@router.post("/google/disconnect-gmail")
def disconnect_gmail(request: Request, user=Depends(require_user)):
    """
    Ngắt kết nối Gmail:
    1. Thu hồi token tại Google qua https://oauth2.googleapis.com/revoke
    2. Xóa dòng lưu trữ token trong DB SQLite.
    """
    _check_csrf(request)
    token_row = get_user_google_token(user["id"])
    if token_row:
        token_to_revoke = token_row.get("refresh_token") or token_row.get("access_token")
        if token_to_revoke:
            try:
                import httpx
                with httpx.Client(timeout=5.0) as http_client:
                    resp = http_client.post(
                        "https://oauth2.googleapis.com/revoke",
                        params={"token": token_to_revoke},
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                    if resp.status_code == 200:
                        logger.info("Đã thu hồi token Google thành công cho user_id=%s.", user["id"])
                    else:
                        logger.warning("Google revoke trả về status %s cho user_id=%s.", resp.status_code, user["id"])
            except Exception as exc:
                logger.warning("Không thể gửi yêu cầu thu hồi token tới Google: %s", type(exc).__name__)

    delete_user_google_token(user["id"])
    return JSONResponse(content={"success": True, "message": "Đã ngắt kết nối Gmail thành công."})


@router.get("/me")
def me(
    response: Response,
    session_id: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    user=Depends(require_user),
):
    """
    Trả về thông tin user đang đăng nhập và trạng thái kết nối Gmail, hoặc 401 nếu chưa đăng nhập.
    Ở chế độ demo:
    - Tự động đặt cookie session cho user demo nếu chưa có session hợp lệ.
    - Ép gmail_connected=False.
    - Trả demo_mode=True.
    """
    demo = is_demo_mode()
    if demo:
        if not session_id or not get_session_user(session_id):
            session_days = get_session_days()
            token = create_session(user_id=user["id"], session_days=session_days)
            _set_session_cookie(response, token, session_days, secure=False)
        return {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "picture": user.get("picture"),
            "gmail_connected": False,
            "demo_mode": True,
        }

    token_row = get_user_google_token(user["id"])
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "picture": user.get("picture"),
        "gmail_connected": token_row is not None and bool(token_row.get("access_token")),
        "demo_mode": False,
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
