import { useEffect, useState } from "react";
import { Button, Table, TableHead, TableRow, TableCell, TableBody, Card, CardContent, Box, Alert, CircularProgress, Paper, TableContainer } from "@mui/material";
import SettingsIcon from "@mui/icons-material/Settings";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import api from "../api/axios";
import "../styles/adminPanel.css";

export default function AdminPanel() {

  const [tickets, setTickets] = useState([]);
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState("");
  const [slaRunning, setSlaRunning] = useState(false);

  function load() {
    api.get("/tickets").then(res => setTickets(res.data || []));
    api.get("/users/providers").then(res => setProviders(res.data || []));
  }

  useEffect(() => { load(); }, [])

  function assign(ticketId, userId) {
    api.put(`/tickets/${ticketId}/assign/${userId}`).then(() => {
      setSuccess("Ticket assigned successfully!");
      setTimeout(() => setSuccess(""), 2000);
      load();
    });
  }

  function runSla() {
    setSlaRunning(true);
    api.post("/tickets/admin/run-sla-check")
      .then(() => {
        setSuccess("SLA Check completed!");
        setTimeout(() => setSuccess(""), 2000);
        load();
      })
      .catch(() => {
        setSuccess("");
      })
      .finally(() => setSlaRunning(false));
  }

  const pendingTickets = tickets.filter(t => t.status === "open" || t.status === "in-progress");
  const slaBreach = tickets.filter(t => t.sla_due && new Date(t.sla_due) < new Date() && t.status !== "closed").length;

  return (
    <>
      <Navbar />
      <Sidebar role={"admin"} />

      <div className="admin-panel-main">
        <div className="admin-panel-header">
          <h1>Admin Control Panel</h1>
          <p>System administration and management tools</p>
        </div>

        {success && <Alert severity="success" sx={{ mb: 3 }}>{success}</Alert>}

        {/* Stats */}
        <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: 2, mb: 4 }}>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)" }}>
            <CardContent>
              <p>Total Tickets</p>
              <h2>{tickets.length}</h2>
            </CardContent>
          </Card>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)" }}>
            <CardContent>
              <p>Pending</p>
              <h2>{pendingTickets.length}</h2>
            </CardContent>
          </Card>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #fa709a 0%, #fee140 100%)" }}>
            <CardContent>
              <p>SLA Breached</p>
              <h2>{slaBreach}</h2>
            </CardContent>
          </Card>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)" }}>
            <CardContent>
              <p>Providers</p>
              <h2>{providers.length}</h2>
            </CardContent>
          </Card>
        </Box>

        {/* SLA Check Button */}
        <Card sx={{ mb: 4, borderRadius: "16px" }}>
          <CardContent>
            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <Box>
                <h3 style={{ margin: "0 0 5px 0", color: "#333" }}>Run SLA Check</h3>
                <p style={{ margin: 0, color: "#999", fontSize: "14px" }}>Check all tickets for SLA breaches</p>
              </Box>
              <Button
                variant="contained"
                onClick={runSla}
                disabled={slaRunning}
                startIcon={slaRunning ? <CircularProgress size={20} color="inherit" /> : <PlayArrowIcon />}
                sx={{
                  background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
                  textTransform: "none",
                  fontWeight: 600
                }}
              >
                {slaRunning ? "Running..." : "Run Now"}
              </Button>
            </Box>
          </CardContent>
        </Card>

        {/* Tickets Table */}
        <Card sx={{ borderRadius: "16px" }}>
          <CardContent>
            <h3 style={{ margin: "0 0 20px 0", color: "#333" }}>Quick Assignment</h3>
            <TableContainer component={Paper} sx={{ borderRadius: "12px", boxShadow: "none" }}>
              <Table>
                <TableHead>
                  <TableRow sx={{ backgroundColor: "#f9f9f9" }}>
                    <TableCell sx={{ fontWeight: 700, color: "#333" }}>Ticket ID</TableCell>
                    <TableCell sx={{ fontWeight: 700, color: "#333" }}>Title</TableCell>
                    <TableCell sx={{ fontWeight: 700, color: "#333" }}>Assign To</TableCell>
                  </TableRow>
                </TableHead>

                <TableBody>
                  {pendingTickets.slice(0, 10).map(t => (
                    <TableRow key={t.id} sx={{ borderBottom: "1px solid #e0e0e0" }}>
                      <TableCell sx={{ fontWeight: 600, color: "#667eea" }}>{t.id}</TableCell>
                      <TableCell>{t.title}</TableCell>
                      <TableCell>
                        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
                          {providers.slice(0, 3).map(p => (
                            <Button
                              key={p.id}
                              size="small"
                              variant="outlined"
                              onClick={() => assign(t.id, p.id)}
                              sx={{
                                textTransform: "none",
                                fontSize: "12px",
                                borderRadius: "6px"
                              }}
                            >
                              {p.name.split(" ")[0]}
                            </Button>
                          ))}
                        </Box>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            {pendingTickets.length > 10 && (
              <p style={{ marginTop: 16, color: "#999", fontSize: "14px" }}>
                Showing 10 of {pendingTickets.length} pending tickets. View all in Tickets page.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
