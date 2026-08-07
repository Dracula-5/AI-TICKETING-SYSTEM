import api from "./axios";

export function registerVendor(payload) {
  return api.post("/vendors/register", payload);
}

export function getCategoryAvailability(tenantId = 1) {
  return api.get("/vendors/categories", { params: { tenant_id: tenantId } });
}

export function getMyVendorProfile() {
  return api.get("/vendors/me");
}

export function updateMyVendorProfile(payload) {
  return api.put("/vendors/me", payload);
}

export function getVendorPublicProfile(vendorId) {
  return api.get(`/vendors/${vendorId}`);
}

export function listVendors(unverifiedOnly = false) {
  return api.get("/vendors/", { params: { unverified_only: unverifiedOnly } });
}

export function verifyVendor(vendorId) {
  return api.put(`/vendors/${vendorId}/verify`);
}
