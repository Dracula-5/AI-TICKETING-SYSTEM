import { Link, useNavigate } from "react-router-dom";
import {
  Box, Card, CardContent, Table, TableHead, TableCell, TableRow, TableBody,
  TableContainer, Paper, IconButton, TextField, Button, Divider,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import RemoveIcon from "@mui/icons-material/Remove";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import Footer from "../components/Footer";
import { useCart } from "../context/CartContext";
import { getAuthItem } from "../utils/authSession";
import "../styles/vendorDashboard.css";

const PLACEHOLDER_IMAGE = "https://placehold.co/80x80?text=%20";

export default function Cart() {
  const navigate = useNavigate();
  const { items, totalPrice, removeItem, updateQuantity } = useCart();
  const currency = items[0]?.currency || "INR";

  const byVendor = items.reduce((groups, item) => {
    const key = item.vendorId ?? "unknown";
    (groups[key] = groups[key] || { vendorShopName: item.vendorShopName, lines: [] }).lines.push(item);
    return groups;
  }, {});

  return (
    <>
      <Navbar />
      <Sidebar role={getAuthItem("role")} />

      <div className="vendor-dashboard-main">
        <div className="vendor-dashboard-header">
          <h1>Your Cart</h1>
          <p>Review your items before checking out</p>
        </div>

        {items.length === 0 ? (
          <Card>
            <CardContent sx={{ textAlign: "center", py: 6, color: "#999" }}>
              Your cart is empty. <Link to="/marketplace">Browse the marketplace</Link>.
            </CardContent>
          </Card>
        ) : (
          <>
            {Object.entries(byVendor).map(([vendorId, group]) => (
              <Box key={vendorId} sx={{ mb: 3 }}>
                <h3 style={{ margin: "0 0 8px" }}>{group.vendorShopName || "Shop"}</h3>
                <TableContainer component={Paper} sx={{ borderRadius: "12px" }}>
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell><b>Item</b></TableCell>
                        <TableCell><b>Price</b></TableCell>
                        <TableCell><b>Quantity</b></TableCell>
                        <TableCell><b>Subtotal</b></TableCell>
                        <TableCell />
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {group.lines.map((item) => (
                        <TableRow key={item.productId}>
                          <TableCell>
                            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
                              <img
                                src={item.image || PLACEHOLDER_IMAGE}
                                alt={item.title}
                                style={{ width: 48, height: 48, objectFit: "cover", borderRadius: 6 }}
                              />
                              {item.title}
                            </Box>
                          </TableCell>
                          <TableCell>{item.currency} {item.price.toLocaleString()}</TableCell>
                          <TableCell>
                            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                              <IconButton size="small" onClick={() => updateQuantity(item.productId, item.quantity - 1)} disabled={item.quantity <= 1}>
                                <RemoveIcon fontSize="small" />
                              </IconButton>
                              <TextField
                                size="small"
                                value={item.quantity}
                                sx={{ width: 56 }}
                                inputProps={{ style: { textAlign: "center" } }}
                                onChange={(e) => updateQuantity(item.productId, Number(e.target.value) || 1)}
                              />
                              <IconButton size="small" onClick={() => updateQuantity(item.productId, item.quantity + 1)} disabled={item.quantity >= item.maxStock}>
                                <AddIcon fontSize="small" />
                              </IconButton>
                            </Box>
                          </TableCell>
                          <TableCell>{item.currency} {(item.price * item.quantity).toLocaleString()}</TableCell>
                          <TableCell>
                            <IconButton size="small" color="error" onClick={() => removeItem(item.productId)}>
                              <DeleteOutlineIcon fontSize="small" />
                            </IconButton>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Box>
            ))}

            <Card sx={{ maxWidth: 360, ml: "auto" }}>
              <CardContent>
                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                  <span>Total</span>
                  <b>{currency} {totalPrice.toLocaleString()}</b>
                </Box>
                <Divider sx={{ mb: 2 }} />
                <Button fullWidth variant="contained" size="large" onClick={() => navigate("/checkout")}>
                  Proceed to Checkout
                </Button>
              </CardContent>
            </Card>
          </>
        )}
      </div>
      <Footer />
    </>
  );
}
