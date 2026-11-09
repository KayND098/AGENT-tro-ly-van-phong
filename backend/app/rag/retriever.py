import os
import re
import hashlib
import sqlite3
import unicodedata
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

from ..db import get_db_path, get_db

DEFAULT_DOCS_DIR = (Path(__file__).resolve().parent.parent.parent / "data" / "docs").resolve()

STOP_WORDS = {
    "tim", "tai", "lieu", "ve", "cua", "cho", "xem", "huong", "dan", "nhe", "a", "oi",
    "la", "va", "cac", "nhung", "trong", "khi", "duoc", "co", "nay", "do", "gi",
    "con", "cai", "duoi", "tren", "ngoai", "sao", "nao", "ai", "dau", "the", "giup",
    "len", "xuong", "ra", "vao",
    "tìm", "tài", "liệu", "về", "của", "cho", "xem", "hướng", "dẫn", "nhé", "ạ", "ơi",
    "là", "và", "các", "những", "trong", "khi", "được", "có", "này", "đó", "gì",
    "còn", "cái", "dưới", "trên", "ngoài", "sao", "nào", "ai", "đâu", "thế", "giúp",
    "lên", "xuống", "ra", "vào"
}

def remove_diacritics(text: str) -> str:
    """Loại bỏ dấu tiếng Việt để đối chiếu không dấu."""
    nfd = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return stripped.replace("đ", "d").replace("Đ", "D")

class Retriever(ABC):
    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Tìm kiếm các tài liệu liên quan tới truy vấn."""
        pass

class FtsRetriever(Retriever):
    """
    Retriever sử dụng SQLite FTS5 với tokenizer unicode61 remove_diacritics 2.
    Hỗ trợ tìm kiếm tiếng Việt có dấu và không dấu, xếp hạng theo BM25 rank,
    lập chỉ mục tự động và ngăn chặn tấn công Path Traversal.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        docs_dir: Optional[str] = None,
        auto_index: bool = True,
    ):
        self.db_path = db_path or get_db_path()
        self.docs_dir = Path(docs_dir or DEFAULT_DOCS_DIR).resolve()
        self.has_fts5 = self._check_fts5_support()
        if not self.has_fts5:
            logging.warning("SQLite không hỗ trợ module FTS5 trên máy này. Tự động chuyển sang fallback keyword scoring.")

        if auto_index:
            try:
                self.index_documents()
            except Exception as e:
                logging.warning("Không thể tự động lập chỉ mục khi khởi động (%s). Sẽ tiếp tục không crash.", str(e))

    @contextmanager
    def _get_connection(self):
        with get_db(self.db_path) as conn:
            yield conn

    def _check_fts5_support(self) -> bool:
        try:
            with self._get_connection() as conn:
                conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_check USING fts5(x);")
                conn.execute("DROP TABLE IF EXISTS _fts5_check;")
            return True
        except Exception:
            return False

    def is_safe_file(self, filename: str) -> bool:
        """Kiểm tra chặn Path Traversal: Tuyệt đối không cho phép truy cập ngoài docs_dir."""
        if not filename or not isinstance(filename, str):
            return False
        # Chặn các ký tự điều hướng thư mục
        if ".." in filename or filename.startswith("/") or filename.startswith("\\") or ":" in filename:
            return False
        try:
            target = (self.docs_dir / filename).resolve()
            resolved_base = self.docs_dir.resolve()
            return target.is_relative_to(resolved_base) and target != resolved_base
        except Exception:
            return False

    def read_document(self, filename: str) -> str:
        """Đọc an toàn nội dung tài liệu với cơ chế chặn Path Traversal."""
        if not self.is_safe_file(filename):
            raise ValueError(f"Đường dẫn tài liệu không hợp lệ hoặc vi phạm bảo mật: '{filename}'")
        target = (self.docs_dir / filename).resolve()
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"Không tìm thấy tài liệu: '{filename}'")
        return target.read_text(encoding="utf-8")

    def chunk_document(self, filename: str, content: str) -> List[Dict[str, Any]]:
        """
        Cắt tài liệu theo tiêu đề mục và đoạn văn bản (khoảng 300 - 800 ký tự).
        Bảo toàn tên file và tiêu đề mục tương ứng.
        """
        lines = content.splitlines()
        chunks: List[Dict[str, Any]] = []
        current_section = "Nội dung chung"
        current_lines: List[str] = []

        for line in lines:
            stripped = line.strip()
            # Bắt đầu mục mới (heading markdown)
            if stripped.startswith("## ") or stripped.startswith("### "):
                if current_lines:
                    text_chunk = "\n".join(current_lines).strip()
                    if text_chunk:
                        chunks.append({
                            "filename": filename,
                            "section": current_section,
                            "content": text_chunk,
                        })
                    current_lines = []
                current_section = stripped.lstrip("#").strip()
            elif stripped.startswith("# "):
                # Tiêu đề tài liệu
                doc_title = stripped.lstrip("#").strip()
                current_lines.append(doc_title)
            else:
                current_lines.append(line)
                # Tách đoạn nếu vượt quá ngưỡng ~700 ký tự
                if len("\n".join(current_lines)) >= 700:
                    text_chunk = "\n".join(current_lines).strip()
                    if text_chunk:
                        chunks.append({
                            "filename": filename,
                            "section": current_section,
                            "content": text_chunk,
                        })
                    current_lines = []

        if current_lines:
            text_chunk = "\n".join(current_lines).strip()
            if text_chunk:
                chunks.append({
                    "filename": filename,
                    "section": current_section,
                    "content": text_chunk,
                })

        return chunks

    def index_documents(self, force: bool = False) -> int:
        """
        Lập chỉ mục các tài liệu trong docs_dir vào SQLite FTS5.
        Chỉ nạp lại khi file thay đổi (so khớp mã băm sha256).
        Không crash nếu thư mục trống hoặc không tồn tại.
        """
        if not self.docs_dir.exists():
            os.makedirs(self.docs_dir, exist_ok=True)
            return 0

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Tạo bảng quản lý phiên bản / mã băm tài liệu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS doc_index_meta (
                    filename TEXT PRIMARY KEY,
                    file_hash TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)

            # Tạo bảng chỉ mục FTS5 hoặc bảng fallback
            if self.has_fts5:
                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunks_fts USING fts5(
                        filename,
                        section,
                        content,
                        tokenize='unicode61 remove_diacritics 2'
                    );
                """)
            else:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS doc_chunks_fallback (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        filename TEXT NOT NULL,
                        section TEXT NOT NULL,
                        content TEXT NOT NULL
                    );
                """)
            conn.commit()

            # Quét các file .md và .txt trong docs_dir
            doc_files = [f for f in self.docs_dir.glob("*") if f.is_file() and f.suffix.lower() in (".md", ".txt")]
            indexed_count = 0

            for doc_file in doc_files:
                filename = doc_file.name
                if not self.is_safe_file(filename):
                    continue

                try:
                    file_bytes = doc_file.read_bytes()
                    file_hash = hashlib.sha256(file_bytes).hexdigest()
                except Exception as e:
                    logging.warning("Không thể đọc file '%s' khi lập chỉ mục: %s", filename, str(e))
                    continue

                # Kiểm tra mã băm xem file có thay đổi hay không
                if not force:
                    cursor.execute("SELECT file_hash FROM doc_index_meta WHERE filename = ?", (filename,))
                    row = cursor.fetchone()
                    if row and row["file_hash"] == file_hash:
                        continue

                # Đọc nội dung và phân đoạn
                try:
                    text_content = file_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    text_content = file_bytes.decode("utf-8", errors="ignore")

                chunks = self.chunk_document(filename, text_content)

                # Xóa dữ liệu cũ của file
                if self.has_fts5:
                    cursor.execute("DELETE FROM doc_chunks_fts WHERE filename = ?", (filename,))
                    for c in chunks:
                        cursor.execute(
                            "INSERT INTO doc_chunks_fts (filename, section, content) VALUES (?, ?, ?)",
                            (c["filename"], c["section"], c["content"]),
                        )
                else:
                    cursor.execute("DELETE FROM doc_chunks_fallback WHERE filename = ?", (filename,))
                    for c in chunks:
                        cursor.execute(
                            "INSERT INTO doc_chunks_fallback (filename, section, content) VALUES (?, ?, ?)",
                            (c["filename"], c["section"], c["content"]),
                        )

                now_iso = datetime.now(timezone.utc).isoformat()
                cursor.execute("""
                    INSERT INTO doc_index_meta (filename, file_hash, chunk_count, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(filename) DO UPDATE SET
                        file_hash = excluded.file_hash,
                        chunk_count = excluded.chunk_count,
                        updated_at = excluded.updated_at;
                """, (filename, file_hash, len(chunks), now_iso))

                indexed_count += len(chunks)

            conn.commit()
            return indexed_count

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Tìm kiếm các đoạn tài liệu phù hợp nhất với truy vấn.
        Trả về danh sách gồm filename, section, content và score.
        Hỗ trợ tìm có dấu và không dấu.
        Câu hỏi hoàn toàn không liên quan sẽ trả về danh sách rỗng.
        """
        if not query or not query.strip():
            return []

        clean_query = query.strip()
        # Tách các từ khóa hợp lệ
        raw_terms = re.findall(r"[\w]+", clean_query)
        if not raw_terms:
            return []

        # Lọc bỏ stop words phổ biến nếu còn từ khóa chính
        meaningful_terms = [t for t in raw_terms if len(t) > 1 and t.lower() not in STOP_WORDS]
        terms = meaningful_terms if meaningful_terms else raw_terms

        # Chuẩn hóa term thành chữ cái/chữ số
        clean_terms = [re.sub(r"[^A-Za-z0-9À-ỹ]", "", t) for t in terms if t]
        clean_terms = [t for t in clean_terms if t]
        if not clean_terms:
            return []

        # 1. Truy vấn bằng FTS5 (nếu hỗ trợ)
        if self.has_fts5:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    # Chiến lược 1: Thử truy vấn AND (tất cả các từ khóa đều xuất hiện trong chunk)
                    # Ưu tiên độ chính xác cao nhất
                    if len(clean_terms) >= 2:
                        fts_and_query = " AND ".join(f'"{t}"' for t in clean_terms)
                        cursor.execute("""
                            SELECT filename, section, content, rank
                            FROM doc_chunks_fts
                            WHERE doc_chunks_fts MATCH ?
                            ORDER BY rank
                            LIMIT ?
                        """, (fts_and_query, top_k))
                        rows = cursor.fetchall()
                        if rows:
                            return [
                                {
                                    "filename": r["filename"],
                                    "section": r["section"],
                                    "content": r["content"],
                                    "score": round(abs(float(r["rank"])), 4),
                                }
                                for r in rows
                            ]

                    # Chiến lược 2: Nếu AND không có kết quả (ví dụ query dài có thêm từ bổ nghĩa),
                    # dùng truy vấn OR nhưng yêu cầu khớp tối thiểu một ngưỡng từ khóa cần thiết
                    fts_or_query = " OR ".join(f'"{t}"' for t in clean_terms)
                    cursor.execute("""
                        SELECT filename, section, content, rank
                        FROM doc_chunks_fts
                        WHERE doc_chunks_fts MATCH ?
                        ORDER BY rank
                        LIMIT ?
                    """, (fts_or_query, top_k * 2))
                    candidate_rows = cursor.fetchall()

                    # Lọc ứng viên: phải chứa tỷ lệ từ khóa đủ cao để tránh khớp bừa bãi âm tiết ngẫu nhiên
                    if len(clean_terms) <= 2:
                        min_match = len(clean_terms)
                    elif len(clean_terms) <= 4:
                        min_match = len(clean_terms) - 1
                    else:
                        min_match = max(3, int(len(clean_terms) * 0.7))

                    filtered_results = []

                    for r in candidate_rows:
                        content_lower = r["content"].lower()
                        content_unacc = remove_diacritics(content_lower)
                        matched_words = 0
                        for t in clean_terms:
                            t_lower = t.lower()
                            t_unacc = remove_diacritics(t_lower)
                            # Khớp nguyên từ để tránh khớp phụ âm rời
                            if re.search(rf"\b{re.escape(t_lower)}\b", content_lower) or re.search(rf"\b{re.escape(t_unacc)}\b", content_unacc):
                                matched_words += 1

                        if matched_words >= min_match:
                            filtered_results.append({
                                "filename": r["filename"],
                                "section": r["section"],
                                "content": r["content"],
                                "score": round(abs(float(r["rank"])), 4),
                            })
                            if len(filtered_results) >= top_k:
                                break

                    if filtered_results:
                        return filtered_results

            except Exception as e:
                logging.warning("Lỗi truy vấn FTS5 (%s). Chuyển sang fallback keyword matching.", str(e))

        # 2. Phương án Fallback bằng Python keyword scoring (không cần FTS5)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if self.has_fts5:
                    cursor.execute("SELECT filename, section, content FROM doc_chunks_fts")
                else:
                    cursor.execute("SELECT filename, section, content FROM doc_chunks_fallback")
                rows = cursor.fetchall()

            scored_chunks = []
            if len(clean_terms) <= 2:
                min_match = len(clean_terms)
            elif len(clean_terms) <= 4:
                min_match = len(clean_terms) - 1
            else:
                min_match = max(3, int(len(clean_terms) * 0.7))

            for r in rows:
                content_lower = r["content"].lower()
                content_unaccented = remove_diacritics(content_lower)
                matched_count = 0
                score = 0.0

                for t in clean_terms:
                    t_lower = t.lower()
                    t_unaccented = remove_diacritics(t_lower)
                    if t_lower in content_lower:
                        score += 2.0
                        matched_count += 1
                    elif t_unaccented in content_unaccented:
                        score += 1.0
                        matched_count += 1

                if matched_count >= min_match and score > 0:
                    scored_chunks.append({
                        "filename": r["filename"],
                        "section": r["section"],
                        "content": r["content"],
                        "score": round(score, 4),
                    })

            scored_chunks.sort(key=lambda x: x["score"], reverse=True)
            return scored_chunks[:top_k]
        except Exception as e:
            logging.error("Lỗi trong fallback keyword retriever: %s", str(e))
            return []

# Khởi tạo instance retriever mặc định
default_retriever = FtsRetriever()
