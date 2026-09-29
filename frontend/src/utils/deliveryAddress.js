const KEY = "saved_delivery_address";

export function getSavedAddress() {
  return localStorage.getItem(KEY) || "";
}

export function saveAddress(address) {
  if (address) localStorage.setItem(KEY, address);
}
