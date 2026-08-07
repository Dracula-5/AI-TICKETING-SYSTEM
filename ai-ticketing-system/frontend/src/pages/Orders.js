import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Table, TableHead, TableCell, TableRow, TableBody, TableContainer, Paper, Chip, Button,
} from "@mui/material";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import { listMyOrders } from "../api/orders";
import "../styles/vendorDashboard.css";

function statusColor(status) {
  if (status === "completed") return "success";
  if (status === "cancelled") return "default";
  if (status === "shipped") return "info";
  if (status === "confirmed") return "primary";
  return "warning";
}

export default function Orders() {
  const [orders, setOrders] = useState([]);

  useEffect(() => {
    listMyOrders().then((res) => setOrders(res.data)).catch(() => setOrders([]));
  }, []);

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />

      <div className="vendor-dashboard-main">
        <div className="vendor-dashboard-header">
          <h1>My Orders</h1>
          <p>Everything you've bought or negotiated on the marketplace</p>
        </div>

        <TableContainer component={Paper} sx={{ borderRadius: "12px" }}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell><b>Product</b></TableCell>
                <TableCell><b>Qty</b></TableCell>
                <TableCell><b>Unit Price</b></TableCell>
                <TableCell><b>Total</b></TableCell>
                <TableCell><b>Status</b></TableCell>
                <TableCell><b>Placed</b></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {orders.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} sx={{ textAlign: "center", py: 4, color: "#999" }}>
                    No orders yet. <Link to="/marketplace">Browse the marketplace</Link>.
                  </TableCell>
                </TableRow>
              ) : (
                orders.map((o) => (
                  <TableRow key={o.id}>
                    <TableCell>{o.product.title}</TableCell>
                    <TableCell>{o.quantity}</TableCell>
                    <TableCell>{o.product.currency} {o.unit_price.toLocaleString()}</TableCell>
                    <TableCell>{o.product.currency} {o.total_price.toLocaleString()}</TableCell>
                    <TableCell>
                      <Chip label={o.status} color={statusColor(o.status)} size="small" />
                      {o.negotiation_session_id && (
                        <Button size="small" component={Link} to={`/negotiation/${o.negotiation_session_id}`} sx={{ ml: 1 }}>
                          View Deal
                        </Button>
                      )}
                    </TableCell>
                    <TableCell>{new Date(o.created_at).toLocaleString()}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </div>
    </>
  );
}
