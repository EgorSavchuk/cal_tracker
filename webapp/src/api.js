/**
 * API client for the Nutrition Tracker WebApp.
 * Uses Telegram WebApp initData for authentication.
 */

const getInitData = () => window.Telegram?.WebApp?.initData || "";

async function request(path, options = {}) {
  const headers = {
    "X-Telegram-Init-Data": getInitData(),
    "Content-Type": "application/json",
    ...options.headers,
  };

  const resp = await fetch(path, { ...options, headers });
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status}`);
  }
  return resp.json();
}

export async function fetchDays(from, to) {
  const params = new URLSearchParams();
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  const qs = params.toString();
  return request(`/api/days${qs ? "?" + qs : ""}`);
}

export async function fetchDayDetail(date) {
  return request(`/api/days/${date}`);
}

export async function fetchStats() {
  return request("/api/stats");
}

export async function fetchProfile() {
  return request("/api/profile");
}

export async function updateProfile(data) {
  return request("/api/profile", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function fetchTopProducts(limit = 10) {
  return request(`/api/products/top?limit=${limit}`);
}

export async function fetchRecommendations() {
  return request("/api/recommendations");
}
