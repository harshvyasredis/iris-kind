/**
 * Vite dev server configuration for workshop environments.
 *
 * This app runs in a Docker container and is accessed through the
 * workbench nginx proxy at /app/.
 *
 * Key considerations:
 *
 * - base: '/app/' — Must match the path in workbench/nginx.conf. If you
 *   change the proxy path there, update it here too. This ensures assets
 *   and HMR WebSocket connections use the correct path.
 *
 * - host: true — Listen on all interfaces (0.0.0.0) so the container is
 *   reachable from outside, not just localhost inside the container.
 *
 * - allowedHosts: true — PS Portal's proxy rewrites the Host header to just
 *   the VM identifier (e.g. "rl-s-labs-xyz"), stripping the domain. Since
 *   this is dynamic and unpredictable, we cannot use a pattern-based allowlist.
 *
 * - usePolling: true — Required for HMR on Docker volumes mounted from
 *   macOS/Windows, where native filesystem events don't propagate.
 */
import { defineConfig } from 'vite';

export default defineConfig({
  base: '/app/', // Must match the path in workbench/nginx.conf and workbench/config.js
  server: {
    host: true,
    port: 3000,
    strictPort: true,
    allowedHosts: true,
    watch: {
      usePolling: true
    }
  }
});

