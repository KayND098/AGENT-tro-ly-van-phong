export type Role = 'user' | 'assistant' | 'system';

export interface PendingAction {
  id: string;
  tool_name: string;
  original_args: Record<string, any>;
  edited_args?: Record<string, any> | null;
  preview: Record<string, any>;
  risk_level: 'read' | 'reversible' | 'confirm';
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXPIRED';
  result?: any;
  created_at: string;
  expires_at: string;
  updated_at?: string;
}

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  type?: 'text' | 'tool_executed' | 'confirm_required' | 'error';
  tool_name?: string;
  risk_level?: string;
  result?: any;
  pending_action?: PendingAction | null;
  timestamp: string;
}

export interface AuditLogItem {
  id: number;
  action_id?: string | null;
  action_type: string;
  tool_name: string;
  original_args: string;
  edited_args?: string | null;
  result?: string | null;
  status: string;
  created_at: string;
}

export interface SnackbarInfo {
  id: string;
  message: string;
  type?: 'info' | 'success' | 'warning' | 'error';
  actionLabel?: string;
  onAction?: () => void;
}

export type TabType = 'chat' | 'pending' | 'audit' | 'settings';
