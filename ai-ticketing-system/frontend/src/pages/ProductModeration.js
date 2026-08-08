import { useEffect, useState } from "react";
import {
  Table, TableHead, TableCell, TableRow, TableBody, TableContainer, Paper,
  Chip, Box, FormControl, InputLabel, Select, MenuItem, Alert,
} from "@mui/material";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import Footer from "../components/Footer";
import { listAllProductsAdmin, setProductStatus } from "../api/products";
import "../styles/vendorDashboard.css";

const STATUS_OPTIONS = ["active", "inactive", "out_of_stock"];

function statusColor(status) {
  if (status === "active") return "success";
  if (status === "out_of_stock") return "warning";
  return "default";
}

export default function ProductModeration() {
  const [products, setProducts] = useState([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");

  function load() {
    listAllProductsAdmin(filter ? { status: filter } : {})
      .then((res) => setProducts(res.data.items))
      .catch(() => setProducts([]));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  async function handleStatusChange(productId, newStatus) {
    setError("");
    try {
      await setProductStatus(productId, newStatus);
      load();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to update product status");
    }
  }

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />

      <div className="vendor-dashboard-main">
        <div className="vendor-dashboard-header">
          <h1>Product Moderation</h1>
          <p>Review and manage all product listings across the marketplace</p>
        </div>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        <Box className="vendor-dashboard-toolbar">
          <FormControl size="small" sx={{ minWidth: 180 }}>
            <InputLabel>Status filter</InputLabel>
            <Select value={filter} label="Status filter" onChange={(e) => setFilter(e.target.value)}>
              <MenuItem value="">All statuses</MenuItem>
              {STATUS_OPTIONS.map((s) => (
                <MenuItem key={s} value={s}>{s}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>

        <TableContainer component={Paper} sx={{ borderRadius: "12px" }}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell><b>Title</b></TableCell>
                <TableCell><b>Vendor</b></TableCell>
                <TableCell><b>Price</b></TableCell>
                <TableCell><b>Status</b></TableCell>
                <TableCell><b>Change Status</b></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {products.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} sx={{ textAlign: "center", py: 4, color: "#999" }}>
                    No products found.
                  </TableCell>
                </TableRow>
              ) : (
                products.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell>{p.title}</TableCell>
                    <TableCell>{p.vendor?.shop_name}</TableCell>
                    <TableCell>{p.currency} {p.price.toLocaleString()}</TableCell>
                    <TableCell>
                      <Chip label={p.status} color={statusColor(p.status)} size="small" />
                    </TableCell>
                    <TableCell>
                      <FormControl size="small" sx={{ minWidth: 140 }}>
                        <Select value={p.status} onChange={(e) => handleStatusChange(p.id, e.target.value)}>
                          {STATUS_OPTIONS.map((s) => (
                            <MenuItem key={s} value={s}>{s}</MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </div>
      <Footer />
    </>
  );
}
