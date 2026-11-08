interface TopBarProps {
  onToggleSidebar: () => void;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
}

export const TopBar = ({
  onToggleSidebar,
  theme,
  onToggleTheme,
}: TopBarProps) => {
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
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
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
          }}
          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--md-surface-container-high)')}
          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
        >
          <span className="material-symbols-outlined">
            {theme === 'dark' ? 'light_mode' : 'dark_mode'}
          </span>
        </button>

        {/* User Avatar */}
        <div
          role="button"
          tabIndex={0}
          aria-label="Tài khoản người dùng"
          style={{
            width: '36px',
            height: '36px',
            borderRadius: 'var(--radius-full)',
            backgroundColor: '#0288d1',
            color: '#ffffff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 600,
            fontSize: '14px',
            marginLeft: '4px',
            cursor: 'pointer',
            boxShadow: 'var(--elevation-1)',
          }}
        >
          V
        </div>
      </div>
    </header>
  );
};
