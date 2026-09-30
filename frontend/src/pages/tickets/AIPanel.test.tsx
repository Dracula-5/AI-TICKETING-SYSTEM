import { render, screen } from "@testing-library/react";

import type { AIPrediction } from "../../api/types";
import { Confidence, describe as describePrediction } from "./AIPanel";

const pred = (kind: AIPrediction["kind"], value: Record<string, unknown>, confidence: number | null = null): AIPrediction => ({
  id: 1,
  kind,
  source: "ai",
  model: "m",
  model_version: "v",
  value,
  confidence,
  evidence: null,
  latency_ms: 10,
  status: "proposed",
  final_value: null,
  decided_at: null,
  created_at: "2026-09-30T10:00:00Z",
});

describe("AI recommendation text", () => {
  it("describes each recommendation in plain language", () => {
    expect(describePrediction(pred("category", { category: "Network" }))).toBe("Network");
    expect(describePrediction(pred("priority", { priority: "critical" }))).toBe("Critical");
    expect(describePrediction(pred("duplicate", { ticket_id: 4, number: 17 }))).toBe("#17");
    expect(describePrediction(pred("sla_risk", { breach_probability: 0.347, level: "medium" }))).toBe("35% (medium)");
    expect(describePrediction(pred("resolution_time", { hours: 3, low_hours: 1, high_hours: 26 }))).toBe(
      "about 3h (typical 1h–1d 2h)",
    );
  });

  it("shows confidence as a percentage and hides it when there is none", () => {
    const { rerender, container } = render(<Confidence value={0.874} />);
    expect(screen.getByText("87%")).toBeInTheDocument();
    rerender(<Confidence value={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
