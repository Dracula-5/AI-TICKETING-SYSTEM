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
import VendorRegister from "./pages/VendorRegister";
import Marketplace from "./pages/Marketplace";
import ProductDetail from "./pages/ProductDetail";
import VendorDashboard from "./pages/VendorDashboard";
import NegotiationChat from "./pages/NegotiationChat";
import VendorInbox from "./pages/VendorInbox";
import Orders from "./pages/Orders";
import VendorVerification from "./pages/VendorVerification";
import ProductModeration from "./pages/ProductModeration";
import AdminAnalytics from "./pages/AdminAnalytics";
import ProviderPreferences from "./pages/ProviderPreferences";
import NotFound from "./pages/NotFound";



export default function App(){
  return(
    
      <Routes>
        <Route path="/" element={<Login/>}/>
        <Route path="/register" element={<Register/>}/>
        <Route path="/vendor/register" element={<VendorRegister/>}/>

        <Route path="/dashboard" element={<ProtectedRoute><Dashboard/></ProtectedRoute>}/>
        <Route path="/marketplace" element={<ProtectedRoute><Marketplace/></ProtectedRoute>}/>
        <Route path="/product/:id" element={<ProtectedRoute><ProductDetail/></ProtectedRoute>}/>
        <Route path="/vendor/dashboard" element={<ProtectedRoute><VendorDashboard/></ProtectedRoute>}/>
        <Route path="/negotiation/:id" element={<ProtectedRoute><NegotiationChat/></ProtectedRoute>}/>
        <Route path="/vendor/inbox" element={<ProtectedRoute><VendorInbox/></ProtectedRoute>}/>
        <Route path="/orders" element={<ProtectedRoute><Orders/></ProtectedRoute>}/>
        <Route path="/tickets" element={<ProtectedRoute><Tickets/></ProtectedRoute>}/>
        <Route path="/create-ticket" element={<ProtectedRoute><CreateTicket/></ProtectedRoute>}/>
        <Route path="/assign" element={<ProtectedRoute><AdminAssign/></ProtectedRoute>}/>
        <Route path="/provider-tickets" element={<ProtectedRoute><ProviderTickets/></ProtectedRoute>} />
        <Route path="/ticket/:id" element={<ProtectedRoute><TicketDetails/></ProtectedRoute>} />
        <Route path="/users" element={<ProtectedRoute><Users/></ProtectedRoute>} />
        <Route path="/provider-actions" element={<ProtectedRoute><ProviderActions/></ProtectedRoute>} />
        <Route path="/admin-panel" element={<ProtectedRoute><AdminPanel/></ProtectedRoute>} />
        <Route path="/ai-ticket" element={<ProtectedRoute><AiTicketCreate/></ProtectedRoute>} />
        <Route path="/admin/vendors" element={<ProtectedRoute><VendorVerification/></ProtectedRoute>} />
        <Route path="/admin/products" element={<ProtectedRoute><ProductModeration/></ProtectedRoute>} />
        <Route path="/admin/analytics" element={<ProtectedRoute><AdminAnalytics/></ProtectedRoute>} />
        <Route path="/provider/preferences" element={<ProtectedRoute><ProviderPreferences/></ProtectedRoute>} />

        <Route path="*" element={<NotFound/>} />

      </Routes>
    
  )
}
