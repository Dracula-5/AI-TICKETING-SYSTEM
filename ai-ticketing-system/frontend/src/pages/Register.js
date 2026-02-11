import { useState } from "react";
import { Button, TextField, Card, CircularProgress, Alert } from "@mui/material";
import PersonAddIcon from "@mui/icons-material/PersonAdd";
import api from "../api/axios";
import "../styles/login.css";

export default function Register() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function register() {
    if (!email || !password) {
      setError("Email and password are required");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const res = await api.post("/auth/register-simple", {
        email,
        password,
        name: name || undefined
      });

      localStorage.setItem("token", res.data.access_token);
      const me = await api.get("/auth/me");
      localStorage.setItem("role", me.data.role);
      localStorage.setItem("tenant_id", me.data.tenant_id);

      window.location.href = "/dashboard";
    } catch (err) {
      setError(err.response?.data?.detail || "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === "Enter") register();
  };

  return (
    <div className="login-container">
      <div className="login-gradient"></div>
      
      <div className="login-content">
        <Card className="login-card">
          <div className="login-header">
            <div className="login-icon-wrapper">
              <PersonAddIcon className="login-icon" />
            </div>
            <h1>Create Account</h1>
            <p>Join the AI Ticketing System</p>
          </div>

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          <TextField
            label="Name (optional)"
            fullWidth
            variant="outlined"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyPress={handleKeyPress}
            disabled={loading}
            placeholder="Your name"
            sx={{ mb: 2 }}
            autoFocus
          />

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
            placeholder="********"
            sx={{ mb: 3 }}
          />

          <Button
            variant="contained"
            fullWidth
            onClick={register}
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
            {loading ? <CircularProgress size={24} color="inherit" /> : "Create Account"}
          </Button>

          <p className="login-footer">
            Already have an account? <a href="/">Sign in</a>
          </p>
        </Card>
      </div>
    </div>
  );
}
