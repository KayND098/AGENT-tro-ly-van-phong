interface EmptyStateProps {
  onSelectPrompt: (prompt: string) => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({ onSelectPrompt }) => {
  const suggestionChips = [
    {
      icon: 'mail',
      title: 'Tìm email của Minh',
      desc: 'Tìm kiếm nhanh các thư liên quan trong hộp thư',
      prompt: 'tìm email của Minh',
    },
    {
      icon: 'send',
      title: 'Gửi email cho Minh',
      desc: 'Tạo thư và yêu cầu xác nhận trước khi gửi',
      prompt: 'gửi email cho Minh nội dung Báo cáo tuần đã hoàn thành',
    },
    {
      icon: 'calendar_today',
      title: 'Xem lịch hôm nay',
      desc: 'Kiểm tra các sự kiện và cuộc họp sắp tới',
      prompt: 'xem lịch họp tuần này',
    },
    {
      icon: 'table_rows',
      title: 'Xóa 10 dòng đầu sheet Doanh thu',
      desc: 'Xem trước dry-run an toàn trước khi xóa',
      prompt: 'xóa 10 dòng đầu sheet Doanh thu',
    },
  ];

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '60vh',
      padding: '24px',
      textAlign: 'center',
      maxWidth: '720px',
      margin: '0 auto',
    }}>
      {/* Gemini-style greeting header */}
      <div style={{
        background: 'linear-gradient(135deg, #1a73e8 0%, #d93025 50%, #188038 100%)',
        WebkitBackgroundClip: 'text',
        WebkitTextFillColor: 'transparent',
        fontSize: '36px',
        fontWeight: 700,
        marginBottom: '8px',
        letterSpacing: '-0.5px',
      }}>
        Xin chào!
      </div>

      <div style={{
        fontSize: '22px',
        fontWeight: 400,
        color: 'var(--md-on-surface-variant)',
        marginBottom: '32px',
      }}>
        Tôi có thể hỗ trợ gì cho công việc của bạn hôm nay?
      </div>

      {/* Suggestion Chips Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
        gap: '12px',
        width: '100%',
      }}>
        {suggestionChips.map((chip, idx) => (
          <button
            key={idx}
            onClick={() => onSelectPrompt(chip.prompt)}
            style={{
              padding: '16px',
              borderRadius: 'var(--radius-lg)',
              backgroundColor: 'var(--md-surface)',
              border: '1px solid var(--md-outline-variant)',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '14px',
              textAlign: 'left',
              cursor: 'pointer',
              transition: 'all var(--transition-fast)',
              boxShadow: 'var(--elevation-1)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = 'var(--md-surface-container-high)';
              e.currentTarget.style.borderColor = 'var(--md-primary)';
              e.currentTarget.style.transform = 'translateY(-2px)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'var(--md-surface)';
              e.currentTarget.style.borderColor = 'var(--md-outline-variant)';
              e.currentTarget.style.transform = 'translateY(0)';
            }}
          >
            <div style={{
              width: '36px',
              height: '36px',
              borderRadius: 'var(--radius-md)',
              backgroundColor: 'var(--md-primary-container)',
              color: 'var(--md-on-primary-container)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}>
              <span className="material-symbols-outlined">{chip.icon}</span>
            </div>
            <div>
              <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--md-on-surface)' }}>
                {chip.title}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--md-on-surface-variant)', marginTop: '2px' }}>
                {chip.desc}
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
};
