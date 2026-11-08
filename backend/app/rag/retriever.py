from abc import ABC, abstractmethod
from typing import List, Dict, Any

class Retriever(ABC):
    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Tìm kiếm các tài liệu liên quan tới truy vấn."""
        pass

class StubRetriever(Retriever):
    """Bản stub phục vụ giai đoạn skeleton, chưa tích hợp vector DB / embedding thật."""
    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        # Trả về danh sách rỗng đúng theo spec
        return []

default_retriever = StubRetriever()
