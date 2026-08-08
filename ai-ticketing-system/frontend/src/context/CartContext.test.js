import { render, screen, fireEvent } from "@testing-library/react";
import { CartProvider, useCart } from "./CartContext";

const product = {
  id: 1, title: "Widget", price: 100, currency: "INR",
  stock_quantity: 3, vendor_id: 9, vendor: { shop_name: "Acme" }, images: [],
};

function Harness() {
  const { items, totalCount, totalPrice, addItem, removeItem, updateQuantity, clearCart } = useCart();
  return (
    <div>
      <button onClick={() => addItem(product, 1)}>add</button>
      <button onClick={() => addItem(product, 5)}>add-over-stock</button>
      <button onClick={() => removeItem(1)}>remove</button>
      <button onClick={() => updateQuantity(1, 2)}>set-qty-2</button>
      <button onClick={() => updateQuantity(1, 99)}>set-qty-over</button>
      <button onClick={() => clearCart()}>clear</button>
      <div data-testid="count">{totalCount}</div>
      <div data-testid="price">{totalPrice}</div>
      <div data-testid="lines">{items.length}</div>
    </div>
  );
}

function renderHarness() {
  return render(
    <CartProvider>
      <Harness />
    </CartProvider>
  );
}

describe("CartContext", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  test("useCart outside a provider returns safe empty defaults", () => {
    render(<Harness />);
    expect(screen.getByTestId("lines").textContent).toBe("0");
    expect(screen.getByTestId("count").textContent).toBe("0");
  });

  test("addItem adds a new line", () => {
    renderHarness();
    fireEvent.click(screen.getByText("add"));
    expect(screen.getByTestId("lines").textContent).toBe("1");
    expect(screen.getByTestId("count").textContent).toBe("1");
    expect(screen.getByTestId("price").textContent).toBe("100");
  });

  test("addItem merges quantity into the same line instead of duplicating", () => {
    renderHarness();
    fireEvent.click(screen.getByText("add"));
    fireEvent.click(screen.getByText("add"));
    expect(screen.getByTestId("lines").textContent).toBe("1");
    expect(screen.getByTestId("count").textContent).toBe("2");
  });

  test("addItem clamps quantity to stock", () => {
    renderHarness();
    fireEvent.click(screen.getByText("add-over-stock"));
    expect(screen.getByTestId("count").textContent).toBe("3");
  });

  test("updateQuantity clamps to stock and to a minimum of 1", () => {
    renderHarness();
    fireEvent.click(screen.getByText("add"));
    fireEvent.click(screen.getByText("set-qty-over"));
    expect(screen.getByTestId("count").textContent).toBe("3");
  });

  test("removeItem drops the line", () => {
    renderHarness();
    fireEvent.click(screen.getByText("add"));
    fireEvent.click(screen.getByText("remove"));
    expect(screen.getByTestId("lines").textContent).toBe("0");
  });

  test("clearCart empties everything", () => {
    renderHarness();
    fireEvent.click(screen.getByText("add"));
    fireEvent.click(screen.getByText("clear"));
    expect(screen.getByTestId("lines").textContent).toBe("0");
    expect(screen.getByTestId("price").textContent).toBe("0");
  });

  test("cart persists to localStorage under a namespaced key", () => {
    renderHarness();
    fireEvent.click(screen.getByText("add"));
    const stored = localStorage.getItem("cart_guest");
    expect(stored).toBeTruthy();
    expect(JSON.parse(stored)).toHaveLength(1);
  });
});
