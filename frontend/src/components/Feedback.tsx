import StarOutlined from "@mui/icons-material/StarOutlined";
import StarBorderOutlined from "@mui/icons-material/StarBorderOutlined";
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Stack, TextField, Typography } from "@mui/material";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useLocation } from "react-router";

import { errorMessage } from "../api/client";
import { feedbackApi } from "../api/endpoints";
import { useToast } from "./Toast";

const LABELS = ["", "Very poor", "Poor", "OK", "Good", "Excellent"];

export function StarRating({ value, onChange, disabled }: { value: number; onChange: (v: number) => void; disabled?: boolean }) {
  return (
    <Stack direction="row" role="radiogroup" aria-label="Rating from 1 to 5">
      {[1, 2, 3, 4, 5].map((n) => (
        <IconButton
          key={n}
          role="radio"
          aria-checked={value === n}
          aria-label={`${n} — ${LABELS[n]}`}
          disabled={disabled}
          onClick={() => onChange(n)}
          size="small"
          sx={{ color: n <= value ? "warning.main" : "text.disabled" }}
        >
          {n <= value ? <StarOutlined /> : <StarBorderOutlined />}
        </IconButton>
      ))}
    </Stack>
  );
}

/** "How did we do?" for the requester once their ticket is resolved. */
export function CsatPrompt({ ticketId }: { ticketId: number }) {
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [done, setDone] = useState(false);
  const send = useMutation({ mutationFn: () => feedbackApi.csat(ticketId, rating, comment || undefined), onSuccess: () => setDone(true) });
  if (done) return <Typography variant="body2" sx={{ mt: 1 }}>Thanks — your rating helps the team improve.</Typography>;
  return (
    <Box sx={{ mt: 1.5 }}>
      <Typography variant="subtitle2">How did we do?</Typography>
      <StarRating value={rating} onChange={setRating} disabled={send.isPending} />
      {rating > 0 && (
        <Stack spacing={1} sx={{ mt: 1 }}>
          <TextField size="small" label="Anything to add? (optional)" value={comment} onChange={(e) => setComment(e.target.value)}
            multiline minRows={2} sx={{ bgcolor: "background.paper" }} />
          {send.isError && <Alert severity="error">{errorMessage(send.error)}</Alert>}
          <Button variant="outlined" size="small" sx={{ alignSelf: "flex-start" }} disabled={send.isPending} onClick={() => send.mutate()}>
            Send rating
          </Button>
        </Stack>
      )}
    </Box>
  );
}

/** Free-form product feedback from anywhere in the app. */
export function FeedbackDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const location = useLocation();
  const [comment, setComment] = useState("");
  const send = useMutation({
    mutationFn: () => feedbackApi.product(comment.trim(), location.pathname),
    onSuccess: () => {
      toast("Thanks for the feedback");
      setComment("");
      onClose();
    },
  });
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Send feedback</DialogTitle>
      <DialogContent>
        {send.isError && <Alert severity="error" sx={{ mb: 2 }}>{errorMessage(send.error)}</Alert>}
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          What works, what gets in your way, what is missing. Your organization's admins and the NexaDesk team read this.
        </Typography>
        <TextField autoFocus fullWidth multiline minRows={4} label="Your feedback" value={comment} onChange={(e) => setComment(e.target.value)} />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={comment.trim().length < 3 || send.isPending} onClick={() => send.mutate()}>Send</Button>
      </DialogActions>
    </Dialog>
  );
}
