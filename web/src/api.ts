export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let msg = res.statusText
    try {
      const j = await res.json()
      msg = j?.error?.message ?? j?.detail ?? msg
    } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return (await res.json()) as T
}

export const get = <T,>(path: string) => request<T>('GET', path)
export const post = <T,>(path: string, body: unknown = {}) => request<T>('POST', path, body)
