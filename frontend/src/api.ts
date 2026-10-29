import type { SystemStatus, Video } from "./types";

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

/** URL that streams a generated asset (clip / final video) by absolute path. */
export const fileUrl = (path: string) =>
  `/api/file?path=${encodeURIComponent(path)}`;

export const api = {
  system: () => req<SystemStatus>("/api/system"),
  saveSecret: (key: string, value: string) =>
    req("/api/settings/secret", {
      method: "POST",
      body: JSON.stringify({ key, value }),
    }),

  listVideos: () => req<Video[]>("/api/videos"),
  getVideo: (id: string) => req<Video>(`/api/videos/${id}`),
  createVideo: (scp_ref: string, guidance = "", voice = "") =>
    req<Video>("/api/videos", {
      method: "POST",
      body: JSON.stringify({ scp_ref, guidance, voice }),
    }),
  deleteVideo: (id: string) => req(`/api/videos/${id}`, { method: "DELETE" }),
  patchVideo: (id: string, data: { title?: string; voice?: string }) =>
    req<Video>(`/api/videos/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  patchScene: (
    id: string,
    index: number,
    data: { narration?: string; visual?: string; sound?: string },
  ) =>
    req<Video>(`/api/videos/${id}/scenes/${index}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  regenerateScript: (id: string, guidance = "") =>
    req<Video>(`/api/videos/${id}/regenerate-script`, {
      method: "POST",
      body: JSON.stringify({ scp_ref: "", guidance }),
    }),
  produce: (id: string) =>
    req<Video>(`/api/videos/${id}/produce`, { method: "POST" }),
};
