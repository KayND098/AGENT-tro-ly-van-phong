import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from ..db import get_connection, record_audit_log, get_db_path
from ..tools.registry import registry, RiskLevel

class ActionNotFoundError(Exception):
    pass

class ActionExpiredError(Exception):
    pass

class ActionAlreadyProcessedError(Exception):
    def __init__(self, message: str, status: str, result: Optional[Any] = None):
        super().__init__(message)
        self.status = status
        self.result = result

class ValidationError(Exception):
    pass

class ConfirmService:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def _parse_row(self, row) -> Dict[str, Any]:
        data = dict(row)
        data["original_args"] = json.loads(data["original_args"]) if data["original_args"] else {}
        data["edited_args"] = json.loads(data["edited_args"]) if data.get("edited_args") else None
        data["preview"] = json.loads(data["preview"]) if data["preview"] else {}
        data["result"] = json.loads(data["result"]) if data.get("result") else None
        return data

    def create_pending_action(
        self,
        tool_name: str,
        args: Dict[str, Any],
        risk_level: RiskLevel = RiskLevel.CONFIRM,
    ) -> Dict[str, Any]:
        from ..db import init_db as _init_db
        _init_db(self.db_path)  # idempotent: CREATE TABLE IF NOT EXISTS
        tool = registry.get(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' không tồn tại trong Registry.")

        # Sinh preview hoặc dry-run
        preview_data = tool.preview(**args)

        action_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=10)

        now_iso = now.isoformat()
        expires_iso = expires_at.isoformat()

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO pending_actions (
                    id, tool_name, original_args, edited_args, preview,
                    risk_level, status, result, created_at, expires_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action_id,
                    tool_name,
                    json.dumps(args, ensure_ascii=False),
                    None,
                    json.dumps(preview_data, ensure_ascii=False),
                    risk_level.value if isinstance(risk_level, RiskLevel) else risk_level,
                    "PENDING",
                    None,
                    now_iso,
                    expires_iso,
                    now_iso,
                ),
            )
            conn.commit()

        record_audit_log(
            action_type="PENDING_CREATED",
            tool_name=tool_name,
            original_args=args,
            status="PENDING",
            action_id=action_id,
            result={"preview": preview_data, "expires_at": expires_iso},
            db_path=self.db_path,
        )

        return {
            "id": action_id,
            "tool_name": tool_name,
            "original_args": args,
            "edited_args": None,
            "preview": preview_data,
            "risk_level": risk_level.value if isinstance(risk_level, RiskLevel) else risk_level,
            "status": "PENDING",
            "result": None,
            "created_at": now_iso,
            "expires_at": expires_iso,
            "updated_at": now_iso,
        }

    def get_action(self, action_id: str) -> Dict[str, Any]:
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pending_actions WHERE id = ?", (action_id,))
            row = cursor.fetchone()
            if not row:
                raise ActionNotFoundError(f"Không tìm thấy Pending Action với id: {action_id}")

            data = self._parse_row(row)

            # Kiểm tra hết hạn TTL 10 phút
            now = datetime.now(timezone.utc)
            expires_at = datetime.fromisoformat(data["expires_at"])
            if data["status"] == "PENDING" and now > expires_at:
                # Cập nhật thành EXPIRED
                cursor.execute(
                    "UPDATE pending_actions SET status = 'EXPIRED', updated_at = ? WHERE id = ?",
                    (now.isoformat(), action_id),
                )
                conn.commit()
                data["status"] = "EXPIRED"
                data["updated_at"] = now.isoformat()

                record_audit_log(
                    action_type="EXPIRED",
                    tool_name=data["tool_name"],
                    original_args=data["original_args"],
                    status="EXPIRED",
                    action_id=action_id,
                    db_path=self.db_path,
                )

            return data

    def list_pending_actions(self) -> List[Dict[str, Any]]:
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pending_actions ORDER BY created_at DESC")
            rows = cursor.fetchall()

        results = []
        for r in rows:
            action = self.get_action(r["id"])
            if action["status"] == "PENDING":
                results.append(action)
        return results

    def _validate_args(self, tool_name: str, args: Dict[str, Any]) -> None:
        tool = registry.get(tool_name)
        if not tool:
            raise ValidationError(f"Tool '{tool_name}' không tồn tại.")
        required_fields = tool.parameters.get("required", [])
        for field in required_fields:
            if field not in args:
                raise ValidationError(f"Thiếu tham số bắt buộc '{field}' cho tool '{tool_name}'.")

    def approve_action(
        self,
        action_id: str,
        edited_args: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            # Khóa dòng để tránh race condition (idempotency)
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("SELECT * FROM pending_actions WHERE id = ?", (action_id,))
            row = cursor.fetchone()
            if not row:
                conn.rollback()
                raise ActionNotFoundError(f"Không tìm thấy Pending Action với id: {action_id}")

            data = self._parse_row(row)

            # 1. Chống duyệt đúp (idempotent): nếu đã APPROVED, trả về kết quả cũ
            if data["status"] == "APPROVED":
                conn.rollback()
                raise ActionAlreadyProcessedError(
                    f"Action '{action_id}' đã được duyệt trước đó.",
                    status="APPROVED",
                    result=data.get("result"),
                )

            # 2. Nếu đã REJECTED
            if data["status"] == "REJECTED":
                conn.rollback()
                raise ActionAlreadyProcessedError(
                    f"Action '{action_id}' đã bị hủy trước đó.",
                    status="REJECTED",
                )

            # 3. Kiểm tra TTL 10 phút
            expires_at = datetime.fromisoformat(data["expires_at"])
            if data["status"] == "EXPIRED" or now > expires_at:
                cursor.execute(
                    "UPDATE pending_actions SET status = 'EXPIRED', updated_at = ? WHERE id = ?",
                    (now_iso, action_id),
                )
                conn.commit()
                record_audit_log(
                    action_type="EXPIRED",
                    tool_name=data["tool_name"],
                    original_args=data["original_args"],
                    status="EXPIRED",
                    action_id=action_id,
                    db_path=self.db_path,
                )
                raise ActionExpiredError(f"Action '{action_id}' đã hết hạn sau 10 phút.")

            tool_name = data["tool_name"]
            tool = registry.get(tool_name)
            if not tool:
                conn.rollback()
                raise ValueError(f"Tool '{tool_name}' không tìm thấy trong Registry.")

            # Xác định tham số thực thi: ưu tiên edited_args nếu có
            if edited_args is not None:
                self._validate_args(tool_name, edited_args)
                execution_args = edited_args
            else:
                execution_args = data["original_args"]

            # Thực thi tool
            try:
                exec_result = tool.execute(**execution_args)
            except Exception as e:
                conn.rollback()
                raise RuntimeError(f"Lỗi khi thực thi tool '{tool_name}': {str(e)}")

            # Cập nhật trạng thái thành APPROVED
            cursor.execute(
                """
                UPDATE pending_actions
                SET status = 'APPROVED',
                    edited_args = ?,
                    result = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    json.dumps(edited_args, ensure_ascii=False) if edited_args is not None else None,
                    json.dumps(exec_result, ensure_ascii=False),
                    now_iso,
                    action_id,
                ),
            )
            conn.commit()

        # Ghi log kiểm toán thành công (lưu cả original_args và edited_args)
        record_audit_log(
            action_type="APPROVED",
            tool_name=tool_name,
            original_args=data["original_args"],
            edited_args=edited_args,
            result=exec_result,
            status="SUCCESS",
            action_id=action_id,
            db_path=self.db_path,
        )

        return {
            "id": action_id,
            "status": "APPROVED",
            "tool_name": tool_name,
            "executed_args": execution_args,
            "original_args": data["original_args"],
            "edited_args": edited_args,
            "result": exec_result,
            "updated_at": now_iso,
        }

    def reject_action(self, action_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pending_actions WHERE id = ?", (action_id,))
            row = cursor.fetchone()
            if not row:
                raise ActionNotFoundError(f"Không tìm thấy Pending Action với id: {action_id}")

            data = self._parse_row(row)

            if data["status"] != "PENDING":
                raise ActionAlreadyProcessedError(
                    f"Action '{action_id}' không ở trạng thái PENDING (hiện tại: {data['status']}).",
                    status=data["status"],
                )

            cursor.execute(
                "UPDATE pending_actions SET status = 'REJECTED', updated_at = ? WHERE id = ?",
                (now_iso, action_id),
            )
            conn.commit()

        record_audit_log(
            action_type="REJECTED",
            tool_name=data["tool_name"],
            original_args=data["original_args"],
            result={"reason": reason or "Người dùng hủy bỏ"},
            status="REJECTED",
            action_id=action_id,
            db_path=self.db_path,
        )

        return {
            "id": action_id,
            "status": "REJECTED",
            "message": "Đã hủy bỏ hành động thành công.",
            "updated_at": now_iso,
        }

confirm_service = ConfirmService()
