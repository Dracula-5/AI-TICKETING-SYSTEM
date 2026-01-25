import { useEffect, useState } from "react";
import Sidebar from "../components/Sidebar";
import Navbar from "../components/Navbar";
import api from "../api/axios";
import { Table, TableRow, TableHead, TableCell, TableBody, Card, CardContent, Paper, TableContainer, Chip, Box } from "@mui/material";
import PeopleIcon from "@mui/icons-material/People";
import "../styles/users.css";

export default function Users() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/users")
      .then(res => {
        setUsers(res.data || []);
        setLoading(false);
      })
      .catch(() => {
        console.error("Failed to load users");
        setLoading(false);
      });
  }, []);

  const getRoleColor = (role) => {
    if (role === "admin") return "error";
    if (role === "provider") return "warning";
    return "success";
  };

  if (loading) {
    return (
      <>
        <Navbar />
        <Sidebar role={localStorage.getItem("role")} />
        <div className="users-main" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
          <p>Loading users...</p>
        </div>
      </>
    );
  }

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />

      <div className="users-main">
        <div className="users-header">
          <h1>Users & Team Members</h1>
          <p>Manage users in your organization</p>
        </div>

        {/* Stats */}
        <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: 2, mb: 4 }}>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)" }}>
            <CardContent>
              <p>Total Users</p>
              <h2>{users.length}</h2>
            </CardContent>
          </Card>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)" }}>
            <CardContent>
              <p>Admins</p>
              <h2>{users.filter(u => u.role === "admin").length}</h2>
            </CardContent>
          </Card>
          <Card className="stat-card" style={{ background: "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)" }}>
            <CardContent>
              <p>Providers</p>
              <h2>{users.filter(u => u.role === "provider").length}</h2>
            </CardContent>
          </Card>
        </Box>

        <Card className="users-card">
          <CardContent>
            <TableContainer component={Paper} sx={{ borderRadius: "12px", boxShadow: "none" }}>
              <Table>
                <TableHead>
                  <TableRow sx={{ backgroundColor: "#f9f9f9" }}>
                    <TableCell sx={{ fontWeight: 700, color: "#333" }}>ID</TableCell>
                    <TableCell sx={{ fontWeight: 700, color: "#333" }}>Name</TableCell>
                    <TableCell sx={{ fontWeight: 700, color: "#333" }}>Email</TableCell>
                    <TableCell sx={{ fontWeight: 700, color: "#333" }}>Role</TableCell>
                    <TableCell sx={{ fontWeight: 700, color: "#333" }}>Department</TableCell>
                  </TableRow>
                </TableHead>

                <TableBody>
                  {users.length > 0 ? (
                    users.map(u => (
                      <TableRow 
                        key={u.id}
                        sx={{
                          transition: "all 0.3s ease",
                          "&:hover": {
                            background: "#f9f9f9",
                            boxShadow: "0 2px 8px rgba(0,0,0,0.05)"
                          },
                          borderBottom: "1px solid #e0e0e0"
                        }}
                      >
                        <TableCell sx={{ fontWeight: 600, color: "#667eea" }}>{u.id}</TableCell>
                        <TableCell sx={{ fontWeight: 500 }}>{u.name}</TableCell>
                        <TableCell>{u.email}</TableCell>
                        <TableCell>
                          <Chip
                            label={u.role}
                            color={getRoleColor(u.role)}
                            size="small"
                            sx={{ fontWeight: 600 }}
                          />
                        </TableCell>
                        <TableCell>
                          <span style={{ color: "#666", fontSize: "14px" }}>
                            {u.department || "-"}
                          </span>
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell colSpan={5} sx={{ textAlign: "center", py: 4, color: "#999" }}>
                        No users found
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>

            {/* Summary */}
            <Box sx={{ mt: 3, p: 2, backgroundColor: "#f9f9f9", borderRadius: "8px" }}>
              <p style={{ margin: 0, color: "#666", fontSize: "14px" }}>
                Total of <strong>{users.length}</strong> users in the system
              </p>
            </Box>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
