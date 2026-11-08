from enum import Enum
from typing import Callable, Dict, Any, Optional, List, Tuple
from pydantic import BaseModel, ConfigDict

class RiskLevel(str, Enum):
    READ = "read"
    REVERSIBLE = "reversible"
    CONFIRM = "confirm"

class ToolDefinition(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str
    description: str
    risk_level: RiskLevel
    parameters: Dict[str, Any]

class RegisteredTool:
    def __init__(
        self,
        name: str,
        description: str,
        risk_level: RiskLevel,
        parameters: Dict[str, Any],
        execute_fn: Callable[..., Any],
        dry_run_fn: Optional[Callable[..., Any]] = None,
    ):
        self.name = name
        self.description = description
        self.risk_level = risk_level
        self.parameters = parameters
        self.execute_fn = execute_fn
        self.dry_run_fn = dry_run_fn

    def execute(self, **kwargs) -> Any:
        return self.execute_fn(**kwargs)

    def preview(self, **kwargs) -> Dict[str, Any]:
        if self.dry_run_fn:
            return self.dry_run_fn(**kwargs)
        return kwargs

    def validate_args(self, args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Kiểm tra tính hợp lệ của tham số dựa trên schema JSON được định nghĩa trong parameters.
        Trả về tuple (is_valid, error_message).
        """
        if not isinstance(args, dict):
            return False, "Tham số truyền vào phải là một đối tượng từ điển (dictionary)."

        required_fields = self.parameters.get("required", [])
        for field in required_fields:
            if field not in args or args[field] is None:
                return False, f"Thiếu tham số bắt buộc '{field}'."

        properties = self.parameters.get("properties", {})
        for key, val in args.items():
            if key in properties and val is not None:
                expected_type = properties[key].get("type")
                if expected_type == "string" and not isinstance(val, str):
                    return False, f"Tham số '{key}' phải là chuỗi (string), nhận được {type(val).__name__}."
                elif expected_type == "integer" and (isinstance(val, bool) or not isinstance(val, int)):
                    return False, f"Tham số '{key}' phải là số nguyên (integer), nhận được {type(val).__name__}."
                elif expected_type == "number" and (isinstance(val, bool) or not isinstance(val, (int, float))):
                    return False, f"Tham số '{key}' phải là số (number), nhận được {type(val).__name__}."
                elif expected_type == "array" and not isinstance(val, list):
                    return False, f"Tham số '{key}' phải là danh sách (array), nhận được {type(val).__name__}."
                elif expected_type == "object" and not isinstance(val, dict):
                    return False, f"Tham số '{key}' phải là đối tượng (object), nhận được {type(val).__name__}."
                elif expected_type == "boolean" and not isinstance(val, bool):
                    return False, f"Tham số '{key}' phải là boolean, nhận được {type(val).__name__}."

        return True, None

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, RegisteredTool] = {}

    def register(
        self,
        name: str,
        description: str,
        risk_level: RiskLevel,
        parameters: Dict[str, Any],
        execute_fn: Callable[..., Any],
        dry_run_fn: Optional[Callable[..., Any]] = None,
    ) -> RegisteredTool:
        tool = RegisteredTool(
            name=name,
            description=description,
            risk_level=risk_level,
            parameters=parameters,
            execute_fn=execute_fn,
            dry_run_fn=dry_run_fn,
        )
        self._tools[name] = tool
        return tool

    def get(self, name: str) -> Optional[RegisteredTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "risk_level": t.risk_level.value,
                "parameters": t.parameters,
            }
            for t in self._tools.values()
        ]

registry = ToolRegistry()
