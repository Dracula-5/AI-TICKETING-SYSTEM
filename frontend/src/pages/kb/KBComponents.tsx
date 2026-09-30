import {
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Link,
  Stack,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import { kbApi } from "../../api/endpoints";
import type { KBHit } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { ErrorState, Loading } from "../../components/states";

export function HitList({ hits, onOpen }: { hits: KBHit[]; onOpen: (documentId: number) => void }) {
  const { can } = useAuth();
  return (
    <Stack component="ul" spacing={1.5} sx={{ listStyle: "none", p: 0, m: 0 }}>
      {hits.map((hit) => (
        <Stack component="li" key={hit.chunk_id} spacing={0.5}>
          <div>
            <Link component="button" variant="body2" onClick={() => onOpen(hit.document_id)} sx={{ fontWeight: 600, textAlign: "left" }}>
              {hit.title}
              {hit.heading && hit.heading !== hit.title ? ` › ${hit.heading}` : ""}
            </Link>
            {can("tickets:work") && hit.visibility === "internal" && (
              <Chip size="small" label="Internal" variant="outlined" sx={{ ml: 1, height: 18, fontSize: 11 }} />
            )}
          </div>
          <Typography variant="body2" color="text.secondary" sx={{ display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
            {hit.snippet}
          </Typography>
        </Stack>
      ))}
    </Stack>
  );
}

export function DocumentDialog({ id, onClose }: { id: number | null; onClose: () => void }) {
  const doc = useQuery({ queryKey: ["kb", "document", id], queryFn: () => kbApi.document(id!), enabled: id !== null });
  return (
    <Dialog open={id !== null} onClose={onClose} fullWidth maxWidth="md" scroll="paper">
      <DialogTitle>{doc.data?.title ?? "Article"}</DialogTitle>
      <DialogContent dividers>
        {doc.isLoading && <Loading />}
        {doc.isError && <ErrorState error={doc.error} />}
        {doc.data && (
          <Typography component="div" variant="body2" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
            {doc.data.text}
          </Typography>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
