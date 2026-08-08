import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  Box, Card, CardContent, TextField, Button, Chip, CircularProgress, Alert, IconButton,
  Dialog, DialogTitle, DialogContent, DialogActions,
} from "@mui/material";
import SendIcon from "@mui/icons-material/Send";
import LocalOfferIcon from "@mui/icons-material/LocalOffer";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import Footer from "../components/Footer";
import { getNegotiation } from "../api/negotiations";
import { createOrder } from "../api/orders";
import useNegotiationSocket from "../hooks/useNegotiationSocket";
import { getAuthItem } from "../utils/authSession";
import { getSavedAddress, saveAddress } from "../utils/deliveryAddress";
import "../styles/negotiationChat.css";

export default function NegotiationChat() {
  const { id } = useParams();
  const navigate = useNavigate();
  const role = getAuthItem("role");

  const [session, setSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [text, setText] = useState("");
  const [offerAmount, setOfferAmount] = useState("");
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [addressDialogOpen, setAddressDialogOpen] = useState(false);
  const [addressInput, setAddressInput] = useState("");
  const bottomRef = useRef(null);

  const { liveMessages, connected, send } = useNegotiationSocket(id);

  useEffect(() => {
    getNegotiation(id)
      .then((res) => {
        setSession(res.data);
        setMessages(res.data.messages || []);
      })
      .catch((err) => setError(err.response?.data?.detail || "Could not load this negotiation"))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    if (liveMessages.length === 0) return;
    setMessages((prev) => {
      const existingIds = new Set(prev.map((m) => m.id));
      const newOnes = liveMessages.filter((m) => !existingIds.has(m.id));
      return newOnes.length ? [...prev, ...newOnes] : prev;
    });
  }, [liveMessages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const isAccepted = useMemo(() => messages.some((m) => m.message_type === "accept"), [messages]);
  const latestOffer = useMemo(() => {
    const priced = messages.filter((m) => m.amount !== null && m.amount !== undefined);
    return priced.length ? priced[priced.length - 1] : null;
  }, [messages]);
  const acceptedAmount = useMemo(() => {
    const accept = [...messages].reverse().find((m) => m.message_type === "accept");
    return accept?.amount;
  }, [messages]);

  function sendText() {
    if (!text.trim()) return;
    send({ type: "text", text: text.trim() });
    setText("");
  }

  function sendOffer() {
    const amount = Number(offerAmount);
    if (!amount || amount <= 0) return;
    send({ type: "offer", amount, text: text.trim() || undefined });
    setOfferAmount("");
    setText("");
  }

  function respondToOffer(type) {
    send({ type });
  }

  function checkout() {
    const saved = getSavedAddress();
    if (!saved) {
      setAddressInput("");
      setAddressDialogOpen(true);
      return;
    }
    placeOrder(saved);
  }

  async function placeOrder(address) {
    if (!session) return;
    setCheckoutLoading(true);
    try {
      await createOrder({
        product_id: session.product_id,
        quantity: 1,
        negotiation_session_id: session.id,
        delivery_address: address,
      });
      navigate("/orders");
    } catch (err) {
      setError(err.response?.data?.detail || "Checkout failed");
    } finally {
      setCheckoutLoading(false);
    }
  }

  function confirmAddressAndCheckout() {
    if (!addressInput.trim()) return;
    saveAddress(addressInput.trim());
    setAddressDialogOpen(false);
    placeOrder(addressInput.trim());
  }

  return (
    <>
      <Navbar />
      <Sidebar role={role} />

      <div className="negotiation-chat-main">
        {loading && (
          <Box className="negotiation-chat-loading">
            <CircularProgress />
          </Box>
        )}

        {!loading && error && !session && (
          <Alert severity="error">{error}</Alert>
        )}

        {!loading && session && (
          <>
            <Box className="negotiation-chat-header">
              <IconButton component={Link} to={`/product/${session.product_id}`} size="small" aria-label="Back to product">
                <ArrowBackIcon />
              </IconButton>
              <Box>
                <h2>{session.product.title}</h2>
                <p>
                  Listed at {session.product.currency} {session.product.price.toLocaleString()} &middot; sold by{" "}
                  {session.product.vendor.shop_name}
                </p>
              </Box>
              <Chip
                label={connected ? "Live" : "Connecting..."}
                color={connected ? "success" : "default"}
                size="small"
                className="negotiation-chat-status-chip"
              />
            </Box>

            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

            {isAccepted && (
              <Alert severity="success" sx={{ mb: 2 }} action={
                <Button color="inherit" size="small" onClick={checkout} disabled={checkoutLoading}>
                  {checkoutLoading ? "Placing Order..." : "Proceed to Checkout"}
                </Button>
              }>
                Deal reached at {session.product.currency} {acceptedAmount?.toLocaleString()}
              </Alert>
            )}

            <Card className="negotiation-chat-window">
              <CardContent className="negotiation-chat-scroll">
                {messages.map((m) => {
                  const mine = m.sender_role === role;
                  const isOffer = m.message_type === "offer" || m.message_type === "counter_offer";
                  const isLatestOpenOffer = isOffer && latestOffer?.id === m.id && !isAccepted;

                  return (
                    <Box key={m.id} className={`chat-bubble-row ${mine ? "mine" : "theirs"}`}>
                      <Box className={`chat-bubble ${mine ? "mine" : "theirs"} ${isOffer ? "offer" : ""}`}>
                        {isOffer && (
                          <Box className="chat-offer-amount">
                            <LocalOfferIcon fontSize="small" /> {session.product.currency} {m.amount?.toLocaleString()}
                          </Box>
                        )}
                        {m.text_content && <p>{m.text_content}</p>}
                        {m.message_type === "accept" && <p className="chat-accept-label">Offer accepted</p>}
                        {m.message_type === "reject" && <p className="chat-reject-label">Offer declined</p>}

                        {isLatestOpenOffer && !mine && (
                          <Box className="chat-offer-actions">
                            <Button size="small" variant="contained" onClick={() => respondToOffer("accept")}>
                              Accept
                            </Button>
                            <Button size="small" variant="outlined" onClick={() => respondToOffer("reject")}>
                              Decline
                            </Button>
                          </Box>
                        )}
                      </Box>
                    </Box>
                  );
                })}
                <div ref={bottomRef} />
              </CardContent>
            </Card>

            {!isAccepted && (
              <Box className="negotiation-chat-input-row">
                <TextField
                  fullWidth
                  size="small"
                  placeholder="Type a message..."
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && sendText()}
                />
                <TextField
                  size="small"
                  type="number"
                  placeholder="Offer amount"
                  className="negotiation-offer-input"
                  value={offerAmount}
                  onChange={(e) => setOfferAmount(e.target.value)}
                />
                <Button variant="outlined" onClick={sendOffer} disabled={!offerAmount}>
                  Make Offer
                </Button>
                <Button variant="contained" endIcon={<SendIcon />} onClick={sendText} disabled={!text.trim()}>
                  Send
                </Button>
              </Box>
            )}
          </>
        )}

        <Dialog open={addressDialogOpen} onClose={() => setAddressDialogOpen(false)} maxWidth="xs" fullWidth>
          <DialogTitle>Delivery Address</DialogTitle>
          <DialogContent>
            <TextField
              fullWidth
              multiline
              rows={3}
              autoFocus
              placeholder="Flat/House no., street, city, state, PIN code"
              value={addressInput}
              onChange={(e) => setAddressInput(e.target.value)}
              sx={{ mt: 1 }}
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setAddressDialogOpen(false)}>Cancel</Button>
            <Button variant="contained" onClick={confirmAddressAndCheckout} disabled={!addressInput.trim() || checkoutLoading}>
              Confirm & Place Order
            </Button>
          </DialogActions>
        </Dialog>
      </div>
      <Footer />
    </>
  );
}
