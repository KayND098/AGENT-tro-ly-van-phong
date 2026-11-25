FROM python:3.12-slim

# Tạo non-root user 'appuser'
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Cài đặt dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép mã nguồn ứng dụng và tài liệu mẫu RAG (không copy secrets, .env hay db)
COPY app/ ./app/
COPY data/docs/ ./data/docs/

# Tạo thư mục dữ liệu /data và cấp quyền cho appuser
RUN mkdir -p /data && chown -R appuser:appuser /data /app

# Chuyển sang non-root user
USER appuser

# Cấu hình biến môi trường mặc định trỏ dữ liệu vào /data
ENV DATABASE_PATH=/data/app.db \
    DOCS_DIR=/app/data/docs \
    PYTHONUNBUFFERED=1

# Healthcheck kiểm tra route /health
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

# Chạy uvicorn KHÔNG dùng --reload trong container sản xuất
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
