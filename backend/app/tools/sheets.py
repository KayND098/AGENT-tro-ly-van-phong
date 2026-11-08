from typing import List, Dict, Any, Optional
from .registry import registry, RiskLevel

class MockSheetsProvider:
    def __init__(self):
        # Giả lập sheet "Doanh thu"
        self.sheets: Dict[str, List[List[Any]]] = {
            "Doanh thu": [
                ["Mã ĐH", "Khách hàng", "Doanh thu (VNĐ)", "Trạng thái", "Ngày tạo"],
                ["DH001", "Công ty Alpha", 15000000, "Đã thanh toán", "2026-10-01"],
                ["DH002", "Công ty Beta", 8500000, "Chờ duyệt", "2026-10-02"],
                ["DH003", "Anh Tuấn", 3200000, "Đã thanh toán", "2026-10-03"],
                ["DH004", "Chị Mai", 12000000, "Đã hủy", "2026-10-04"],
                ["DH005", "Tập đoàn Gamma", 45000000, "Đã thanh toán", "2026-10-05"],
                ["DH006", "Cửa hàng X", 6700000, "Đã thanh toán", "2026-10-06"],
                ["DH007", "Công ty Delta", 19500000, "Chờ duyệt", "2026-10-07"],
                ["DH008", "Đại lý Y", 24000000, "Đã thanh toán", "2026-10-08"],
                ["DH009", "Anh Hùng", 5100000, "Đã thanh toán", "2026-10-09"],
                ["DH010", "Chị Lan", 17800000, "Đã thanh toán", "2026-10-10"],
                ["DH011", "Công ty Omega", 31000000, "Đang xử lý", "2026-10-11"],
                ["DH012", "Cửa hàng Z", 4200000, "Đã thanh toán", "2026-10-12"],
            ]
        }

    def read_range(self, sheet_name: str, range_name: str = "A1:E15") -> Dict[str, Any]:
        data = self.sheets.get(sheet_name, [])
        return {"sheet_name": sheet_name, "range": range_name, "values": data}

    def update_cells(self, sheet_name: str, range_name: str, values: List[List[Any]]) -> Dict[str, Any]:
        return {"success": True, "sheet_name": sheet_name, "range": range_name, "updated_rows": len(values)}

    def dry_run_delete_rows(self, sheet_name: str, count: int) -> Dict[str, Any]:
        data = self.sheets.get(sheet_name, [])
        # Bỏ qua header ở index 0, lấy `count` dòng đầu tiên bị ảnh hưởng
        rows_to_delete = data[1 : 1 + count] if len(data) > 1 else []
        return {
            "title": f"Xác nhận xóa {count} dòng trong Sheet '{sheet_name}'",
            "action_type": "delete_rows",
            "sheet_name": sheet_name,
            "target_count": count,
            "total_available_rows": max(0, len(data) - 1),
            "affected_range": f"Hàng 2 đến Hàng {min(1 + count, len(data))}",
            "sample_rows_preview": rows_to_delete[:4],  # Lấy tối đa 4 dòng mẫu làm ví dụ
            "warning": f"Hành động này sẽ XÓA VĨNH VIỄN {count} dòng dữ liệu trong sheet '{sheet_name}'. Không thể tự động khôi phục!",
        }

    def delete_rows(self, sheet_name: str, count: int) -> Dict[str, Any]:
        if sheet_name not in self.sheets:
            return {"success": False, "error": f"Không tìm thấy sheet '{sheet_name}'"}
        
        current = self.sheets[sheet_name]
        header = current[:1]
        remaining = current[1 + count :]
        self.sheets[sheet_name] = header + remaining
        return {
            "success": True,
            "sheet_name": sheet_name,
            "deleted_count": count,
            "remaining_rows": len(self.sheets[sheet_name]) - 1,
        }

sheets_provider = MockSheetsProvider()

def read_range_handler(sheet_name: str, range_name: str = "A1:E15") -> Dict[str, Any]:
    return sheets_provider.read_range(sheet_name=sheet_name, range_name=range_name)

def update_cells_handler(sheet_name: str, range_name: str, values: List[List[Any]]) -> Dict[str, Any]:
    return sheets_provider.update_cells(sheet_name=sheet_name, range_name=range_name, values=values)

def delete_rows_handler(sheet_name: str, count: int) -> Dict[str, Any]:
    return sheets_provider.delete_rows(sheet_name=sheet_name, count=count)

def delete_rows_preview(sheet_name: str, count: int) -> Dict[str, Any]:
    return sheets_provider.dry_run_delete_rows(sheet_name=sheet_name, count=count)

registry.register(
    name="read_range",
    description="Đọc dữ liệu từ bảng tính Google Sheets.",
    risk_level=RiskLevel.READ,
    parameters={
        "type": "object",
        "properties": {
            "sheet_name": {"type": "string", "description": "Tên sheet hoặc bảng tính"},
            "range_name": {"type": "string", "description": "Dải ô cần đọc, ví dụ: A1:D10"},
        },
        "required": ["sheet_name"],
    },
    execute_fn=read_range_handler,
)

registry.register(
    name="update_cells",
    description="Cập nhật ô trong Google Sheets.",
    risk_level=RiskLevel.CONFIRM,
    parameters={
        "type": "object",
        "properties": {
            "sheet_name": {"type": "string"},
            "range_name": {"type": "string"},
            "values": {"type": "array"},
        },
        "required": ["sheet_name", "range_name", "values"],
    },
    execute_fn=update_cells_handler,
)

registry.register(
    name="delete_rows",
    description="Xóa các hàng đầu tiên trong bảng tính (yêu cầu xác nhận và dry-run).",
    risk_level=RiskLevel.CONFIRM,
    parameters={
        "type": "object",
        "properties": {
            "sheet_name": {"type": "string", "description": "Tên sheet"},
            "count": {"type": "integer", "description": "Số dòng cần xóa"},
        },
        "required": ["sheet_name", "count"],
    },
    execute_fn=delete_rows_handler,
    dry_run_fn=delete_rows_preview,
)
