import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  Table, TableHead, TableCell, TableRow, TableBody, TableContainer, Paper, Chip, Button,
  IconButton, Collapse, Box, Alert,
} from "@mui/material";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import Footer from "../components/Footer";
import OrderStatusStepper from "../components/OrderStatusStepper";
import LoadingState from "../components/LoadingState";
import { listMyOrders } from "../api/orders";
import { getAuthItem } from "../utils/authSession";
import "../styles/vendorDashboard.css";
import { useToast } from "../context/ToastContext";

function statusColor(status) {
  if (status === "completed") return "success";
  if (status === "cancelled") return "default";
  if (status === "shipped") return "info";
  if (status === "confirmed") return "primary";
  return "warning";
}

function OrderRow({ order }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <TableRow>
        <TableCell>
          <IconButton size="small" onClick={() => setOpen(!open)} aria-label={open ? "Collapse order details" : "Expand order details"}>
            {open ? <KeyboardArrowUpIcon fontSize="small" /> : <KeyboardArrowDownIcon fontSize="small" />}
          </IconButton>
        </TableCell>
        <TableCell>{order.product.title}</TableCell>
        <TableCell>{order.quantity}</TableCell>
        <TableCell>{order.product.currency} {order.unit_price.toLocaleString()}</TableCell>
        <TableCell>{order.product.currency} {order.total_price.toLocaleString()}</TableCell>
        <TableCell>
          <Chip label={order.status} color={statusColor(order.status)} size="small" />
          {order.negotiation_session_id && (
            <Button size="small" component={Link} to={`/negotiation/${order.negotiation_session_id}`} sx={{ ml: 1 }}>
              View Deal
            </Button>
          )}
        </TableCell>
        <TableCell>{new Date(order.created_at).toLocaleString()}</TableCell>
      </TableRow>
      <TableRow>
        <TableCell colSpan={7} sx={{ py: 0, borderBottom: open ? undefined : "none" }}>
          <Collapse in={open} timeout="auto" unmountOnExit>
            <Box sx={{ py: 2, px: 1 }}>
              <OrderStatusStepper status={order.status} />
              <p style={{ margin: "8px 0 0", fontSize: 14, color: "#64748b" }}>
                <b>Delivering to:</b> {order.delivery_address || "No address on file"}
              </p>
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  );
}

export default function Orders() {
  const location = useLocation();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const toast = useToast();
  const justPlaced = location.state?.justPlaced;

  useEffect(() => {
    listMyOrders()
      .then((res) => setOrders(res.data))
      .catch(() => {
        setOrders([]);
        toast.error("Couldn't load your orders.");
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <Navbar />
      <Sidebar role={getAuthItem("role")} />

      <div className="vendor-dashboard-main">
        <div className="vendor-dashboard-header">
          <h1>My Orders</h1>
          <p>Everything you've bought or negotiated on the marketplace</p>
        </div>

        {justPlaced && (
          <Alert severity="success" sx={{ mb: 2 }}>
            Order placed successfully{location.state?.count > 1 ? ` (${location.state.count} items)` : ""}!
          </Alert>
        )}

        {loading ? <LoadingState label="Loading your orders..." /> : (
        <TableContainer component={Paper} sx={{ borderRadius: "12px" }}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell />
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
                  <TableCell colSpan={7} sx={{ textAlign: "center", py: 4, color: "#999" }}>
                    No orders yet. <Link to="/marketplace">Browse the marketplace</Link>.
                  </TableCell>
                </TableRow>
              ) : (
                orders.map((o) => <OrderRow key={o.id} order={o} />)
              )}
            </TableBody>
          </Table>
        </TableContainer>
        )}
      </div>
      <Footer />
    </>
  );
}
