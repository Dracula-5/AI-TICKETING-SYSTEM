import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Table, TableHead, TableCell, TableRow, TableBody, TableContainer, Paper, Chip, Button,
} from "@mui/material";
import ChatIcon from "@mui/icons-material/Chat";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import Footer from "../components/Footer";
import { listVendorInbox } from "../api/negotiations";
import "../styles/vendorDashboard.css";

function statusColor(status) {
  if (status === "accepted") return "success";
  if (status === "rejected") return "default";
  return "warning";
}

export default function VendorInbox() {
  const [sessions, setSessions] = useState([]);

  useEffect(() => {
    listVendorInbox().then((res) => setSessions(res.data)).catch(() => setSessions([]));
  }, []);

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />

      <div className="vendor-dashboard-main">
        <div className="vendor-dashboard-header">
          <h1>Negotiation Inbox</h1>
          <p>Active and past price negotiations across your products</p>
        </div>

        <TableContainer component={Paper} sx={{ borderRadius: "12px" }}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell><b>Product</b></TableCell>
                <TableCell><b>Customer</b></TableCell>
                <TableCell><b>Current Offer</b></TableCell>
                <TableCell><b>Status</b></TableCell>
                <TableCell><b>Started</b></TableCell>
                <TableCell><b>Action</b></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {sessions.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} sx={{ textAlign: "center", py: 4, color: "#999" }}>
                    No negotiations yet.
                  </TableCell>
                </TableRow>
              ) : (
                sessions.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell>{s.product.title}</TableCell>
                    <TableCell>Customer #{s.customer_id}</TableCell>
                    <TableCell>
                      {s.current_offer_price != null ? `${s.product.currency} ${s.current_offer_price.toLocaleString()}` : "-"}
                    </TableCell>
                    <TableCell>
                      <Chip label={s.status} color={statusColor(s.status)} size="small" />
                    </TableCell>
                    <TableCell>{new Date(s.created_at).toLocaleString()}</TableCell>
                    <TableCell>
                      <Button size="small" component={Link} to={`/negotiation/${s.id}`} startIcon={<ChatIcon />}>
                        Open Chat
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </div>
      <Footer />
    </>
  );
}
