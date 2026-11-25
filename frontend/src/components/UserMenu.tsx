import { useState, useRef, useEffect } from 'react';
import { User } from '../types';

interface UserMenuProps {
  user: User | null;
  onLogout?: () => void;
  onConnectGmail?: () => void;
  onDisconnectGmail?: () => void;
}

export const UserMenu = ({
  user,
  onLogout,
  onConnectGmail,
  onDisconnectGmail,
}: UserMenuProps) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    if (menuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [menuOpen]);

  const initial = user?.name ? user.name[0].toUpperCase() : (user?.email ? user.email[0].toUpperCase() : 'U');

  return (
    <div ref={menuRef} style={{ position: 'relative' }}>
      <div
        role="button"
        tabIndex={0}
        onClick={() => setMenuOpen(!menuOpen)}
        aria-label="Tài khoản người dùng"
        title={user ? `${user.name} (${user.email})` : 'Tài khoản'}
        style={{
          width: '36px',
          height: '36px',
          borderRadius: 'var(--radius-full)',
          backgroundColor: '#1a73e8',
          color: '#ffffff',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontWeight: 600,
          fontSize: '14px',
          marginLeft: '4px',
          cursor: 'pointer',
          boxShadow: 'var(--elevation-1)',
          overflow: 'hidden',
          userSelect: 'none',
        }}
      >
        {user?.picture ? (
          <img src={user.picture} alt={user.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : (
          initial
        )}
      </div>

      {menuOpen && (
        <div style={{
          position: 'absolute',
          top: '46px',
          right: 0,
          width: '260px',
          backgroundColor: 'var(--md-surface)',
          borderRadius: 'var(--radius-md)',
          boxShadow: 'var(--elevation-3)',
          border: '1px solid var(--md-outline-variant)',
          padding: '12px 0',
          zIndex: 100,
        }}>
          {user && (
            <div style={{ padding: '0 16px 10px 16px', borderBottom: '1px solid var(--md-outline-variant)' }}>
              <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--md-on-surface)' }}>{user.name}</div>
              <div style={{ fontSize: '12px', color: 'var(--md-on-surface-variant)', wordBreak: 'break-all' }}>{user.email}</div>
            </div>
          )}

          {/* Gmail connection section */}
          <div style={{ padding: '8px 0', borderBottom: '1px solid var(--md-outline-variant)' }}>
            {user?.gmail_connected ? (
              <>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '6px 16px',
                  fontSize: '12px',
                  color: 'var(--md-success, #1e8e3e)',
                  fontWeight: 500,
                }}>
                  <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>check_circle</span>
                  <span>Đã kết nối Gmail</span>
                </div>
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => {
                    setMenuOpen(false);
                    onDisconnectGmail?.();
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    padding: '8px 16px',
                    fontSize: '13px',
                    color: 'var(--md-on-surface-variant)',
                    cursor: 'pointer',
                    transition: 'background var(--transition-fast)',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--md-surface-container-high)')}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>link_off</span>
                  <span>Ngắt kết nối Gmail</span>
                </div>
              </>
            ) : (
              <div
                role="button"
                tabIndex={0}
                onClick={() => {
                  setMenuOpen(false);
                  onConnectGmail?.();
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '8px 16px',
                  fontSize: '13px',
                  color: 'var(--md-primary)',
                  fontWeight: 500,
                  cursor: 'pointer',
                  transition: 'background var(--transition-fast)',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--md-surface-container-high)')}
                onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
              >
                <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>mail</span>
                <span>Kết nối Gmail</span>
              </div>
            )}
          </div>

          {/* Logout */}
          <div
            role="button"
            tabIndex={0}
            onClick={() => {
              setMenuOpen(false);
              onLogout?.();
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '10px 16px',
              fontSize: '13px',
              color: 'var(--md-on-surface)',
              cursor: 'pointer',
              transition: 'background var(--transition-fast)',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--md-surface-container-high)')}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
          >
            <span className="material-symbols-outlined" style={{ fontSize: '18px', color: 'var(--md-error)' }}>
              logout
            </span>
            <span>Đăng xuất</span>
          </div>
        </div>
      )}
    </div>
  );
};
