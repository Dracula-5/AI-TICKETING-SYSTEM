import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import ProtectedRoute from "./ProtectedRoute";

function renderWithRoute(initialPath) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/" element={<div>Login Page</div>} />
        <Route
          path="/secret"
          element={
            <ProtectedRoute>
              <div>Secret Content</div>
            </ProtectedRoute>
          }
        />
      </Routes>
    </MemoryRouter>
  );
}

describe("ProtectedRoute", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  test("redirects to / when no auth token is present", () => {
    renderWithRoute("/secret");
    expect(screen.getByText("Login Page")).toBeInTheDocument();
    expect(screen.queryByText("Secret Content")).not.toBeInTheDocument();
  });

  test("renders children when an auth token is present", () => {
    sessionStorage.setItem("token", "valid-token");
    renderWithRoute("/secret");
    expect(screen.getByText("Secret Content")).toBeInTheDocument();
  });
});
