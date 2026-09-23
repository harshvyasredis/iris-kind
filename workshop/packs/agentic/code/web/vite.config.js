/**
 * Vite app for agentic packs. base must match workbench nginx /app/.
 */
import { defineConfig } from 'vite';

export default defineConfig({
  base: '/app/',
  server: {
    host: true,
    port: 3000,
    strictPort: true,
    allowedHosts: true,
    watch: { usePolling: true },
  },
});
