import { getAuthItem, setAuthSession, clearAuthSession } from "./authSession";

describe("authSession", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  test("setAuthSession stores values in sessionStorage", () => {
    setAuthSession({ token: "abc123", role: "customer" });
    expect(sessionStorage.getItem("token")).toBe("abc123");
    expect(sessionStorage.getItem("role")).toBe("customer");
  });

  test("setAuthSession skips null/undefined values", () => {
    setAuthSession({ token: "abc", name: undefined, email: null });
    expect(sessionStorage.getItem("token")).toBe("abc");
    expect(sessionStorage.getItem("name")).toBeNull();
    expect(sessionStorage.getItem("email")).toBeNull();
  });

  test("getAuthItem prefers sessionStorage over localStorage", () => {
    sessionStorage.setItem("token", "session-token");
    localStorage.setItem("token", "local-token");
    expect(getAuthItem("token")).toBe("session-token");
  });

  test("getAuthItem falls back to localStorage when sessionStorage is empty", () => {
    localStorage.setItem("token", "local-token");
    expect(getAuthItem("token")).toBe("local-token");
  });

  test("getAuthItem returns null when neither storage has the key", () => {
    expect(getAuthItem("token")).toBeNull();
  });

  test("clearAuthSession removes all known auth keys from both storages", () => {
    setAuthSession({ token: "abc", user_id: "1", name: "A", email: "a@b.com", role: "customer", tenant_id: "1" });
    localStorage.setItem("token", "abc");

    clearAuthSession();

    ["token", "user_id", "name", "email", "role", "tenant_id"].forEach((key) => {
      expect(sessionStorage.getItem(key)).toBeNull();
      expect(localStorage.getItem(key)).toBeNull();
    });
  });
});
