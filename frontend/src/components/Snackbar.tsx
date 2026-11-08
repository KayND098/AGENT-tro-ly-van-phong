import { useEffect } from 'react';
import { SnackbarInfo } from '../types';

interface SnackbarProps {
  snackbars: SnackbarInfo[];
  onDismiss: (id: string) => void;
}

export const SnackbarContainer = ({ snackbars, onDismiss }: SnackbarProps) => {
  return (
    <div style={{
      position: 'fixed',
      bottom: '24px',
      left: '24px',
      zIndex: 9999,
      display: 'flex',
      flexDirection: 'column',
      gap: '8px',
      maxWidth: '480px',
    }}>
      {snackbars.map((s) => (
        <SnackbarItem key={s.id} snackbar={s} onDismiss={onDismiss} />
      ))}
    </div>
  );
};

const SnackbarItem = ({
  snackbar,
  onDismiss,
}: {
  snackbar: SnackbarInfo;
  onDismiss: (id: string) => void;
}) => {
  useEffect(() => {
    const timer = setTimeout(() => {
      onDismiss(snackbar.id);
    }, 4500);
    return () => clearTimeout(timer);
  }, [snackbar.id, onDismiss]);

  const typeStyles = {
    info: { icon: 'info', color: 'var(--md-primary)' },
    success: { icon: 'check_circle', color: 'var(--md-success)' },
    warning: { icon: 'warning', color: 'var(--md-warning)' },
    error: { icon: 'error', color: 'var(--md-error)' },
  };

  const current = typeStyles[snackbar.type || 'info'];

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: '12px',
      backgroundColor: 'var(--md-surface-container-highest)',
      color: 'var(--md-on-surface)',
      borderRadius: 'var(--radius-sm)',
      padding: '12px 16px',
      boxShadow: 'var(--elevation-3)',
      fontSize: '14px',
      border: '1px solid var(--md-outline-variant)',
      animation: 'fadeIn 0.2s ease-out',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <span className="material-symbols-outlined" style={{ color: current.color, fontSize: '20px' }}>
          {current.icon}
        </span>
        <span>{snackbar.message}</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {snackbar.actionLabel && (
          <button
            onClick={() => {
              if (snackbar.onAction) snackbar.onAction();
              onDismiss(snackbar.id);
            }}
            style={{
              color: 'var(--md-primary)',
              fontWeight: 600,
              fontSize: '13px',
              padding: '4px 8px',
              borderRadius: 'var(--radius-xs)',
            }}
          >
            {snackbar.actionLabel}
          </button>
        )}
        <button
          onClick={() => onDismiss(snackbar.id)}
          aria-label="Đóng thông báo"
          style={{
            color: 'var(--md-on-surface-variant)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '24px',
            height: '24px',
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>close</span>
        </button>
      </div>
    </div>
  );
};
