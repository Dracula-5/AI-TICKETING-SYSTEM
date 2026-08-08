import { useEffect, useState } from "react";
import { Card, CardContent, Grid, Box, CircularProgress } from "@mui/material";
import { Bar } from "react-chartjs-2";
import "chart.js/auto";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import Footer from "../components/Footer";
import EmptyState from "../components/EmptyState";
import { getAdminAnalytics } from "../api/analytics";
import "../styles/dashboard.css";
import { useToast } from "../context/ToastContext";

const STAT_CARDS = [
  { key: "total_vendors", label: "Vendors", grad: "stat-grad-violet" },
  { key: "total_products", label: "Products", grad: "stat-grad-blue" },
  { key: "total_views", label: "Product Views", grad: "stat-grad-teal" },
  { key: "total_orders", label: "Orders", grad: "stat-grad-amber" },
];

export default function AdminAnalytics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  useEffect(() => {
    getAdminAnalytics()
      .then((res) => setData(res.data))
      .catch(() => {
        setData(null);
        toast.error("Couldn't load platform analytics.");
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />

      <div className="dashboard-main">
        <div className="dashboard-header">
          <h1>Platform Analytics</h1>
          <p>Marketplace performance across all vendors</p>
        </div>

        {loading && (
          <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
            <CircularProgress />
          </Box>
        )}

        {!loading && !data && (
          <EmptyState
            title="Couldn't load analytics"
            description="Something went wrong fetching platform analytics. Try refreshing the page."
          />
        )}

        {!loading && data && (
          <>
            <Grid container spacing={3} sx={{ mb: 4 }}>
              {STAT_CARDS.map((c, i) => (
                <Grid item xs={12} sm={6} md={3} key={c.key}>
                  <Box className={`stat-card ${c.grad}`} style={{ animationDelay: `${0.05 + i * 0.1}s` }}>
                    <CardContent>
                      <p>{c.label}</p>
                      <h2>{data[c.key]?.toLocaleString?.() ?? data[c.key]}</h2>
                    </CardContent>
                  </Box>
                </Grid>
              ))}
            </Grid>

            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Card className="chart-card">
                  <CardContent>
                    <h3>Revenue</h3>
                    <h2 style={{ margin: "8px 0" }}>₹{data.total_revenue.toLocaleString()}</h2>
                    <p style={{ color: "#999" }}>
                      Negotiation success rate: <b>{data.negotiation_success_rate_pct}%</b> ({data.accepted_negotiations} of {data.total_negotiations} negotiations)
                    </p>
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12} md={6}>
                <Card className="chart-card">
                  <CardContent>
                    <h3>Top Vendors by Revenue</h3>
                    {data.top_vendors.length === 0 ? (
                      <p style={{ color: "#999" }}>No revenue yet.</p>
                    ) : (
                      <Bar
                        data={{
                          labels: data.top_vendors.map((v) => v.shop_name),
                          datasets: [{
                            label: "Revenue",
                            data: data.top_vendors.map((v) => v.revenue),
                            backgroundColor: "#6366f1",
                            borderRadius: 8,
                          }],
                        }}
                        options={{
                          responsive: true,
                          plugins: { legend: { display: false } },
                          scales: { y: { beginAtZero: true } },
                        }}
                      />
                    )}
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
