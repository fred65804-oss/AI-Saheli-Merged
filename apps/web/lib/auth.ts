import { API_BASE } from "./utils";

const REFRESH_KEY = "ai-saheli-refresh-token";

export type AuthUser = {
  id: string;
  name: string;
  email: string;
  role: string;
  created_at: string;
};

type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number; // access token lifetime, seconds
  user: AuthUser;
};

// Access token lives in memory only (never localStorage) — a page reload
// re-derives it from the refresh token via restoreSession(). The refresh
// token is long-lived and does go to localStorage so a reload doesn't force
// a fresh login.
let accessToken: string | null = null;
let accessTokenExpiresAt = 0; // epoch ms
let refreshPromise: Promise<string | null> | null = null;

function setSession(tokens: TokenPair) {
  accessToken = tokens.access_token;
  accessTokenExpiresAt = Date.now() + tokens.expires_in * 1000;
  if (typeof window !== "undefined") {
    localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  }
}

function clearSession() {
  accessToken = null;
  accessTokenExpiresAt = 0;
  if (typeof window !== "undefined") {
    localStorage.removeItem(REFRESH_KEY);
  }
}

function getStoredRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

async function requestTokenPair(path: string, body: unknown): Promise<TokenPair> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => null);
    throw new Error(detail?.detail || `${path} failed (${r.status})`);
  }
  return r.json();
}

export async function signup(name: string, email: string, password: string): Promise<AuthUser> {
  const tokens = await requestTokenPair("/auth/signup", { name, email, password });
  setSession(tokens);
  return tokens.user;
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const tokens = await requestTokenPair("/auth/login", { email, password });
  setSession(tokens);
  return tokens.user;
}

export async function logout(): Promise<void> {
  const refresh_token = getStoredRefreshToken();
  clearSession();
  if (!refresh_token) return;
  try {
    await fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token }),
    });
  } catch {
    // Best-effort server-side revoke — the client session is already gone.
  }
}

// Dedupes concurrent refresh attempts (e.g. several authFetch calls firing
// on load) behind one in-flight request rather than racing the rotation.
async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;
  const stored = getStoredRefreshToken();
  if (!stored) return null;

  refreshPromise = (async () => {
    try {
      const tokens = await requestTokenPair("/auth/refresh", { refresh_token: stored });
      setSession(tokens);
      return tokens.access_token;
    } catch {
      clearSession();
      return null;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

/** Called once on app load to turn a stored refresh token back into a session. */
export async function restoreSession(): Promise<AuthUser | null> {
  const token = await refreshAccessToken();
  if (!token) return null;
  const r = await fetch(`${API_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) return null;
  return r.json();
}

/** fetch wrapper for endpoints that require auth — attaches the access
 * token, refreshing it first if it's missing/near expiry, and retries once
 * on a 401 in case it was revoked/expired between checks. */
export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const doFetch = (token: string | null) =>
    fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        ...(init.headers || {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });

  let token = accessToken;
  if (!token || Date.now() >= accessTokenExpiresAt - 5000) {
    token = await refreshAccessToken();
  }

  let res = await doFetch(token);
  if (res.status === 401) {
    token = await refreshAccessToken();
    res = await doFetch(token);
  }
  return res;
}
