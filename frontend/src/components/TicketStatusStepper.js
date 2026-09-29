import { Stepper, Step, StepLabel, Alert } from "@mui/material";

const FORWARD_STATUSES = ["open", "negotiating", "in-progress", "resolved", "closed"];

function label(status) {
  return status.split("-").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join("-");
}

export default function TicketStatusStepper({ status }) {
  if (status === "escalated") {
    return <Alert severity="error" sx={{ mt: 1, mb: 1 }}>SLA breached — this ticket was escalated</Alert>;
  }

  const activeStep = FORWARD_STATUSES.indexOf(status);

  return (
    <Stepper activeStep={activeStep} alternativeLabel sx={{ mt: 1, mb: 1 }}>
      {FORWARD_STATUSES.map((s) => (
        <Step key={s}>
          <StepLabel>{label(s)}</StepLabel>
        </Step>
      ))}
    </Stepper>
  );
}
