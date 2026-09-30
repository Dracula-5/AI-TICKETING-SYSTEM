import { render, screen } from "@testing-library/react";

import type { SlaState } from "../api/types";
import { DecisionSourceChip, PriorityChip, SlaChip, StatusChip } from "./chips";
import { EmptyState } from "./states";

const sla = (state: SlaState["state"]): SlaState => ({
  first_response_due: null,
  first_responded_at: null,
  first_response_breached: false,
  resolution_due: "2026-10-01T10:00:00Z",
  resolution_breached: state === "breached",
  paused: state === "paused",
  state,
});

describe("status chips", () => {
  it("label statuses and priorities in plain language", () => {
    render(
      <>
        <StatusChip status="waiting_for_customer" />
        <PriorityChip priority="critical" />
        <SlaChip sla={sla("at_risk")} />
      </>,
    );
    expect(screen.getByText("Waiting on requester")).toBeInTheDocument();
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.getByText("At risk")).toBeInTheDocument();
  });
});

describe("DecisionSourceChip", () => {
  it("keeps system rules, human decisions and AI visibly distinct", () => {
    const { rerender } = render(<DecisionSourceChip source="rules" />);
    expect(screen.getByText("System rule")).toBeInTheDocument();
    rerender(<DecisionSourceChip source="manual" />);
    expect(screen.getByText("Human decision")).toBeInTheDocument();
    rerender(<DecisionSourceChip source="ai" />);
    expect(screen.getByText("AI recommendation")).toBeInTheDocument();
  });

  it("renders nothing without a source", () => {
    const { container } = render(<DecisionSourceChip source={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});

it("EmptyState shows title, body and action", () => {
  render(<EmptyState title="Nothing here" body="No tickets yet" action={<button>Create</button>} />);
  expect(screen.getByRole("heading", { name: "Nothing here" })).toBeInTheDocument();
  expect(screen.getByText("No tickets yet")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Create" })).toBeInTheDocument();
});
