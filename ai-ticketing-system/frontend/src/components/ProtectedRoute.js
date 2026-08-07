import { Navigate } from "react-router-dom";
import { getAuthItem } from "../utils/authSession";

export default function ProtectedRoute({ children }) {
  const token = getAuthItem("token");
  return token ? children : <Navigate to="/" />;
}
