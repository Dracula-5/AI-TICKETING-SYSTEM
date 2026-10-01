import { act, render, screen } from "@testing-library/react";

import { notificationSocketUrl } from "../api/client";
import { ServerWakeBanner } from "./ServerWakeBanner";

describe("notificationSocketUrl", () => {
  const page = { protocol: "https:", host: "demo.example.com" } as Location;

  it("uses the page's host when SPA and API share an origin", () => {
    expect(notificationSocketUrl("", page)).toBe("wss://demo.example.com/api/v1/notifications/ws");
  });

  it("connects straight to a separate API origin (static host without WebSocket proxying)", () => {
    expect(notificationSocketUrl("https://api.example.com", page)).toBe(
      "wss://api.example.com/api/v1/notifications/ws",
    );
    expect(notificationSocketUrl("http://localhost:8000", page)).toBe("ws://localhost:8000/api/v1/notifications/ws");
  });
});

describe("ServerWakeBanner", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("renders nothing and pings nothing without a separate API origin", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(<ServerWakeBanner apiOrigin="" />);
    expect(container).toBeEmptyDOMElement();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("explains a slow start and disappears once the API answers", async () => {
    vi.useFakeTimers();
    let answer: () => void = () => {};
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => (answer = () => resolve(new Response()))));
    vi.stubGlobal("fetch", fetchMock);

    render(<ServerWakeBanner apiOrigin="https://api.example.com" showAfterMs={1000} />);
    expect(fetchMock).toHaveBeenCalledWith("https://api.example.com/health", expect.objectContaining({ mode: "no-cors" }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByRole("status")).toHaveTextContent(/starting up/);

    await act(async () => answer());
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("stays hidden when the API is already awake", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response())));
    render(<ServerWakeBanner apiOrigin="https://api.example.com" showAfterMs={1000} />);
    await act(async () => vi.advanceTimersByTime(5000));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
