import { useState, useEffect } from 'react';
import { ChatMessage, PendingAction, SnackbarInfo, TabType } from './types';
import { TopBar } from './components/TopBar';
import { Sidebar } from './components/Sidebar';
import { ChatView } from './components/ChatView';
import { PendingListView } from './components/PendingListView';
import { AuditLogView } from './components/AuditLogView';
import { SnackbarContainer } from './components/Snackbar';
import './theme.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export function App() {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const [activeTab, setActiveTab] = useState<TabType>('chat');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pendingActions, setPendingActions] = useState<PendingAction[]>([]);
  const [loading, setLoading] = useState(false);
  const [snackbars, setSnackbars] = useState<SnackbarInfo[]>([]);

  // Dark mode theme effect
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  // Responsive mobile detection
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

  const showSnackbar = (message: string, type: SnackbarInfo['type'] = 'info') => {
    const id = Date.now().toString() + Math.random().toString().slice(2, 5);
    setSnackbars((prev) => [...prev, { id, message, type }]);
  };

  const removeSnackbar = (id: string) => setSnackbars((prev) => prev.filter((s) => s.id !== id));

  const fetchPendingActions = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/actions/pending`);
      if (res.ok) {
        const data = await res.json();
        setPendingActions(data.actions || []);
      }
    } catch (e) {
      console.error('Fetch pending error:', e);
    }
  };

  useEffect(() => { fetchPendingActions(); }, []);

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
      const res = await fetch(`${API_BASE_URL}/chat`, {
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
      showSnackbar(`Lỗi kết nối: ${err.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (actionId: string, editedArgs?: Record<string, any>) => {
    try {
      const res = await fetch(`${API_BASE_URL}/actions/${actionId}/approve`, {
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
      if (err.status !== 422) {
        showSnackbar(`Duyệt thất bại: ${err.message}`, 'error');
      }
      throw err;
    }
  };

  const handleReject = async (actionId: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/actions/${actionId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Người dùng hủy bỏ' }),
      });
      if (!res.ok) throw new Error('Lỗi khi hủy');
      showSnackbar('✕ Đã hủy bỏ hành động.', 'info');
      setPendingActions((prev) => prev.filter((a) => a.id !== actionId));
    } catch (err: any) {
      showSnackbar(`Hủy thất bại: ${err.message}`, 'error');
      throw err;
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw', overflow: 'hidden' }}>
      <TopBar
        onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
        theme={theme}
        onToggleTheme={() => setTheme((prev) => (prev === 'light' ? 'dark' : 'light'))}
      />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden', position: 'relative' }}>
        <Sidebar
          isOpen={sidebarOpen}
          isMobile={isMobile}
          onCloseMobile={() => setSidebarOpen(false)}
          activeTab={activeTab}
          onSelectTab={setActiveTab}
          onNewChat={() => {
            setMessages([]);
            setActiveTab('chat');
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
