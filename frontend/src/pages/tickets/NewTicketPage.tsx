import { Alert, Button, Card, CardContent, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { errorMessage } from "../../api/client";
import { kbApi, orgApi, ticketsApi } from "../../api/endpoints";
import type { Priority } from "../../api/types";
import { PageHeader } from "../../components/states";
import { useToast } from "../../components/Toast";
import { useAuth } from "../../auth/AuthProvider";
import { PRIORITIES, PRIORITY } from "../../lib/labels";
import { DocumentDialog, HitList } from "../kb/KBComponents";

/** Published articles matching what the requester is typing (debounced). */
function SuggestedArticles({ text }: { text: string }) {
  const { can } = useAuth();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  useEffect(() => {
    const id = setTimeout(() => setQuery(text.trim().slice(0, 300)), 600);
    return () => clearTimeout(id);
  }, [text]);
  const results = useQuery({
    queryKey: ["kb", "suggest", query],
    queryFn: () => kbApi.search(query, 3),
    enabled: can("kb:read") && query.length >= 12,
    staleTime: 60_000,
  });
  const hits = (results.data?.hits ?? []).filter((h) => (h.dense_similarity ?? 0) >= 0.45 || h.reranked);
  if (!hits.length) return null;
  return (
    <Alert severity="info" icon={false}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>These articles might solve it right away</Typography>
      <HitList hits={hits} onOpen={setOpen} />
      <DocumentDialog id={open} onClose={() => setOpen(null)} />
    </Alert>
  );
}

export function NewTicketPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const categories = useQuery({ queryKey: ["categories"], queryFn: () => orgApi.categories() });
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [priority, setPriority] = useState<Priority | "">("");
  const [files, setFiles] = useState<File[]>([]);

  const create = useMutation({
    mutationFn: async () => {
      const ticket = await ticketsApi.create({
        title: title.trim(),
        description: description.trim(),
        ...(category ? { category } : {}),
        ...(priority ? { priority } : {}),
      });
      const failed: string[] = [];
      for (const file of files) {
        try {
          await ticketsApi.upload(ticket.id, file);
        } catch (e) {
          failed.push(`${file.name}: ${errorMessage(e)}`);
        }
      }
      return { ticket, failed };
    },
    onSuccess: ({ ticket, failed }) => {
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      if (failed.length) toast(`Ticket created, but some files were rejected — ${failed.join("; ")}`, "warning");
      else toast(`Ticket #${ticket.number} created`);
      navigate(`/tickets/${ticket.id}`);
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  return (
    <>
      <PageHeader title="New ticket" subtitle="Describe the problem or request. The more detail, the faster it gets to the right team." />
      <Card sx={{ maxWidth: 820 }}>
        <CardContent>
          <Stack component="form" spacing={2.5} onSubmit={submit} noValidate>
            {create.isError && <Alert severity="error">{errorMessage(create.error)}</Alert>}
            <TextField
              label="Summary"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              autoFocus
              slotProps={{ htmlInput: { maxLength: 200 } }}
              helperText="One line, e.g. “VPN disconnects every few minutes”"
            />
            <TextField
              label="Details"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
              multiline
              minRows={6}
              slotProps={{ htmlInput: { maxLength: 10000 } }}
              helperText="What happened, when it started, who is affected, any error messages."
            />
            <SuggestedArticles text={`${title}\n${description}`} />
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField select label="Category (optional)" value={category} onChange={(e) => setCategory(e.target.value)} fullWidth
                helperText="Leave empty and it will be categorized automatically.">
                <MenuItem value="">Let NexaDesk decide</MenuItem>
                {categories.data?.map((c) => (
                  <MenuItem key={c.id} value={c.name}>{c.name}</MenuItem>
                ))}
              </TextField>
              <TextField select label="Priority (optional)" value={priority} onChange={(e) => setPriority(e.target.value as Priority)} fullWidth
                helperText="Leave empty to have it assessed from your description.">
                <MenuItem value="">Assess automatically</MenuItem>
                {PRIORITIES.map((p) => (
                  <MenuItem key={p} value={p}>{PRIORITY[p].label}</MenuItem>
                ))}
              </TextField>
            </Stack>
            <Stack spacing={1}>
              <Button variant="outlined" component="label" sx={{ alignSelf: "flex-start" }}>
                Attach files
                <input hidden type="file" multiple onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
              </Button>
              <Typography variant="caption" color="text.secondary">
                {files.length ? files.map((f) => f.name).join(", ") : "Screenshots, PDFs, logs, Office documents — up to 10 MB each."}
              </Typography>
            </Stack>
            <Stack direction="row" spacing={1} sx={{ justifyContent: "flex-end" }}>
              <Button onClick={() => navigate(-1)}>Cancel</Button>
              <Button type="submit" variant="contained" disabled={create.isPending || title.trim().length < 3 || !description.trim()}>
                {create.isPending ? "Submitting…" : "Submit ticket"}
              </Button>
            </Stack>
          </Stack>
        </CardContent>
      </Card>
    </>
  );
}
