import { useEffect, useState } from "react";
import Sidebar from "../components/Sidebar";
import Navbar from "../components/Navbar";
import api from "../api/axios";
import { Card, CardContent, Grid, Box, LinearProgress } from "@mui/material";
import { Pie, Bar } from "react-chartjs-2";
import "chart.js/auto";
import ChatBot from "../components/ChatBot";
import "../styles/dashboard.css";


export default function Dashboard() {
  const [tickets, setTickets] = useState([]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  function load() {
    api.get("/tickets")
      .then(res => setTickets(res.data || []))
      .catch(() => console.log("Dashboard load fail"));
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

  const totalPriority = priorities.high + priorities.medium + priorities.low;
  const openPercentage = tickets.length > 0 ? Math.round((open / tickets.length) * 100) : 0;
  const closedPercentage = tickets.length > 0 ? Math.round((closed / tickets.length) * 100) : 0;

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />

      <div className="dashboard-main">
        <div className="dashboard-header">
          <h1>Dashboard</h1>
          <p>Welcome back! Here's your ticket overview.</p>
        </div>

        {/* ====== STAT CARDS ====== */}
        <Grid container spacing={3} sx={{ mb: 4 }}>
          <Grid item xs={12} md={4}>
            <Box
              className="stat-card"
              style={{
                background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)"
              }}
            >
              <CardContent>
                <p>Total Tickets</p>
                <h2>{tickets.length}</h2>
              </CardContent>
            </Box>
          </Grid>

          <Grid item xs={12} md={4}>
            <Box
              className="stat-card"
              style={{
                background: "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)"
              }}
            >
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

          <Grid item xs={12} md={4}>
            <Box
              className="stat-card"
              style={{
                background: sla_breach > 0 
                  ? "linear-gradient(135deg, #fa709a 0%, #fee140 100%)"
                  : "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)"
              }}
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
            <Card className="chart-card">
              <CardContent>
                <h3>Status Distribution</h3>
                <Pie
                  data={{
                    labels: ["Open", "Closed"],
                    datasets: [
                      {
                        data: [open, closed],
                        backgroundColor: ["#f093fb", "#4facfe"],
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
            <Card className="chart-card">
              <CardContent>
                <h3>Priority Distribution</h3>
                <Bar
                  data={{
                    labels: ["High", "Medium", "Low"],
                    datasets: [
                      {
                        label: "Tickets",
                        data: [priorities.high, priorities.medium, priorities.low],
                        backgroundColor: ["#ef5350", "#ffa726", "#66bb6a"],
                        borderColor: ["#e53935", "#fb8c00", "#43a047"],
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
      </div>
    </>
  );
}
