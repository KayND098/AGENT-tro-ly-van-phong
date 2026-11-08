from typing import List, Dict, Any, Optional
from .registry import registry, RiskLevel

class MockEmailProvider:
    def __init__(self):
        self.inbox = [
            {
                "id": "msg_001",
                "from": "minh.nguyen@company.com",
                "to": "me@company.com",
                "subject": "Báo cáo doanh thu quý 3",
                "body": "Chào anh, em gửi báo cáo doanh thu quý 3 đính kèm trong sheet Doanh thu nhé.",
                "date": "2026-10-30 09:30:00",
            },
            {
                "id": "msg_002",
                "from": "minh.nguyen@company.com",
                "to": "me@company.com",
                "subject": "Lịch họp dự án tuần tới",
                "body": "Anh xem sắp xếp họp thảo luận về tính năng xác nhận an toàn vào sáng thứ Tư nhé.",
                "date": "2026-11-01 14:15:00",
            },
            {
                "id": "msg_003",
                "from": "lan.tran@company.com",
                "to": "me@company.com",
                "subject": "Yêu cầu tài liệu quy trình",
                "body": "Nhờ anh chia sẻ tài liệu quy trình vận hành mới nhất.",
                "date": "2026-11-02 11:00:00",
            },
        ]
        self.drafts = []
        self.sent = []

    def search_email(self, query: str) -> List[Dict[str, Any]]:
        q = query.lower()
        results = []
        for msg in self.inbox + self.sent:
            if (
                q in msg["from"].lower()
                or q in msg["to"].lower()
                or q in msg["subject"].lower()
                or q in msg["body"].lower()
            ):
                results.append(msg)
        return results

    def create_draft(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        draft_id = f"draft_{len(self.drafts) + 1:03d}"
        draft = {
            "id": draft_id,
            "to": to,
            "subject": subject,
            "body": body,
            "status": "draft",
        }
        self.drafts.append(draft)
        return {"success": True, "draft_id": draft_id, "message": "Đã tạo thư nháp thành công."}

    def send_email(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        msg_id = f"sent_{len(self.sent) + 1:03d}"
        msg = {
            "id": msg_id,
            "from": "me@company.com",
            "to": to,
            "subject": subject,
            "body": body,
            "status": "sent",
        }
        self.sent.append(msg)
        return {"success": True, "message_id": msg_id, "status": "sent", "to": to, "subject": subject}

email_provider = MockEmailProvider()

def search_email_handler(query: str) -> Dict[str, Any]:
    emails = email_provider.search_email(query=query)
    return {"query": query, "count": len(emails), "emails": emails}

def create_draft_handler(to: str, subject: str, body: str) -> Dict[str, Any]:
    return email_provider.create_draft(to=to, subject=subject, body=body)

def send_email_handler(to: str, subject: str, body: str) -> Dict[str, Any]:
    return email_provider.send_email(to=to, subject=subject, body=body)

def send_email_preview(to: str, subject: str, body: str) -> Dict[str, Any]:
    return {
        "title": "Xác nhận gửi Email",
        "action_type": "send_email",
        "to": to,
        "subject": subject,
        "body": body,
        "warning": "Email sẽ được gửi chính thức đến hộp thư của người nhận.",
    }

# Register tools
registry.register(
    name="search_email",
    description="Tìm kiếm email theo từ khóa người gửi, người nhận, tiêu đề hoặc nội dung.",
    risk_level=RiskLevel.READ,
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Từ khóa tìm kiếm"}},
        "required": ["query"],
    },
    execute_fn=search_email_handler,
)

registry.register(
    name="create_draft",
    description="Tạo bản nháp email mà không gửi đi.",
    risk_level=RiskLevel.REVERSIBLE,
    parameters={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Địa chỉ người nhận"},
            "subject": {"type": "string", "description": "Tiêu đề email"},
            "body": {"type": "string", "description": "Nội dung email"},
        },
        "required": ["to", "subject", "body"],
    },
    execute_fn=create_draft_handler,
)

registry.register(
    name="send_email",
    description="Gửi email chính thức tới người nhận (yêu cầu xác nhận).",
    risk_level=RiskLevel.CONFIRM,
    parameters={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Địa chỉ người nhận"},
            "subject": {"type": "string", "description": "Tiêu đề email"},
            "body": {"type": "string", "description": "Nội dung email"},
        },
        "required": ["to", "subject", "body"],
    },
    execute_fn=send_email_handler,
    dry_run_fn=send_email_preview,
)
