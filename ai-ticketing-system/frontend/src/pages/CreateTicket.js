import { TextField, Button, Card, CardContent, Box, FormControl, InputLabel, Select, MenuItem, Alert } from "@mui/material";
import { useState } from "react";
import api from "../api/axios";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import AddIcon from "@mui/icons-material/Add";
import "../styles/createTicket.css";

export default function CreateTicket() {
  const [title, setTitle] = useState("");
  const [description, setDesc] = useState("");
  const [priority, setPriority] = useState("medium");
  const [category, setCategory] = useState("general");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState("");
  const [error, setError] = useState("");

  async function submit() {
    if (!title || !description) {
      setError("Title and description are required");
      return;
    }

    setLoading(true);
    setError("");
    setSuccess("");

    try {
      await api.post("/tickets", {
        title,
        description,
        priority,
        category: category || "general",
        tenant_id: Number(localStorage.getItem("tenant_id"))
      });

      setSuccess("Ticket created successfully!");
      setTitle("");
      setDesc("");
      setPriority("medium");
      setCategory("general");

      setTimeout(() => {
        setSuccess("");
        // Optionally redirect
        // window.location.href = "/tickets";
      }, 2000);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to create ticket");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />
      <div className="create-ticket-main">
        <div className="create-ticket-header">
          <h1>Create New Ticket</h1>
          <p>Submit a new support request</p>
        </div>

        <Card className="create-ticket-card">
          <CardContent>
            {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}
            {success && <Alert severity="success" sx={{ mb: 3 }}>{success}</Alert>}

            <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
              {/* Title Field */}
              <TextField
                fullWidth
                label="Ticket Title"
                placeholder="Brief description of your issue"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={loading}
                variant="outlined"
                sx={{
                  "& .MuiOutlinedInput-root": {
                    borderRadius: "10px"
                  }
                }}
              />

              {/* Description Field */}
              <TextField
                fullWidth
                multiline
                rows={5}
                label="Description"
                placeholder="Provide detailed information about your issue..."
                value={description}
                onChange={(e) => setDesc(e.target.value)}
                disabled={loading}
                variant="outlined"
                sx={{
                  "& .MuiOutlinedInput-root": {
                    borderRadius: "10px"
                  }
                }}
              />

              {/* Priority & Category Row */}
              <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
                <FormControl fullWidth>
                  <InputLabel>Priority</InputLabel>
                  <Select
                    value={priority}
                    label="Priority"
                    onChange={(e) => setPriority(e.target.value)}
                    disabled={loading}
                  >
                    <MenuItem value="low">Low</MenuItem>
                    <MenuItem value="medium">Medium</MenuItem>
                    <MenuItem value="high">High</MenuItem>
                    <MenuItem value="critical">Critical</MenuItem>
                  </Select>
                </FormControl>

                <FormControl fullWidth>
                  <InputLabel>Category</InputLabel>
                  <Select
                    value={category}
                    label="Category"
                    onChange={(e) => setCategory(e.target.value)}
                    disabled={loading}
                  >
                    <MenuItem value="general">General</MenuItem>
                    <MenuItem value="technical">Technical</MenuItem>
                    <MenuItem value="billing">Billing</MenuItem>
                    <MenuItem value="account">Account</MenuItem>
                  </Select>
                </FormControl>
              </Box>

              {/* Submit Button */}
              <Button
                variant="contained"
                size="large"
                onClick={submit}
                disabled={loading}
                startIcon={<AddIcon />}
                sx={{
                  height: 48,
                  fontSize: "1rem",
                  fontWeight: 600,
                  textTransform: "none",
                  borderRadius: "10px",
                  background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
                  "&:hover": {
                    background: "linear-gradient(135deg, #5568d3 0%, #6b3f8f 100%)"
                  }
                }}
              >
                {loading ? "Creating..." : "Create Ticket"}
              </Button>
            </Box>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
