import { useState, useRef, useEffect } from "react";
import {
  Button,
  TextField,
  Card,
  CardContent,
  IconButton,
  CircularProgress
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import api from "../api/axios";

export default function ChatBot() {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  const tenant_id = Number(localStorage.getItem("tenant_id"));
  const chatRef = useRef(null);

  // Auto scroll to bottom
  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages]);

  async function send() {
    if (!text.trim() || loading) return;

    setMessages(prev => [...prev, { me: true, text }]);
    setText("");
    setLoading(true);

    try {
      const title =
        text.split(".")[0].substring(0, 40) || "AI Generated Ticket";

      const res = await api.post("/tickets", {
        title,
        description: text,
        priority: "low",
        tenant_id: tenant_id
      });

      setMessages(prev => [
        ...prev,
        {
          me: false,
          text: `✅ Ticket Created Successfully!\n\n🆔 ID: ${res.data.id}\n📂 Category: ${res.data.category}\n⚡ Priority: ${res.data.priority}`,
        },
      ]);
    } catch (err) {
      setMessages(prev => [
        ...prev,
        {
          me: false,
          text: "❌ Failed to create ticket.\nPlease login again and try.",
        },
      ]);
    }

    setLoading(false);
  }

  if (!open)
    return (
      <Button
        variant="contained"
        style={{ position: "fixed", right: 20, bottom: 20 }}
        onClick={() => setOpen(true)}
      >
        Chat Assistant 🤖
      </Button>
    );

  return (
    <Card
      style={{
        position: "fixed",
        right: 20,
        bottom: 20,
        width: 340,
        borderRadius: 12,
      }}
      elevation={8}
    >
      <CardContent>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <h3>AI Support Assistant</h3>
          <IconButton onClick={() => setOpen(false)}>
            <CloseIcon />
          </IconButton>
        </div>

        <div
          ref={chatRef}
          style={{
            height: 260,
            overflowY: "auto",
            padding: 10,
            background: "#f5f5f5",
            borderRadius: 8,
            marginBottom: 10
          }}
        >
          {messages.map((m, i) => (
            <p
              key={i}
              style={{
                textAlign: m.me ? "right" : "left",
                background: m.me ? "#1976d2" : "#e0e0e0",
                color: m.me ? "white" : "black",
                padding: 8,
                borderRadius: 10,
                maxWidth: "85%",
                marginLeft: m.me ? "auto" : "0",
                whiteSpace: "pre-line"
              }}
            >
              {m.text}
            </p>
          ))}

          {loading && (
            <p style={{ textAlign: "left", color: "#555" }}>
              <CircularProgress size={18} /> Creating ticket...
            </p>
          )}
        </div>

        <TextField
          fullWidth
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Describe your issue in natural language..."
          onKeyDown={(e) => e.key === "Enter" && send()}
        />

        <Button
          fullWidth
          variant="contained"
          style={{ marginTop: 10 }}
          onClick={send}
          disabled={loading}
        >
          {loading ? "Processing..." : "Send"}
        </Button>
      </CardContent>
    </Card>
  );
}
