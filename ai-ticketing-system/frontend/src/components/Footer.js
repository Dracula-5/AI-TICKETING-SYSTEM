import { Link } from "react-router-dom";
import "../styles/footer.css";

export default function Footer() {
  return (
    <footer className="app-footer">
      <span>&copy; {new Date().getFullYear()} AI Ticketing System</span>
      <span className="app-footer-links">
        <Link to="/privacy">Privacy Policy</Link>
        <Link to="/terms">Terms of Service</Link>
        <Link to="/security">Security</Link>
      </span>
    </footer>
  );
}
