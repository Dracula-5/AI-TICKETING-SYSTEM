import api from "./axios";

export function createOrder(payload) {
  return api.post("/orders/", payload);
}

export function listMyOrders() {
  return api.get("/orders/my");
}

export function listVendorOrders() {
  return api.get("/orders/vendor/received");
}

export function updateOrderStatus(orderId, newStatus) {
  return api.put(`/orders/${orderId}/status`, null, {
    params: { new_status: newStatus },
  });
}
