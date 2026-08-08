import { useEffect, useState } from "react";
import {
  Table, TableHead, TableCell, TableRow, TableBody, TableContainer, Paper,
  Card, CardContent, Box, Button, TextField, Chip, Alert, Dialog, DialogTitle,
  DialogContent, DialogActions, Grid, FormControlLabel, Switch, MenuItem, Select, FormControl,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import Footer from "../components/Footer";
import LoadingState from "../components/LoadingState";
import { listMyProducts, createProduct, updateProduct, deleteProduct } from "../api/products";
import { getMyVendorProfile } from "../api/vendors";
import { listVendorOrders, updateOrderStatus } from "../api/orders";
import { getVendorAnalytics } from "../api/analytics";
import "../styles/vendorDashboard.css";
import { useToast } from "../context/ToastContext";

const ANALYTICS_CARDS = [
  { key: "total_products", label: "Products" },
  { key: "total_views", label: "Views" },
  { key: "total_orders", label: "Orders" },
  { key: "total_revenue", label: "Revenue", prefix: "₹" },
  { key: "negotiation_success_rate_pct", label: "Deal Success Rate", suffix: "%" },
];

const EMPTY_FORM = {
  title: "", description: "", price: "", stock_quantity: "", image_urls: "",
  floor_price: "", auto_negotiate_enabled: false,
};

const ORDER_STATUSES = ["pending", "confirmed", "shipped", "completed", "cancelled"];

export default function VendorDashboard() {
  const [vendor, setVendor] = useState(null);
  const [products, setProducts] = useState([]);
  const [orders, setOrders] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  function loadAll() {
    let anyFailed = false;
    Promise.allSettled([
      getMyVendorProfile().then((res) => setVendor(res.data)).catch(() => { anyFailed = true; setVendor(null); }),
      listMyProducts().then((res) => setProducts(res.data)).catch(() => { anyFailed = true; setProducts([]); }),
      listVendorOrders().then((res) => setOrders(res.data)).catch(() => { anyFailed = true; setOrders([]); }),
      getVendorAnalytics().then((res) => setAnalytics(res.data)).catch(() => { anyFailed = true; setAnalytics(null); }),
    ]).then(() => {
      setLoading(false);
      if (anyFailed) toast.error("Some dashboard data couldn't be loaded.");
    });
  }

  async function handleOrderStatusChange(orderId, newStatus) {
    try {
      await updateOrderStatus(orderId, newStatus);
      setOrders((prev) => prev.map((o) => (o.id === orderId ? { ...o, status: newStatus } : o)));
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to update order status");
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openCreateDialog() {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  }

  function openEditDialog(p) {
    setEditingId(p.id);
    setForm({
      title: p.title,
      description: p.description,
      price: String(p.price),
      stock_quantity: String(p.stock_quantity),
      image_urls: (p.images || []).map((i) => i.url).join(", "),
      floor_price: p.floor_price != null ? String(p.floor_price) : "",
      auto_negotiate_enabled: !!p.auto_negotiate_enabled,
    });
    setDialogOpen(true);
  }

  async function submitForm() {
    setError("");
    const payload = {
      title: form.title,
      description: form.description,
      price: Number(form.price),
      stock_quantity: Number(form.stock_quantity) || 0,
      image_urls: form.image_urls
        ? form.image_urls.split(",").map((s) => s.trim()).filter(Boolean)
        : [],
      floor_price: form.floor_price ? Number(form.floor_price) : undefined,
      auto_negotiate_enabled: form.auto_negotiate_enabled,
    };

    try {
      if (editingId) {
        await updateProduct(editingId, payload);
        setSuccess("Product updated.");
      } else {
        await createProduct(payload);
        setSuccess("Product created.");
      }
      setDialogOpen(false);
      loadAll();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to save product");
    }
  }

  async function handleDelete(productId) {
    try {
      await deleteProduct(productId);
      setSuccess("Product deleted.");
      loadAll();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to delete product");
    }
  }

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />

      <div className="vendor-dashboard-main">
        <div className="vendor-dashboard-header">
          <h1>Vendor Dashboard</h1>
          <p>Manage your shop and product listings</p>
        </div>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

        {vendor && (
          <Card className="vendor-dashboard-shop-card">
            <CardContent>
              <h3>{vendor.shop_name}</h3>
              <p>{vendor.phone_number} &middot; {vendor.shop_address}</p>
              <Box sx={{ display: "flex", gap: 1 }}>
                <Chip
                  label={vendor.is_verified ? "Verified" : "Pending Verification"}
                  color={vendor.is_verified ? "success" : "warning"}
                  size="small"
                />
                {vendor.category && (
                  <Chip label={vendor.category} variant="outlined" size="small" />
                )}
              </Box>
            </CardContent>
          </Card>
        )}

        {analytics && (
          <Grid container spacing={2} sx={{ mb: 4 }}>
            {ANALYTICS_CARDS.map((c) => (
              <Grid item xs={6} sm={4} md={2.4} key={c.key}>
                <Card className="vendor-dashboard-shop-card">
                  <CardContent>
                    <p style={{ margin: 0, color: "#999", fontSize: 13 }}>{c.label}</p>
                    <h2 style={{ margin: "4px 0 0 0" }}>
                      {c.prefix || ""}{analytics[c.key]?.toLocaleString?.() ?? analytics[c.key]}{c.suffix || ""}
                    </h2>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}

        <Box className="vendor-dashboard-toolbar">
          <h2>Your Products ({products.length})</h2>
          <Button variant="contained" startIcon={<AddIcon />} onClick={openCreateDialog}>
            Add Product
          </Button>
        </Box>

        {loading ? <LoadingState label="Loading your shop..." /> : (
        <TableContainer component={Paper} sx={{ borderRadius: "12px" }}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell><b>Title</b></TableCell>
                <TableCell><b>Category</b></TableCell>
                <TableCell><b>Price</b></TableCell>
                <TableCell><b>Stock</b></TableCell>
                <TableCell><b>Status</b></TableCell>
                <TableCell><b>Views</b></TableCell>
                <TableCell><b>Actions</b></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {products.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} sx={{ textAlign: "center", py: 4, color: "#999" }}>
                    No products yet. Click "Add Product" to create your first listing.
                  </TableCell>
                </TableRow>
              ) : (
                products.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell>{p.title}</TableCell>
                    <TableCell>{p.category || "-"}</TableCell>
                    <TableCell>{p.currency} {p.price.toLocaleString()}</TableCell>
                    <TableCell>{p.stock_quantity}</TableCell>
                    <TableCell>
                      <Chip label={p.status} size="small" />
                    </TableCell>
                    <TableCell>{p.views_count}</TableCell>
                    <TableCell>
                      <Button size="small" startIcon={<EditIcon />} onClick={() => openEditDialog(p)}>
                        Edit
                      </Button>
                      <Button size="small" color="error" startIcon={<DeleteIcon />} onClick={() => handleDelete(p.id)}>
                        Delete
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
        )}

        <Box className="vendor-dashboard-toolbar" sx={{ mt: 5 }}>
          <h2>Received Orders ({orders.length})</h2>
        </Box>

        {!loading && (
        <TableContainer component={Paper} sx={{ borderRadius: "12px" }}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell><b>Product</b></TableCell>
                <TableCell><b>Qty</b></TableCell>
                <TableCell><b>Total</b></TableCell>
                <TableCell><b>Status</b></TableCell>
                <TableCell><b>Placed</b></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {orders.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} sx={{ textAlign: "center", py: 4, color: "#999" }}>
                    No orders yet.
                  </TableCell>
                </TableRow>
              ) : (
                orders.map((o) => (
                  <TableRow key={o.id}>
                    <TableCell>
                      {o.product.title}
                      {o.delivery_address && (
                        <p style={{ margin: "2px 0 0", fontSize: 12, color: "#94a3b8" }}>
                          Ship to: {o.delivery_address}
                        </p>
                      )}
                    </TableCell>
                    <TableCell>{o.quantity}</TableCell>
                    <TableCell>{o.product.currency} {o.total_price.toLocaleString()}</TableCell>
                    <TableCell>
                      <FormControl size="small" sx={{ minWidth: 140 }}>
                        <Select value={o.status} onChange={(e) => handleOrderStatusChange(o.id, e.target.value)}>
                          {ORDER_STATUSES.map((s) => (
                            <MenuItem key={s} value={s}>{s}</MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </TableCell>
                    <TableCell>{new Date(o.created_at).toLocaleString()}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
        )}

        <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
          <DialogTitle>{editingId ? "Edit Product" : "Add Product"}</DialogTitle>
          <DialogContent>
            <Grid container spacing={2} sx={{ mt: 0.5 }}>
              <Grid item xs={12}>
                <TextField fullWidth label="Title" value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })} />
              </Grid>
              <Grid item xs={12}>
                <TextField fullWidth multiline rows={3} label="Description" value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </Grid>
              <Grid item xs={12}>
                <Alert severity="info" sx={{ py: 0 }}>
                  Products are automatically listed under your shop's category: <b>{vendor?.category || "—"}</b>
                </Alert>
              </Grid>
              <Grid item xs={6}>
                <TextField fullWidth type="number" label="Price" value={form.price}
                  onChange={(e) => setForm({ ...form, price: e.target.value })} />
              </Grid>
              <Grid item xs={6}>
                <TextField fullWidth type="number" label="Stock Quantity" value={form.stock_quantity}
                  onChange={(e) => setForm({ ...form, stock_quantity: e.target.value })} />
              </Grid>
              <Grid item xs={12}>
                <TextField fullWidth label="Image URLs (comma-separated)" value={form.image_urls}
                  onChange={(e) => setForm({ ...form, image_urls: e.target.value })} />
              </Grid>
              <Grid item xs={6}>
                <TextField fullWidth type="number" label="Floor Price (bargaining minimum)" value={form.floor_price}
                  helperText="Hidden from customers. Defaults to 80% of price if left blank."
                  onChange={(e) => setForm({ ...form, floor_price: e.target.value })} />
              </Grid>
              <Grid item xs={6} sx={{ display: "flex", alignItems: "center" }}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={form.auto_negotiate_enabled}
                      onChange={(e) => setForm({ ...form, auto_negotiate_enabled: e.target.checked })}
                    />
                  }
                  label="AI auto-negotiate"
                />
              </Grid>
            </Grid>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button variant="contained" onClick={submitForm}>
              {editingId ? "Save Changes" : "Create Product"}
            </Button>
          </DialogActions>
        </Dialog>
      </div>
      <Footer />
    </>
  );
}
