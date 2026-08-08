import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent, TextField, Button, Alert, Chip, Box, Divider } from "@mui/material";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import Footer from "../components/Footer";
import api from "../api/axios";
import { updateMyProfile, changeMyPassword } from "../api/users";
import { getMyVendorProfile, updateMyVendorProfile } from "../api/vendors";
import { getAuthItem, setAuthSession } from "../utils/authSession";
import "../styles/settings.css";

export default function Settings() {
  const role = getAuthItem("role");
  const [profile, setProfile] = useState({ name: "", email: "" });
  const [profileMsg, setProfileMsg] = useState("");
  const [profileError, setProfileError] = useState("");
  const [profileSaving, setProfileSaving] = useState(false);

  const [passwords, setPasswords] = useState({ current: "", next: "", confirm: "" });
  const [passwordMsg, setPasswordMsg] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordSaving, setPasswordSaving] = useState(false);

  const [shop, setShop] = useState(null);
  const [shopMsg, setShopMsg] = useState("");
  const [shopError, setShopError] = useState("");
  const [shopSaving, setShopSaving] = useState(false);

  useEffect(() => {
    api.get("/auth/me").then((res) => {
      setProfile({ name: res.data.name || "", email: res.data.email || "" });
    });
    if (role === "vendor") {
      getMyVendorProfile().then((res) => setShop(res.data)).catch(() => {});
    }
  }, [role]);

  async function saveProfile() {
    setProfileSaving(true);
    setProfileMsg("");
    setProfileError("");
    try {
      const res = await updateMyProfile(profile);
      setAuthSession({ name: res.data.name, email: res.data.email });
      setProfileMsg("Profile updated");
    } catch (err) {
      setProfileError(err.response?.data?.detail || "Could not update profile");
    } finally {
      setProfileSaving(false);
    }
  }

  async function savePassword() {
    setPasswordMsg("");
    setPasswordError("");
    if (passwords.next !== passwords.confirm) {
      setPasswordError("New password and confirmation don't match");
      return;
    }
    setPasswordSaving(true);
    try {
      await changeMyPassword({ current_password: passwords.current, new_password: passwords.next });
      setPasswordMsg("Password updated");
      setPasswords({ current: "", next: "", confirm: "" });
    } catch (err) {
      setPasswordError(err.response?.data?.detail || "Could not change password");
    } finally {
      setPasswordSaving(false);
    }
  }

  async function saveShop() {
    setShopSaving(true);
    setShopMsg("");
    setShopError("");
    try {
      const res = await updateMyVendorProfile({
        shop_name: shop.shop_name,
        phone_number: shop.phone_number,
        shop_address: shop.shop_address,
        description: shop.description,
      });
      setShop(res.data);
      setShopMsg("Shop profile updated");
    } catch (err) {
      setShopError(err.response?.data?.detail || "Could not update shop profile");
    } finally {
      setShopSaving(false);
    }
  }

  return (
    <>
      <Navbar />
      <Sidebar role={role} />

      <div className="settings-main">
        <div className="settings-header">
          <h1>Settings</h1>
          <p>Manage your account</p>
        </div>

        <Card sx={{ mb: 3 }}>
          <CardContent>
            <h3 style={{ marginTop: 0 }}>Profile</h3>
            {profileMsg && <Alert severity="success" sx={{ mb: 2 }}>{profileMsg}</Alert>}
            {profileError && <Alert severity="error" sx={{ mb: 2 }}>{profileError}</Alert>}
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 2, mb: 2 }}>
              <TextField label="Name" value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} />
              <TextField label="Email" value={profile.email} onChange={(e) => setProfile({ ...profile, email: e.target.value })} />
            </Box>
            <Button variant="contained" onClick={saveProfile} disabled={profileSaving}>
              Save Profile
            </Button>
          </CardContent>
        </Card>

        <Card sx={{ mb: 3 }}>
          <CardContent>
            <h3 style={{ marginTop: 0 }}>Change Password</h3>
            {passwordMsg && <Alert severity="success" sx={{ mb: 2 }}>{passwordMsg}</Alert>}
            {passwordError && <Alert severity="error" sx={{ mb: 2 }}>{passwordError}</Alert>}
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr 1fr" }, gap: 2, mb: 2 }}>
              <TextField
                label="Current Password" type="password"
                value={passwords.current} onChange={(e) => setPasswords({ ...passwords, current: e.target.value })}
              />
              <TextField
                label="New Password" type="password"
                value={passwords.next} onChange={(e) => setPasswords({ ...passwords, next: e.target.value })}
              />
              <TextField
                label="Confirm New Password" type="password"
                value={passwords.confirm} onChange={(e) => setPasswords({ ...passwords, confirm: e.target.value })}
              />
            </Box>
            <Button variant="contained" onClick={savePassword} disabled={passwordSaving}>
              Update Password
            </Button>
          </CardContent>
        </Card>

        {role === "vendor" && shop && (
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
                <h3 style={{ margin: 0 }}>Shop Profile</h3>
                <Chip label={shop.category} size="small" variant="outlined" />
              </Box>
              {shopMsg && <Alert severity="success" sx={{ mb: 2 }}>{shopMsg}</Alert>}
              {shopError && <Alert severity="error" sx={{ mb: 2 }}>{shopError}</Alert>}
              <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 2, mb: 2 }}>
                <TextField label="Shop Name" value={shop.shop_name} onChange={(e) => setShop({ ...shop, shop_name: e.target.value })} />
                <TextField label="Phone Number" value={shop.phone_number} onChange={(e) => setShop({ ...shop, phone_number: e.target.value })} />
                <TextField label="Shop Address" sx={{ gridColumn: "1 / -1" }} value={shop.shop_address} onChange={(e) => setShop({ ...shop, shop_address: e.target.value })} />
                <TextField label="Description" multiline rows={2} sx={{ gridColumn: "1 / -1" }} value={shop.description || ""} onChange={(e) => setShop({ ...shop, description: e.target.value })} />
              </Box>
              <Button variant="contained" onClick={saveShop} disabled={shopSaving}>
                Save Shop Profile
              </Button>
            </CardContent>
          </Card>
        )}

        {(role === "provider" || role === "service_provider") && (
          <Card>
            <CardContent>
              <h3 style={{ marginTop: 0 }}>Ticket Category Preferences</h3>
              <p style={{ color: "#64748b", marginBottom: 12 }}>
                Choose which ticket categories you're alerted for.
              </p>
              <Button component={Link} to="/provider/preferences" variant="outlined">
                Manage in My Categories →
              </Button>
            </CardContent>
          </Card>
        )}

        <Divider sx={{ my: 4 }} />
        <p style={{ color: "#94a3b8", fontSize: 13 }}>
          Read our <Link to="/privacy">Privacy Policy</Link>, <Link to="/terms">Terms of Service</Link>, and{" "}
          <Link to="/security">Security Policy</Link>.
        </p>
      </div>
      <Footer />
    </>
  );
}
