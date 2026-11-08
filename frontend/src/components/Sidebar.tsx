import { useEffect } from 'react';
import { TabType } from '../types';

interface SidebarProps {
  isOpen: boolean;
  isMobile: boolean;
  onCloseMobile: () => void;
  activeTab: TabType;
  onSelectTab: (tab: TabType) => void;
  onNewChat: () => void;
  pendingCount: number;
}

export const Sidebar = ({
  isOpen,
  isMobile,
  onCloseMobile,
  activeTab,
  onSelectTab,
  onNewChat,
  pendingCount,
}: SidebarProps) => {
  // Đóng drawer khi nhấn phím Esc
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isMobile && isOpen) {
        onCloseMobile();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isMobile, isOpen, onCloseMobile]);

  const navItems = [
    { id: 'chat' as TabType, label: 'Trò chuyện', icon: 'chat' },
    { id: 'pending' as TabType, label: 'Cần xác nhận', icon: 'notification_important', badge: pendingCount },
    { id: 'audit' as TabType, label: 'Nhật ký hoạt động', icon: 'history' },
    { id: 'settings' as TabType, label: 'Cài đặt', icon: 'settings' },
  ];

  const sidebarContent = (
    <aside style={{
      width: isOpen ? '260px' : '72px',
      height: '100%',
      backgroundColor: 'var(--md-surface)',
      borderRight: '1px solid var(--md-outline-variant)',
      display: 'flex',
      flexDirection: 'column',
      padding: '12px',
      gap: '8px',
      transition: 'width var(--transition-normal)',
      overflowX: 'hidden',
    }}>
      {/* Nút '+ Cuộc trò chuyện mới' kiểu Google MD3 Extended FAB */}
      <button
        onClick={onNewChat}
        aria-label="Tạo cuộc trò chuyện mới"
        style={{
          height: '48px',
          borderRadius: 'var(--radius-xl)',
          backgroundColor: 'var(--md-primary-container)',
          color: 'var(--md-on-primary-container)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: isOpen ? 'flex-start' : 'center',
          gap: '12px',
          padding: isOpen ? '0 20px' : '0',
          fontWeight: 500,
          fontSize: '14px',
          boxShadow: 'var(--elevation-1)',
          marginBottom: '8px',
          transition: 'all var(--transition-fast)',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.boxShadow = 'var(--elevation-2)';
          e.currentTarget.style.backgroundColor = 'var(--md-primary)';
          e.currentTarget.style.color = 'var(--md-on-primary)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.boxShadow = 'var(--elevation-1)';
          e.currentTarget.style.backgroundColor = 'var(--md-primary-container)';
          e.currentTarget.style.color = 'var(--md-on-primary-container)';
        }}
      >
        <span className="material-symbols-outlined">add</span>
        {isOpen && <span>Cuộc trò chuyện mới</span>}
      </button>

      {/* Danh sách các mục điều hướng */}
      <nav style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1 }}>
        {navItems.map((item) => {
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => {
                onSelectTab(item.id);
                if (isMobile) onCloseMobile();
              }}
              aria-label={item.label}
              style={{
                height: '44px',
                borderRadius: 'var(--radius-xl)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: isOpen ? 'flex-start' : 'center',
                gap: '14px',
                padding: isOpen ? '0 16px' : '0',
                backgroundColor: isActive ? 'var(--md-primary-container)' : 'transparent',
                color: isActive ? 'var(--md-on-primary-container)' : 'var(--md-on-surface-variant)',
                fontWeight: isActive ? 600 : 500,
                fontSize: '14px',
                position: 'relative',
                transition: 'background var(--transition-fast)',
              }}
              onMouseEnter={(e) => {
                if (!isActive) e.currentTarget.style.backgroundColor = 'var(--md-surface-container-high)';
              }}
              onMouseLeave={(e) => {
                if (!isActive) e.currentTarget.style.backgroundColor = 'transparent';
              }}
            >
              <span className={`material-symbols-outlined ${isActive ? 'fill' : ''}`}>
                {item.icon}
              </span>
              {isOpen && <span style={{ flex: 1, textAlign: 'left' }}>{item.label}</span>}
              {/* Badge số lượng đang chờ */}
              {item.badge !== undefined && item.badge > 0 && (
                <span style={{
                  backgroundColor: 'var(--md-error)',
                  color: '#ffffff',
                  fontSize: '11px',
                  fontWeight: 700,
                  padding: '2px 7px',
                  borderRadius: 'var(--radius-full)',
                  marginLeft: isOpen ? 'auto' : '0',
                }}>
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>
    </aside>
  );

  // Nếu là Mobile: Drawer có lớp Backdrop mờ
  if (isMobile) {
    if (!isOpen) return null;
    return (
      <div style={{
        position: 'fixed',
        inset: 0,
        zIndex: 100,
        display: 'flex',
      }}>
        {/* Backdrop */}
        <div
          onClick={onCloseMobile}
          style={{
            position: 'absolute',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.4)',
            backdropFilter: 'blur(2px)',
          }}
        />
        <div style={{ position: 'relative', zIndex: 101, height: '100%' }}>
          {sidebarContent}
        </div>
      </div>
    );
  }

  return sidebarContent;
};
