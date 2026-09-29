import api from "./axios";

export function listNotifications() {
  return api.get("/notifications/");
}

export function getUnreadCount() {
  return api.get("/notifications/unread-count");
}

export function markNotificationRead(notificationId) {
  return api.put(`/notifications/${notificationId}/read`);
}

export function markAllNotificationsRead() {
  return api.put("/notifications/read-all");
}

export function getMyCategories() {
  return api.get("/users/me/categories");
}

export function setMyCategories(categories) {
  return api.put("/users/me/categories", { categories });
}
