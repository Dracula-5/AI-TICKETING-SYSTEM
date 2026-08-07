import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ProductCard from "./ProductCard";

const baseProduct = {
  id: 1,
  title: "Wireless Headphones",
  price: 2999,
  currency: "INR",
  category: "Electronics",
  stock_quantity: 5,
  images: [{ url: "https://example.com/img.png" }],
  vendor: { shop_name: "Test Shop", is_verified: true, rating_avg: 4.5 },
};

function renderCard(product) {
  return render(
    <MemoryRouter>
      <ProductCard product={product} />
    </MemoryRouter>
  );
}

describe("ProductCard", () => {
  test("renders title, price, and vendor name", () => {
    renderCard(baseProduct);
    expect(screen.getByText("Wireless Headphones")).toBeInTheDocument();
    expect(screen.getByText(/2,999/)).toBeInTheDocument();
    expect(screen.getByText("Test Shop")).toBeInTheDocument();
  });

  test("shows in-stock count when stock is available", () => {
    renderCard(baseProduct);
    expect(screen.getByText("5 in stock")).toBeInTheDocument();
  });

  test("shows out of stock when stock is zero", () => {
    renderCard({ ...baseProduct, stock_quantity: 0 });
    expect(screen.getByText("Out of stock")).toBeInTheDocument();
  });

  test("shows a verified badge when the vendor is verified", () => {
    renderCard(baseProduct);
    expect(screen.getByTitle("Verified vendor")).toBeInTheDocument();
  });

  test("hides the verified badge when the vendor is not verified", () => {
    renderCard({ ...baseProduct, vendor: { ...baseProduct.vendor, is_verified: false } });
    expect(screen.queryByTitle("Verified vendor")).not.toBeInTheDocument();
  });

  test("does not render a rating when the vendor has none", () => {
    renderCard({ ...baseProduct, vendor: { shop_name: "No Rating Shop", is_verified: false, rating_avg: 0 } });
    expect(screen.queryByText(/4\.5/)).not.toBeInTheDocument();
  });
});
