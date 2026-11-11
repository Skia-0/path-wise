const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
const TOKEN_KEY = "pathwise_token";

export const SESSION_EXPIRED_EVENT = "pathwise:session-expired";
export const SERVER_WAKING_EVENT = "pathwise:server-waking";
export const SERVER_READY_EVENT = "pathwise:server-ready";

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

function extractMessage(data, status) {
  if (status === 429) {
    return "Too many attempts. Please wait a few minutes before trying again.";
  }
  const detail = data?.detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => item?.msg).filter(Boolean);
    if (messages.length > 0) {
      return messages.join("; ");
    }
  }
  return `Request failed with status ${status}.`;
}

let activeSlowRequests = 0;

export async function apiRequest(path, { method = "GET", body, auth = true } = {}) {
  if (!API_BASE_URL) {
    throw new ApiError(
      "VITE_API_BASE_URL is not set. Check frontend/.env.local and restart npm run dev.",
      0,
      null
    );
  }

  const headers = { Accept: "application/json" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (auth) {
    const token = getToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  }

  let wakingTimer = null;
  let isSlow = false;

  wakingTimer = setTimeout(() => {
    isSlow = true;
    activeSlowRequests++;
    window.dispatchEvent(new Event(SERVER_WAKING_EVENT));
  }, 2500);

  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(
      "Cannot reach the Path-Wise server. Check that the backend is running.",
      0,
      null
    );
  } finally {
    clearTimeout(wakingTimer);
    if (isSlow) {
      activeSlowRequests = Math.max(0, activeSlowRequests - 1);
      if (activeSlowRequests === 0) {
        window.dispatchEvent(new Event(SERVER_READY_EVENT));
      }
    }
  }

  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    if (response.status === 401 && auth) {
      clearToken();
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
    throw new ApiError(extractMessage(data, response.status), response.status, data?.detail ?? null);
  }

  return data;
}

export const api = {
  get: (path, options) => apiRequest(path, { ...options, method: "GET" }),
  post: (path, body, options) => apiRequest(path, { ...options, method: "POST", body }),
};