import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Fonts are bundled with the site (no Google Fonts request), so the page needs nothing
// from other origins except hero portraits.
import "@fontsource/big-shoulders-display/latin-800";
import "@fontsource/barlow/latin-400";
import "@fontsource/barlow/latin-600";
import { App } from "./App";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("index.html is missing #root");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
