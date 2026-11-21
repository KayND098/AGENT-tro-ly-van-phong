import React from 'react';

interface LoginPageProps {
  errorMessage?: string | null;
}

export const LoginPage: React.FC<LoginPageProps> = ({ errorMessage }) => {
  const handleLogin = () => {
    window.location.href = '/auth/google/login';
  };

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      backgroundColor: 'var(--md-surface-container-low)',
      padding: '24px',
    }}>
      <div style={{
        maxWidth: '420px',
        width: '100%',
        backgroundColor: 'var(--md-surface)',
        borderRadius: 'var(--radius-xl)',
        padding: '40px 32px',
        boxShadow: 'var(--elevation-2)',
        border: '1px solid var(--md-outline-variant)',
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
      }}>
        {/* Logo */}
        <div style={{
          width: '56px',
          height: '56px',
          borderRadius: 'var(--radius-md)',
          backgroundColor: 'var(--md-primary-container)',
          color: 'var(--md-on-primary-container)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: 'var(--elevation-1)',
          marginBottom: '20px',
        }}>
          <span className="material-symbols-outlined" style={{ fontSize: '32px', color: 'var(--md-primary)' }}>
            smart_toy
          </span>
        </div>

        {/* Tên App */}
        <h1 style={{
          fontSize: '24px',
          fontWeight: 600,
          color: 'var(--md-on-surface)',
          margin: '0 0 8px 0',
          letterSpacing: '-0.3px',
        }}>
          Trợ lý văn phòng AI
        </h1>

        <p style={{
          fontSize: '14px',
          color: 'var(--md-on-surface-variant)',
          margin: '0 0 28px 0',
          lineHeight: '1.5',
        }}>
          Trợ lý AI hỗ trợ công việc văn phòng với luồng kiểm soát an toàn và bảo vệ dữ liệu
        </p>

        {/* Thông báo lỗi nếu có */}
        {errorMessage && (
          <div style={{
            width: '100%',
            backgroundColor: 'var(--md-error-container)',
            color: 'var(--md-on-error-container)',
            borderRadius: 'var(--radius-sm)',
            padding: '12px',
            fontSize: '13px',
            marginBottom: '20px',
            textAlign: 'left',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}>
            <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>error</span>
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Nút Đăng nhập bằng Google */}
        <button
          onClick={handleLogin}
          style={{
            width: '100%',
            height: '44px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '12px',
            backgroundColor: 'var(--md-surface)',
            border: '1px solid var(--md-outline)',
            borderRadius: 'var(--radius-full)',
            fontSize: '14px',
            fontWeight: 500,
            color: 'var(--md-on-surface)',
            cursor: 'pointer',
            transition: 'all var(--transition-fast)',
            boxShadow: 'var(--elevation-1)',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--md-surface-container-high)';
            e.currentTarget.style.borderColor = 'var(--md-primary)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--md-surface)';
            e.currentTarget.style.borderColor = 'var(--md-outline)';
          }}
        >
          {/* SVG Google 'G' Icon */}
          <svg width="18" height="18" viewBox="0 0 18 18">
            <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.616z"/>
            <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.258c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"/>
            <path fill="#FBBC05" d="M3.964 10.707c-.18-.54-.282-1.117-.282-1.707s.102-1.167.282-1.707V4.961H.957C.347 6.173 0 7.548 0 9s.347 2.827.957 4.039l3.007-2.332z"/>
            <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.961L3.964 7.293C4.672 5.166 6.656 3.58 9 3.58z"/>
          </svg>
          Đăng nhập bằng Google
        </button>

        {/* Dòng nhỏ */}
        <p style={{
          fontSize: '12px',
          color: 'var(--md-on-surface-variant)',
          marginTop: '24px',
          marginBottom: '0',
        }}>
          Chỉ dùng tài khoản được cấp quyền thử nghiệm
        </p>
      </div>
    </div>
  );
};
