import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// The live-notification socket is exercised end-to-end (Playwright), not in jsdom.
vi.stubGlobal("WebSocket", undefined);
