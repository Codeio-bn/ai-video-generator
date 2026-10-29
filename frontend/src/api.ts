import type {
  Episode, Job, Project, ScriptGenResult, Shot, SystemStatus,
} from "./types";

async function req<T>(url: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* non-JSON error */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** URL that streams a project asset file by absolute path. */
export const fileUrl = (path: string) =>
  `/api/file?path=${encodeURIComponent(path)}`;

export const api = {
  system: () => req<SystemStatus>("/api/system"),
  saveSecret: (key: string, value: string) =>
    req("/api/settings/secret", {
      method: "POST",
      body: JSON.stringify({ key, value }),
    }),
  testGemini: () =>
    req<{ ok: boolean; detail: string }>("/api/settings/test-gemini", {
      method: "POST",
    }),

  listProjects: () => req<Project[]>("/api/projects"),
  getProject: (id: number) => req<Project>(`/api/projects/${id}`),
  createProject: (data: Partial<Project>) =>
    req<Project>("/api/projects", { method: "POST", body: JSON.stringify(data) }),
  updateProject: (id: number, data: Partial<Project>) =>
    req<Project>(`/api/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteProject: (id: number) =>
    req(`/api/projects/${id}`, { method: "DELETE" }),

  listEpisodes: (pid: number) =>
    req<Episode[]>(`/api/projects/${pid}/episodes`),
  getEpisode: (eid: number) => req<Episode>(`/api/episodes/${eid}`),
  createEpisode: (pid: number, data: Partial<Episode>) =>
    req<Episode>(`/api/projects/${pid}/episodes`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  generateScript: (
    pid: number,
    data: { source_text: string; num_parts: number; guidance: string; replace: boolean },
  ) =>
    req<ScriptGenResult>(`/api/projects/${pid}/generate-script`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateEpisode: (eid: number, data: Partial<Episode>) =>
    req<Episode>(`/api/episodes/${eid}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteEpisode: (eid: number) =>
    req(`/api/episodes/${eid}`, { method: "DELETE" }),

  listShots: (eid: number) => req<Shot[]>(`/api/episodes/${eid}/shots`),
  createShot: (eid: number, data: Partial<Shot>) =>
    req<Shot>(`/api/episodes/${eid}/shots`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateShot: (sid: number, data: Partial<Shot>) =>
    req<Shot>(`/api/shots/${sid}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteShot: (sid: number) => req(`/api/shots/${sid}`, { method: "DELETE" }),
  reorderShots: (eid: number, shot_ids: number[]) =>
    req<Shot[]>(`/api/episodes/${eid}/shots/reorder`, {
      method: "POST",
      body: JSON.stringify({ shot_ids }),
    }),

  startRender: (eid: number, options: object) =>
    req<Job>(`/api/episodes/${eid}/render`, {
      method: "POST",
      body: JSON.stringify({ options }),
    }),
  getJob: (jid: number) => req<Job>(`/api/jobs/${jid}`),
  latestJob: (eid: number) => req<Job>(`/api/episodes/${eid}/latest-job`),
};

/** Multipart upload helper (skips the JSON content-type). */
export async function upload<T>(url: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(url, { method: "POST", body: form });
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.json() as Promise<T>;
}
