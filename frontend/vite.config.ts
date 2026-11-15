import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, forward API calls to the FastAPI backend (uvicorn on :8000).
// The backend only accepts changes whose Origin is the app's own (APP_BASE_URL / APP_ORIGIN,
// default http://localhost). The dev server lives on another port, so the proxy presents the
// request as coming from that origin. This exists only in `npm run dev`: production serves the
// built files from FastAPI itself, and its Origin check is unchanged. The CSRF token is still required.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const APP_ORIGIN: string = (globalThis as any).process?.env?.LW_APP_ORIGIN ?? "http://localhost";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        configure: (proxy) => {
          proxy.on("proxyReq", (req) => {
            if (req.getHeader("origin")) req.setHeader("origin", APP_ORIGIN);
            if (req.getHeader("referer")) req.removeHeader("referer");
          });
        },
      },
    },
  },
});
