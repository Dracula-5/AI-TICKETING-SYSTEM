import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";
import theme from "./theme";
import { UIProvider } from "./context/UIContext";
import { NotificationProvider } from "./context/NotificationContext";
import "./index.css";
import "./App.css";
import "./styles/globals.css";

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <ThemeProvider theme={theme}>
    <UIProvider>
      <NotificationProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </NotificationProvider>
    </UIProvider>
  </ThemeProvider>
);
