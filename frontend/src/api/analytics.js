import api from "./axios";

export function getVendorAnalytics() {
  return api.get("/analytics/vendor");
}

export function getAdminAnalytics() {
  return api.get("/analytics/admin");
}
