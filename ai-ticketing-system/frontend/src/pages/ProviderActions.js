import { useEffect, useState } from "react";
import { Button, Table, TableHead, TableRow, TableCell, TableBody, Chip, Card, CardContent, Box, Paper, TableContainer } from "@mui/material";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import DoneAllIcon from "@mui/icons-material/DoneAll";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import api from "../api/axios";
import "../styles/providerActions.css";

export default function ProviderActions() {

  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);

  function load() {
    api.get("/tickets/provider/my-tickets")
      .then(res => {
        setTickets(res.data || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }

  useEffect(() => { load(); }, [])

  function update(id, status) {
    api.put(`/tickets/provider/${id}/status?status=${status}`)
      .then(load);
  }

  const stats = {
    total: tickets.length,
    open: tickets.filter(t => t.status === "open").length,
    inProgress: tickets.filter(t => t.status === "in-progress").length
  };

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />

      <div className="provider-actions-main">
        <div className="provider-actions-header">
          <h1>My Assigned Tickets</h1>
          <p>Track and update your ticket progress</p>
        </div>

        {/* Stats */}
        <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: 2, mb: 4 }}>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #2b3a55 0%, #3f4c6b 100%)" }}>
            <CardContent>
              <p>Total Tickets</p>
              <h2>{stats.total}</h2>
            </CardContent>
          </Card>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #24435a 0%, #1f6f8b 100%)" }}>
            <CardContent>
              <p>Open</p>
              <h2>{stats.open}</h2>
            </CardContent>
          </Card>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #1f3c4d 0%, #2c6975 100%)" }}>
            <CardContent>
              <p>In Progress</p>
              <h2>{stats.inProgress}</h2>
            </CardContent>
          </Card>
        </Box>

        <Card className="provider-actions-card">
          <CardContent>
            {loading ? (
              <p style={{ textAlign: "center", color: "#999" }}>Loading...</p>
            ) : (
              <TableContainer component={Paper} sx={{ borderRadius: "12px", boxShadow: "none" }}>
                <Table>
                  <TableHead>
                    <TableRow sx={{ backgroundColor: "#f9f9f9" }}>
                      <TableCell sx={{ fontWeight: 700, color: "#333" }}>ID</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: "#333" }}>Title</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: "#333" }}>Status</TableCell>
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
                            <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
                              <Button
                                size="small"
                                variant="outlined"
                                startIcon={<PlayArrowIcon />}
                                onClick={() => update(t.id, "in-progress")}
                                sx={{ textTransform: "none", fontSize: "12px" }}
                              >
                                Start
                              </Button>
                              <Button
                                size="small"
                                variant="outlined"
                                startIcon={<CheckCircleIcon />}
                                onClick={() => update(t.id, "resolved")}
                                sx={{ textTransform: "none", fontSize: "12px" }}
                              >
                                Resolve
                              </Button>
                              <Button
                                size="small"
                                variant="outlined"
                                startIcon={<DoneAllIcon />}
                                onClick={() => update(t.id, "closed")}
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
                        <TableCell colSpan={4} sx={{ textAlign: "center", py: 4, color: "#999" }}>
                          No tickets assigned
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
