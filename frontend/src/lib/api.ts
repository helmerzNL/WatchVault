// Thin fetch wrapper. Same-origin in production (nginx proxies /api → backend);
// dev uses Vite's proxy. Session is a HttpOnly cookie, so we just send creds.

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function handle(res: Response): Promise<any> {
  const ct = res.headers.get("content-type") || "";
  const body = ct.includes("application/json") ? await res.json().catch(() => ({})) : await res.text();
  if (!res.ok) {
    const msg = (body && (body.error || body.message)) || res.statusText || "Request failed";
    throw new ApiError(res.status, msg);
  }
  return body;
}

function qs(params?: Record<string, any>): string {
  if (!params) return "";
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  }
  const str = s.toString();
  return str ? `?${str}` : "";
}

export const api = {
  get: (path: string, params?: Record<string, any>) =>
    fetch(`/api${path}${qs(params)}`, { credentials: "include" }).then(handle),

  post: (path: string, body?: any) =>
    fetch(`/api${path}`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }).then(handle),

  put: (path: string, body?: any) =>
    fetch(`/api${path}`, {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    }).then(handle),

  patch: (path: string, body?: any) =>
    fetch(`/api${path}`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    }).then(handle),

  del: (path: string) =>
    fetch(`/api${path}`, { method: "DELETE", credentials: "include" }).then(handle),

  upload: (path: string, form: FormData) =>
    fetch(`/api${path}`, { method: "POST", credentials: "include", body: form }).then(handle),
};
