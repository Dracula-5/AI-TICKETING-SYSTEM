import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Marketplace from "./Marketplace";
import { listProducts } from "../api/products";

jest.mock("../api/products");

const mockProduct = {
  id: 1,
  title: "Bluetooth Speaker",
  price: 1500,
  currency: "INR",
  category: "Electronics",
  stock_quantity: 3,
  images: [],
  vendor: { shop_name: "Sound Shop", is_verified: true, rating_avg: 4.0 },
};

describe("Marketplace", () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  test("renders products returned by the API", async () => {
    listProducts.mockResolvedValue({ data: { items: [mockProduct], total: 1, page: 1, page_size: 12 } });

    render(
      <MemoryRouter>
        <Marketplace />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText("Bluetooth Speaker")).toBeInTheDocument());
    expect(screen.getByText("Sound Shop")).toBeInTheDocument();
  });

  test("shows an empty state when there are no products", async () => {
    listProducts.mockResolvedValue({ data: { items: [], total: 0, page: 1, page_size: 12 } });

    render(
      <MemoryRouter>
        <Marketplace />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText(/No products found/i)).toBeInTheDocument());
  });
});
