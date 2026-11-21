import { useState, useRef, useEffect } from 'react';
import { User } from '../types';

interface TopBarProps {
  onToggleSidebar: () => void;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  user?: User | null;
  onLogout?: () => void;
}

export const TopBar = ({
  onToggleSidebar,
  theme,
  onToggleTheme,
  user,
  onLogout,
}: TopBarProps) => {
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
    <header style={{
      height: '64px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 16px',
      backgroundColor: 'var(--md-surface)',
      borderBottom: '1px solid var(--md-outline-variant)',
      zIndex: 50,
      position: 'relative',
    }}>
      {/* Left section: Hamburger & Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button
          onClick={onToggleSidebar}
          aria-label="Thu gọn hoặc mở menu"
          style={{
            width: '40px',
            height: '40px',
            borderRadius: 'var(--radius-full)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--md-on-surface-variant)',
            transition: 'background var(--transition-fast)',
            border: 'none',
            background: 'transparent',
            cursor: 'pointer',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--md-surface-container-high)')}
          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
        >
          <span className="material-symbols-outlined">menu</span>
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', userSelect: 'none' }}>
          <div style={{
            width: '36px',
            height: '36px',
            borderRadius: 'var(--radius-sm)',
            backgroundColor: 'var(--md-primary-container)',
            color: 'var(--md-on-primary-container)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: 'var(--elevation-1)',
          }}>
            <span className="material-symbols-outlined" style={{ color: 'var(--md-primary)' }}>
              smart_toy
            </span>
          </div>
          <span style={{
            fontSize: '18px',
            fontWeight: 500,
            color: 'var(--md-on-surface)',
            letterSpacing: '-0.2px',
          }}>
            Trợ lý văn phòng
          </span>
        </div>
      </div>

      {/* Middle section: Google Workspace style search box */}
      <div style={{
        flex: 1,
        maxWidth: '560px',
        margin: '0 24px',
        display: 'flex',
        alignItems: 'center',
        backgroundColor: 'var(--md-surface-container)',
        borderRadius: 'var(--radius-xl)',
        padding: '0 16px',
        height: '46px',
        border: '1px solid transparent',
        transition: 'all var(--transition-fast)',
      }}>
        <span className="material-symbols-outlined" style={{ color: 'var(--md-on-surface-variant)', marginRight: '10px' }}>
          search
        </span>
        <input
          type="text"
          placeholder="Tìm kiếm trong cuộc trò chuyện hoặc công việc..."
          aria-label="Tìm kiếm trong cuộc trò chuyện"
          style={{
            flex: 1,
            border: 'none',
            background: 'transparent',
            outline: 'none',
            fontSize: '14px',
            color: 'var(--md-on-surface)',
          }}
        />
      </div>

      {/* Right section: Dark mode toggle & Avatar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', position: 'relative' }}>
        <button
          onClick={onToggleTheme}
          aria-label={theme === 'dark' ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối'}
          title={theme === 'dark' ? 'Giao diện sáng' : 'Giao diện tối'}
          style={{
            width: '40px',
            height: '40px',
            borderRadius: 'var(--radius-full)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--md-on-surface-variant)',
            transition: 'background var(--transition-fast)',
            border: 'none',
            background: 'transparent',
            cursor: 'pointer',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--md-surface-container-high)')}
          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
        >
          <span className="material-symbols-outlined">
            {theme === 'dark' ? 'light_mode' : 'dark_mode'}
          </span>
        </button>

        {/* User Avatar with Dropdown */}
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

          {/* Menu popup */}
          {menuOpen && (
            <div style={{
              position: 'absolute',
              top: '46px',
              right: 0,
              width: '240px',
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
      </div>
    </header>
  );
};
