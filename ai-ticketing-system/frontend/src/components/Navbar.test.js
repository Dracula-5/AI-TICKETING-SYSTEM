import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Navbar from "./Navbar";
import { useNotifications } from "../context/NotificationContext";

jest.mock("../context/NotificationContext");

const mockNotifications = [
  { id: 1, type: "negotiation_started", title: "New price negotiation", message: "Offered INR 800", link: "/negotiation/1", is_read: false, created_at: new Date().toISOString() },
  { id: 2, type: "order_placed", title: "New order received", message: "Ordered 2 x Widget", link: "/vendor/dashboard", is_read: true, created_at: new Date().toISOString() },
];

function renderNavbar() {
  return render(
    <MemoryRouter>
      <Navbar />
    </MemoryRouter>
  );
}

describe("Navbar notification bell", () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  test("renders the unread count badge", () => {
    useNotifications.mockReturnValue({
      notifications: mockNotifications,
      unreadCount: 1,
      markRead: jest.fn(),
      markAllRead: jest.fn(),
    });

    renderNavbar();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  test("shows an empty state when there are no notifications", () => {
    useNotifications.mockReturnValue({
      notifications: [],
      unreadCount: 0,
      markRead: jest.fn(),
      markAllRead: jest.fn(),
    });

    renderNavbar();
    fireEvent.click(screen.getByLabelText("Notifications"));
    expect(screen.getByText(/No notifications yet/i)).toBeInTheDocument();
  });

  test("opens the dropdown and lists recent notifications", () => {
    useNotifications.mockReturnValue({
      notifications: mockNotifications,
      unreadCount: 1,
      markRead: jest.fn(),
      markAllRead: jest.fn(),
    });

    renderNavbar();
    fireEvent.click(screen.getByLabelText("Notifications"));

    expect(screen.getByText("New price negotiation")).toBeInTheDocument();
    expect(screen.getByText("New order received")).toBeInTheDocument();
  });

  test("clicking an unread notification marks it read", async () => {
    const markRead = jest.fn();
    useNotifications.mockReturnValue({
      notifications: mockNotifications,
      unreadCount: 1,
      markRead,
      markAllRead: jest.fn(),
    });

    renderNavbar();
    fireEvent.click(screen.getByLabelText("Notifications"));
    fireEvent.click(screen.getByText("New price negotiation"));

    await waitFor(() => expect(markRead).toHaveBeenCalledWith(1));
  });

  test("clicking an already-read notification does not call markRead again", async () => {
    const markRead = jest.fn();
    useNotifications.mockReturnValue({
      notifications: mockNotifications,
      unreadCount: 1,
      markRead,
      markAllRead: jest.fn(),
    });

    renderNavbar();
    fireEvent.click(screen.getByLabelText("Notifications"));
    fireEvent.click(screen.getByText("New order received"));

    await waitFor(() => expect(markRead).not.toHaveBeenCalled());
  });

  test("Mark all read button calls markAllRead", () => {
    const markAllRead = jest.fn();
    useNotifications.mockReturnValue({
      notifications: mockNotifications,
      unreadCount: 1,
      markRead: jest.fn(),
      markAllRead,
    });

    renderNavbar();
    fireEvent.click(screen.getByLabelText("Notifications"));
    fireEvent.click(screen.getByText(/Mark all read/i));

    expect(markAllRead).toHaveBeenCalled();
  });
});
