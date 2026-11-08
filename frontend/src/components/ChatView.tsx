import { useRef, useEffect } from 'react';
import { ChatMessage } from '../types';
import { EmptyState } from './EmptyState';
import { ConfirmCard } from './ConfirmCard';
import { ChatInput } from './ChatInput';

interface ChatViewProps {
  messages: ChatMessage[];
  loading: boolean;
  onSend: (text: string) => void;
  onApprove: (actionId: string, editedArgs?: Record<string, any>) => Promise<void>;
  onReject: (actionId: string) => Promise<void>;
  onEditPlaceholder: () => void;
}

export const ChatView = ({
  messages,
  loading,
  onSend,
  onApprove,
  onReject,
  onEditPlaceholder,
}: ChatViewProps) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const renderToolResult = (msg: ChatMessage) => {
    if (!msg.result) return null;

    if (msg.tool_name === 'search_email' && msg.result.emails) {
      return (
        <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--md-on-surface-variant)' }}>
            Kết quả tìm thấy ({msg.result.emails.length} email):
          </div>
          {msg.result.emails.map((e: any) => (
            <div key={e.id} style={{
              backgroundColor: 'var(--md-surface)',
              border: '1px solid var(--md-outline-variant)',
              borderRadius: 'var(--radius-md)',
              padding: '12px',
              fontSize: '13px',
              boxShadow: 'var(--elevation-1)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <strong>{e.from}</strong>
                <span style={{ fontSize: '11px', color: 'var(--md-on-surface-variant)' }}>{e.date}</span>
              </div>
              <div style={{ fontWeight: 500, color: 'var(--md-primary)', marginBottom: '2px' }}>{e.subject}</div>
              <div style={{ color: 'var(--md-on-surface-variant)', fontSize: '12px' }}>{e.body}</div>
            </div>
          ))}
        </div>
      );
    }

    if (msg.tool_name === 'list_events' && msg.result.events) {
      return (
        <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--md-on-surface-variant)' }}>
            Lịch họp sắp tới ({msg.result.events.length}):
          </div>
          {msg.result.events.map((evt: any) => (
            <div key={evt.id} style={{
              backgroundColor: 'var(--md-surface)',
              border: '1px solid var(--md-outline-variant)',
              borderRadius: 'var(--radius-md)',
              padding: '10px 14px',
              fontSize: '13px',
              boxShadow: 'var(--elevation-1)',
            }}>
              <div style={{ fontWeight: 600 }}>📅 {evt.title}</div>
              <div style={{ fontSize: '12px', color: 'var(--md-on-surface-variant)', marginTop: '2px' }}>
                {evt.start_time} - {evt.end_time}
              </div>
            </div>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      position: 'relative',
      backgroundColor: 'var(--md-surface-container-low)',
    }}>
      {/* Messages Scroll Area */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '24px 16px',
        display: 'flex',
        flexDirection: 'column',
      }}>
        <div style={{ maxWidth: '800px', margin: '0 auto', width: '100%' }}>
          {messages.length === 0 ? (
            <EmptyState onSelectPrompt={onSend} />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {messages.map((msg) => {
                const isUser = msg.role === 'user';
                return (
                  <div key={msg.id} style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: isUser ? 'flex-end' : 'flex-start',
                    width: '100%',
                  }}>
                    <div style={{
                      maxWidth: '85%',
                      padding: '12px 18px',
                      borderRadius: isUser ? '20px 20px 4px 20px' : '20px 20px 20px 4px',
                      backgroundColor: isUser ? 'var(--md-surface-container-highest)' : 'var(--md-surface)',
                      color: 'var(--md-on-surface)',
                      border: isUser ? 'none' : '1px solid var(--md-outline-variant)',
                      boxShadow: isUser ? 'none' : 'var(--elevation-1)',
                      fontSize: '14.5px',
                      lineHeight: '1.5',
                      whiteSpace: 'pre-wrap',
                    }}>
                      {msg.content}
                    </div>

                    {renderToolResult(msg)}

                    {msg.pending_action && (
                      <ConfirmCard
                        action={msg.pending_action}
                        onApprove={onApprove}
                        onReject={onReject}
                        onEditPlaceholder={onEditPlaceholder}
                      />
                    )}

                    <span style={{ fontSize: '11px', color: 'var(--md-on-surface-variant)', marginTop: '4px', padding: '0 4px' }}>
                      {msg.timestamp}
                    </span>
                  </div>
                );
              })}

              {/* Gemini thinking effect */}
              {loading && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--md-primary)', fontSize: '13px', padding: '12px 0' }}>
                  <span className="material-symbols-outlined" style={{ animation: 'spin 1.5s linear infinite' }}>
                    progress_activity
                  </span>
                  <span>Đang suy nghĩ và kiểm tra mức độ rủi ro...</span>
                </div>
              )}
              <div ref={scrollRef} />
            </div>
          )}
        </div>
      </div>

      {/* Input Bar */}
      <ChatInput onSend={onSend} disabled={loading} />
    </div>
  );
};
