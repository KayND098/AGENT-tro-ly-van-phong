import { useState, useRef, useEffect } from 'react';

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export const ChatInput = ({ onSend, disabled }: ChatInputProps) => {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 140)}px`;
    }
  }, [text]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    if (!text.trim() || disabled) return;
    onSend(text.trim());
    setText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  return (
    <div style={{
      maxWidth: '820px',
      margin: '0 auto',
      width: '100%',
      padding: '0 16px 16px 16px',
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'flex-end',
        gap: '8px',
        backgroundColor: 'var(--md-surface-container-high)',
        borderRadius: 'var(--radius-xl)',
        padding: '10px 16px',
        border: '1px solid var(--md-outline-variant)',
        boxShadow: 'var(--elevation-1)',
        transition: 'border-color var(--transition-fast), background var(--transition-fast)',
      }}>
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Nhập yêu cầu (ví dụ: 'tìm email', 'gửi email cho Minh', 'xem lịch')..."
          disabled={disabled}
          rows={1}
          aria-label="Nhập tin nhắn yêu cầu cho trợ lý"
          style={{
            flex: 1,
            border: 'none',
            background: 'transparent',
            outline: 'none',
            resize: 'none',
            fontSize: '15px',
            lineHeight: '1.4',
            fontFamily: 'inherit',
            color: 'var(--md-on-surface)',
            maxHeight: '140px',
            padding: '4px 0',
          }}
        />

        <button
          onClick={handleSubmit}
          disabled={!text.trim() || disabled}
          aria-label="Gửi tin nhắn"
          style={{
            width: '38px',
            height: '38px',
            borderRadius: 'var(--radius-full)',
            backgroundColor: text.trim() && !disabled ? 'var(--md-primary)' : 'transparent',
            color: text.trim() && !disabled ? 'var(--md-on-primary)' : 'var(--md-on-surface-variant)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: text.trim() && !disabled ? 'pointer' : 'not-allowed',
            transition: 'all var(--transition-fast)',
            flexShrink: 0,
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: '20px' }}>
            arrow_upward
          </span>
        </button>
      </div>

      <div style={{
        fontSize: '11px',
        color: 'var(--md-on-surface-variant)',
        textAlign: 'center',
        marginTop: '6px',
      }}>
        Trợ lý hoạt động với cơ chế Human-in-the-loop: Mọi hành động nhạy cảm đều cần sự phê duyệt của bạn.
      </div>
    </div>
  );
};
