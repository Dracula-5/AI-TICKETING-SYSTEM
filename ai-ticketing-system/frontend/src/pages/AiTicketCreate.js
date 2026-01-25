import { useState } from "react";
import { Card, CardContent, TextField, Button, Box, Alert, Chip } from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import api from "../api/axios";
import "../styles/aiTicketCreate.css";

export default function AiTicketCreate() {

  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function submit() {
    if (!text.trim()) {
      setError("Please describe your problem");
      return;
    }

    setLoading(true);
    setError("");

    api.post("/tickets/ai-create", text, {
      headers: { "Content-Type": "text/plain" }
    })
      .then(res => {
        setResult(res.data);
        setText("");
      })
      .catch(err => {
        setError("Failed to create ticket. Please try again.");
      })
      .finally(() => setLoading(false));
  }

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />

      <div className="ai-ticket-main">
        <div className="ai-ticket-header">
          <h1>AI-Powered Ticket Creator</h1>
          <p>Describe your problem and let AI categorize it for you</p>
        </div>

        <Card className="ai-ticket-card">
          <CardContent>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 3 }}>
              <AutoAwesomeIcon sx={{ color: "#667eea", fontSize: 24 }} />
              <h3 style={{ margin: 0, color: "#333" }}>Smart Ticket Generation</h3>
            </Box>

            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

            <TextField
              label="Describe your problem..."
              fullWidth
              multiline
              rows={6}
              placeholder="e.g., 'I cannot login to my account. It says invalid credentials when I'm sure my password is correct.'"
              value={text}
              onChange={(e) => setText(e.target.value)}
              disabled={loading}
              variant="outlined"
              sx={{
                mb: 3,
                "& .MuiOutlinedInput-root": {
                  borderRadius: "10px"
                }
              }}
            />

            <Button
              variant="contained"
              fullWidth
              onClick={submit}
              disabled={loading}
              startIcon={<AutoAwesomeIcon />}
              sx={{
                height: 48,
                fontSize: "1rem",
                fontWeight: 600,
                textTransform: "none",
                background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
                "&:hover": {
                  background: "linear-gradient(135deg, #5568d3 0%, #6b3f8f 100%)"
                }
              }}
            >
              {loading ? "Creating Ticket..." : "Generate Ticket"}
            </Button>
          </CardContent>
        </Card>

        {result && (
          <Card className="result-card">
            <CardContent>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
                <span style={{ fontSize: "24px" }}>✅</span>
                <h3 style={{ margin: 0, color: "#333", fontSize: "20px", fontWeight: 700 }}>Ticket Created Successfully!</h3>
              </Box>

              <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2, mt: 3 }}>
                <div className="result-item">
                  <label>Ticket ID</label>
                  <p style={{ color: "#667eea", fontWeight: 700, fontSize: "18px" }}>#{result.id}</p>
                </div>

                <div className="result-item">
                  <label>Priority</label>
                  <Chip
                    label={result.priority}
                    color={result.priority === "high" ? "error" : result.priority === "medium" ? "warning" : "success"}
                    sx={{ fontWeight: 600 }}
                  />
                </div>

                <div className="result-item" style={{ gridColumn: "1 / -1" }}>
                  <label>Title</label>
                  <p style={{ color: "#333", fontWeight: 600 }}>{result.title}</p>
                </div>

                <div className="result-item" style={{ gridColumn: "1 / -1" }}>
                  <label>Category</label>
                  <Chip label={result.category || "General"} variant="outlined" />
                </div>
              </Box>

              <Box sx={{ mt: 3, pt: 2, borderTop: "1px solid #e0e0e0" }}>
                <Button
                  variant="contained"
                  onClick={() => setResult(null)}
                  sx={{
                    background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
                    textTransform: "none",
                    fontWeight: 600
                  }}
                >
                  Create Another
                </Button>
              </Box>
            </CardContent>
          </Card>
        )}
      </div>
    </>
  );
}
