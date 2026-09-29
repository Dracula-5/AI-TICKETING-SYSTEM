import api from "./axios";

export function startNegotiation(payload) {
  return api.post("/negotiations/", payload);
}

export function getNegotiation(sessionId) {
  return api.get(`/negotiations/${sessionId}`);
}

export function acceptNegotiation(sessionId) {
  return api.post(`/negotiations/${sessionId}/accept`);
}

export function listVendorInbox() {
  return api.get("/negotiations/vendor/inbox");
}
