import { z } from 'zod';

export class ApiError extends Error {
  status: number;
  errorMsg: string;
  detail: string | null;
  requestId: string | null;

  constructor(status: number, errorMsg: string, detail: string | null = null, requestId: string | null = null) {
    super(detail || errorMsg || `API error with status ${status}`);
    this.status = status;
    this.errorMsg = errorMsg;
    this.detail = detail;
    this.requestId = requestId;
    this.name = 'ApiError';
  }
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

export async function request<T>(
  path: string,
  options?: RequestInit,
  schema?: z.ZodType<T, any, any>
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url, options);

  if (!response.ok) {
    let errorMsg = 'HTTP error';
    let detail = null;
    let requestId = null;

    try {
      const errBody = await response.json();
      errorMsg = errBody.error || errorMsg;
      detail = errBody.detail || null;
      requestId = errBody.request_id || null;
    } catch {
      // ignore json parse error
    }

    throw new ApiError(response.status, errorMsg, detail, requestId);
  }

  const data = await response.json();

  if (schema) {
    return schema.parse(data);
  }

  return data as T;
}
