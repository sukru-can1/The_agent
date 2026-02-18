export interface AgentStatus {
  queue_depth: number;
  pending_drafts: number;
  dlq_count: number;
  last_action: {
    timestamp: string;
    system: string;
    action_type: string;
  } | null;
}

export interface Draft {
  id: number;
  gmail_message_id: string;
  from_address: string;
  to_address: string;
  subject: string;
  draft_body: string;
  status: string;
  classification: string;
  created_at: string;
}

export interface AgentEvent {
  id: string;
  source: string;
  event_type: string;
  priority: number;
  status: string;
  created_at: string;
  error: string | null;
}

export interface DlqEntry {
  id: string;
  original_event_id: string;
  source: string;
  event_type: string;
  priority: number;
  error_history: Array<{ retry: number; error: string }>;
  retry_count: number;
  created_at: string;
}

export type CardType = "draft" | "alert" | "question" | "info" | "error";

export interface ActionCard {
  id: string;
  type: CardType;
  title: string;
  subtitle?: string;
  body: string;
  priority: "critical" | "high" | "medium" | "low";
  timestamp: string;
  actions: Array<{
    label: string;
    variant: "primary" | "secondary" | "danger";
    onClick: () => void;
  }>;
  meta?: Record<string, string>;
}
