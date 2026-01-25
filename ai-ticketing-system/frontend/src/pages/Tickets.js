import { useEffect, useState } from "react";
import {
  Table,
  TableHead,
  TableCell,
  TableRow,
  TableBody,
  Chip,
  Card,
  CardContent,
  Paper,
  TableContainer,
  Box,
  InputAdornment,
  TextField
} from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import api from "../api/axios";
import ChatBot from "../components/ChatBot";
import "../styles/tickets.css";


export default function Tickets() {
  const [tickets, setTickets] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");

  function loadTickets() {
    api.get("/tickets")
      .then(res => setTickets(res.data))
      .catch(() => console.log("Failed to load tickets"));
  }

  useEffect(() => {
    loadTickets();
    const interval = setInterval(loadTickets, 4000);
    return () => clearInterval(interval);
  }, []);

  function getStatusColor(status) {
    if (status === "open") return "warning";
    if (status === "in-progress") return "info";
    if (status === "resolved") return "success";
    if (status === "closed") return "default";
    return "primary";
  }

  const filteredTickets = tickets.filter(t =>
    t.title?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    t.id?.toString().includes(searchTerm)
  );

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />

      <div className="tickets-main">
        <div className="tickets-header">
          <h1>Tickets</h1>
          <p>Manage all your support tickets</p>
        </div>

        <Card className="tickets-card">
          <CardContent>
            {/* Search Bar */}
            <Box sx={{ mb: 3 }}>
              <TextField
                placeholder="Search tickets by ID or title..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                fullWidth
                variant="outlined"
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon sx={{ color: "#999" }} />
                    </InputAdornment>
                  ),
                }}
                sx={{
                  "& .MuiOutlinedInput-root": {
                    borderRadius: "10px",
                    backgroundColor: "#f5f5f5"
                  }
                }}
              />
            </Box>

            {/* Table */}
            <TableContainer component={Paper} sx={{ borderRadius: "12px", boxShadow: "none" }}>
              <Table>
                <TableHead>
                  <TableRow sx={{ backgroundColor: "#f9f9f9" }}>
                    <TableCell sx={{ fontWeight: 700, color: "#333" }}><b>ID</b></TableCell>
                    <TableCell sx={{ fontWeight: 700, color: "#333" }}><b>Title</b></TableCell>
                    <TableCell sx={{ fontWeight: 700, color: "#333" }}><b>Status</b></TableCell>
                    <TableCell sx={{ fontWeight: 700, color: "#333" }}><b>Priority</b></TableCell>
                    <TableCell sx={{ fontWeight: 700, color: "#333" }}><b>SLA Due</b></TableCell>
                  </TableRow>
                </TableHead>

                <TableBody>
                  {filteredTickets.length > 0 ? (
                    filteredTickets.map((t, index) => {
                      const overdue =
                        t.sla_due &&
                        new Date(t.sla_due) < new Date() &&
                        t.status !== "closed";

                      return (
                        <TableRow
                          key={t.id}
                          className={`ticket-row ${overdue ? "overdue" : ""}`}
                          sx={{
                            background: overdue ? "#fff5f5" : "white",
                            transition: "all 0.3s ease",
                            "&:hover": {
                              background: overdue ? "#ffe8e8" : "#f9f9f9",
                              boxShadow: "0 2px 8px rgba(0,0,0,0.05)"
                            },
                            borderBottom: "1px solid #e0e0e0"
                          }}
                        >
                          <TableCell sx={{ fontWeight: 600, color: "#667eea" }}>{t.id}</TableCell>
                          <TableCell sx={{ maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis" }}>
                            {t.title}
                          </TableCell>

                          <TableCell>
                            <Chip 
                              label={t.status} 
                              color={getStatusColor(t.status)}
                              size="small"
                              sx={{ fontWeight: 600 }}
                            />
                          </TableCell>

                          <TableCell>
                            <Chip
                              label={t.priority}
                              color={
                                t.priority === "high"
                                  ? "error"
                                  : t.priority === "medium"
                                  ? "warning"
                                  : "success"
                              }
                              size="small"
                              sx={{ fontWeight: 600 }}
                            />
                          </TableCell>

                          <TableCell>
                            <span style={{ 
                              color: overdue ? "#e53935" : "#4caf50",
                              fontWeight: 600
                            }}>
                              {t.sla_due ? new Date(t.sla_due).toLocaleDateString() : "N/A"}
                            </span>
                          </TableCell>
                        </TableRow>
                      );
                    })
                  ) : (
                    <TableRow>
                      <TableCell colSpan={5} sx={{ textAlign: "center", py: 4, color: "#999" }}>
                        No tickets found
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>

            {/* Stats */}
            <Box sx={{ mt: 3, p: 2, backgroundColor: "#f9f9f9", borderRadius: "8px" }}>
              <p style={{ margin: 0, color: "#666", fontSize: "14px" }}>
                Showing <strong>{filteredTickets.length}</strong> of <strong>{tickets.length}</strong> tickets
              </p>
            </Box>

          </CardContent>
        </Card>
      </div>
    </>
  );
}

