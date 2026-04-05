const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/v1";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

async function apiFetch(path: string, options: RequestInit = {}) {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${API_KEY}`,
      ...options.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

export async function getHealth() {
  return apiFetch("/health");
}

export async function getMemories(params: Record<string, string>) {
  const qs = new URLSearchParams(params).toString();
  return apiFetch(`/memories/?${qs}`);
}

export async function searchMemories(query: string, filters: Record<string, unknown> = {}) {
  return apiFetch("/memories/search/", {
    method: "POST",
    body: JSON.stringify({ query, ...filters }),
  });
}

export async function addMemory(data: Record<string, unknown>) {
  return apiFetch("/memories/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateMemory(id: string, data: Record<string, unknown>) {
  return apiFetch(`/memories/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteMemory(id: string) {
  return apiFetch(`/memories/${id}`, { method: "DELETE" });
}

export async function deleteMemories(ids: string[]) {
  return Promise.all(ids.map((id) => deleteMemory(id)));
}

export async function getStats() {
  return apiFetch("/stats/");
}

export async function getCategories() {
  return apiFetch("/memories/categories/");
}

export async function getAgentsList() {
  return apiFetch("/memories/agents/");
}

export async function getActivity(params: Record<string, string> = {}) {
  const qs = new URLSearchParams(params).toString();
  return apiFetch(`/activity/?${qs}`);
}

// v0.3.0 — Events, Conflicts, Subscriptions
export async function getEvents(params: Record<string, string> = {}) {
  const qs = new URLSearchParams(params).toString();
  return apiFetch(`/events/?${qs}`);
}

export async function getMemoryHistory(memoryId: string) {
  return apiFetch(`/memories/${memoryId}/history/`);
}

export async function getMemoryConflicts(memoryId: string) {
  return apiFetch(`/memories/${memoryId}/conflicts/`);
}

export async function resolveConflict(memoryId: string, data: { resolution: string; merged_content?: string }) {
  return apiFetch(`/memories/${memoryId}/resolve/`, { method: "POST", body: JSON.stringify(data) });
}

export async function getSubscriptions(agentId?: string) {
  const qs = agentId ? `?agent_id=${agentId}` : "";
  return apiFetch(`/subscriptions/${qs}`);
}

export async function createSubscription(data: { agent_id: string; scope_filter?: string; pool_filter?: string; category_filter?: string; event_types?: string[] }) {
  return apiFetch("/subscriptions/", { method: "POST", body: JSON.stringify(data) });
}

export async function deleteSubscription(id: string) {
  return apiFetch(`/subscriptions/${id}`, { method: "DELETE" });
}

export function getWsUrl() {
  const base = typeof window !== "undefined" ? window.location.origin : "";
  const wsBase = base.replace(/^http/, "ws");
  return `${wsBase}/v1/ws?api_key=${API_KEY}`;
}

// Sessions
export async function getSessions(userId: string) {
  return apiFetch(`/sessions/?user_id=${encodeURIComponent(userId)}`);
}

export async function createSession(data: { name: string; user_id: string; agent_id?: string; expires_in_minutes?: number }) {
  return apiFetch("/sessions/", { method: "POST", body: JSON.stringify(data) });
}

export async function deleteSession(id: string) {
  return apiFetch(`/sessions/${id}`, { method: "DELETE" });
}

// Pool Access
export async function getPoolAccess(poolId: string) {
  return apiFetch(`/pools/${encodeURIComponent(poolId)}/access/`);
}

export async function grantPoolAccess(data: { pool_id: string; agent_id: string; permissions: { read: boolean; write: boolean; admin: boolean } }) {
  return apiFetch(`/pools/${encodeURIComponent(data.pool_id)}/access/`, { method: "POST", body: JSON.stringify(data) });
}

export async function revokePoolAccess(poolId: string, id: string) {
  return apiFetch(`/pools/${encodeURIComponent(poolId)}/access/${id}`, { method: "DELETE" });
}

// Webhooks
export async function getWebhooks() {
  return apiFetch("/webhooks/");
}

export async function createWebhook(data: { url: string; events: string[]; secret?: string }) {
  return apiFetch("/webhooks/", { method: "POST", body: JSON.stringify(data) });
}

export async function deleteWebhook(id: string) {
  return apiFetch(`/webhooks/${id}`, { method: "DELETE" });
}

// Schemas
export async function getSchemas() {
  return apiFetch("/schemas/");
}

export async function createSchema(data: { name: string; fields: { name: string; type: string; required: boolean }[]; description?: string }) {
  return apiFetch("/schemas/", { method: "POST", body: JSON.stringify(data) });
}

export async function deleteSchema(id: string) {
  return apiFetch(`/schemas/${id}`, { method: "DELETE" });
}

// Instructions
export async function getInstructions(userId: string) {
  return apiFetch(`/instructions/?user_id=${encodeURIComponent(userId)}`);
}

export async function createInstruction(data: { user_id: string; instruction: string }) {
  return apiFetch("/instructions/", { method: "POST", body: JSON.stringify(data) });
}

export async function deleteInstruction(id: string) {
  return apiFetch(`/instructions/${id}`, { method: "DELETE" });
}

// Analytics
export async function getAnalytics() {
  return apiFetch("/analytics/");
}

// Decay
export async function getDecayPreview(limit?: number) {
  const qs = limit ? `?limit=${limit}` : "";
  return apiFetch(`/decay/preview${qs}`);
}

export async function runDecayCleanup(threshold?: number) {
  const body = threshold !== undefined ? JSON.stringify({ threshold }) : "{}";
  return apiFetch("/decay/cleanup", { method: "POST", body });
}

// Audit
export async function getAudit(params?: Record<string, string>) {
  const qs = params ? `?${new URLSearchParams(params).toString()}` : "";
  return apiFetch(`/audit/${qs}`);
}

// Bulk
export async function bulkExport(data: { user_id: string; agent_id?: string; pool_id?: string; memory_type?: string }) {
  return apiFetch("/bulk/export", { method: "POST", body: JSON.stringify(data) });
}

export async function getGraph(params: Record<string, string> = {}) {
  const qs = new URLSearchParams(params).toString();
  return apiFetch(`/graph/?${qs}`);
}

export async function bulkImport(data: { memories: Array<{ text: string; user_id: string; agent_id?: string; pool_id?: string }> }) {
  return apiFetch("/bulk/import", { method: "POST", body: JSON.stringify(data) });
}

// v0.3.0 functions defined above (lines 77-107)

// v0.4.0 — Projects
export async function getProjects() {
  return apiFetch("/projects/");
}

export async function getProject(id: string) {
  return apiFetch(`/projects/${id}`);
}

export async function createProject(data: { name: string; slug: string; description?: string; agents?: string[] }) {
  return apiFetch("/projects/", { method: "POST", body: JSON.stringify(data) });
}

export async function updateProject(id: string, data: Record<string, unknown>) {
  return apiFetch(`/projects/${id}`, { method: "PUT", body: JSON.stringify(data) });
}

export async function deleteProject(id: string) {
  return apiFetch(`/projects/${id}`, { method: "DELETE" });
}

// Tasks
export async function getTasks(params: Record<string, string> = {}) {
  const qs = new URLSearchParams(params).toString();
  return apiFetch(`/tasks/?${qs}`);
}

export async function createTask(data: { name: string; project_id?: string; agents?: string[]; expires_in_hours?: number }) {
  return apiFetch("/tasks/", { method: "POST", body: JSON.stringify(data) });
}

export async function updateTask(id: string, data: Record<string, unknown>) {
  return apiFetch(`/tasks/${id}`, { method: "PUT", body: JSON.stringify(data) });
}

export async function deleteTask(id: string) {
  return apiFetch(`/tasks/${id}`, { method: "DELETE" });
}

// Agent Context
export async function getAgentContext(agentId: string) {
  return apiFetch(`/agents/${agentId}/context/`);
}

export async function setAgentContext(agentId: string, data: { active_project_id?: string; active_task_id?: string; default_scope?: string; default_pool_id?: string }) {
  return apiFetch(`/agents/${agentId}/context/`, { method: "PUT", body: JSON.stringify(data) });
}

export async function clearAgentContext(agentId: string) {
  return apiFetch(`/agents/${agentId}/context/`, { method: "DELETE" });
}
