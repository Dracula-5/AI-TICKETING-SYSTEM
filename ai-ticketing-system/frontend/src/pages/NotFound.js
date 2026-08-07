import { Link } from "react-router-dom";
import { Button, Card } from "@mui/material";
import HomeRoundedIcon from "@mui/icons-material/HomeRounded";
import { getAuthItem } from "../utils/authSession";
import "../styles/login.css";

export default function NotFound() {
  const loggedIn = !!getAuthItem("token");

  return (
    <div className="login-container">
      <div className="login-gradient"></div>

      <div className="login-content">
        <Card className="login-card" style={{ textAlign: "center" }}>
          <div className="login-header">
            <h1 style={{ fontSize: "3.5rem", margin: 0 }}>404</h1>
            <p>This page doesn't exist, or you don't have access to it.</p>
          </div>

          <Button
            variant="contained"
            fullWidth
            component={Link}
            to={loggedIn ? "/dashboard" : "/"}
            startIcon={<HomeRoundedIcon />}
            className="login-button"
            sx={{
              height: 48,
              fontSize: "1rem",
              fontWeight: 600,
              background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
              "&:hover": {
                background: "linear-gradient(135deg, #5568d3 0%, #6b3f8f 100%)",
              }
            }}
          >
            {loggedIn ? "Back to Dashboard" : "Back to Login"}
          </Button>
        </Card>
      </div>
    </div>
  );
}
