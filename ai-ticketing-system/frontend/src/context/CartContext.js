import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { getAuthItem } from "../utils/authSession";

// Default value doubles as the fallback for anything rendered outside the
// provider (e.g. component tests that mount a page directly) -- cart-aware
// components just see an empty cart instead of crashing.
const CartContext = createContext({
  items: [],
  totalCount: 0,
  totalPrice: 0,
  addItem: () => {},
  removeItem: () => {},
  updateQuantity: () => {},
  clearCart: () => {},
});

function storageKey() {
  return `cart_${getAuthItem("user_id") || "guest"}`;
}

function loadCart() {
  try {
    const raw = localStorage.getItem(storageKey());
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function CartProvider({ children }) {
  const [items, setItems] = useState(loadCart);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey(), JSON.stringify(items));
    } catch {
      // storage full/unavailable -- cart just won't persist across reloads
    }
  }, [items]);

  const addItem = useCallback((product, quantity = 1) => {
    setItems((prev) => {
      const existing = prev.find((i) => i.productId === product.id);
      const maxStock = product.stock_quantity;
      if (existing) {
        const nextQty = Math.min(existing.quantity + quantity, maxStock);
        return prev.map((i) => (i.productId === product.id ? { ...i, quantity: nextQty } : i));
      }
      return [...prev, {
        productId: product.id,
        title: product.title,
        price: product.price,
        currency: product.currency,
        quantity: Math.min(quantity, maxStock),
        vendorId: product.vendor_id,
        vendorShopName: product.vendor?.shop_name || "",
        image: product.images?.[0]?.url || null,
        maxStock,
      }];
    });
  }, []);

  const removeItem = useCallback((productId) => {
    setItems((prev) => prev.filter((i) => i.productId !== productId));
  }, []);

  const updateQuantity = useCallback((productId, quantity) => {
    setItems((prev) => prev.map((i) => {
      if (i.productId !== productId) return i;
      const clamped = Math.max(1, Math.min(quantity, i.maxStock));
      return { ...i, quantity: clamped };
    }));
  }, []);

  const clearCart = useCallback(() => setItems([]), []);

  const totalCount = useMemo(() => items.reduce((sum, i) => sum + i.quantity, 0), [items]);
  const totalPrice = useMemo(() => items.reduce((sum, i) => sum + i.price * i.quantity, 0), [items]);

  const value = useMemo(
    () => ({ items, totalCount, totalPrice, addItem, removeItem, updateQuantity, clearCart }),
    [items, totalCount, totalPrice, addItem, removeItem, updateQuantity, clearCart]
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart() {
  return useContext(CartContext);
}
