import { useEffect, useState } from "react";
import {
  Table, TableHead, TableRow, TableCell,
  TableBody, Button, Chip, Card, CardContent, Box, Paper, TableContainer, Alert
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
  const [loading, setLoading] = useState(true);
  const [success, setSuccess] = useState("");

  useEffect(() => {
    loadTickets();
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

  const stats = {
    total: tickets.length,
    inProgress: tickets.filter(t => t.status === "in-progress").length,
    resolved: tickets.filter(t => t.status === "resolved").length
  };

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

        {/* Stats */}
        <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: 2, mb: 4 }}>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)" }}>
            <CardContent>
              <p>Total Assigned</p>
              <h2>{stats.total}</h2>
            </CardContent>
          </Card>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)" }}>
            <CardContent>
              <p>In Progress</p>
              <h2>{stats.inProgress}</h2>
            </CardContent>
          </Card>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)" }}>
            <CardContent>
              <p>Resolved</p>
              <h2>{stats.resolved}</h2>
            </CardContent>
          </Card>
        </Box>

        <Card className="provider-tickets-card">
          <CardContent>
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
                    {tickets.length > 0 ? (
                      tickets.map(t => (
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
                          <TableCell sx={{ fontWeight: 600, color: "#667eea" }}>{t.id}</TableCell>
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
                          No assigned tickets
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
