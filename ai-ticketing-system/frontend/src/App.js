import { Routes, Route } from "react-router-dom";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Tickets from "./pages/Tickets";
import CreateTicket from "./pages/CreateTicket";
import AdminAssign from "./pages/AdminAssign";
import ProtectedRoute from "./components/ProtectedRoute";
import ProviderTickets from "./pages/ProviderTickets";
import TicketDetails from "./pages/TicketDetails";
import Users from "./pages/Users";
import ProviderActions from "./pages/ProviderActions";
import AdminPanel from "./pages/AdminPanel";
import AiTicketCreate from "./pages/AiTicketCreate";
import Register from "./pages/Register";



export default function App(){
  return(
    
      <Routes>
        <Route path="/" element={<Login/>}/>
        <Route path="/register" element={<Register/>}/>
        
        <Route path="/dashboard" element={<ProtectedRoute><Dashboard/></ProtectedRoute>}/>
        <Route path="/tickets" element={<ProtectedRoute><Tickets/></ProtectedRoute>}/>
        <Route path="/create-ticket" element={<ProtectedRoute><CreateTicket/></ProtectedRoute>}/>
        <Route path="/assign" element={<ProtectedRoute><AdminAssign/></ProtectedRoute>}/>
        <Route path="/provider-tickets" element={<ProtectedRoute><ProviderTickets/></ProtectedRoute>} />
        <Route path="/ticket/:id" element={<ProtectedRoute><TicketDetails/></ProtectedRoute>} />
        <Route path="/users" element={<ProtectedRoute><Users/></ProtectedRoute>} />
        <Route path="/provider-actions" element={<ProtectedRoute><ProviderActions/></ProtectedRoute>} />
        <Route path="/admin-panel" element={<ProtectedRoute><AdminPanel/></ProtectedRoute>} />
        <Route path="/ai-ticket" element={<ProtectedRoute><AiTicketCreate/></ProtectedRoute>} />




      </Routes>
    
  )
}
