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
