import { PendingAction } from '../types';
import { ConfirmCard } from './ConfirmCard';

interface PendingListViewProps {
  pendingActions: PendingAction[];
  onApprove: (actionId: string, editedArgs?: Record<string, any>) => Promise<void>;
  onReject: (actionId: string) => Promise<void>;
  onEditPlaceholder: () => void;
  onRefresh: () => void;
}

export const PendingListView = ({
  pendingActions,
  onApprove,
  onReject,
  onEditPlaceholder,
  onRefresh,
}: PendingListViewProps) => {
  return (
    <div style={{
      maxWidth: '800px',
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
            Hành động cần xác nhận ({pendingActions.length})
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--md-on-surface-variant)' }}>
            Các tác vụ có mức độ rủi ro (gửi email, xóa dữ liệu) đang chờ bạn phê duyệt
          </p>
        </div>
        <button
          onClick={onRefresh}
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
          Làm mới
        </button>
      </div>

      {pendingActions.length === 0 ? (
        <div style={{
          backgroundColor: 'var(--md-surface)',
          padding: '48px 24px',
          borderRadius: 'var(--radius-lg)',
          textAlign: 'center',
          border: '1px dashed var(--md-outline)',
          color: 'var(--md-on-surface-variant)',
        }}>
          <span className="material-symbols-outlined" style={{ fontSize: '48px', color: 'var(--md-success)', marginBottom: '12px' }}>
            check_circle
          </span>
          <div style={{ fontSize: '16px', fontWeight: 600, color: 'var(--md-on-surface)' }}>
            Không có hành động nào đang chờ duyệt
          </div>
          <div style={{ fontSize: '13px', marginTop: '4px' }}>
            Mọi yêu cầu gửi email hoặc xóa dữ liệu mới sẽ xuất hiện tại đây và trong cuộc trò chuyện.
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {pendingActions.map((action) => (
            <ConfirmCard
              key={action.id}
              action={action}
              onApprove={onApprove}
              onReject={onReject}
              onEditPlaceholder={onEditPlaceholder}
            />
          ))}
        </div>
      )}
    </div>
  );
};
