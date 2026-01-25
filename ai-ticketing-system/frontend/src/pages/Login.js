import { useState } from "react";
import { Button, TextField, Card, CircularProgress, Alert } from "@mui/material";
import LockIcon from "@mui/icons-material/Lock";
import api from "../api/axios";
import "../styles/login.css";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function login() {
    if (!email || !password) {
      setError("Please fill in all fields");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const formData = new URLSearchParams();
      formData.append("username", email);
      formData.append("password", password);

      const res = await api.post("/auth/login", formData, {
        headers: {
          "Content-Type": "application/x-www-form-urlencoded"
        }
      });

      localStorage.setItem("token", res.data.access_token);
      localStorage.setItem("role", res.data.role);
      localStorage.setItem("tenant_id", res.data.tenant_id || 1);

      window.location.href = "/dashboard";
    } catch (err) {
      console.error(err);
      setError("Invalid email or password. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === "Enter") login();
  };

  return (
    <div className="login-container">
      <div className="login-gradient"></div>
      
      <div className="login-content">
        <Card className="login-card">
          <div className="login-header">
            <div className="login-icon-wrapper">
              <LockIcon className="login-icon" />
            </div>
            <h1>Welcome</h1>
            <p>AI Ticketing System</p>
          </div>

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          <TextField
            label="Email Address"
            type="email"
            fullWidth
            variant="outlined"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyPress={handleKeyPress}
            disabled={loading}
            placeholder="you@example.com"
            sx={{ mb: 2 }}
            autoFocus
          />

          <TextField
            label="Password"
            type="password"
            fullWidth
            variant="outlined"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyPress={handleKeyPress}
            disabled={loading}
            placeholder="••••••••"
            sx={{ mb: 3 }}
          />

          <Button
            variant="contained"
            fullWidth
            onClick={login}
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
            {loading ? <CircularProgress size={24} color="inherit" /> : "Sign In"}
          </Button>

          <p className="login-footer">
            Demo Credentials:<br/>
            Email: user@example.com<br/>
            Password: password
          </p>
        </Card>
      </div>
    </div>
  );
}
