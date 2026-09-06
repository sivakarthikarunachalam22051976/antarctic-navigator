import { defineConfig } from "vite";

export default defineConfig({
  server: {
    port: 5173,
    strictPort: true, // fail loudly instead of silently picking another port
  },
});
