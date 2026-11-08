import { useState, useEffect } from 'react';
import { AuditLogItem } from '../types';

interface AuditLogViewProps {
  apiUrl: string;
}

export const AuditLogView = ({ apiUrl }: AuditLogViewProps) => {
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [typeFilter, setTypeFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiUrl}/audit`);
      if (res.ok) {
        const data = await res.json();
        setLogs(data.logs || []);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [apiUrl]);

  const formatRelativeTime = (isoString: string) => {
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffSecs = Math.floor((now.getTime() - date.getTime()) / 1000);
      if (diffSecs < 60) return 'Vừa xong';
      if (diffSecs < 3600) return `${Math.floor(diffSecs / 60)} phút trước`;
      if (diffSecs < 86400) return `${Math.floor(diffSecs / 3600)} giờ trước`;
      return date.toLocaleDateString('vi-VN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch {
      return isoString;
    }
  };

  const filteredLogs = logs.filter((item) => {
    if (typeFilter !== 'ALL' && item.action_type !== typeFilter) return false;
    if (statusFilter !== 'ALL' && item.status !== statusFilter) return false;
    return true;
  });

  return (
    <div style={{
      maxWidth: '1000px',
      margin: '0 auto',
      width: '100%',
      padding: '24px',
      display: 'flex',
      flexDirection: 'column',
      gap: '16px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 600, color: 'var(--md-on-surface)' }}>
            Nhật ký hoạt động (Audit Trail)
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--md-on-surface-variant)' }}>
            Ghi vết toàn bộ hành động được thực thi, duyệt, từ chối hoặc hết hạn theo chuẩn an toàn
          </p>
        </div>
        <button
          onClick={fetchLogs}
          disabled={loading}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '8px 14px',
            borderRadius: 'var(--radius-full)',
            border: '1px solid var(--md-outline)',
            backgroundColor: 'var(--md-surface)',
            color: 'var(--md-primary)',
            fontSize: '13px',
            fontWeight: 500,
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>refresh</span>
          {loading ? 'Đang tải...' : 'Làm mới'}
        </button>
      </div>

      {/* Filter Row */}
      <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          aria-label="Lọc theo loại hành động"
          style={{
            padding: '8px 12px',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--md-outline)',
            backgroundColor: 'var(--md-surface)',
            color: 'var(--md-on-surface)',
            fontSize: '13px',
          }}
        >
          <option value="ALL">Tất cả loại hành động</option>
          <option value="EXECUTE_READ">Đọc dữ liệu (Read)</option>
          <option value="PENDING_CREATED">Tạo yêu cầu duyệt</option>
          <option value="APPROVED">Đã duyệt (Approved)</option>
          <option value="REJECTED">Đã hủy (Rejected)</option>
          <option value="EXPIRED">Đã hết hạn (Expired)</option>
        </select>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          aria-label="Lọc theo trạng thái"
          style={{
            padding: '8px 12px',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--md-outline)',
            backgroundColor: 'var(--md-surface)',
            color: 'var(--md-on-surface)',
            fontSize: '13px',
          }}
        >
          <option value="ALL">Tất cả trạng thái</option>
          <option value="SUCCESS">Thành công (SUCCESS)</option>
          <option value="PENDING">Chờ duyệt (PENDING)</option>
          <option value="REJECTED">Đã hủy (REJECTED)</option>
          <option value="EXPIRED">Hết hạn (EXPIRED)</option>
        </select>
      </div>

      {/* Table */}
      <div style={{
        backgroundColor: 'var(--md-surface)',
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--md-outline-variant)',
        boxShadow: 'var(--elevation-1)',
        overflow: 'hidden',
      }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
            <thead>
              <tr style={{ backgroundColor: 'var(--md-surface-container)', borderBottom: '1px solid var(--md-outline-variant)', color: 'var(--md-on-surface-variant)' }}>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>Thời gian</th>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>Hành động</th>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>Công cụ</th>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>Trạng thái</th>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>Chi tiết tham số</th>
              </tr>
            </thead>
            <tbody>
              {filteredLogs.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ padding: '32px', textAlign: 'center', color: 'var(--md-on-surface-variant)' }}>
                    Chưa có nhật ký hoạt động nào phù hợp
                  </td>
                </tr>
              ) : (
                filteredLogs.map((log) => (
                  <tr key={log.id} style={{ borderBottom: '1px solid var(--md-outline-variant)' }}>
                    <td style={{ padding: '12px 16px', whiteSpace: 'nowrap', color: 'var(--md-on-surface-variant)' }}>
                      {formatRelativeTime(log.created_at)}
                    </td>
                    <td style={{ padding: '12px 16px', fontWeight: 600 }}>{log.action_type}</td>
                    <td style={{ padding: '12px 16px' }}><code>{log.tool_name}</code></td>
                    <td style={{ padding: '12px 16px' }}>
                      <span style={{
                        padding: '2px 8px',
                        borderRadius: 'var(--radius-full)',
                        fontSize: '11px',
                        fontWeight: 700,
                        backgroundColor: log.status === 'SUCCESS' ? 'var(--md-success-container)' : log.status === 'REJECTED' ? 'var(--md-error-container)' : 'var(--md-warning-container)',
                        color: log.status === 'SUCCESS' ? 'var(--md-on-success-container)' : log.status === 'REJECTED' ? 'var(--md-on-error-container)' : 'var(--md-on-warning-container)',
                      }}>
                        {log.status}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', maxWidth: '320px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      <span title={log.edited_args ? `Đã sửa: ${log.edited_args}` : log.original_args}>
                        {log.edited_args ? `(Đã sửa) ${log.edited_args}` : log.original_args}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
