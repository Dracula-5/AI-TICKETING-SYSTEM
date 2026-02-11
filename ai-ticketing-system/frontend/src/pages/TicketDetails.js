import { useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import {
  Card, CardContent, Chip, Button, TextField, Box, Avatar, Divider, CircularProgress
} from "@mui/material";
import SendIcon from "@mui/icons-material/Send";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import api from "../api/axios";
import "../styles/ticketDetails.css";

export default function TicketDetails() {

  const { id } = useParams();
  const [ticket, setTicket] = useState(null);
  const [comments, setComments] = useState([]);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);

  function load() {
    api.get(`/tickets/${id}`).then(res => {
      setTicket(res.data);
      setLoading(false);
    });
    api.get(`/comments/${id}`).then(res => setComments(res.data || []));
  }

  useEffect(() => { load(); }, [id])

  function addComment() {
    if (!text.trim()) return;
    
    api.post(`/comments/${id}`, {
      content: text
    }).then(() => {
      setText("");
      load();
    });
  }

  if (loading || !ticket) return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />
      <div className="ticket-details-main" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
        <CircularProgress />
      </div>
    </>
  );

  const overdue = ticket.sla_due && new Date(ticket.sla_due) < new Date() && ticket.status !== "closed";

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />

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
                        <Avatar sx={{ background: "#667eea", width: 40, height: 40 }}>
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
                    background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
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
