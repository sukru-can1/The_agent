const API = process.env.NEXT_PUBLIC_API_URL || "/api";

export async function fetchStatus() {
  const res = await fetch(`${API}/admin/status`);
  if (!res.ok) throw new Error("Failed to fetch status");
  return res.json();
}

export async function fetchHealth() {
  const res = await fetch(`${API}/health`);
  if (!res.ok) throw new Error("Failed to fetch health");
  return res.json();
}

export async function fetchDrafts(status = "pending") {
  const res = await fetch(`${API}/admin/drafts?status=${status}`);
  if (!res.ok) throw new Error("Failed to fetch drafts");
  return res.json();
}

export async function fetchEvents(status = "pending", limit = 20) {
  const res = await fetch(`${API}/admin/events?status=${status}&limit=${limit}`);
  if (!res.ok) throw new Error("Failed to fetch events");
  return res.json();
}

export async function fetchDlq() {
  const res = await fetch(`${API}/admin/dlq`);
  if (!res.ok) throw new Error("Failed to fetch DLQ");
  return res.json();
}

export async function fetchActions(limit = 100) {
  const res = await fetch(`${API}/admin/actions?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to fetch actions");
  return res.json();
}

export async function fetchKnowledge(limit = 100) {
  const res = await fetch(`${API}/admin/knowledge?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to fetch knowledge");
  return res.json();
}

export async function fetchIntegrations() {
  const res = await fetch(`${API}/admin/integrations`);
  if (!res.ok) throw new Error("Failed to fetch integrations");
  return res.json();
}

export async function fetchConfig() {
  const res = await fetch(`${API}/admin/config`);
  if (!res.ok) throw new Error("Failed to fetch config");
  return res.json();
}

export async function updateConfig(key: string, value: unknown) {
  const res = await fetch(`${API}/admin/config/${key}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
  return res.json();
}

export async function storeKnowledge(content: string, category = "operator_instruction") {
  const res = await fetch(`${API}/admin/knowledge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category, content, source: "dashboard" }),
  });
  return res.json();
}

export async function fetchDraft(draftId: number) {
  const res = await fetch(`${API}/admin/drafts/${draftId}`);
  if (!res.ok) throw new Error("Failed to fetch draft");
  return res.json();
}

export async function reviseDraft(draftId: number, instruction: string) {
  const res = await fetch(`${API}/admin/drafts/${draftId}/revise`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruction }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Revision failed");
  }
  return res.json();
}

export async function approveAndSendDraft(draftId: number, editedBody?: string) {
  const res = await fetch(`${API}/admin/drafts/${draftId}/approve-and-send`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ edited_body: editedBody }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Send failed");
  }
  return res.json();
}

export async function approveDraft(draftId: number, editedBody?: string) {
  const res = await fetch(`${API}/admin/drafts/${draftId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ edited_body: editedBody }),
  });
  return res.json();
}

export async function rejectDraft(draftId: number) {
  const res = await fetch(`${API}/admin/drafts/${draftId}/reject`, {
    method: "POST",
  });
  return res.json();
}

export async function retryDlqEntry(dlqId: string) {
  const res = await fetch(`${API}/admin/dlq/${dlqId}/retry`, { method: "POST" });
  return res.json();
}

export async function resolveDlqEntry(dlqId: string) {
  const res = await fetch(`${API}/admin/dlq/${dlqId}/resolve`, { method: "POST" });
  return res.json();
}

export async function pauseQueue() {
  const res = await fetch(`${API}/admin/queue/pause`, { method: "POST" });
  return res.json();
}

export async function resumeQueue() {
  const res = await fetch(`${API}/admin/queue/resume`, { method: "POST" });
  return res.json();
}

export async function fetchActionDetail(actionId: number) {
  const res = await fetch(`${API}/admin/actions/${actionId}/with-event`);
  if (!res.ok) throw new Error("Failed to fetch action detail");
  return res.json();
}

export async function submitActionFeedback(
  actionId: number,
  comment: string,
  action: "note" | "redo" | "revert" = "note",
) {
  const res = await fetch(`${API}/admin/actions/${actionId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ comment, action }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Feedback failed");
  }
  return res.json();
}

export async function injectEvent(text: string, source = "gchat", eventType = "chat_message") {
  const res = await fetch(`${API}/admin/inject-event`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, event_type: eventType, text }),
  });
  return res.json();
}
