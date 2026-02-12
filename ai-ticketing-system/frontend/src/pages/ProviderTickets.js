import { useEffect, useState } from "react";
import {
  Table, TableHead, TableRow, TableCell,
  TableBody, Button, Chip, Card, CardContent, Box, Paper, TableContainer, Alert, ToggleButton, ToggleButtonGroup
} from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import HourglassTopIcon from "@mui/icons-material/HourglassTop";
import DoneAllIcon from "@mui/icons-material/DoneAll";
import Sidebar from "../components/Sidebar";
import Navbar from "../components/Navbar";
import api from "../api/axios";
import "../styles/providerTickets.css";

export default function ProviderTickets() {
  const [tickets, setTickets] = useState([]);
  const [openTickets, setOpenTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingOpen, setLoadingOpen] = useState(true);
  const [success, setSuccess] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  useEffect(() => {
    loadTickets();
    loadOpenTickets();
  }, []);

  function loadTickets() {
    api.get("/tickets/provider/my-tickets")
      .then(res => {
        setTickets(res.data || []);
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to load tickets");
        setLoading(false);
      });
  }

  function loadOpenTickets() {
    api.get("/tickets/provider/open")
      .then(res => {
        setOpenTickets(res.data || []);
        setLoadingOpen(false);
      })
      .catch(() => {
        setLoadingOpen(false);
      });
  }

  async function updateStatus(id, status) {
    try {
      await api.put(`/tickets/provider/${id}/status?status=${status}`);
      setSuccess(`Ticket status updated to ${status}`);
      setTimeout(() => setSuccess(""), 2000);
      loadTickets();
    } catch (err) {
      alert("Failed to update status");
    }
  }

  async function offerHelp(id) {
    try {
      await api.post(`/tickets/provider/offer/${id}`);
      setSuccess("You are now assigned to the ticket");
      setTimeout(() => setSuccess(""), 2000);
      loadTickets();
      loadOpenTickets();
    } catch (err) {
      alert("Failed to offer help");
    }
  }

  const stats = {
    total: tickets.length,
    inProgress: tickets.filter(t => t.status === "in-progress").length,
    resolved: tickets.filter(t => t.status === "resolved").length
  };
  const filteredTickets = statusFilter === "all"
    ? tickets
    : tickets.filter(t => t.status === statusFilter);

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />

      <div className="provider-tickets-main">
        <div className="provider-header">
          <h1>My Assigned Tickets</h1>
          <p>Manage your assigned support tickets</p>
        </div>

        {success && <Alert severity="success" sx={{ mb: 3 }}>{success}</Alert>}

        <Card className="provider-legend">
          <CardContent>
            <div className="legend-row">
              <div className="legend-item">
                <span className="legend-dot legend-open" />
                <span>Open</span>
              </div>
              <div className="legend-item">
                <span className="legend-dot legend-progress" />
                <span>In-Progress</span>
              </div>
              <div className="legend-item">
                <span className="legend-dot legend-resolved" />
                <span>Resolved</span>
              </div>
              <div className="legend-item">
                <span className="legend-dot legend-high" />
                <span>High Priority</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Stats */}
        <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: 2, mb: 4 }}>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #2b3a55 0%, #3f4c6b 100%)" }}>
            <CardContent>
              <p>Total Assigned</p>
              <h2>{stats.total}</h2>
            </CardContent>
          </Card>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #24435a 0%, #1f6f8b 100%)" }}>
            <CardContent>
              <p>In Progress</p>
              <h2>{stats.inProgress}</h2>
            </CardContent>
          </Card>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #1f3c4d 0%, #2c6975 100%)" }}>
            <CardContent>
              <p>Resolved</p>
              <h2>{stats.resolved}</h2>
            </CardContent>
          </Card>
        </Box>

        <Card className="provider-tickets-card">
          <CardContent>
            <div className="provider-section-header">
              <h2>My Assigned Tickets</h2>
              <ToggleButtonGroup
                size="small"
                value={statusFilter}
                exclusive
                onChange={(_, v) => v && setStatusFilter(v)}
              >
                <ToggleButton value="all">All</ToggleButton>
                <ToggleButton value="open">Open</ToggleButton>
                <ToggleButton value="in-progress">In-Progress</ToggleButton>
                <ToggleButton value="resolved">Resolved</ToggleButton>
              </ToggleButtonGroup>
            </div>
            {loading ? (
              <p style={{ textAlign: "center", color: "#999" }}>Loading tickets...</p>
            ) : (
              <TableContainer component={Paper} sx={{ borderRadius: "12px", boxShadow: "none" }}>
                <Table>
                  <TableHead>
                    <TableRow sx={{ backgroundColor: "#f9f9f9" }}>
                      <TableCell sx={{ fontWeight: 700, color: "#333" }}>ID</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: "#333" }}>Title</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: "#333" }}>Status</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: "#333" }}>Priority</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: "#333" }}>Actions</TableCell>
                    </TableRow>
                  </TableHead>

                  <TableBody>
                    {filteredTickets.length > 0 ? (
                      filteredTickets.map(t => (
                        <TableRow 
                          key={t.id}
                          sx={{
                            transition: "all 0.3s ease",
                            "&:hover": {
                              background: "#f9f9f9",
                              boxShadow: "0 2px 8px rgba(0,0,0,0.05)"
                            },
                            borderBottom: "1px solid #e0e0e0"
                          }}
                        >
                          <TableCell sx={{ fontWeight: 600, color: "var(--accent)" }}>{t.id}</TableCell>
                          <TableCell>{t.title}</TableCell>
                          <TableCell>
                            <Chip
                              label={t.status}
                              color={
                                t.status === "in-progress" ? "warning" :
                                  t.status === "resolved" ? "success" :
                                    "default"
                              }
                              size="small"
                              sx={{ fontWeight: 600 }}
                            />
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={t.priority}
                              color={
                                t.priority === "high" ? "error" :
                                  t.priority === "medium" ? "warning" :
                                    "success"
                              }
                              size="small"
                              sx={{ fontWeight: 600 }}
                            />
                          </TableCell>
                          <TableCell>
                            <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
                              <Button
                                size="small"
                                variant={t.status === "in-progress" ? "contained" : "outlined"}
                                startIcon={<HourglassTopIcon />}
                                onClick={() => updateStatus(t.id, "in-progress")}
                                sx={{ textTransform: "none", fontSize: "12px" }}
                              >
                                In Progress
                              </Button>
                              <Button
                                size="small"
                                variant={t.status === "resolved" ? "contained" : "outlined"}
                                startIcon={<CheckCircleIcon />}
                                onClick={() => updateStatus(t.id, "resolved")}
                                sx={{ textTransform: "none", fontSize: "12px" }}
                              >
                                Resolve
                              </Button>
                              <Button
                                size="small"
                                variant={t.status === "closed" ? "contained" : "outlined"}
                                startIcon={<DoneAllIcon />}
                                onClick={() => updateStatus(t.id, "closed")}
                                sx={{ textTransform: "none", fontSize: "12px" }}
                              >
                                Close
                              </Button>
                            </Box>
                          </TableCell>
                        </TableRow>
                      ))
                    ) : (
                      <TableRow>
                        <TableCell colSpan={5} sx={{ textAlign: "center", py: 4, color: "#999" }}>
                          No tickets for this filter
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </CardContent>
        </Card>

        <Card className="provider-tickets-card provider-open-card">
          <CardContent>
            <h2 style={{ marginTop: 0 }}>Open Tickets (Unassigned)</h2>
            {loadingOpen ? (
              <p style={{ textAlign: "center", color: "#999" }}>Loading open tickets...</p>
            ) : (
              <TableContainer component={Paper} sx={{ borderRadius: "12px", boxShadow: "none" }}>
                <Table>
                  <TableHead>
                    <TableRow sx={{ backgroundColor: "#f9f9f9" }}>
                      <TableCell sx={{ fontWeight: 700, color: "#333" }}>ID</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: "#333" }}>Title</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: "#333" }}>Priority</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: "#333" }}>Action</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {openTickets.length > 0 ? (
                      openTickets.map(t => (
                        <TableRow key={t.id}>
                          <TableCell sx={{ fontWeight: 600, color: "var(--accent)" }}>{t.id}</TableCell>
                          <TableCell>{t.title}</TableCell>
                          <TableCell>
                            <Chip
                              label={t.priority}
                              color={
                                t.priority === "high" ? "error" :
                                  t.priority === "medium" ? "warning" :
                                    "success"
                              }
                              size="small"
                              sx={{ fontWeight: 600 }}
                            />
                          </TableCell>
                          <TableCell>
                            <Button
                              size="small"
                              variant="contained"
                              onClick={() => offerHelp(t.id)}
                              sx={{ textTransform: "none", fontSize: "12px" }}
                            >
                              Offer Help
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))
                    ) : (
                      <TableRow>
                        <TableCell colSpan={4} sx={{ textAlign: "center", py: 4, color: "#999" }}>
                          No open tickets
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
