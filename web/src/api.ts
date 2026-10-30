import type { Config, ImportDetail, ImportSummary, Job, LlmProvider, LlmSettings, RunData, RunMeta } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

export const api = {
  config: () => request<Config>("/api/config"),
  imports: () => request<ImportSummary[]>("/api/imports"),
  import: (id: string) => request<ImportDetail>(`/api/imports/${id}`),
  upload: (file: File) =>
    request<ImportDetail>(`/api/imports?name=${encodeURIComponent(file.name)}`, { method: "POST", body: file }),
  validate: (id: string, decisions: Record<string, boolean>) =>
    post<ImportSummary>(`/api/imports/${id}/validate`, { decisions }),
  analyze: (id: string, web: boolean) => post<Job>(`/api/imports/${id}/analyze`, { web }),
  job: () => request<Job>("/api/job"),
  runs: () => request<RunMeta[]>("/api/runs"),
  run: (id: string) => request<RunData>(`/api/runs/${id}`),
  saveSettings: (body: { provider: LlmProvider; api_key?: string; model?: string }) =>
    post<LlmSettings>("/api/settings", body),
  testSettings: () => post<{ ok: boolean; provider: string; model: string }>("/api/settings/test"),
  fileUrl: (run: string, name: string) => `/api/runs/${run}/files/${name}`,
  memoryUrl: "/api/memory",
};
