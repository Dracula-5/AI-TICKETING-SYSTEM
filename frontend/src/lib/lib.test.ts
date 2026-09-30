import { AxiosError, AxiosHeaders } from "axios";

import { errorMessage } from "../api/client";
import type { Comment, StatusHistoryEntry } from "../api/types";
import { buildTimeline } from "../pages/tickets/TicketTimeline";
import { passwordProblem } from "../pages/public/PasswordField";
import { formatBytes, formatDue, formatMinutes } from "./format";

describe("formatMinutes", () => {
  it.each([
    [0.2, "<1m"],
    [5, "5m"],
    [60, "1h"],
    [95, "1h 35m"],
    [1440, "1d"],
    [1500, "1d 1h"],
  ])("%i -> %s", (input, expected) => {
    expect(formatMinutes(input)).toBe(expected);
  });
});

describe("formatDue", () => {
  const now = new Date("2026-09-30T10:00:00Z");
  it("describes future and overdue deadlines", () => {
    expect(formatDue("2026-09-30T12:30:00Z", now)).toBe("in 2h 30m");
    expect(formatDue("2026-09-30T09:45:00Z", now)).toBe("15m overdue");
    expect(formatDue(null, now)).toBe("—");
  });
});

it("formats bytes", () => {
  expect(formatBytes(512)).toBe("512 B");
  expect(formatBytes(2048)).toBe("2.0 KB");
  expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
});

describe("passwordProblem mirrors the backend policy", () => {
  it.each([
    ["short1A", "At least 10 characters"],
    ["alllowercase1", "Mix upper- and lower-case letters and include a digit"],
    ["NoDigitsHere", "Mix upper- and lower-case letters and include a digit"],
  ])("rejects %s", (pw, message) => expect(passwordProblem(pw)).toBe(message));

  it("accepts a strong password", () => expect(passwordProblem("Correct-Horse-9")).toBeNull());
});

describe("buildTimeline", () => {
  it("interleaves comments and status changes by time", () => {
    const history = [
      { id: 1, from_status: null, to_status: "submitted", created_at: "2026-09-30T10:00:00Z" },
      { id: 2, from_status: "submitted", to_status: "triaged", created_at: "2026-09-30T10:00:01Z" },
      { id: 3, from_status: "triaged", to_status: "resolved", created_at: "2026-09-30T12:00:00Z" },
    ] as StatusHistoryEntry[];
    const comments = [{ id: 9, created_at: "2026-09-30T11:00:00Z" }] as Comment[];
    const kinds = buildTimeline(comments, history).map((i) => (i.kind === "comment" ? `c${i.comment.id}` : `s${i.entry.id}`));
    expect(kinds).toEqual(["s1", "s2", "c9", "s3"]);
  });
});

describe("errorMessage", () => {
  const err = (status: number, data: unknown) =>
    new AxiosError("x", "ERR", undefined, undefined, {
      status, data, statusText: "", headers: {}, config: { headers: new AxiosHeaders() },
    });

  it("uses FastAPI's string detail", () => {
    expect(errorMessage(err(409, { detail: "An account with this email already exists" }))).toBe(
      "An account with this email already exists",
    );
  });

  it("flattens validation errors to the first field", () => {
    const detail = [{ loc: ["body", "password"], msg: "Value error, Password must be at least 10 characters" }];
    expect(errorMessage(err(422, { detail }))).toBe("password: Password must be at least 10 characters");
  });

  it("explains rate limiting and network failures", () => {
    expect(errorMessage(err(429, {}))).toMatch(/Too many attempts/);
    expect(errorMessage(new AxiosError("Network Error"))).toMatch(/Can't reach the server/);
  });
});
