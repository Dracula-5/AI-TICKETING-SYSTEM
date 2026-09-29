import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box, Card, CardContent, TextField, Button, Divider, Alert, CircularProgress,
} from "@mui/material";
import ShoppingCartOutlinedIcon from "@mui/icons-material/ShoppingCartOutlined";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import Footer from "../components/Footer";
import EmptyState from "../components/EmptyState";
import SuccessAnimation from "../components/SuccessAnimation";
import { useCart } from "../context/CartContext";
import { createOrder } from "../api/orders";
import { getSavedAddress, saveAddress } from "../utils/deliveryAddress";
import { getAuthItem } from "../utils/authSession";
import "../styles/vendorDashboard.css";

export default function Checkout() {
  const navigate = useNavigate();
  const { items, totalPrice, removeItem, clearCart } = useCart();
  const [address, setAddress] = useState(getSavedAddress());
  const [placing, setPlacing] = useState(false);
  const [error, setError] = useState("");
  const [placedCount, setPlacedCount] = useState(0);
  const [celebrating, setCelebrating] = useState(false);
  const currency = items[0]?.currency || "INR";

  async function placeOrder() {
    if (!address.trim()) {
      setError("Enter a delivery address");
      return;
    }
    setPlacing(true);
    setError("");
    saveAddress(address.trim());

    const failures = [];
    for (const item of items) {
      try {
        await createOrder({
          product_id: item.productId,
          quantity: item.quantity,
          delivery_address: address.trim(),
        });
        removeItem(item.productId);
      } catch (err) {
        failures.push(`${item.title}: ${err.response?.data?.detail || "failed"}`);
      }
    }

    setPlacing(false);
    if (failures.length === 0) {
      setPlacedCount(items.length);
      clearCart();
      setCelebrating(true);
    } else {
      setError(`Some items could not be ordered: ${failures.join("; ")}`);
    }
  }

  if (items.length === 0 && !celebrating) {
    return (
      <>
        <Navbar />
        <Sidebar role={getAuthItem("role")} />
        <div className="vendor-dashboard-main">
          <EmptyState
            icon={<ShoppingCartOutlinedIcon sx={{ fontSize: 28, color: "text.disabled" }} />}
            title="Your cart is empty"
            description="Add products from the marketplace before checking out."
            action="Browse the marketplace"
            onAction={() => navigate("/marketplace")}
          />
        </div>
        <Footer />
      </>
    );
  }

  return (
    <>
      <Navbar />
      <Sidebar role={getAuthItem("role")} />

      <div className="vendor-dashboard-main">
        <div className="vendor-dashboard-header">
          <h1>Checkout</h1>
          <p>Confirm your delivery address and place your order</p>
        </div>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1.4fr 1fr" }, gap: 3 }}>
          <Card>
            <CardContent>
              <h3 style={{ marginTop: 0 }}>Delivery Address</h3>
              <TextField
                fullWidth
                multiline
                rows={3}
                placeholder="Flat/House no., street, city, state, PIN code"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
              />
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <h3 style={{ marginTop: 0 }}>Order Summary</h3>
              {items.map((item) => (
                <Box key={item.productId} sx={{ display: "flex", justifyContent: "space-between", mb: 1, fontSize: 14 }}>
                  <span>{item.title} &times; {item.quantity}</span>
                  <span>{item.currency} {(item.price * item.quantity).toLocaleString()}</span>
                </Box>
              ))}
              <Divider sx={{ my: 2 }} />
              <Box sx={{ display: "flex", justifyContent: "space-between", mb: 2 }}>
                <b>Total</b>
                <b>{currency} {totalPrice.toLocaleString()}</b>
              </Box>
              <Button fullWidth variant="contained" size="large" onClick={placeOrder} disabled={placing}>
                {placing ? <CircularProgress size={22} color="inherit" /> : "Place Order"}
              </Button>
            </CardContent>
          </Card>
        </Box>
      </div>

      <SuccessAnimation
        open={celebrating}
        title="Order Placed!"
        message={`${placedCount} item${placedCount === 1 ? "" : "s"} on the way`}
        primaryLabel="View Orders"
        onPrimary={() => navigate("/orders", { state: { justPlaced: true, count: placedCount } })}
        autoCloseMs={2200}
      />

      <Footer />
    </>
  );
}
