import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  Card, CardContent, Grid, Box, Chip, Button, Alert,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField, IconButton,
} from "@mui/material";
import HandshakeIcon from "@mui/icons-material/Handshake";
import ShoppingCartIcon from "@mui/icons-material/ShoppingCart";
import AddShoppingCartIcon from "@mui/icons-material/AddShoppingCart";
import AddIcon from "@mui/icons-material/Add";
import RemoveIcon from "@mui/icons-material/Remove";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import Footer from "../components/Footer";
import VendorInfoCard from "../components/VendorInfoCard";
import LoadingState from "../components/LoadingState";
import { getProduct } from "../api/products";
import { startNegotiation } from "../api/negotiations";
import { useCart } from "../context/CartContext";
import "../styles/productDetail.css";

const PLACEHOLDER_IMAGE = "https://placehold.co/600x450?text=No+Image";

export default function ProductDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { addItem } = useCart();
  const [product, setProduct] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [quantity, setQuantity] = useState(1);
  const [addedMsg, setAddedMsg] = useState("");

  const [negotiateOpen, setNegotiateOpen] = useState(false);
  const [offerAmount, setOfferAmount] = useState("");
  const [offerMessage, setOfferMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    setLoading(true);
    getProduct(id)
      .then((res) => setProduct(res.data))
      .catch((err) => setError(err.response?.data?.detail || "Product not found"))
      .finally(() => setLoading(false));
  }, [id]);

  async function submitNegotiation() {
    const amount = Number(offerAmount);
    if (!amount || amount <= 0) {
      setSubmitError("Enter a valid offer amount");
      return;
    }
    setSubmitting(true);
    setSubmitError("");
    try {
      const res = await startNegotiation({
        product_id: product.id,
        amount,
        message: offerMessage || undefined,
      });
      navigate(`/negotiation/${res.data.id}`);
    } catch (err) {
      setSubmitError(err.response?.data?.detail || "Could not start negotiation");
    } finally {
      setSubmitting(false);
    }
  }

  function addToCart() {
    addItem(product, quantity);
    setAddedMsg(`Added ${quantity} to cart`);
    setTimeout(() => setAddedMsg(""), 2000);
  }

  function buyNow() {
    addItem(product, quantity);
    navigate("/checkout");
  }

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />

      <div className="product-detail-main">
        {loading && <LoadingState label="Loading product..." />}

        {!loading && error && (
          <Card className="product-detail-error">
            <CardContent>
              <p>{error}</p>
              <Button component={Link} to="/marketplace" variant="outlined">
                Back to Marketplace
              </Button>
            </CardContent>
          </Card>
        )}

        {!loading && product && (
          <Grid container spacing={4}>
            <Grid item xs={12} md={6}>
              <Card className="product-detail-image-card">
                <img
                  src={product.images?.[0]?.url || PLACEHOLDER_IMAGE}
                  alt={product.title}
                  className="product-detail-image"
                />
              </Card>
            </Grid>

            <Grid item xs={12} md={6}>
              <Box className="product-detail-info">
                {product.category && <Chip label={product.category} size="small" sx={{ mb: 1.5 }} />}
                <h1>{product.title}</h1>
                <p className="product-detail-description">{product.description}</p>

                <Box className="product-detail-price-row">
                  <span className="product-detail-price">
                    {product.currency} {product.price.toLocaleString()}
                  </span>
                  <Chip
                    label={product.stock_quantity > 0 ? `${product.stock_quantity} in stock` : "Out of stock"}
                    color={product.stock_quantity > 0 ? "success" : "default"}
                    size="small"
                  />
                </Box>

                {product.stock_quantity > 0 && (
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
                    <span style={{ fontSize: 14, color: "#64748b" }}>Quantity</span>
                    <IconButton
                      size="small"
                      onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                      disabled={quantity <= 1}
                      aria-label="Decrease quantity"
                    >
                      <RemoveIcon fontSize="small" />
                    </IconButton>
                    <TextField
                      size="small"
                      value={quantity}
                      sx={{ width: 56 }}
                      inputProps={{ style: { textAlign: "center" }, "aria-label": "Quantity" }}
                      onChange={(e) => setQuantity(Math.max(1, Math.min(Number(e.target.value) || 1, product.stock_quantity)))}
                    />
                    <IconButton
                      size="small"
                      onClick={() => setQuantity((q) => Math.min(product.stock_quantity, q + 1))}
                      disabled={quantity >= product.stock_quantity}
                      aria-label="Increase quantity"
                    >
                      <AddIcon fontSize="small" />
                    </IconButton>
                  </Box>
                )}

                {addedMsg && <Alert severity="success" sx={{ mb: 2 }}>{addedMsg}</Alert>}

                <Box className="product-detail-actions">
                  <Button
                    variant="contained"
                    size="large"
                    startIcon={<HandshakeIcon />}
                    disabled={product.stock_quantity === 0}
                    onClick={() => setNegotiateOpen(true)}
                  >
                    Negotiate Price
                  </Button>
                  <Button
                    variant="outlined"
                    size="large"
                    startIcon={<AddShoppingCartIcon />}
                    disabled={product.stock_quantity === 0}
                    onClick={addToCart}
                  >
                    Add to Cart
                  </Button>
                  <Button
                    variant="outlined"
                    size="large"
                    startIcon={<ShoppingCartIcon />}
                    disabled={product.stock_quantity === 0 || submitting}
                    onClick={buyNow}
                  >
                    Buy Now
                  </Button>
                </Box>

                <VendorInfoCard vendor={product.vendor} />
              </Box>
            </Grid>
          </Grid>
        )}

        <Dialog open={negotiateOpen} onClose={() => setNegotiateOpen(false)} maxWidth="xs" fullWidth>
          <DialogTitle>Make an Opening Offer</DialogTitle>
          <DialogContent>
            {submitError && <Alert severity="error" sx={{ mb: 2 }}>{submitError}</Alert>}
            <TextField
              fullWidth
              type="number"
              label={`Your offer (${product?.currency || ""})`}
              value={offerAmount}
              onChange={(e) => setOfferAmount(e.target.value)}
              sx={{ mb: 2, mt: 1 }}
              autoFocus
            />
            <TextField
              fullWidth
              multiline
              rows={2}
              label="Message (optional)"
              value={offerMessage}
              onChange={(e) => setOfferMessage(e.target.value)}
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setNegotiateOpen(false)}>Cancel</Button>
            <Button variant="contained" onClick={submitNegotiation} disabled={submitting}>
              {submitting ? "Starting..." : "Start Negotiating"}
            </Button>
          </DialogActions>
        </Dialog>
      </div>
      <Footer />
    </>
  );
}
