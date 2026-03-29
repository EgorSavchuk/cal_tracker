import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

// Expand Telegram WebApp to full height
if (window.Telegram?.WebApp) {
  window.Telegram.WebApp.expand();
  window.Telegram.WebApp.ready();
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>
);
