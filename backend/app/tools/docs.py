from typing import List, Dict, Any
from .registry import registry, RiskLevel
from ..rag.retriever import default_retriever

def search_documents_handler(query: str) -> Dict[str, Any]:
    """Tìm kiếm trong tài liệu nội bộ công ty qua FtsRetriever."""
    results = default_retriever.retrieve(query=query, top_k=5)
    return {
        "query": query,
        "count": len(results),
        "documents": results,
    }

# Đăng ký tool search_documents mức READ
registry.register(
    name="search_documents",
    description="Tìm kiếm thông tin trong các tài liệu nội bộ của công ty (quy trình nghỉ phép, quy định công tác phí, báo cáo, chính sách bảo mật).",
    risk_level=RiskLevel.READ,
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Từ khóa tìm kiếm thông tin trong tài liệu nội bộ",
            }
        },
        "required": ["query"],
    },
    execute_fn=search_documents_handler,
)
