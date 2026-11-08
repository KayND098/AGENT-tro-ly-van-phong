import { useState, useEffect } from 'react';
import { PendingAction } from '../types';
import { EditEmailDialog } from './EditEmailDialog';
import { EditSheetDialog } from './EditSheetDialog';

interface ConfirmCardProps {
  action: PendingAction;
  onApprove: (actionId: string, editedArgs?: Record<string, any>) => Promise<void>;
  onReject: (actionId: string) => Promise<void>;
  onEditPlaceholder: () => void;
}

export const ConfirmCard = ({ action, onApprove, onReject, onEditPlaceholder }: ConfirmCardProps) => {
  const [loading, setLoading] = useState(false);
  const [currentStatus, setCurrentStatus] = useState(action.status);
  const [timeLeft, setTimeLeft] = useState('');
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [isEditSheetDialogOpen, setIsEditSheetDialogOpen] = useState(false);
  const [isEdited, setIsEdited] = useState(Boolean(action.edited_args));
  const preview = action.preview || {};

  const [displayedEmail, setDisplayedEmail] = useState({
    to: action.edited_args?.to || preview.to || action.original_args?.to || '',
    subject: action.edited_args?.subject || preview.subject || action.original_args?.subject || '',
    body: action.edited_args?.body || preview.body || action.original_args?.body || '',
  });

  const [displayedSheet, setDisplayedSheet] = useState({
    sheet_name: action.edited_args?.sheet_name || preview.sheet_name || action.original_args?.sheet_name || '',
    count: action.edited_args?.count ?? preview.target_count ?? action.original_args?.count ?? 0,
  });

  useEffect(() => {
    if (currentStatus !== 'PENDING') return;
    const calculateTime = () => {
      const diff = Math.max(0, new Date(action.expires_at).getTime() - Date.now());
      if (diff === 0) {
        setCurrentStatus('EXPIRED');
        setTimeLeft('00:00');
        return;
      }
      const mins = Math.floor(diff / 60000);
      const secs = Math.floor((diff % 60000) / 1000);
      setTimeLeft(`${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`);
    };
    calculateTime();
    const timer = setInterval(calculateTime, 1000);
    return () => clearInterval(timer);
  }, [action.expires_at, currentStatus]);

  const handleAction = async (type: 'approve' | 'reject') => {
    if (loading || currentStatus !== 'PENDING') return;
    setLoading(true);
    try {
      if (type === 'approve') { await onApprove(action.id); setCurrentStatus('APPROVED'); }
      else { await onReject(action.id); setCurrentStatus('REJECTED'); }
    } finally { setLoading(false); }
  };

  const handleSaveEmail = async (args: { to: string; subject: string; body: string }) => {
    await onApprove(action.id, args);
    setDisplayedEmail(args);
    setIsEdited(true);
    setCurrentStatus('APPROVED');
  };

  const handleSaveSheet = async (args: { sheet_name: string; count: number }) => {
    await onApprove(action.id, args);
    setDisplayedSheet(args);
    setIsEdited(true);
    setCurrentStatus('APPROVED');
  };

  const isExternal = (email: string = '') => !email.endsWith('@company.com');
  const onEdit = () => {
    if (action.tool_name === 'send_email') setIsEditDialogOpen(true);
    else if (action.tool_name === 'delete_rows') setIsEditSheetDialogOpen(true);
    else onEditPlaceholder();
  };

  return (
    <div style={{ marginTop: '12px', backgroundColor: 'var(--md-surface)', border: '1px solid var(--md-outline)', borderRadius: 'var(--radius-lg)', boxShadow: 'var(--elevation-2)', overflow: 'hidden', maxWidth: '680px', width: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', backgroundColor: 'var(--md-surface-container)', borderBottom: '1px solid var(--md-outline-variant)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="material-symbols-outlined" style={{ color: 'var(--md-warning)' }}>notification_important</span>
          <span style={{ fontWeight: 600, fontSize: '14px', color: 'var(--md-on-surface)' }}>CẦN XÁC NHẬN HÀNH ĐỘNG</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {currentStatus === 'PENDING' && (
            <span style={{ fontSize: '12px', color: 'var(--md-on-surface-variant)', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>timer</span> {timeLeft}
            </span>
          )}
          {isEdited && (
            <span style={{ fontSize: '11px', fontWeight: 600, padding: '2px 8px', borderRadius: 'var(--radius-full)', backgroundColor: 'var(--md-primary-container)', color: 'var(--md-on-primary-container)' }}>
              Đã chỉnh sửa
            </span>
          )}
          <span style={{
            fontSize: '11px', fontWeight: 700, padding: '2px 8px', borderRadius: 'var(--radius-full)',
            backgroundColor: currentStatus === 'APPROVED' ? 'var(--md-success-container)' : currentStatus === 'REJECTED' ? 'var(--md-surface-container-highest)' : 'var(--md-warning-container)',
            color: currentStatus === 'APPROVED' ? 'var(--md-on-success-container)' : currentStatus === 'REJECTED' ? 'var(--md-on-surface-variant)' : 'var(--md-on-warning-container)',
          }}>
            {currentStatus === 'APPROVED' ? (action.tool_name === 'send_email' ? 'Đã gửi' : 'Đã duyệt') : currentStatus === 'REJECTED' ? 'Đã hủy' : currentStatus === 'EXPIRED' ? 'Đã hết hạn' : 'Chờ duyệt'}
          </span>
        </div>
      </div>

      <div style={{ padding: '16px' }}>
        {action.tool_name === 'send_email' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '13.5px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ color: 'var(--md-on-surface-variant)', width: '60px' }}>Đến:</span>
              <strong>{displayedEmail.to}</strong>
              {isExternal(displayedEmail.to) && (
                <span style={{ backgroundColor: 'var(--md-warning-container)', color: 'var(--md-on-warning-container)', fontSize: '11px', padding: '1px 6px', borderRadius: 'var(--radius-sm)', fontWeight: 600 }}>
                  Ngoài tổ chức
                </span>
              )}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ color: 'var(--md-on-surface-variant)', width: '60px' }}>Tiêu đề:</span>
              <span>{displayedEmail.subject}</span>
            </div>
            <div style={{ marginTop: '6px', padding: '10px 12px', backgroundColor: 'var(--md-surface-container)', borderRadius: 'var(--radius-sm)', borderLeft: '3px solid var(--md-primary)', whiteSpace: 'pre-wrap' }}>
              {displayedEmail.body}
            </div>
          </div>
        )}

        {action.tool_name === 'delete_rows' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '13.5px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>Bảng tính: <strong>Sheet "{displayedSheet.sheet_name}"</strong></div>
              <span style={{ backgroundColor: 'var(--md-error-container)', color: 'var(--md-on-error-container)', fontSize: '11px', padding: '2px 8px', borderRadius: 'var(--radius-full)', fontWeight: 700 }}>
                Không thể hoàn tác
              </span>
            </div>
            <div>
              Số dòng ảnh hưởng:{' '}
              <strong style={{ color: 'var(--md-error)' }}>
                {isEdited ? `Hàng 2 đến Hàng ${1 + Number(displayedSheet.count)}` : preview.affected_range} ({displayedSheet.count} dòng)
              </strong>
            </div>
            {preview.sample_rows_preview && (
              <div style={{ overflowX: 'auto', marginTop: '6px' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', border: '1px solid var(--md-outline-variant)' }}>
                  <tbody>
                    {preview.sample_rows_preview.map((row: any[], i: number) => (
                      <tr key={i} style={{ borderBottom: '1px solid var(--md-outline-variant)', backgroundColor: i % 2 === 0 ? 'var(--md-surface-container)' : 'transparent' }}>
                        <td style={{ padding: '6px 8px', color: 'var(--md-on-surface-variant)', width: '30px' }}>#{i+1}</td>
                        {row.map((c, j) => <td key={j} style={{ padding: '6px 8px' }}>{String(c)}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {currentStatus === 'PENDING' ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '8px', padding: '12px 16px', backgroundColor: 'var(--md-surface-container-low)', borderTop: '1px solid var(--md-outline-variant)' }}>
          <button onClick={() => handleAction('reject')} disabled={loading} style={{ color: 'var(--md-on-surface-variant)', padding: '8px 16px', borderRadius: 'var(--radius-full)', fontWeight: 500, fontSize: '13px' }}>Hủy</button>
          <button onClick={onEdit} disabled={loading} style={{ border: '1px solid var(--md-outline)', color: 'var(--md-primary)', padding: '8px 16px', borderRadius: 'var(--radius-full)', fontWeight: 500, fontSize: '13px' }}>
            Sửa
          </button>
          <button onClick={() => handleAction('approve')} disabled={loading} style={{ backgroundColor: 'var(--md-primary)', color: 'var(--md-on-primary)', padding: '8px 20px', borderRadius: 'var(--radius-full)', fontWeight: 500, fontSize: '13px', boxShadow: 'var(--elevation-1)' }}>
            {loading ? 'Đang duyệt...' : 'Duyệt'}
          </button>
        </div>
      ) : (
        <div style={{ padding: '10px 16px', backgroundColor: 'var(--md-surface-container)', fontSize: '12px', color: 'var(--md-on-surface-variant)', fontStyle: 'italic', borderTop: '1px solid var(--md-outline-variant)' }}>
          {currentStatus === 'APPROVED' ? '✓ Đã duyệt và lưu vào audit log.' : currentStatus === 'REJECTED' ? '✕ Hành động đã bị hủy.' : '⏱ Đã quá thời hạn xác nhận.'}
        </div>
      )}

      {action.tool_name === 'send_email' && (
        <EditEmailDialog
          isOpen={isEditDialogOpen}
          initialData={displayedEmail}
          onClose={() => setIsEditDialogOpen(false)}
          onSaveAndApprove={handleSaveEmail}
        />
      )}
      {action.tool_name === 'delete_rows' && (
        <EditSheetDialog
          isOpen={isEditSheetDialogOpen}
          initialData={displayedSheet}
          onClose={() => setIsEditSheetDialogOpen(false)}
          onSaveAndApprove={handleSaveSheet}
        />
      )}
    </div>
  );
};
