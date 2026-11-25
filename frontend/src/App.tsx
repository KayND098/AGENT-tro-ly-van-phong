import { useState, useEffect, useCallback } from 'react';
import { ChatMessage, PendingAction, SnackbarInfo, TabType, User } from './types';
import { TopBar } from './components/TopBar';
import { Sidebar } from './components/Sidebar';
import { ChatView } from './components/ChatView';
import { PendingListView } from './components/PendingListView';
import { AuditLogView } from './components/AuditLogView';
import { SnackbarContainer } from './components/Snackbar';
import { LoginPage } from './components/LoginPage';
import './theme.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export function App() {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });
  const [user, setUser] = useState<User | null>(null);
  const [authChecking, setAuthChecking] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const [activeTab, setActiveTab] = useState<TabType>('chat');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pendingActions, setPendingActions] = useState<PendingAction[]>([]);
  const [loading, setLoading] = useState(false);
  const [snackbars, setSnackbars] = useState<SnackbarInfo[]>([]);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (mobile) setSidebarOpen(false);
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const showSnackbar = useCallback((message: string, type: SnackbarInfo['type'] = 'info') => {
    const id = Date.now().toString() + Math.random().toString().slice(2, 5);
    setSnackbars((prev) => [...prev, { id, message, type }]);
  }, []);

  const removeSnackbar = (id: string) => setSnackbars((prev) => prev.filter((s) => s.id !== id));

  // Kiểm tra phiên đăng nhập
  const checkAuth = useCallback(async () => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('gmail_connected') === '1') {
      showSnackbar('Đã kết nối tài khoản Gmail thành công!', 'success');
      window.history.replaceState({}, '', window.location.pathname);
    }
    const err = params.get('error') || params.get('auth_error');
    if (err) {
      const errorMap: Record<string, string> = {
        email_mismatch: 'Email Google kết nối không khớp với tài khoản đang đăng nhập.',
        connect_failed: 'Kết nối Gmail thất bại. Vui lòng thử lại.',
        not_allowed: 'Tài khoản của bạn không nằm trong danh sách được cấp quyền thử nghiệm.',
        login_failed: 'Đăng nhập Google thất bại. Vui lòng thử lại.',
        invalid_state: 'Yêu cầu xác thực không hợp lệ hoặc đã hết hạn.',
        state_invalid: 'Yêu cầu xác thực không hợp lệ hoặc đã hết hạn.',
        state_expired: 'Yêu cầu xác thực đã hết hạn.',
        nonce_mismatch: 'Xác thực không thành công (nonce không khớp).',
        no_code: 'Không nhận được mã xác thực từ Google.',
        code_missing: 'Không nhận được mã xác thực từ Google.',
        no_client_config: 'Hệ thống chưa cấu hình Google OAuth Client Secret.',
        auth_failed: 'Xác thực Google thất bại. Vui lòng thử lại.',
      };
      setAuthError(errorMap[err] || `Xác thực thất bại (${err}).`);
      showSnackbar(errorMap[err] || `Có lỗi xảy ra (${err}).`, 'error');
      window.history.replaceState({}, '', window.location.pathname);
    }

    try {
      const res = await fetch(`${API_BASE_URL}/auth/me`, {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data);
      } else {
        setUser(null);
      }
    } catch {
      setUser(null);
    } finally {
      setAuthChecking(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  // Wrapper gọi API gửi kèm credentials và header CSRF
  const apiCall = useCallback(async (url: string, options: RequestInit = {}) => {
    const headers = new Headers(options.headers || {});
    headers.set('X-Requested-With', 'XMLHttpRequest');
    const res = await fetch(`${API_BASE_URL}${url}`, {
      ...options,
      headers,
      credentials: 'same-origin',
    });
    if (res.status === 401) {
      setUser(null);
      showSnackbar('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.', 'warning');
      throw new Error('401_UNAUTHORIZED');
    }
    return res;
  }, [showSnackbar]);

  const handleLogout = async () => {
    try {
      await fetch(`${API_BASE_URL}/auth/logout`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
    } catch (e) {
      console.error('Logout error:', e);
    }
    setUser(null);
    showSnackbar('Đã đăng xuất thành công.', 'info');
  };

  const handleConnectGmail = () => {
    window.location.href = `${API_BASE_URL}/auth/google/connect-gmail`;
  };

  const handleDisconnectGmail = async () => {
    try {
      const res = await apiCall('/auth/google/disconnect-gmail', {
        method: 'POST',
      });
      if (res.ok) {
        setUser((prev) => (prev ? { ...prev, gmail_connected: false } : null));
        showSnackbar('Đã ngắt kết nối Gmail thành công.', 'info');
      } else {
        const data = await res.json().catch(() => ({}));
        showSnackbar(data.message || 'Ngắt kết nối Gmail thất bại.', 'error');
      }
    } catch (e: any) {
      if (e?.message !== '401_UNAUTHORIZED') {
        showSnackbar('Không thể kết nối đến máy chủ.', 'error');
      }
    }
  };

  const fetchPendingActions = useCallback(async () => {
    if (!user) return;
    try {
      const res = await apiCall('/actions/pending');
      if (res.ok) {
        const data = await res.json();
        setPendingActions(data.actions || []);
      }
    } catch (e: any) {
      if (e?.message !== '401_UNAUTHORIZED') {
        console.error('Fetch pending error:', e);
      }
    }
  }, [user, apiCall]);

  useEffect(() => {
    if (user) {
      fetchPendingActions();
    }
  }, [user, fetchPendingActions]);

  const handleSend = async (text: string) => {
    if (!text.trim() || loading) return;
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const payload = [...messages, userMsg].map((m) => ({ role: m.role, content: m.content }));
      const res = await apiCall('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: payload }),
      });
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();

      const assistantMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.content || '',
        type: data.type,
        tool_name: data.tool_name,
        risk_level: data.risk_level,
        result: data.result,
        pending_action: data.pending_action,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, assistantMsg]);
      if (data.pending_action) {
        setPendingActions((prev) => [data.pending_action, ...prev]);
        showSnackbar('Có 1 hành động mới cần bạn xác nhận', 'warning');
      }
    } catch (err: any) {
      if (err.message !== '401_UNAUTHORIZED') {
        showSnackbar(`Lỗi kết nối: ${err.message}`, 'error');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (actionId: string, editedArgs?: Record<string, any>) => {
    try {
      const res = await apiCall(`/actions/${actionId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editedArgs ? { edited_args: editedArgs } : {}),
      });
      const data = await res.json();
      if (!res.ok) {
        const errorMsg = data.detail?.message || data.detail || 'Lỗi khi duyệt';
        const err: any = new Error(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg));
        err.status = res.status;
        throw err;
      }

      showSnackbar('✓ Đã duyệt và thực thi thành công!', 'success');
      setPendingActions((prev) => prev.filter((a) => a.id !== actionId));
    } catch (err: any) {
      if (err.status !== 422 && err.message !== '401_UNAUTHORIZED') {
        showSnackbar(`Duyệt thất bại: ${err.message}`, 'error');
      }
      throw err;
    }
  };

  const handleReject = async (actionId: string) => {
    try {
      const res = await apiCall(`/actions/${actionId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Người dùng hủy bỏ' }),
      });
      if (!res.ok) throw new Error('Lỗi khi hủy');
      showSnackbar('✕ Đã hủy bỏ hành động.', 'info');
      setPendingActions((prev) => prev.filter((a) => a.id !== actionId));
    } catch (err: any) {
      if (err.message !== '401_UNAUTHORIZED') {
        showSnackbar(`Hủy thất bại: ${err.message}`, 'error');
      }
      throw err;
    }
  };

  // 1. Đang kiểm tra auth
  if (authChecking) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', backgroundColor: 'var(--md-surface)' }}>
        <div style={{ color: 'var(--md-primary)', fontSize: '14px', fontWeight: 500 }}>Đang tải...</div>
      </div>
    );
  }

  // 2. Chưa đăng nhập -> Hiện màn hình Login
  if (!user) {
    return (
      <>
        <LoginPage errorMessage={authError} />
        <SnackbarContainer snackbars={snackbars} onDismiss={removeSnackbar} />
      </>
    );
  }

  // 3. Đã đăng nhập -> Hiện ứng dụng chính
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw', overflow: 'hidden' }}>
      <TopBar
        onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
        theme={theme}
        onToggleTheme={() => setTheme((prev) => (prev === 'light' ? 'dark' : 'light'))}
        user={user}
        onLogout={handleLogout}
        onConnectGmail={handleConnectGmail}
        onDisconnectGmail={handleDisconnectGmail}
      />
      {user?.demo_mode && (
        <div
          role="status"
          style={{
            backgroundColor: theme === 'dark' ? '#3e2e04' : '#fef7e0',
            color: theme === 'dark' ? '#ffdf99' : '#734c00',
            padding: '6px 16px',
            fontSize: '13px',
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            borderBottom: theme === 'dark' ? '1px solid #5d4508' : '1px solid #f9e2af',
            userSelect: 'none',
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: '18px', verticalAlign: 'middle' }}>
            info
          </span>
          <span>Chế độ demo: dữ liệu mẫu, không kết nối Gmail</span>
        </div>
      )}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden', position: 'relative' }}>
        <Sidebar
          isOpen={sidebarOpen}
          isMobile={isMobile}
          onCloseMobile={() => setSidebarOpen(false)}
          activeTab={activeTab}
          onSelectTab={setActiveTab}
          onNewChat={async () => {
            setMessages([]);
            setActiveTab('chat');
            try {
              await apiCall('/chat/clear', { method: 'POST' });
            } catch (e) {
              console.debug('Clear chat history error', e);
            }
          }}
          pendingCount={pendingActions.length}
        />
        <main style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
          {activeTab === 'chat' && (
            <ChatView
              messages={messages}
              loading={loading}
              onSend={handleSend}
              onApprove={handleApprove}
              onReject={handleReject}
              onEditPlaceholder={() => showSnackbar('Chức năng đang phát triển', 'warning')}
            />
          )}
          {activeTab === 'pending' && (
            <PendingListView
              pendingActions={pendingActions}
              onApprove={handleApprove}
              onReject={handleReject}
              onEditPlaceholder={() => showSnackbar('Chức năng đang phát triển', 'warning')}
              onRefresh={fetchPendingActions}
            />
          )}
          {activeTab === 'audit' && <AuditLogView apiUrl={API_BASE_URL} />}
          {activeTab === 'settings' && (
            <div style={{ padding: '32px', textAlign: 'center', color: 'var(--md-on-surface-variant)' }}>
              <h3>Cài đặt hệ thống</h3>
              <p style={{ marginTop: '8px' }}>Chức năng cài đặt tài khoản và quyền hạn (RBAC) đang được phát triển.</p>
            </div>
          )}
        </main>
      </div>
      <SnackbarContainer snackbars={snackbars} onDismiss={removeSnackbar} />
    </div>
  );
}

export default App;
