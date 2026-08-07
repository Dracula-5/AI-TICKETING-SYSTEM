import {
  TextField,
  Button,
  Card,
  CardContent,
  Box,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Alert
} from "@mui/material";
import { useState } from "react";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import RestartAltRoundedIcon from "@mui/icons-material/RestartAltRounded";
import AutorenewRoundedIcon from "@mui/icons-material/AutorenewRounded";
import AddIcon from "@mui/icons-material/Add";
import api from "../api/axios";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import { getAuthItem } from "../utils/authSession";
import "../styles/createTicket.css";

export default function CreateTicket() {
  const [title, setTitle] = useState("");
  const [description, setDesc] = useState("");
  const [priority, setPriority] = useState("medium");
  const [category, setCategory] = useState("general");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState("");
  const [error, setError] = useState("");

  function resetAll() {
    setTitle("");
    setDesc("");
    setPriority("medium");
    setCategory("general");
    setError("");
    setSuccess("");
  }

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
        tenant_id: Number(getAuthItem("tenant_id"))
      });

      setSuccess("Ticket created successfully.");
      setTitle("");
      setDesc("");
      setPriority("medium");
      setCategory("general");
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
        <div className="create-ticket-headline">
          <div>
            <h1>Import Ticket Details</h1>
            <p>Set configuration and submit your support request in one flow.</p>
          </div>

          <Button
            variant="outlined"
            onClick={resetAll}
            startIcon={<RestartAltRoundedIcon />}
            className="reset-btn"
          >
            Reset All
          </Button>
        </div>

        <Card className="config-card">
          <CardContent>
            <Box className="config-title-wrap">
              <InfoOutlinedIcon fontSize="small" />
              <h3>Your Configuration</h3>
            </Box>

            <Box className="config-grid">
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

              <Button
                variant="contained"
                className="reload-btn"
                startIcon={<AutorenewRoundedIcon />}
                onClick={() => {
                  setPriority("medium");
                  setCategory("general");
                }}
              >
                Reload Defaults
              </Button>
            </Box>

            <p className="config-helper">Configuration helps auto-route your ticket to the right team.</p>
          </CardContent>
        </Card>

        <Card className="create-ticket-card">
          <CardContent>
            <div className="import-header">
              <h3>Submit Ticket Request</h3>
              <p>Complete the steps, then create your ticket.</p>
            </div>

            <div className="step-list">
              <div className="step-item">
                <span>1</span>
                <div>
                  <h4>Add a clear title</h4>
                  <p>Use one sentence that explains the issue.</p>
                </div>
              </div>
              <div className="step-item">
                <span>2</span>
                <div>
                  <h4>Describe the problem</h4>
                  <p>Include what happened, expected behavior, and impact.</p>
                </div>
              </div>
              <div className="step-item">
                <span>3</span>
                <div>
                  <h4>Submit for assignment</h4>
                  <p>The system assigns and prioritizes based on configuration.</p>
                </div>
              </div>
            </div>

            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
            {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

            <Box sx={{ display: "flex", flexDirection: "column", gap: 2.5 }}>
              <TextField
                fullWidth
                label="Ticket Title"
                placeholder="Example: Unable to access invoice page"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={loading}
              />

              <TextField
                fullWidth
                multiline
                rows={7}
                label="Detailed Description"
                placeholder="Paste full issue details here. Extra text is fine, include errors and steps to reproduce."
                value={description}
                onChange={(e) => setDesc(e.target.value)}
                disabled={loading}
              />

              <Box className="create-ticket-actions">
                <Button variant="text" onClick={() => setDesc("")} disabled={loading}>
                  Clear Description
                </Button>

                <Button
                  variant="contained"
                  onClick={submit}
                  disabled={loading}
                  startIcon={<AddIcon />}
                  className="submit-btn"
                >
                  {loading ? "Creating..." : "Create Ticket"}
                </Button>
              </Box>
            </Box>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
