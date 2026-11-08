import React, { useState, useEffect, useRef } from 'react';

interface EditSheetDialogProps {
  isOpen: boolean;
  initialData: { sheet_name?: string; count?: number };
  onClose: () => void;
  onSaveAndApprove: (editedArgs: { sheet_name: string; count: number }) => Promise<void>;
}

export const EditSheetDialog: React.FC<EditSheetDialogProps> = ({
  isOpen,
  initialData,
  onClose,
  onSaveAndApprove,
}) => {
  const [sheetName, setSheetName] = useState(initialData.sheet_name || '');
  const [count, setCount] = useState<string>(String(initialData.count || ''));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [apiError, setApiError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const sheetInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setSheetName(initialData.sheet_name || '');
      setCount(String(initialData.count || ''));
      setErrors({});
      setApiError(null);
      setTimeout(() => sheetInputRef.current?.focus(), 50);
    }
  }, [isOpen, initialData]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const countNum = parseInt(count, 10);
  const isValidCount = !isNaN(countNum) && Number.isInteger(Number(count)) && countNum > 0;
  const toRow = isValidCount ? 1 + countNum : 'Y';
  const displaySheet = sheetName.trim() || 'Z';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!sheetName.trim()) {
      errs.sheetName = 'Tên sheet không được để trống.';
    }
    if (!count.trim() || !isValidCount) {
      errs.count = 'Số dòng phải là số nguyên lớn hơn 0.';
    }

    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      return;
    }

    setLoading(true);
    setApiError(null);
    try {
      await onSaveAndApprove({ sheet_name: sheetName.trim(), count: countNum });
      onClose();
    } catch (err: any) {
      setApiError(err.message || 'Lỗi kiểm tra dữ liệu từ máy chủ (422)');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="md-dialog-overlay" onClick={onClose} role="presentation">
      <div
        className="md-dialog-surface"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Chỉnh sửa lệnh xóa dòng sheet"
      >
        <div className="md-dialog-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="material-symbols-outlined" style={{ color: 'var(--md-error)' }}>delete_sweep</span>
            <h3>Chỉnh sửa xóa dòng sheet trước khi duyệt</h3>
          </div>
          <button type="button" onClick={onClose} aria-label="Đóng" className="md-dialog-close-btn">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        {apiError && (
          <div className="md-dialog-error-banner" role="alert">
            <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>error</span>
            <span>{apiError}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="md-dialog-form">
          <div className="md-form-field">
            <label htmlFor="edit-sheet-name">Tên sheet <span style={{ color: 'var(--md-error)' }}>*</span></label>
            <input
              id="edit-sheet-name"
              ref={sheetInputRef}
              type="text"
              value={sheetName}
              onChange={(e) => { setSheetName(e.target.value); setErrors((prev) => ({ ...prev, sheetName: '' })); }}
              placeholder="Ví dụ: Doanh thu"
              className={errors.sheetName ? 'input-error' : ''}
              disabled={loading}
              aria-label="Tên sheet"
            />
            {errors.sheetName && <span className="field-error-text">{errors.sheetName}</span>}
          </div>

          <div className="md-form-field">
            <label htmlFor="edit-sheet-count">Số dòng cần xóa <span style={{ color: 'var(--md-error)' }}>*</span></label>
            <input
              id="edit-sheet-count"
              type="number"
              min="1"
              step="1"
              value={count}
              onChange={(e) => { setCount(e.target.value); setErrors((prev) => ({ ...prev, count: '' })); }}
              placeholder="Ví dụ: 5"
              className={errors.count ? 'input-error' : ''}
              disabled={loading}
              aria-label="Số dòng cần xóa"
            />
            {errors.count && <span className="field-error-text">{errors.count}</span>}
          </div>

          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '8px',
            padding: '10px 14px',
            backgroundColor: 'var(--md-surface-container)',
            borderRadius: 'var(--radius-sm)',
            borderLeft: '3px solid var(--md-error)',
            fontSize: '13px'
          }}>
            <span>
              Sẽ xóa <strong>{isValidCount ? countNum : 'N'}</strong> dòng, từ hàng <strong>2</strong> đến hàng <strong>{toRow}</strong> của sheet "<strong>{displaySheet}</strong>"
            </span>
            <span style={{
              backgroundColor: 'var(--md-error-container)',
              color: 'var(--md-on-error-container)',
              fontSize: '11px',
              padding: '2px 8px',
              borderRadius: 'var(--radius-full)',
              fontWeight: 700,
              whiteSpace: 'nowrap'
            }}>
              Không thể hoàn tác
            </span>
          </div>

          <div className="md-dialog-actions">
            <button type="button" onClick={onClose} disabled={loading} className="btn-cancel">
              Hủy
            </button>
            <button
              type="submit"
              disabled={loading}
              className="btn-save-approve"
              style={{ backgroundColor: 'var(--md-error)', color: '#ffffff' }}
            >
              {loading ? 'Đang xóa...' : 'Lưu và xóa'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
