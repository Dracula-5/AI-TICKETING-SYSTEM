import { useParams } from "react-router-dom";
import { useEffect, useState, useCallback } from "react";
import {
  Card, CardContent, Chip, Button, TextField, Box, Avatar, Divider, CircularProgress, Alert
} from "@mui/material";
import SendIcon from "@mui/icons-material/Send";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import api from "../api/axios";
import { getAuthItem } from "../utils/authSession";
import "../styles/ticketDetails.css";

export default function TicketDetails() {

  const { id } = useParams();
  const [ticket, setTicket] = useState(null);
  const [comments, setComments] = useState([]);
  const [text, setText] = useState("");
  const [offerAmount, setOfferAmount] = useState("");
  const [offerNote, setOfferNote] = useState("");
  const [bargains, setBargains] = useState([]);
  const [selectedOfferId, setSelectedOfferId] = useState(null);
  const [bargainLoading, setBargainLoading] = useState(false);
  const [bargainError, setBargainError] = useState("");
  const [bargainSuccess, setBargainSuccess] = useState("");
  const [lastSyncAt, setLastSyncAt] = useState(null);
  const [loading, setLoading] = useState(true);
  const role = getAuthItem("role");

  const load = useCallback(() => {
    api.get(`/tickets/${id}`).then(res => {
      setTicket(res.data);
      setLoading(false);
      setLastSyncAt(new Date());
    });
    api.get(`/comments/${id}`).then(res => setComments(res.data || []));
    api.get(`/tickets/${id}/bargaining`).then(res => {
      setBargains(res.data || []);
      setLastSyncAt(new Date());
    });
  }, [id]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 1500);
    return () => clearInterval(interval);
  }, [load]);

  function addComment() {
    if (!text.trim()) return;
    
    api.post(`/comments/${id}`, {
      content: text
    }).then(() => {
      setText("");
      load();
    });
  }

  const latestOffer = [...bargains]
    .reverse()
    .find((x) => x.action === "offer" || x.action === "counter");
  const selectedOffer = bargains.find((x) => x.id === selectedOfferId);
  const isSelectedLatestOffer = Boolean(selectedOffer && latestOffer && selectedOffer.id === latestOffer.id);

  const canUseBargainControls = role === "customer" || role === "provider" || role === "service_provider";
  const currentUserId = Number(getAuthItem("user_id"));
  const currentSide = role === "customer" ? "customer" : (role === "provider" || role === "service_provider" ? "provider" : role);
  const canRespondToSelected = Boolean(
    selectedOffer
    && isSelectedLatestOffer
    && ticket?.pricing_status !== "finalized"
    && selectedOffer.sender_role !== currentSide
  );

  const selectedOfferHint = selectedOffer
    ? (
      !isSelectedLatestOffer
        ? "Selected offer is not the latest active offer. Select the latest row to accept/reject."
        : selectedOffer.sender_role === currentSide
          ? `Selected offer was posted by ${selectedOffer.sender_role}. Waiting for the other side to accept/reject.`
          : `Selected offer was posted by ${selectedOffer.sender_role}. You can accept or reject it.`
    )
    : "Select an offer row (offer/counter) to accept or reject.";

  async function placeOffer() {
    if (!offerAmount || Number(offerAmount) <= 0) return;
    setBargainLoading(true);
    setBargainError("");
    setBargainSuccess("");
    try {
      const res = await api.post(`/tickets/${id}/bargaining/offer`, {
        amount: Number(offerAmount),
        message: offerNote || null
      });
      setOfferAmount("");
      setOfferNote("");
      setBargainSuccess(res.data?.message || "Budget/offer submitted");
      load();
    } catch (err) {
      setBargainError(err.response?.data?.detail || "Failed to send offer");
      load();
    } finally {
      setBargainLoading(false);
    }
  }

  async function acceptOffer() {
    setBargainLoading(true);
    setBargainError("");
    setBargainSuccess("");
    try {
      const res = await api.post(`/tickets/${id}/bargaining/accept`, {
        negotiation_id: selectedOffer?.id,
        message: "Accepted. Finalized."
      });
      setBargainSuccess(res.data?.message || `Deal finalized at Rs ${res.data?.final_price ?? selectedOffer?.amount}`);
      setSelectedOfferId(null);
      load();
    } catch (err) {
      setBargainError(err.response?.data?.detail || "Failed to accept offer");
      load();
    } finally {
      setBargainLoading(false);
    }
  }

  async function rejectOffer() {
    setBargainLoading(true);
    setBargainError("");
    setBargainSuccess("");
    try {
      const res = await api.post(`/tickets/${id}/bargaining/reject`, {
        negotiation_id: selectedOffer?.id,
        message: "Rejected, please counter."
      });
      setBargainSuccess(res.data?.message || "Offer rejected. Send your budget/counter.");
      setSelectedOfferId(null);
      load();
    } catch (err) {
      setBargainError(err.response?.data?.detail || "Failed to reject offer");
      load();
    } finally {
      setBargainLoading(false);
    }
  }

  if (loading || !ticket) return (
    <>
      <Navbar />
      <Sidebar role={getAuthItem("role")} />
      <div className="ticket-details-main" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
        <CircularProgress />
      </div>
    </>
  );

  const overdue = ticket.sla_due && new Date(ticket.sla_due) < new Date() && ticket.status !== "closed";

  return (
    <>
      <Navbar />
      <Sidebar role={getAuthItem("role")} />

      <div className="ticket-details-main">
        <div className="ticket-header">
          <h1>Ticket #{ticket.id}</h1>
          <p>{ticket.title}</p>
        </div>

        <div className="ticket-content">
          {/* Main Ticket Card */}
          <Card className="ticket-main-card">
            <CardContent>
              <h3>{ticket.title}</h3>
              <p className="ticket-description">{ticket.description}</p>

              <Divider sx={{ my: 2 }} />

              {/* Status Chips */}
              <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", mb: 3 }}>
                <Chip 
                  label={ticket.status} 
                  color={ticket.status === "closed" ? "default" : "primary"}
                  sx={{ fontWeight: 600 }}
                />
                <Chip
                  label={ticket.priority}
                  color={
                    ticket.priority === "high"
                      ? "error"
                      : ticket.priority === "medium"
                      ? "warning"
                      : "success"
                  }
                  sx={{ fontWeight: 600 }}
                />
                {ticket.category && <Chip label={ticket.category} variant="outlined" />}
              </Box>

              {/* Details Grid */}
              <div className="ticket-details-grid">
                <div className="detail-item">
                  <label>SLA Due Date</label>
                  <p style={{ color: overdue ? "#e53935" : "#4caf50", fontWeight: 600 }}>
                    {ticket.sla_due ? new Date(ticket.sla_due).toLocaleDateString() : "N/A"}
                  </p>
                </div>
                <div className="detail-item">
                  <label>Created</label>
                  <p>{ticket.created_at ? new Date(ticket.created_at).toLocaleDateString() : "N/A"}</p>
                </div>
                <div className="detail-item">
                  <label>Updated</label>
                  <p>{ticket.updated_at ? new Date(ticket.updated_at).toLocaleDateString() : "N/A"}</p>
                </div>
                <div className="detail-item">
                  <label>Bargaining Status</label>
                  <p style={{ fontWeight: 600, color: ticket.pricing_status === "finalized" ? "#2e7d32" : "#5b21b6" }}>
                    {ticket.pricing_status || "pending"}
                  </p>
                </div>
                <div className="detail-item">
                  <label>Finalized Price</label>
                  <p style={{ fontWeight: 600 }}>
                    {ticket.final_price != null ? `Rs ${ticket.final_price}` : "Not finalized"}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="ticket-main-card">
            <CardContent>
              <h3 style={{ marginTop: 0 }}>Live Bargaining</h3>
              <p style={{ marginTop: 0, color: "#64748b" }}>
                Provider and customer can negotiate service cost here. Admin can monitor this timeline.
              </p>
              <p style={{ marginTop: -6, marginBottom: 12, color: "#94a3b8", fontSize: 12 }}>
                Live sync active (every ~1.5s){lastSyncAt ? ` • Last update: ${lastSyncAt.toLocaleTimeString()}` : ""}
              </p>

              {bargainError && <Alert severity="error" sx={{ mb: 2 }}>{bargainError}</Alert>}
              {bargainSuccess && <Alert severity="success" sx={{ mb: 2 }}>{bargainSuccess}</Alert>}
              {ticket.pricing_status === "finalized" && ticket.final_price != null && (
                <Alert severity="success" sx={{ mb: 2 }}>
                  Deal finalized at Rs {ticket.final_price}
                </Alert>
              )}

              <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", mb: 2 }}>
                <Chip label={`Pricing: ${ticket.pricing_status || "pending"}`} color={ticket.pricing_status === "finalized" ? "success" : "info"} />
                {latestOffer && (
                  <Chip
                    label={`Latest: Rs ${latestOffer.amount} by ${latestOffer.sender_role}`}
                    variant="outlined"
                  />
                )}
                {selectedOffer && (
                  <Chip
                    label={`Selected: Rs ${selectedOffer.amount} by ${selectedOffer.sender_role}`}
                    color="warning"
                    variant="outlined"
                  />
                )}
              </Box>

              <Alert severity={canRespondToSelected ? "info" : "warning"} sx={{ mb: 2 }}>
                {selectedOfferHint}
              </Alert>

              {canUseBargainControls && ticket.pricing_status !== "finalized" && (
                <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "160px 1fr auto auto auto" }, gap: 1.2, mb: 2 }}>
                  <TextField
                    label="Your Budget / Offer"
                    type="number"
                    value={offerAmount}
                    onChange={(e) => setOfferAmount(e.target.value)}
                    size="small"
                  />
                  <TextField
                    label="Negotiation Note"
                    value={offerNote}
                    onChange={(e) => setOfferNote(e.target.value)}
                    size="small"
                  />
                  <Button disabled={bargainLoading} variant="contained" onClick={placeOffer}>Offer/Counter</Button>
                  <Button disabled={bargainLoading || !canRespondToSelected} variant="outlined" color="success" onClick={acceptOffer}>Accept</Button>
                  <Button disabled={bargainLoading || !canRespondToSelected} variant="outlined" color="error" onClick={rejectOffer}>Reject</Button>
                </Box>
              )}

              <div className="bargain-list">
                {bargains.length === 0 ? (
                  <p style={{ color: "#94a3b8", margin: 0 }}>No bargaining activity yet.</p>
                ) : (
                  bargains.map((b) => {
                    const isOfferRow = b.action === "offer" || b.action === "counter";
                    const selectable = isOfferRow;
                    const isSelected = selectedOfferId === b.id;
                    const who = b.sender_role === "customer" ? "Customer" : "Provider";
                    const you =
                      (currentUserId && Number(b.sender_user_id) === currentUserId)
                      || b.sender_role === currentSide;
                    return (
                    <div
                      key={b.id}
                      className={`bargain-item${selectable ? " selectable" : ""}${isSelected ? " selected" : ""}`}
                      onClick={() => {
                        if (!selectable) return;
                        setSelectedOfferId(b.id);
                      }}
                    >
                      <div>
                        <strong>Posted by {who}</strong> {you ? "(You)" : ""} - {b.action} <strong>Rs {b.amount}</strong>
                        {b.is_final ? " (finalized)" : ""}
                      </div>
                      <small>{new Date(b.created_at).toLocaleString()}</small>
                      {b.message && <p>{b.message}</p>}
                    </div>
                  )})
                )}
              </div>
            </CardContent>
          </Card>

          {/* Comments Section */}
          <div className="comments-section">
            <h3>Comments ({comments.length})</h3>

            <div className="comments-list">
              {comments.length > 0 ? (
                comments.map((c) => (
                  <Card key={c.id} className="comment-card">
                    <CardContent>
                      <Box sx={{ display: "flex", gap: 2, alignItems: "flex-start" }}>
                        <Avatar sx={{ background: "var(--accent)", width: 40, height: 40 }}>
                          {c.user_name?.[0] || "U"}
                        </Avatar>
                        <div style={{ flex: 1 }}>
                          <p style={{ margin: 0, fontWeight: 600, color: "#333" }}>
                            {c.user_name || "Anonymous"}
                          </p>
                          <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "#999" }}>
                            {new Date(c.created_at).toLocaleString()}
                          </p>
                          <p style={{ margin: "8px 0 0 0", color: "#555", lineHeight: 1.6 }}>
                            {c.content}
                          </p>
                        </div>
                      </Box>
                    </CardContent>
                  </Card>
                ))
              ) : (
                <p style={{ textAlign: "center", color: "#999", py: 3 }}>No comments yet</p>
              )}
            </div>

            {/* Add Comment */}
            <Card className="add-comment-card">
              <CardContent>
                <p style={{ margin: "0 0 12px 0", fontWeight: 600, color: "#333" }}>Add a Comment</p>
                <TextField
                  fullWidth
                  multiline
                  rows={3}
                  label="Your comment"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Share your thoughts or updates..."
                  variant="outlined"
                  sx={{ mb: 2 }}
                />

                <Button
                  variant="contained"
                  onClick={addComment}
                  endIcon={<SendIcon />}
                  sx={{
                    background: "linear-gradient(135deg, #2b3a55 0%, #3f4c6b 100%)",
                    textTransform: "none",
                    fontWeight: 600
                  }}
                >
                  Post Comment
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}
