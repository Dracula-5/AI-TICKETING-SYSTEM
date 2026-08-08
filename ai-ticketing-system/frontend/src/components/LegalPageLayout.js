import { Link } from "react-router-dom";
import { Button, Card } from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { getAuthItem } from "../utils/authSession";
import "../styles/login.css";
import "../styles/legal.css";

export default function LegalPageLayout({ title, updated, children }) {
  const loggedIn = !!getAuthItem("token");

  return (
    <div className="login-container">
      <div className="login-gradient"></div>

      <div className="legal-content">
        <Card className="legal-card">
          <h1>{title}</h1>
          <p className="legal-updated">Last updated {updated}</p>

          {children}

          <Button
            component={Link}
            to={loggedIn ? "/dashboard" : "/"}
            startIcon={<ArrowBackIcon />}
            sx={{ mt: 3, textTransform: "none" }}
          >
            {loggedIn ? "Back to Dashboard" : "Back to Login"}
          </Button>
        </Card>
      </div>
    </div>
  );
}
