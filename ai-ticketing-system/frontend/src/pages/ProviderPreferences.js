import { useEffect, useState } from "react";
import {
  Card, CardContent, Box, Checkbox, FormControlLabel, Button, Alert, CircularProgress,
} from "@mui/material";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import { getMyCategories, setMyCategories } from "../api/notifications";
import { getAuthItem } from "../utils/authSession";

// Mirrors the categories app/services/auto_router.py auto-assigns to tickets.
const TICKET_CATEGORIES = ["IT Support", "Electrical", "Plumbing", "Medical", "Security", "General"];

export default function ProviderPreferences() {
  const [selected, setSelected] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getMyCategories()
      .then((res) => setSelected(res.data?.categories || []))
      .finally(() => setLoading(false));
  }, []);

  function toggle(category) {
    setSaved(false);
    setSelected((prev) =>
      prev.includes(category) ? prev.filter((c) => c !== category) : [...prev, category]
    );
  }

  function save() {
    setSaving(true);
    setSaved(false);
    setMyCategories(selected)
      .then((res) => {
        setSelected(res.data?.categories || []);
        setSaved(true);
      })
      .finally(() => setSaving(false));
  }

  return (
    <>
      <Navbar />
      <Sidebar role={getAuthItem("role")} />

      <div className="provider-actions-main">
        <div className="provider-actions-header">
          <h1>My Categories</h1>
          <p>Pick which ticket categories you want to be alerted for.</p>
        </div>

        <Card>
          <CardContent>
            {loading ? (
              <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
                <CircularProgress />
              </Box>
            ) : (
              <>
                <Alert severity="info" sx={{ mb: 2 }}>
                  Leaving this empty means you'll be alerted for every category (generalist mode).
                  Selecting one or more categories limits your alerts to just those.
                </Alert>

                {saved && <Alert severity="success" sx={{ mb: 2 }}>Preferences saved</Alert>}

                <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
                  {TICKET_CATEGORIES.map((category) => (
                    <FormControlLabel
                      key={category}
                      control={
                        <Checkbox
                          checked={selected.includes(category)}
                          onChange={() => toggle(category)}
                        />
                      }
                      label={category}
                    />
                  ))}
                </Box>

                <Button
                  variant="contained"
                  onClick={save}
                  disabled={saving}
                  sx={{ mt: 3, textTransform: "none", fontWeight: 600 }}
                >
                  Save Preferences
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
