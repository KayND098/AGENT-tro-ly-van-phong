from typing import List, Dict, Any, Optional
from datetime import datetime
from .registry import registry, RiskLevel

class MockCalendarProvider:
    def __init__(self):
        self.events = [
            {
                "id": "evt_001",
                "title": "Họp giao ban tuần",
                "start_time": "2026-11-04 09:00:00",
                "end_time": "2026-11-04 10:00:00",
                "attendees": ["team@company.com"],
            },
            {
                "id": "evt_002",
                "title": "Thảo luận quy trình Trợ lý AI",
                "start_time": "2026-11-04 14:00:00",
                "end_time": "2026-11-04 15:30:00",
                "attendees": ["minh.nguyen@company.com", "me@company.com"],
            },
        ]

    def list_events(self, query: Optional[str] = None) -> List[Dict[str, Any]]:
        if not query:
            return self.events
        q = query.lower()
        return [e for e in self.events if q in e["title"].lower()]

    def create_event(self, title: str, start_time: str, end_time: str, attendees: Optional[List[str]] = None) -> Dict[str, Any]:
        evt_id = f"evt_{len(self.events) + 1:03d}"
        event = {
            "id": evt_id,
            "title": title,
            "start_time": start_time,
            "end_time": end_time,
            "attendees": attendees or [],
        }
        self.events.append(event)
        return {"success": True, "event": event}

calendar_provider = MockCalendarProvider()

def list_events_handler(query: Optional[str] = None) -> Dict[str, Any]:
    events = calendar_provider.list_events(query=query)
    return {"count": len(events), "events": events}

def create_event_handler(title: str, start_time: str, end_time: str, attendees: Optional[List[str]] = None) -> Dict[str, Any]:
    return calendar_provider.create_event(title=title, start_time=start_time, end_time=end_time, attendees=attendees)

def create_event_preview(title: str, start_time: str, end_time: str, attendees: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "title": "Xác nhận tạo sự kiện Lịch",
        "action_type": "create_event",
        "event_title": title,
        "start_time": start_time,
        "end_time": end_time,
        "attendees": attendees or [],
        "warning": "Sự kiện sẽ được ghi nhận vào Lịch chính và gửi thư mời tới người tham dự.",
    }

registry.register(
    name="list_events",
    description="Xem danh sách sự kiện lịch.",
    risk_level=RiskLevel.READ,
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Từ khóa tìm kiếm sự kiện"}},
    },
    execute_fn=list_events_handler,
)

registry.register(
    name="create_event",
    description="Tạo sự kiện mới trong Google Calendar.",
    risk_level=RiskLevel.CONFIRM,
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Tên sự kiện"},
            "start_time": {"type": "string", "description": "Thời gian bắt đầu"},
            "end_time": {"type": "string", "description": "Thời gian kết thúc"},
            "attendees": {"type": "array", "items": {"type": "string"}, "description": "Danh sách email tham dự"},
        },
        "required": ["title", "start_time", "end_time"],
    },
    execute_fn=create_event_handler,
    dry_run_fn=create_event_preview,
)
