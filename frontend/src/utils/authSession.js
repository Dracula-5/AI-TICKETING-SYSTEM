const AUTH_KEYS = ["token", "user_id", "name", "email", "role", "tenant_id"];

export function getAuthItem(key) {
  return sessionStorage.getItem(key) ?? localStorage.getItem(key);
}

export function setAuthSession(data) {
  Object.entries(data).forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    sessionStorage.setItem(key, String(value));
  });
}

export function clearAuthSession() {
  AUTH_KEYS.forEach((key) => {
    sessionStorage.removeItem(key);
    localStorage.removeItem(key);
  });
}
