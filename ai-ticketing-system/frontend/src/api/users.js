import api from "./axios";

export function updateMyProfile(payload) {
  return api.put("/users/me", payload);
}

export function changeMyPassword(payload) {
  return api.put("/users/me/password", payload);
}
