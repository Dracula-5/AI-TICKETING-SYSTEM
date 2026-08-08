import { Stepper, Step, StepLabel, Alert } from "@mui/material";

const FORWARD_STATUSES = ["pending", "confirmed", "shipped", "completed"];

export default function OrderStatusStepper({ status }) {
  if (status === "cancelled") {
    return <Alert severity="error" sx={{ mt: 1 }}>This order was cancelled</Alert>;
  }

  const activeStep = FORWARD_STATUSES.indexOf(status);

  return (
    <Stepper activeStep={activeStep} alternativeLabel sx={{ mt: 1, mb: 1 }}>
      {FORWARD_STATUSES.map((s) => (
        <Step key={s}>
          <StepLabel>{s.charAt(0).toUpperCase() + s.slice(1)}</StepLabel>
        </Step>
      ))}
    </Stepper>
  );
}
