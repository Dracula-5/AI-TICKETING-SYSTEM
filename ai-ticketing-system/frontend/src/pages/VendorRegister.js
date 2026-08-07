import { useEffect, useState } from "react";
import {
  Button, TextField, Card, CircularProgress, Alert,
  FormControl, InputLabel, Select, MenuItem,
} from "@mui/material";
import StorefrontIcon from "@mui/icons-material/Storefront";
import { registerVendor, getCategoryAvailability } from "../api/vendors";
import { MARKETPLACE_CATEGORIES } from "../constants/marketplaceCategories";
import { setAuthSession } from "../utils/authSession";
import api from "../api/axios";
import "../styles/login.css";

export default function VendorRegister() {
  const [form, setForm] = useState({
    name: "", email: "", password: "",
    shop_name: "", phone_number: "", shop_address: "", description: "", category: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [availability, setAvailability] = useState({});

  useEffect(() => {
    getCategoryAvailability()
      .then((res) => {
        const map = {};
        (res.data || []).forEach((c) => { map[c.category] = c; });
        setAvailability(map);
      })
      .catch(() => {}); // fail open -- all categories stay selectable, server still enforces uniqueness
  }, []);

  function set(field) {
    return (e) => setForm({ ...form, [field]: e.target.value });
  }

  async function submit() {
    const required = ["name", "email", "password", "shop_name", "phone_number", "shop_address", "category"];
    if (required.some((f) => !form[f])) {
      setError("Please fill in all required fields");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const res = await registerVendor({ ...form, tenant_id: 1 });
      setAuthSession({ token: res.data.access_token });
      const me = await api.get("/auth/me");
      setAuthSession({
        user_id: me.data.id,
        name: me.data.name || "",
        email: me.data.email || "",
        role: me.data.role,
        tenant_id: me.data.tenant_id,
      });
      window.location.href = "/vendor/dashboard";
    } catch (err) {
      setError(err.response?.data?.detail || "Vendor registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-container">
      <div className="login-gradient"></div>

      <div className="login-content">
        <Card className="login-card">
          <div className="login-header">
            <div className="login-icon-wrapper">
              <StorefrontIcon className="login-icon" />
            </div>
            <h1>Become a Vendor</h1>
            <p>Set up your shop and start selling</p>
          </div>

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          <TextField label="Your Name" fullWidth variant="outlined" value={form.name}
            onChange={set("name")} disabled={loading} sx={{ mb: 2 }} autoFocus />
          <TextField label="Email Address" type="email" fullWidth variant="outlined" value={form.email}
            onChange={set("email")} disabled={loading} sx={{ mb: 2 }} />
          <TextField label="Password" type="password" fullWidth variant="outlined" value={form.password}
            onChange={set("password")} disabled={loading} sx={{ mb: 2 }} />
          <TextField label="Shop Name" fullWidth variant="outlined" value={form.shop_name}
            onChange={set("shop_name")} disabled={loading} sx={{ mb: 2 }} />

          <FormControl fullWidth sx={{ mb: 2 }} disabled={loading}>
            <InputLabel id="vendor-category-label">Category</InputLabel>
            <Select
              labelId="vendor-category-label"
              label="Category"
              value={form.category}
              onChange={set("category")}
            >
              {MARKETPLACE_CATEGORIES.map((category) => {
                const taken = availability[category] && !availability[category].available;
                return (
                  <MenuItem key={category} value={category} disabled={taken}>
                    {category}{taken ? ` (taken by ${availability[category].shop_name})` : ""}
                  </MenuItem>
                );
              })}
            </Select>
          </FormControl>

          <TextField label="Shop Phone Number" fullWidth variant="outlined" value={form.phone_number}
            onChange={set("phone_number")} disabled={loading} sx={{ mb: 2 }} />
          <TextField label="Shop Address" fullWidth variant="outlined" value={form.shop_address}
            onChange={set("shop_address")} disabled={loading} sx={{ mb: 2 }} />
          <TextField label="Shop Description (optional)" fullWidth multiline rows={2} variant="outlined"
            value={form.description} onChange={set("description")} disabled={loading} sx={{ mb: 3 }} />

          <Button
            variant="contained"
            fullWidth
            onClick={submit}
            disabled={loading}
            className="login-button"
            sx={{
              height: 48,
              fontSize: "1rem",
              fontWeight: 600,
              textTransform: "none",
              background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
              "&:hover": {
                background: "linear-gradient(135deg, #5568d3 0%, #6b3f8f 100%)",
              }
            }}
          >
            {loading ? <CircularProgress size={24} color="inherit" /> : "Create Shop"}
          </Button>

          <p className="login-footer">
            Just want to shop? <a href="/register">Sign up as a customer</a>
          </p>
        </Card>
      </div>
    </div>
  );
}
