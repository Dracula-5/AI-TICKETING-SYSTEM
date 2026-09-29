import { useEffect, useRef, useState } from "react";
import Sidebar from "../components/Sidebar";
import Footer from "../components/Footer";
import Navbar from "../components/Navbar";
import LoadingState from "../components/LoadingState";
import EmptyState from "../components/EmptyState";
import api from "../api/axios";
import { Card, CardContent, Grid, Box, LinearProgress } from "@mui/material";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import { Pie, Bar } from "react-chartjs-2";
import "chart.js/auto";
import "../styles/dashboard.css";
import { useToast } from "../context/ToastContext";


export default function Dashboard() {
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const toast = useToast();
  const hasLoadedOnce = useRef(false);

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function load() {
    api.get("/tickets")
      .then(res => setTickets(res.data || []))
      .catch(() => {
        if (!hasLoadedOnce.current) toast.error("Couldn't load your ticket overview. Retrying shortly.");
      })
      .finally(() => {
        hasLoadedOnce.current = true;
        setLoading(false);
      });
  }

  const open = tickets.filter(t => t.status !== "closed").length;
  const closed = tickets.filter(t => t.status === "closed").length;

  const sla_breach = tickets.filter(t =>
    t.sla_due &&
    new Date(t.sla_due) < new Date() &&
    t.status !== "closed"
  ).length;

  const priorities = {
    high: tickets.filter(t => t.priority === "high").length,
    medium: tickets.filter(t => t.priority === "medium").length,
    low: tickets.filter(t => t.priority === "low").length,
  };

  const openPercentage = tickets.length > 0 ? Math.round((open / tickets.length) * 100) : 0;

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />

      <div className="dashboard-main">
        <div className="dashboard-header">
          <h1>Dashboard</h1>
          <p>Welcome back! Here's your ticket overview.</p>
        </div>

        {loading ? (
          <LoadingState label="Loading your ticket overview..." />
        ) : tickets.length === 0 ? (
          <EmptyState
            icon={<AssignmentOutlinedIcon sx={{ fontSize: 28, color: "text.disabled" }} />}
            title="No tickets yet"
            description="Once tickets are created, your overview and charts will appear here."
          />
        ) : (
        <>
        {/* ====== STAT CARDS ====== */}
        <Grid container spacing={3} sx={{ mb: 4 }}>
          <Grid item xs={12} sm={6} md={3}>
            <Box className="stat-card stat-grad-violet" style={{ animationDelay: "0.05s" }}>
              <CardContent>
                <p>Total Tickets</p>
                <h2>{tickets.length}</h2>
              </CardContent>
            </Box>
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <Box className="stat-card stat-grad-blue" style={{ animationDelay: "0.15s" }}>
              <CardContent>
                <p>Open Tickets</p>
                <h2>{open}</h2>
                <LinearProgress
                  variant="determinate"
                  value={openPercentage}
                  sx={{ mt: 1, height: 6, borderRadius: 3 }}
                />
              </CardContent>
            </Box>
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <Box className="stat-card stat-grad-emerald" style={{ animationDelay: "0.25s" }}>
              <CardContent>
                <p>Resolved</p>
                <h2>{closed}</h2>
              </CardContent>
            </Box>
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <Box
              className={`stat-card ${sla_breach > 0 ? "stat-grad-rose" : "stat-grad-teal"}`}
              style={{ animationDelay: "0.35s" }}
            >
              <CardContent>
                <p>SLA Breached</p>
                <h2>{sla_breach}</h2>
              </CardContent>
            </Box>
          </Grid>
        </Grid>

        {/* ====== CHARTS SECTION ====== */}
        <Grid container spacing={3}>
          {/* Pie Chart */}
          <Grid item xs={12} md={6}>
            <Card className="chart-card" style={{ animationDelay: "0.4s" }}>
              <CardContent>
                <h3>Status Distribution</h3>
                <Pie
                  data={{
                    labels: ["Open", "Closed"],
                    datasets: [
                      {
                        data: [open, closed],
                        backgroundColor: ["#6366f1", "#10b981"],
                        borderColor: "#fff",
                        borderWidth: 2
                      },
                    ],
                  }}
                  options={{
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {
                      legend: {
                        position: 'bottom'
                      }
                    }
                  }}
                />
              </CardContent>
            </Card>
          </Grid>

          {/* Bar Chart */}
          <Grid item xs={12} md={6}>
            <Card className="chart-card" style={{ animationDelay: "0.5s" }}>
              <CardContent>
                <h3>Priority Distribution</h3>
                <Bar
                  data={{
                    labels: ["High", "Medium", "Low"],
                    datasets: [
                      {
                        label: "Tickets",
                        data: [priorities.high, priorities.medium, priorities.low],
                        backgroundColor: ["#f43f5e", "#f59e0b", "#10b981"],
                        borderColor: ["#e11d48", "#ea580c", "#059669"],
                        borderWidth: 1,
                        borderRadius: 8
                      },
                    ],
                  }}
                  options={{
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {
                      legend: {
                        display: false
                      }
                    },
                    scales: {
                      y: {
                        beginAtZero: true
                      }
                    }
                  }}
                />
              </CardContent>
            </Card>
          </Grid>
        </Grid>
        </>
        )}
      </div>
      <Footer />
    </>
  );
}
