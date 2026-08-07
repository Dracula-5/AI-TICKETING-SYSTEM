import api from "./axios";

export function listProducts(params = {}) {
  return api.get("/products/", { params });
}

export function getProduct(productId) {
  return api.get(`/products/${productId}`);
}

export function createProduct(payload) {
  return api.post("/products/", payload);
}

export function updateProduct(productId, payload) {
  return api.put(`/products/${productId}`, payload);
}

export function deleteProduct(productId) {
  return api.delete(`/products/${productId}`);
}

export function listMyProducts() {
  return api.get("/products/vendor/my-products");
}

export function setProductStatus(productId, newStatus) {
  return api.put(`/products/${productId}/status`, null, {
    params: { new_status: newStatus },
  });
}

export function listAllProductsAdmin(params = {}) {
  return api.get("/products/admin/all", { params });
}
