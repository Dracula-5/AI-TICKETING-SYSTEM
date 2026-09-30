import AutoAwesomeOutlined from "@mui/icons-material/AutoAwesomeOutlined";
import PersonOutline from "@mui/icons-material/PersonOutline";
import RuleOutlined from "@mui/icons-material/RuleOutlined";
import { Chip, Tooltip, type ChipProps } from "@mui/material";

import type { Priority, SlaState, TicketStatus } from "../api/types";
import { formatDue } from "../lib/format";
import { DECISION_SOURCE, PRIORITY, SLA, STATUS } from "../lib/labels";

type Size = ChipProps["size"];

export function StatusChip({ status, size = "small" }: { status: TicketStatus; size?: Size }) {
  const s = STATUS[status];
  return <Chip size={size} label={s.label} color={s.tone} variant={s.tone === "default" ? "outlined" : "filled"} />;
}

export function PriorityChip({ priority, size = "small" }: { priority: Priority; size?: Size }) {
  const p = PRIORITY[priority];
  return <Chip size={size} label={p.label} color={p.tone} variant="outlined" />;
}

export function SlaChip({ sla, size = "small" }: { sla: SlaState; size?: Size }) {
  const meta = SLA[sla.state];
  let detail = "";
  if (sla.state === "paused") detail = "Clock paused while waiting on the requester";
  else if (sla.resolution_due && sla.state !== "met" && sla.state !== "none")
    detail = `Resolution due ${formatDue(sla.resolution_due)}`;
  return (
    <Tooltip title={detail} disableHoverListener={!detail}>
      <Chip size={size} label={meta.label} color={meta.tone} variant={sla.state === "breached" ? "filled" : "outlined"} />
    </Tooltip>
  );
}

const SOURCE_ICON = {
  rules: <RuleOutlined fontSize="small" />,
  manual: <PersonOutline fontSize="small" />,
  ai: <AutoAwesomeOutlined fontSize="small" />,
};

/** Who made a decision: system rule vs human vs AI — always visually distinct. */
export function DecisionSourceChip({ source, size = "small" }: { source: "rules" | "manual" | "ai" | null; size?: Size }) {
  if (!source) return null;
  const meta = DECISION_SOURCE[source];
  return (
    <Tooltip title={meta.description}>
      <Chip
        size={size}
        icon={SOURCE_ICON[source]}
        label={meta.label}
        variant="outlined"
        color={source === "ai" ? "secondary" : "default"}
        sx={source === "rules" ? { borderStyle: "dashed" } : undefined}
      />
    </Tooltip>
  );
}
