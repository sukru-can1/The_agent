export interface AgentStatus {
  queue_depth: number;
  pending_drafts: number;
  dlq_count: number;
  pending_proposals: number;
  is_paused: boolean;
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
  original_body?: string | null;
  edited_body?: string | null;
  context_used?: Record<string, unknown> | null;
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
  payload: Record<string, unknown> | null;
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

export interface AgentAction {
  id: number;
  timestamp: string;
  system: string;
  action_type: string;
  outcome: string;
  model_used: string;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  details: Record<string, unknown> | null;
}

export interface Integration {
  id: string;
  name: string;
  active: boolean;
}

export interface KnowledgeEntry {
  id: number;
  category: string;
  content: string;
  source: string;
  created_at: string;
  active: boolean;
  confidence: number;
  supersedes_id: number | null;
}

export type Category = "cs" | "finance" | "operations" | "website" | "marketing" | "system";

export const CATEGORY_CONFIG: Record<Category, { label: string; color: string; bg: string }> = {
  cs: { label: "CS", color: "#22d3ee", bg: "bg-cyan-500/10 text-cyan-400" },
  finance: { label: "Finance", color: "#fbbf24", bg: "bg-amber-500/10 text-amber-400" },
  operations: { label: "Ops", color: "#818cf8", bg: "bg-indigo-500/10 text-indigo-400" },
  website: { label: "Web", color: "#34d399", bg: "bg-emerald-500/10 text-emerald-400" },
  marketing: { label: "Mktg", color: "#c084fc", bg: "bg-purple-500/10 text-purple-400" },
  system: { label: "Sys", color: "#64748b", bg: "bg-slate-500/10 text-slate-400" },
};

export function getCategory(source: string, eventType: string): Category {
  if (source === "freshdesk" || source === "feedbacks") return "cs";
  if (eventType.includes("payment") || eventType.includes("refund")) return "finance";
  if (source === "starinfinity") return "operations";
  if (eventType.includes("seo") || eventType.includes("website")) return "website";
  if (eventType.includes("campaign") || eventType.includes("marketing")) return "marketing";
  if (source === "gmail") return "operations";
  if (source === "gchat") return "operations";
  return "system";
}

export function extractDetail(source: string, payload: Record<string, unknown> | null): string {
  if (!payload) return "";
  if (source === "freshdesk") {
    return `Ticket #${payload.ticket_id ?? ""} — ${payload.subject ?? ""}`;
  }
  if (source === "gmail") {
    return `From: ${payload.from_address ?? payload.sender ?? ""} — ${payload.subject ?? ""}`;
  }
  if (source === "gchat") {
    const text = String(payload.text ?? "").slice(0, 120);
    return `${payload.sender ?? ""}: "${text}"`;
  }
  if (source === "starinfinity") {
    return `Board: ${payload.board_name ?? ""} — ${payload.task_title ?? ""}`;
  }
  if (source === "feedbacks") {
    return `${payload.customer_email ?? ""} — Rating: ${payload.rating ?? ""}`;
  }
  return JSON.stringify(payload).slice(0, 150);
}

export interface ActionSummary {
  eventSummary: string;
  toolsUsed: string[];
  agentResponse: string;
  externalLink: string | null;
  triggerMessage: string | null;
  classification: Record<string, unknown> | null;
}

export function extractActionSummary(action: AgentAction): ActionSummary {
  const d = action.details ?? {};
  const classification = (d.classification as Record<string, unknown>) ?? {};

  // Event summary from enriched details or fallback
  let eventSummary = (d.event_summary as string) || "";
  if (!eventSummary) {
    eventSummary = action.action_type.replace(/_/g, " ");
  }

  // Tools called
  const toolsUsed = (d.tools_called as string[]) || [];

  // Agent response (first 300 chars stored by backend)
  const agentResponse = (d.agent_response as string) || "";

  // Try to build an external link
  let externalLink: string | null = null;
  const eventPayload = d.event_payload as Record<string, unknown> | undefined;
  const source = action.system;
  if (source === "freshdesk") {
    const ticketId = (d.ticket_id as string) || (eventPayload?.ticket_id as string);
    if (ticketId) {
      externalLink = `https://glmr.freshdesk.com/a/tickets/${ticketId}`;
    }
  } else if (source === "gmail") {
    const threadId = (eventPayload?.gmail_thread_id as string) || (eventPayload?.thread_id as string);
    if (threadId) {
      externalLink = `https://mail.google.com/mail/u/0/#inbox/${threadId}`;
    }
  }

  // Trigger message — what the user/customer said
  let triggerMessage: string | null = null;
  if (eventPayload) {
    // Chat messages
    const text = eventPayload.text as string;
    if (text) triggerMessage = text;
    // Emails
    const subject = eventPayload.subject as string;
    const from = (eventPayload.from_address ?? eventPayload.sender) as string;
    if (subject && !triggerMessage) {
      triggerMessage = `${from ? from + ": " : ""}${subject}`;
    }
    // Freshdesk
    const ticketSubject = eventPayload.subject as string;
    const ticketId = eventPayload.ticket_id as string;
    if (ticketId && !triggerMessage) {
      triggerMessage = `Ticket #${ticketId}: ${ticketSubject || ""}`;
    }
  }
  // Auto-response details
  if (!triggerMessage && d.question) {
    triggerMessage = d.question as string;
  }

  // Classification data
  const classificationData = Object.keys(classification).length > 0
    ? classification as Record<string, unknown>
    : null;

  return { eventSummary, toolsUsed, agentResponse, externalLink, triggerMessage, classification: classificationData };
}

export interface Proposal {
  id: string;
  type: string;
  title: string;
  description: string;
  evidence: string | null;
  code: string | null;
  config: Record<string, unknown> | null;
  confidence: number;
  status: string;
  created_at: string;
  expires_at: string | null;
  reviewed_at: string | null;
  reviewed_by: string | null;
}

export const PROPOSAL_TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  learned_rule: { label: "Rule", color: "text-cyan-400" },
  strong_rule: { label: "Strong Rule", color: "text-cyan-300" },
  tool_creation: { label: "Tool", color: "text-amber-400" },
  automation: { label: "Automation", color: "text-purple-400" },
  mcp_server: { label: "MCP", color: "text-emerald-400" },
  guardrail_override: { label: "Override", color: "text-red-400" },
  threshold_adjustment: { label: "Threshold", color: "text-indigo-400" },
  playbook_suggestion: { label: "Playbook", color: "text-slate-400" },
};

export function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
