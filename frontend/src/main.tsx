import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { createApi } from "./api/client";
import { readToken } from "./api/token";
import { App } from "./app/App";

const root = document.getElementById("root");
if (!root) {
  throw new Error("#root が見つかりません");
}

// トークンは起動時に 1 回読み、API クライアントの中だけで持つ（Design Doc 3-5-1）
const token = readToken(document);
const api =
  token === null ? null : createApi({ token, baseUrl: window.location.origin });

createRoot(root).render(
  <StrictMode>
    <App api={api} />
  </StrictMode>,
);
