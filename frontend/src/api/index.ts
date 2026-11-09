import type { Job } from "../types";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch("/api" + path, init);
  if (!r.ok) {
    let detail = r.statusText;
    try { const j = await r.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j); } catch { /* ignore */ }
    throw new Error(detail);
  }
  return r.json() as Promise<T>;
}

export const post = <T,>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });

/** Poll a background job until it finishes; `onUpdate` receives each status. */
export async function pollJob(id: string, onUpdate: (j: Job) => void, intervalMs = 400): Promise<Job> {
  for (;;) {
    const j = await api<Job>(`/jobs/${id}`);
    onUpdate(j);
    if (["done", "failed", "cancelled"].includes(j.status)) return j;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

export const fmt = (n: number | undefined | null, d = 0) =>
  n === undefined || n === null ? "–" : n.toLocaleString(undefined, { maximumFractionDigits: d });
export const bytes = (n: number) => (n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : n > 1024 ? (n / 1024).toFixed(0) + " KB" : n + " B");
