import type { LlmChoice } from "./lib/app";
import type { Config, ImportDetail, ImportSummary, Job, RunData, RunMeta } from "./types";

export const UNAUTHORIZED = "tamtam-unauthorized";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (res.status === 401 && !path.startsWith("/api/login")) window.dispatchEvent(new Event(UNAUTHORIZED));
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
  session: () => request<{ protege: boolean; connecte: boolean }>("/api/session"),
  login: (password: string) => post<{ connecte: boolean }>("/api/login", { password }),
  logout: () => post<{ connecte: boolean }>("/api/logout"),
  config: () => request<Config>("/api/config"),
  imports: () => request<ImportSummary[]>("/api/imports"),
  import: (id: string) => request<ImportDetail>(`/api/imports/${id}`),
  upload: (file: File) =>
    request<ImportDetail>(`/api/imports?name=${encodeURIComponent(file.name)}`, { method: "POST", body: file }),
  validate: (id: string, decisions: Record<string, boolean>) =>
    post<ImportSummary>(`/api/imports/${id}/validate`, { decisions }),
  analyze: (id: string, web: boolean, llm: LlmChoice | null) =>
    post<Job>(`/api/imports/${id}/analyze`, { web, llm }),
  job: () => request<Job>("/api/job"),
  runs: () => request<RunMeta[]>("/api/runs"),
  run: (id: string) => request<RunData>(`/api/runs/${id}`),
  testLlm: (llm: LlmChoice) => post<{ ok: boolean; provider: string; model: string }>("/api/llm/test", llm),
  fileUrl: (run: string, name: string) => `/api/runs/${run}/files/${name}`,
  memoryUrl: "/api/memory",
};

/** Télécharge un fichier de l'API. Passer par un blob évite qu'un navigateur (Safari) ignore
    le téléchargement lancé depuis un menu qui se referme, et permet d'afficher une erreur. */
export async function download(path: string, filename: string): Promise<void> {
  const res = await fetch(path);
  if (res.status === 401) window.dispatchEvent(new Event(UNAUTHORIZED));
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `${res.status} ${res.statusText}`);
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
