# Giai đoạn 1: Build React SPA bằng Node
FROM node:20-alpine AS builder

WORKDIR /app

# Cài đặt dependencies (sử dụng cache)
COPY package.json package-lock.json ./
RUN npm ci || npm install

# Sao chép toàn bộ mã nguồn frontend và thực hiện build
COPY . .
RUN npm run build

# Giai đoạn 2: Phục vụ file tĩnh bằng Nginx
FROM nginx:alpine

# Sao chép dist từ builder sang thư mục phục vụ của nginx
COPY --from=builder /app/dist /usr/share/nginx/html

# Cấu hình nginx reverse proxy
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# Chạy Nginx ở chế độ foreground
CMD ["nginx", "-g", "daemon off;"]
