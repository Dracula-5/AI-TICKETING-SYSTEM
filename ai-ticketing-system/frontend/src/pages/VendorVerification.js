import { useEffect, useState } from "react";
import {
  Table, TableHead, TableCell, TableRow, TableBody, TableContainer, Paper,
  Chip, Button, Box, FormControlLabel, Switch, Alert,
} from "@mui/material";
import VerifiedIcon from "@mui/icons-material/Verified";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import Footer from "../components/Footer";
import LoadingState from "../components/LoadingState";
import { listVendors, verifyVendor } from "../api/vendors";
import "../styles/vendorDashboard.css";
import { useToast } from "../context/ToastContext";

export default function VendorVerification() {
  const [vendors, setVendors] = useState([]);
  const [unverifiedOnly, setUnverifiedOnly] = useState(true);
  const [success, setSuccess] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  function load() {
    listVendors(unverifiedOnly)
      .then((res) => setVendors(res.data))
      .catch(() => {
        setVendors([]);
        toast.error("Couldn't load vendors.");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unverifiedOnly]);

  async function handleVerify(vendorId) {
    setError("");
    try {
      await verifyVendor(vendorId);
      setSuccess("Vendor verified.");
      load();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to verify vendor");
    }
  }

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />

      <div className="vendor-dashboard-main">
        <div className="vendor-dashboard-header">
          <h1>Vendor Verification</h1>
          <p>Review and verify vendor shop accounts</p>
        </div>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

        <Box className="vendor-dashboard-toolbar">
          <FormControlLabel
            control={
              <Switch checked={unverifiedOnly} onChange={(e) => setUnverifiedOnly(e.target.checked)} />
            }
            label="Show unverified only"
          />
        </Box>

        {loading ? <LoadingState label="Loading vendors..." /> : (
        <TableContainer component={Paper} sx={{ borderRadius: "12px" }}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell><b>Shop Name</b></TableCell>
                <TableCell><b>Phone</b></TableCell>
                <TableCell><b>Address</b></TableCell>
                <TableCell><b>Rating</b></TableCell>
                <TableCell><b>Status</b></TableCell>
                <TableCell><b>Action</b></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {vendors.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} sx={{ textAlign: "center", py: 4, color: "#999" }}>
                    No vendors found.
                  </TableCell>
                </TableRow>
              ) : (
                vendors.map((v) => (
                  <TableRow key={v.id}>
                    <TableCell>{v.shop_name}</TableCell>
                    <TableCell>{v.phone_number}</TableCell>
                    <TableCell>{v.shop_address}</TableCell>
                    <TableCell>{v.rating_avg?.toFixed(1) ?? "-"}</TableCell>
                    <TableCell>
                      <Chip
                        label={v.is_verified ? "Verified" : "Pending"}
                        color={v.is_verified ? "success" : "warning"}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Button
                        size="small"
                        variant="outlined"
                        startIcon={<VerifiedIcon />}
                        disabled={v.is_verified}
                        onClick={() => handleVerify(v.id)}
                      >
                        {v.is_verified ? "Verified" : "Verify"}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
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
