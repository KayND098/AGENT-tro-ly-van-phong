from fastapi.responses import HTMLResponse

HTML_PAGE = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Trợ Lý Văn Phòng AI - Safe Office Assistant</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: #f1f5f9;
      color: #0f172a;
      display: flex;
      justify-content: center;
      height: 100vh;
      overflow: hidden;
    }
    .app-container {
      width: 100%;
      max-width: 860px;
      height: 100vh;
      background: #ffffff;
      display: flex;
      flex-direction: column;
      box-shadow: 0 4px 20px rgba(0,0,0,0.08);
    }
    header {
      padding: 16px 24px;
      border-bottom: 1px solid #e2e8f0;
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: #ffffff;
    }
    .header-left { display: flex; align-items: center; gap: 12px; }
    .logo-badge {
      width: 40px; height: 40px; border-radius: 10px;
      background: #2563eb; color: #ffffff;
      display: flex; align-items: center; justify-content: center;
      font-weight: bold; font-size: 18px;
    }
    .header-title h1 { font-size: 17px; font-weight: 700; color: #0f172a; }
    .header-title p { font-size: 12px; color: #64748b; margin-top: 2px; }
    .status-badge {
      display: flex; align-items: center; gap: 6px;
      font-size: 12px; color: #15803d; background: #dcfce7;
      padding: 4px 12px; border-radius: 16px; font-weight: 600;
    }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: #16a34a; }

    #chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 18px;
      background: #f8fafc;
    }
    .message-row { display: flex; flex-direction: column; width: 100%; }
    .message-row.user { align-items: flex-end; }
    .message-row.assistant { align-items: flex-start; }
    .message-bubble {
      max-width: 85%;
      padding: 12px 18px;
      border-radius: 16px;
      font-size: 14.5px;
      line-height: 1.5;
      white-space: pre-wrap;
    }
    .message-row.user .message-bubble {
      background: #2563eb; color: #ffffff;
      border-radius: 16px 16px 4px 16px;
      box-shadow: 0 2px 4px rgba(37,99,235,0.2);
    }
    .message-row.assistant .message-bubble {
      background: #ffffff; color: #1e293b;
      border-radius: 16px 16px 16px 4px;
      border: 1px solid #e2e8f0;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .time-stamp { font-size: 11px; color: #94a3b8; margin-top: 4px; padding: 0 4px; }

    /* Thẻ Cần Xác Nhận */
    .confirm-card {
      margin-top: 10px;
      max-width: 600px;
      background: #fffaf5;
      border: 1px solid #fed7aa;
      border-radius: 10px;
      padding: 16px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .confirm-header {
      display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;
    }
    .confirm-title {
      display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 14px; color: #9a3412;
    }
    .warning-icon {
      width: 22px; height: 22px; border-radius: 50%; background: #ea580c; color: white;
      display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: bold;
    }
    .confirm-status {
      font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 12px;
      background: #fef3c7; color: #d97706; border: 1px solid #fde68a;
    }
    .confirm-warning {
      background: #fff7ed; border-left: 3px solid #ea580c;
      padding: 8px 12px; border-radius: 4px; font-size: 13px; color: #c2410c;
      margin-bottom: 12px; font-weight: 500;
    }
    .preview-box {
      background: #ffffff; border: 1px solid #f1f5f9; border-radius: 8px;
      padding: 12px 14px; font-size: 13.5px; margin-bottom: 12px;
    }
    .preview-row { margin-bottom: 6px; }
    .preview-label { font-weight: 600; color: #475569; }
    .preview-body {
      background: #f1f5f9; padding: 8px 12px; border-radius: 6px; margin-top: 4px;
      border-left: 3px solid #3b82f6; white-space: pre-wrap; font-size: 13px;
    }
    .dry-run-table {
      width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 6px;
      border: 1px solid #e2e8f0;
    }
    .dry-run-table td { padding: 6px 10px; border-bottom: 1px solid #f1f5f9; }
    .btn-group { display: flex; gap: 8px; margin-top: 8px; }
    .btn {
      padding: 8px 16px; border-radius: 6px; font-size: 13px; font-weight: 600;
      cursor: pointer; border: none; transition: 0.15s;
    }
    .btn-approve { background: #16a34a; color: white; flex: 1; }
    .btn-approve:hover { background: #15803d; }
    .btn-edit { background: #fef3c7; color: #b45309; border: 1px solid #fcd34d; }
    .btn-edit:hover { background: #fde68a; }
    .btn-reject { background: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; }
    .btn-reject:hover { background: #fecaca; }
    .btn:disabled { opacity: 0.6; cursor: not-allowed; }

    /* Email & Event list */
    .result-card {
      background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px;
      padding: 10px 14px; font-size: 13px; margin-top: 6px; max-width: 600px;
    }

    /* Quick Pills */
    .quick-pills {
      padding: 10px 24px; background: #f1f5f9; border-top: 1px solid #e2e8f0;
      display: flex; gap: 8px; overflow-x: auto;
    }
    .pill {
      padding: 6px 14px; background: #ffffff; border: 1px solid #cbd5e1;
      border-radius: 16px; font-size: 12px; font-weight: 500; color: #334155;
      cursor: pointer; white-space: nowrap; transition: 0.15s;
    }
    .pill:hover { background: #f8fafc; border-color: #94a3b8; }

    /* Footer Input */
    footer { padding: 16px 24px; border-top: 1px solid #e2e8f0; background: #ffffff; }
    .input-form { display: flex; gap: 10px; }
    .chat-input {
      flex: 1; padding: 12px 16px; border-radius: 8px; border: 1px solid #cbd5e1;
      font-size: 14px; outline: none;
    }
    .chat-input:focus { border-color: #2563eb; }
    .btn-send {
      padding: 12px 24px; background: #2563eb; color: white; border: none;
      border-radius: 8px; font-weight: 600; font-size: 14px; cursor: pointer;
    }
    .btn-send:hover { background: #1d4ed8; }

    /* Toast */
    #toast-container {
      position: fixed; bottom: 24px; right: 24px; z-index: 9999;
      display: flex; flex-direction: column; gap: 8px;
    }
    .toast {
      padding: 12px 18px; border-radius: 8px; font-size: 13.5px; font-weight: 500;
      color: white; box-shadow: 0 4px 12px rgba(0,0,0,0.15); animation: fadeIn 0.2s;
    }
    .toast.info { background: #2563eb; }
    .toast.success { background: #16a34a; }
    .toast.warning { background: #d97706; }
    .toast.error { background: #dc2626; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
  </style>
</head>
<body>
  <div class="app-container">
    <header>
      <div class="header-left">
        <div class="logo-badge">AI</div>
        <div class="header-title">
          <h1>Trợ Lý Văn Phòng An Toàn</h1>
          <p>Bản Skeleton • Human-in-the-loop • Bảo Mật & Audit Log</p>
        </div>
      </div>
      <div class="status-badge">
        <span class="status-dot"></span> Đang hoạt động
      </div>
    </header>

    <main id="chat-messages"></main>

    <div class="quick-pills">
      <button class="pill" onclick="sendPrompt('tìm email của Minh')">🔍 Tìm email của Minh</button>
      <button class="pill" onclick="sendPrompt('gửi email cho Minh nội dung Báo cáo tuần đã hoàn thành')">✉️ Gửi email cho Minh</button>
      <button class="pill" onclick="sendPrompt('xóa 10 dòng đầu sheet Doanh thu')">🗑️ Xóa 10 dòng sheet Doanh thu</button>
      <button class="pill" onclick="sendPrompt('xem lịch họp tuần này')">📅 Xem lịch họp</button>
    </div>

    <footer>
      <form class="input-form" onsubmit="handleSubmit(event)">
        <input type="text" id="user-input" class="chat-input" placeholder="Nhập yêu cầu (ví dụ: 'tìm email', 'gửi email cho Minh', 'xóa dòng sheet')...">
        <button type="submit" class="btn-send">Gửi</button>
      </form>
    </footer>
  </div>

  <div id="toast-container"></div>

  <script>
    const messages = [];

    function addToast(text, type = 'info') {
      const container = document.getElementById('toast-container');
      const toast = document.createElement('div');
      toast.className = `toast ${type}`;
      toast.innerText = text;
      container.appendChild(toast);
      setTimeout(() => toast.remove(), 3500);
    }

    function getTimeString() {
      const d = new Date();
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    function appendMessage(role, content, extra = null) {
      const container = document.getElementById('chat-messages');
      const row = document.createElement('div');
      row.className = `message-row ${role}`;

      let extraHtml = '';

      // Kết quả Đọc (READ)
      if (extra && extra.type === 'tool_executed') {
        if (extra.tool_name === 'search_email' && extra.result.emails) {
          extraHtml += `<div style="font-weight:600; font-size:13px; margin: 8px 0 4px;">Kết quả tìm thấy (${extra.result.emails.length} email):</div>`;
          extra.result.emails.forEach(e => {
            extraHtml += `
              <div class="result-card">
                <div style="display:flex; justify-content:space-between;">
                  <strong>${e.from}</strong>
                  <span style="color:#94a3b8; font-size:11px;">${e.date}</span>
                </div>
                <div style="color:#2563eb; font-weight:500; margin:2px 0;">${e.subject}</div>
                <div style="color:#475569; font-size:12px;">${e.body}</div>
              </div>
            `;
          });
        } else if (extra.tool_name === 'list_events' && extra.result.events) {
          extraHtml += `<div style="font-weight:600; font-size:13px; margin: 8px 0 4px;">Sự kiện lịch sắp tới:</div>`;
          extra.result.events.forEach(evt => {
            extraHtml += `
              <div class="result-card">
                <strong>📅 ${evt.title}</strong>
                <div style="color:#64748b; font-size:12px; margin-top:2px;">${evt.start_time} - ${evt.end_time}</div>
              </div>
            `;
          });
        }
      }

      // Thẻ Xác Nhận (CONFIRM)
      if (extra && extra.pending_action) {
        const action = extra.pending_action;
        const p = action.preview || {};
        let previewDetails = '';

        if (action.tool_name === 'send_email') {
          previewDetails = `
            <div class="preview-row"><span class="preview-label">Người nhận (To):</span> <strong>${p.to || ''}</strong></div>
            <div class="preview-row"><span class="preview-label">Tiêu đề:</span> ${p.subject || ''}</div>
            <div class="preview-row">
              <span class="preview-label">Nội dung:</span>
              <div class="preview-body">${p.body || ''}</div>
            </div>
          `;
        } else if (action.tool_name === 'delete_rows') {
          let rowsHtml = '';
          if (p.sample_rows_preview) {
            p.sample_rows_preview.forEach((r, idx) => {
              rowsHtml += `<tr><td style="color:#94a3b8; width:25px;">#${idx+1}</td>${r.map(c => `<td>${c}</td>`).join('')}</tr>`;
            });
          }
          previewDetails = `
            <div class="preview-row"><span class="preview-label">Bảng tính:</span> <strong>Sheet "${p.sheet_name}"</strong></div>
            <div class="preview-row"><span class="preview-label">Phạm vi:</span> <strong style="color:#dc2626;">${p.affected_range} (${p.target_count} dòng)</strong></div>
            <div style="margin-top:6px; font-weight:600; color:#475569; font-size:12px;">Dữ liệu mẫu sắp bị xóa (Dry-run):</div>
            <table class="dry-run-table">${rowsHtml}</table>
          `;
        }

        extraHtml += `
          <div class="confirm-card" id="card-${action.id}">
            <div class="confirm-header">
              <div class="confirm-title"><span class="warning-icon">!</span> CẦN XÁC NHẬN HÀNH ĐỘNG</div>
              <span class="confirm-status" id="status-${action.id}">Chờ duyệt</span>
            </div>
            ${p.warning ? `<div class="confirm-warning">${p.warning}</div>` : ''}
            <div class="preview-box">${previewDetails}</div>
            <div style="font-size:11px; color:#94a3b8; margin-bottom:10px;">Thời hạn xác nhận: 10 phút.</div>
            <div class="btn-group" id="btn-group-${action.id}">
              <button class="btn btn-approve" onclick="approveAction('${action.id}', '${action.tool_name}')">✓ Duyệt thực thi</button>
              <button class="btn btn-edit" onclick="editAction()">✎ Sửa</button>
              <button class="btn btn-reject" onclick="rejectAction('${action.id}')">✕ Hủy bỏ</button>
            </div>
          </div>
        `;
      }

      row.innerHTML = `
        <div class="message-bubble">${content}</div>
        ${extraHtml}
        <div class="time-stamp">${getTimeString()}</div>
      `;
      container.appendChild(row);
      container.scrollTop = container.scrollHeight;
    }

    async function approveAction(actionId, toolName) {
      try {
        const res = await fetch(`/actions/${actionId}/approve`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({})
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail?.message || data.detail || 'Lỗi khi duyệt');

        addToast('✓ Đã duyệt và thực thi thành công!', 'success');
        document.getElementById(`status-${actionId}`).innerText = 'Đã duyệt & Ghi audit_log';
        document.getElementById(`status-${actionId}`).style.background = '#dcfce7';
        document.getElementById(`status-${actionId}`).style.color = '#15803d';
        document.getElementById(`btn-group-${actionId}`).innerHTML = '<span style="color:#16a34a; font-weight:600; font-size:13px;">✓ Đã thực thi và lưu vết kiểm toán.</span>';
      } catch (err) {
        addToast(err.message, 'error');
      }
    }

    async function rejectAction(actionId) {
      try {
        const res = await fetch(`/actions/${actionId}/reject`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason: 'Người dùng bấm Hủy' })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Lỗi khi hủy');

        addToast('✕ Đã hủy bỏ hành động.', 'info');
        document.getElementById(`status-${actionId}`).innerText = 'Đã hủy';
        document.getElementById(`status-${actionId}`).style.background = '#fee2e2';
        document.getElementById(`status-${actionId}`).style.color = '#b91c1c';
        document.getElementById(`btn-group-${actionId}`).innerHTML = '<span style="color:#64748b; font-size:13px;">✕ Đã hủy bỏ thao tác.</span>';
      } catch (err) {
        addToast(err.message, 'error');
      }
    }

    function editAction() {
      addToast('Chức năng đang phát triển', 'warning');
    }

    async function sendPrompt(text) {
      if (!text.trim()) return;
      messages.push({ role: 'user', content: text });
      appendMessage('user', text);

      try {
        const res = await fetch('/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ messages })
        });
        const data = await res.json();
        messages.push({ role: 'assistant', content: data.content || '' });
        appendMessage('assistant', data.content, data);
      } catch (err) {
        appendMessage('assistant', '⚠️ Lỗi khi kết nối tới backend.');
        addToast('Lỗi kết nối tới Backend', 'error');
      }
    }

    function handleSubmit(e) {
      e.preventDefault();
      const input = document.getElementById('user-input');
      const val = input.value.trim();
      if (val) {
        sendPrompt(val);
        input.value = '';
      }
    }

    // Tin nhắn chào mừng ban đầu
    window.onload = () => {
      appendMessage(
        'assistant',
        'Xin chào! Tôi là Trợ Lý Văn Phòng AI (Bản Khung Skeleton).\\n' +
        'Tôi đã sẵn sàng với 4 kịch bản kiểm thử an toàn có Human-in-the-loop. Bạn có thể chọn nhanh gợi ý bên dưới hoặc tự nhập lệnh.'
      );
    };
  </script>
</body>
</html>
"""
