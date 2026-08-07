import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  Card, CardContent, Grid, Box, Chip, Button, CircularProgress, Alert,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField,
} from "@mui/material";
import HandshakeIcon from "@mui/icons-material/Handshake";
import ShoppingCartIcon from "@mui/icons-material/ShoppingCart";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import VendorInfoCard from "../components/VendorInfoCard";
import { getProduct } from "../api/products";
import { startNegotiation } from "../api/negotiations";
import { createOrder } from "../api/orders";
import "../styles/productDetail.css";

const PLACEHOLDER_IMAGE = "https://placehold.co/600x450?text=No+Image";

export default function ProductDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [product, setProduct] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

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

  async function buyNow() {
    setSubmitting(true);
    setError("");
    try {
      await createOrder({ product_id: product.id, quantity: 1 });
      navigate("/orders");
    } catch (err) {
      setError(err.response?.data?.detail || "Checkout failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />

      <div className="product-detail-main">
        {loading && (
          <Box className="product-detail-loading">
            <CircularProgress />
          </Box>
        )}

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
    </>
  );
}
