import SearchOutlined from "@mui/icons-material/SearchOutlined";
import UploadFileOutlined from "@mui/icons-material/UploadFileOutlined";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  InputAdornment,
  Link,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { errorMessage } from "../../api/client";
import { aiApi, kbApi } from "../../api/endpoints";
import type { KBAnswer, KBDocument, KBHit } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { EmptyState, ErrorState, Loading, PageHeader } from "../../components/states";
import { useToast } from "../../components/Toast";
import { formatBytes, formatRelative } from "../../lib/format";
import { DocumentDialog, HitList } from "./KBComponents";

const STATUS_TONE = { processing: "info", ready: "success", failed: "error" } as const;

function AnswerCard({ answer, onOpen }: { answer: KBAnswer; onOpen: (documentId: number) => void }) {
  const [rated, setRated] = useState<boolean | null>(null);
  const feedback = useMutation({ mutationFn: (helpful: boolean) => kbApi.feedback(answer.query_id!, helpful), onSuccess: (_, h) => setRated(h) });
  if (answer.status === "search_only") return null;
  if (answer.status === "no_answer")
    return (
      <Alert severity="info" sx={{ mb: 2 }}>
        The knowledge base doesn't answer this. The closest articles are listed below — or raise a ticket.
      </Alert>
    );
  return (
    <Card sx={{ mb: 2, borderColor: "secondary.main" }} variant="outlined">
      <CardContent>
        <Typography variant="caption" color="text.secondary">
          Generated answer from your knowledge base — check the sources
        </Typography>
        <Typography sx={{ whiteSpace: "pre-wrap", mt: 0.5 }}>{answer.answer}</Typography>
        {answer.supported_ratio !== null && answer.supported_ratio < 1 && (
          <Alert severity="warning" sx={{ mt: 1 }}>
            Part of this answer could not be matched to its sources: “{answer.unsupported_sentences.join(" ")}”
          </Alert>
        )}
        <Stack component="ol" spacing={0.5} sx={{ mt: 1.5, pl: 2.5, mb: 0 }}>
          {answer.citations.map((c) => (
            <Typography component="li" variant="body2" key={c.number} value={c.number}>
              <Link component="button" onClick={() => onOpen(c.document_id)} sx={{ textAlign: "left" }}>
                {c.title}
                {c.heading && c.heading !== c.title ? ` › ${c.heading}` : ""}
              </Link>
            </Typography>
          ))}
        </Stack>
        {answer.query_id && (
          <Stack direction="row" spacing={1} sx={{ mt: 1.5, alignItems: "center" }}>
            {rated === null ? (
              <>
                <Typography variant="caption" color="text.secondary">Did this help?</Typography>
                <Button size="small" onClick={() => feedback.mutate(true)}>Yes</Button>
                <Button size="small" color="inherit" onClick={() => feedback.mutate(false)}>No</Button>
              </>
            ) : (
              <Typography variant="caption" color="text.secondary">Thanks for the feedback.</Typography>
            )}
          </Stack>
        )}
      </CardContent>
    </Card>
  );
}

function SearchPanel({ onOpen }: { onOpen: (documentId: number) => void }) {
  const toast = useToast();
  const caps = useQuery({ queryKey: ["ai", "capabilities"], queryFn: aiApi.capabilities, staleTime: 5 * 60_000 });
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState<KBAnswer | null>(null);
  const [hits, setHits] = useState<KBHit[] | null>(null);
  const ask = useMutation({
    mutationFn: async (text: string) => {
      if (caps.data?.text_generation) return kbApi.answer(text);
      const r = await kbApi.search(text, 8);
      return { query_id: r.query_id, status: "search_only", answer: null, citations: [], supported_ratio: null, unsupported_sentences: [], mode: r.mode, hits: r.hits } as KBAnswer;
    },
    onSuccess: (a) => {
      setAnswer(a);
      setHits(a.hits);
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (q.trim().length >= 2) ask.mutate(q.trim());
  };
  return (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        <Box component="form" onSubmit={submit}>
          <TextField
            fullWidth
            placeholder={caps.data?.text_generation ? "Ask a question, e.g. How do I reset MFA?" : "Search articles, e.g. VPN error 809"}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            slotProps={{
              htmlInput: { "aria-label": "Search the knowledge base" },
              input: {
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton type="submit" aria-label="Search" disabled={ask.isPending}>
                      <SearchOutlined />
                    </IconButton>
                  </InputAdornment>
                ),
              },
            }}
          />
        </Box>
        {ask.isPending && <Loading label={caps.data?.text_generation ? "Looking for an answer…" : "Searching…"} />}
        {!ask.isPending && answer && (
          <Box sx={{ mt: 2 }}>
            <AnswerCard key={answer.query_id ?? 0} answer={answer} onOpen={onOpen} />
            {hits && hits.length > 0 ? (
              <>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>Articles</Typography>
                <HitList hits={hits} onOpen={onOpen} />
              </>
            ) : (
              <Typography color="text.secondary">No matching articles.</Typography>
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );
}

function UploadDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [visibility, setVisibility] = useState<"internal" | "public">("internal");
  const upload = useMutation({
    mutationFn: () => kbApi.upload(file!, visibility),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kb"] });
      toast("Uploaded — indexing in the background");
      setFile(null);
      onClose();
    },
  });
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Add an article</DialogTitle>
      <DialogContent>
        {upload.isError && <Alert severity="error" sx={{ mb: 2 }}>{errorMessage(upload.error)}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Button component="label" variant="outlined" startIcon={<UploadFileOutlined />}>
            {file ? file.name : "Choose a file (.md, .txt, .html, .pdf, .docx)"}
            <input hidden type="file" accept=".md,.markdown,.txt,.html,.htm,.pdf,.docx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </Button>
          <TextField select label="Who can read it" value={visibility} onChange={(e) => setVisibility(e.target.value as "internal" | "public")}
            helperText={visibility === "public" ? "Requesters can find it in the portal" : "Support staff only"}>
            <MenuItem value="internal">Support staff only</MenuItem>
            <MenuItem value="public">Everyone in the organization (portal)</MenuItem>
          </TextField>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={!file || upload.isPending} onClick={() => upload.mutate()}>Upload</Button>
      </DialogActions>
    </Dialog>
  );
}

function DocumentsTable({ docs, onOpen }: { docs: KBDocument[]; onOpen: (id: number) => void }) {
  const { can } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const manage = can("kb:manage");
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["kb"] });
  const update = useMutation({
    mutationFn: ({ id, visibility }: { id: number; visibility: "internal" | "public" }) => kbApi.update(id, { visibility }),
    onSuccess: refresh,
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const remove = useMutation({ mutationFn: kbApi.remove, onSuccess: refresh, onError: (e) => toast(errorMessage(e), "error") });
  const reindex = useMutation({ mutationFn: kbApi.reindex, onSuccess: refresh, onError: (e) => toast(errorMessage(e), "error") });
  if (docs.length === 0)
    return <EmptyState title="No articles yet" body={manage ? "Upload runbooks, how-tos and FAQs so agents and requesters can find answers." : "Nothing has been published yet."} />;
  return (
    <TableContainer>
      <Table size="small" aria-label="Knowledge-base articles">
        <TableHead>
          <TableRow>
            <TableCell>Article</TableCell>
            {manage && <TableCell>Visibility</TableCell>}
            {manage && <TableCell>Status</TableCell>}
            <TableCell align="right">Updated</TableCell>
            {manage && <TableCell align="right">Actions</TableCell>}
          </TableRow>
        </TableHead>
        <TableBody>
          {docs.map((d) => (
            <TableRow key={d.id}>
              <TableCell sx={{ maxWidth: 360 }}>
                <Link component="button" onClick={() => onOpen(d.id)} sx={{ textAlign: "left" }}>{d.title}</Link>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                  {d.filename} · {formatBytes(d.size_bytes)}{d.status === "ready" ? ` · ${d.chunk_count} passages` : ""}
                </Typography>
              </TableCell>
              {manage && (
                <TableCell>
                  <TextField select size="small" value={d.visibility} variant="standard"
                    onChange={(e) => update.mutate({ id: d.id, visibility: e.target.value as "internal" | "public" })}
                    slotProps={{ htmlInput: { "aria-label": `Visibility of ${d.title}` } }}>
                    <MenuItem value="internal">Staff only</MenuItem>
                    <MenuItem value="public">Published</MenuItem>
                  </TextField>
                </TableCell>
              )}
              {manage && (
                <TableCell>
                  <Tooltip title={d.error ?? ""} disableHoverListener={!d.error}>
                    <Chip size="small" label={d.status} color={STATUS_TONE[d.status]} variant="outlined" />
                  </Tooltip>
                </TableCell>
              )}
              <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>{formatRelative(d.updated_at)}</TableCell>
              {manage && (
                <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                  <Button size="small" onClick={() => reindex.mutate(d.id)}>Re-index</Button>
                  <Button size="small" color="error" onClick={() => window.confirm(`Delete “${d.title}”?`) && remove.mutate(d.id)}>
                    Delete
                  </Button>
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

export function KnowledgePage() {
  const { can } = useAuth();
  const [open, setOpen] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const docs = useQuery({
    queryKey: ["kb", "documents"],
    queryFn: kbApi.documents,
    refetchInterval: (q) => (q.state.data?.some((d) => d.status === "processing") ? 3000 : false),
  });
  return (
    <>
      <PageHeader
        title="Knowledge base"
        subtitle={can("tickets:work") ? "Runbooks and how-tos for agents; published articles also appear in the requester portal." : "Find answers before raising a ticket."}
        actions={can("kb:manage") ? <Button variant="contained" startIcon={<UploadFileOutlined />} onClick={() => setUploading(true)}>Add article</Button> : undefined}
      />
      <SearchPanel onOpen={setOpen} />
      <Card>
        <CardContent>
          <Typography variant="h3" sx={{ mb: 1 }}>{can("tickets:work") ? "All articles" : "Published articles"}</Typography>
          {docs.isLoading ? <Loading /> : docs.isError ? <ErrorState error={docs.error} onRetry={() => docs.refetch()} /> : <DocumentsTable docs={docs.data ?? []} onOpen={setOpen} />}
        </CardContent>
      </Card>
      <UploadDialog open={uploading} onClose={() => setUploading(false)} />
      <DocumentDialog id={open} onClose={() => setOpen(null)} />
    </>
  );
}
