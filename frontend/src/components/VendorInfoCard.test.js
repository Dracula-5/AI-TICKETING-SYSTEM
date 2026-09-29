import { render, screen } from "@testing-library/react";
import VendorInfoCard from "./VendorInfoCard";

describe("VendorInfoCard", () => {
  test("renders nothing when no vendor is provided", () => {
    const { container } = render(<VendorInfoCard vendor={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  test("renders shop details", () => {
    render(
      <VendorInfoCard
        vendor={{
          shop_name: "Test Shop",
          phone_number: "+91-9876543210",
          shop_address: "123 Market Street",
          rating_avg: 4.2,
          is_verified: true,
          description: "A great shop",
        }}
      />
    );

    expect(screen.getByText("Test Shop")).toBeInTheDocument();
    expect(screen.getByText("+91-9876543210")).toBeInTheDocument();
    expect(screen.getByText("123 Market Street")).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.getByText("A great shop")).toBeInTheDocument();
  });

  test("hides the verified chip when the vendor is not verified", () => {
    render(
      <VendorInfoCard
        vendor={{
          shop_name: "Unverified Shop",
          phone_number: "111",
          shop_address: "Nowhere",
          rating_avg: 0,
          is_verified: false,
        }}
      />
    );

    expect(screen.queryByText("Verified")).not.toBeInTheDocument();
  });
});
