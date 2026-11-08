import React, { useState, useEffect, useRef } from 'react';

interface EditEmailDialogProps {
  isOpen: boolean;
  initialData: { to?: string; cc?: string; subject?: string; body?: string };
  onClose: () => void;
  onSaveAndApprove: (editedArgs: { to: string; subject: string; body: string }) => Promise<void>;
}

const isValidEmail = (email: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
const validateEmails = (str: string) => {
  const list = str.split(',').map((e) => e.trim()).filter(Boolean);
  return list.length > 0 && list.every(isValidEmail);
};

export const EditEmailDialog: React.FC<EditEmailDialogProps> = ({
  isOpen,
  initialData,
  onClose,
  onSaveAndApprove,
}) => {
  const [to, setTo] = useState(initialData.to || '');
  const [cc, setCc] = useState(initialData.cc || '');
  const [subject, setSubject] = useState(initialData.subject || '');
  const [body, setBody] = useState(initialData.body || '');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [apiError, setApiError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const toInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setTo(initialData.to || '');
      setCc(initialData.cc || '');
      setSubject(initialData.subject || '');
      setBody(initialData.body || '');
      setErrors({});
      setApiError(null);
      setTimeout(() => toInputRef.current?.focus(), 50);
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!to.trim()) errs.to = 'Vui lòng nhập địa chỉ người nhận.';
    else if (!validateEmails(to)) errs.to = 'Email không hợp lệ (hỗ trợ nhiều email cách nhau dấu phẩy).';

    if (cc.trim() && !validateEmails(cc)) errs.cc = 'Email Cc không đúng định dạng.';
    if (!subject.trim()) errs.subject = 'Tiêu đề không được để trống.';
    if (!body.trim()) errs.body = 'Nội dung email không được để trống.';

    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      return;
    }

    setLoading(true);
    setApiError(null);
    try {
      await onSaveAndApprove({ to: to.trim(), subject: subject.trim(), body: body.trim() });
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
        aria-label="Chỉnh sửa email"
      >
        <div className="md-dialog-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="material-symbols-outlined" style={{ color: 'var(--md-primary)' }}>edit</span>
            <h3>Chỉnh sửa email trước khi duyệt</h3>
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
            <label htmlFor="edit-email-to">Đến (To) <span style={{ color: 'var(--md-error)' }}>*</span></label>
            <input
              id="edit-email-to"
              ref={toInputRef}
              type="text"
              value={to}
              onChange={(e) => { setTo(e.target.value); setErrors((prev) => ({ ...prev, to: '' })); }}
              placeholder="nguoinhan@company.com"
              className={errors.to ? 'input-error' : ''}
              disabled={loading}
              aria-label="Người nhận email"
            />
            {errors.to && <span className="field-error-text">{errors.to}</span>}
          </div>

          <div className="md-form-field">
            <label htmlFor="edit-email-cc">Cc</label>
            <input
              id="edit-email-cc"
              type="text"
              value={cc}
              onChange={(e) => { setCc(e.target.value); setErrors((prev) => ({ ...prev, cc: '' })); }}
              placeholder="dongnghiep@company.com (tùy chọn)"
              className={errors.cc ? 'input-error' : ''}
              disabled={loading}
              aria-label="Địa chỉ Cc email"
            />
            {errors.cc && <span className="field-error-text">{errors.cc}</span>}
          </div>

          <div className="md-form-field">
            <label htmlFor="edit-email-subject">Tiêu đề <span style={{ color: 'var(--md-error)' }}>*</span></label>
            <input
              id="edit-email-subject"
              type="text"
              value={subject}
              onChange={(e) => { setSubject(e.target.value); setErrors((prev) => ({ ...prev, subject: '' })); }}
              placeholder="Nhập tiêu đề email"
              className={errors.subject ? 'input-error' : ''}
              disabled={loading}
              aria-label="Tiêu đề email"
            />
            {errors.subject && <span className="field-error-text">{errors.subject}</span>}
          </div>

          <div className="md-form-field">
            <label htmlFor="edit-email-body">Nội dung <span style={{ color: 'var(--md-error)' }}>*</span></label>
            <textarea
              id="edit-email-body"
              rows={5}
              value={body}
              onChange={(e) => { setBody(e.target.value); setErrors((prev) => ({ ...prev, body: '' })); }}
              placeholder="Nhập nội dung thư..."
              className={errors.body ? 'input-error' : ''}
              disabled={loading}
              aria-label="Nội dung email"
            />
            {errors.body && <span className="field-error-text">{errors.body}</span>}
          </div>

          <div className="md-dialog-actions">
            <button type="button" onClick={onClose} disabled={loading} className="btn-cancel">
              Hủy
            </button>
            <button type="submit" disabled={loading} className="btn-save-approve">
              {loading ? 'Đang duyệt...' : 'Lưu và duyệt'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
