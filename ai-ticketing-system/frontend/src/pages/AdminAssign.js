import { useEffect, useState } from "react";
import api from "../api/axios";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import { 
  Select, MenuItem, Button, Card, CardContent, Typography, FormControl, InputLabel, Box, Alert
} from "@mui/material";
import AssignmentIcon from "@mui/icons-material/Assignment";
import "../styles/adminAssign.css";

export default function AdminAssign() {
  const [tickets, setTickets] = useState([]);
  const [providers, setProviders] = useState([]);
  const [selected, setSelected] = useState({});
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState("");

  useEffect(() => {
    api.get("/tickets").then(res => setTickets(res.data || []));
    api.get("/users/providers").then(res => setProviders(res.data || []));
  }, []);

  async function assign(ticketId) {
    if (!selected[ticketId]) {
      alert("Please select a provider");
      return;
    }

    setLoading(true);
    try {
      await api.put(`/tickets/${ticketId}/assign/${selected[ticketId]}`);
      setSuccess("Ticket Assigned Successfully!");
      setTimeout(() => setSuccess(""), 2000);
      setSelected({ ...selected, [ticketId]: "" });
    } catch (err) {
      alert("Failed to assign ticket");
    } finally {
      setLoading(false);
    }
  }

  const unassignedTickets = tickets.filter(t => !t.assigned_to_user_id);
  const pendingTickets = tickets.filter(t => t.status === "open");

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />

      <div className="admin-assign-main">
        <div className="admin-header">
          <h1>Assign Tickets to Providers</h1>
          <p>Distribute support tickets among your providers</p>
        </div>

        {success && <Alert severity="success" sx={{ mb: 3 }}>{success}</Alert>}

        {/* Stats */}
        <Box sx={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 2, mb: 4 }}>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)" }}>
            <CardContent>
              <p>Total Tickets</p>
              <h2>{tickets.length}</h2>
            </CardContent>
          </Card>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)" }}>
            <CardContent>
              <p>Unassigned</p>
              <h2>{unassignedTickets.length}</h2>
            </CardContent>
          </Card>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)" }}>
            <CardContent>
              <p>Providers</p>
              <h2>{providers.length}</h2>
            </CardContent>
          </Card>
        </Box>

        {/* Assignment Cards */}
        <div className="assignment-grid">
          {pendingTickets.length > 0 ? (
            pendingTickets.map(t => (
              <Card key={t.id} className="assignment-card">
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 1, fontWeight: 700, color: "#333" }}>
                    {t.title}
                  </Typography>
                  <Typography variant="body2" sx={{ mb: 2, color: "#666" }}>
                    Ticket #{t.id}
                  </Typography>

                  <FormControl fullWidth sx={{ mb: 2 }}>
                    <InputLabel>Select Provider</InputLabel>
                    <Select
                      label="Select Provider"
                      value={selected[t.id] || ""}
                      onChange={e =>
                        setSelected({ ...selected, [t.id]: e.target.value })
                      }
                      disabled={loading}
                    >
                      <MenuItem value="">-- Choose a provider --</MenuItem>

                      {providers.map(p => (
                        <MenuItem key={p.id} value={p.id}>
                          {p.name} ({p.department || "General"})
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>

                  <Button
                    variant="contained"
                    fullWidth
                    onClick={() => assign(t.id)}
                    disabled={loading || !selected[t.id]}
                    startIcon={<AssignmentIcon />}
                    sx={{
                      background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
                      textTransform: "none",
                      fontWeight: 600
                    }}
                  >
                    Assign Now
                  </Button>
                </CardContent>
              </Card>
            ))
          ) : (
            <Box sx={{ gridColumn: "1 / -1", textAlign: "center", py: 4 }}>
              <Typography color="textSecondary">No pending tickets to assign</Typography>
            </Box>
          )}
        </div>
      </div>
    </>
  );
}
