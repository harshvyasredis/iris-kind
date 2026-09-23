/**
 * Vite app for agentic packs. base must match workbench nginx /app/.
 */
import { defineConfig } from 'vite';

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : {};
}

function send(response, status, body, headers = {}) {
  response.writeHead(status, { 'content-type': 'application/json', ...headers });
  response.end(JSON.stringify(body));
}

async function relay(response, url, init, exposedHeaders = []) {
  const upstream = await fetch(url, init);
  const text = await upstream.text();
  const headers = { 'content-type': upstream.headers.get('content-type') || 'application/json' };
  for (const name of exposedHeaders) {
    const value = upstream.headers.get(name);
    if (value) headers[name] = value;
  }
  response.writeHead(upstream.status, headers);
  response.end(text);
}

function irisProxy() {
  return {
    name: 'iris-workshop-proxy',
    configureServer(server) {
      server.middlewares.use(async (request, response, next) => {
        try {
          const path = new URL(request.url, 'http://workshop').pathname.replace(/^\/app/, '');
          if (!path.startsWith('/iris/')) return next();
          const irisPath = path.replace(/^\/iris/, '');
          if (request.method === 'GET' && irisPath === '/health') {
            return send(response, 200, {
              contextRetriever: Boolean(process.env.CR_MCP_URL && process.env.CR_AGENT_KEY),
              agentMemory: Boolean(process.env.RAM_URL && process.env.RAM_STORE_ID),
              langCache: Boolean(process.env.LC_URL && process.env.LC_TOKEN),
              openAI: Boolean(process.env.OPENAI_API_KEY),
            });
          }

          const body = await readJson(request);
          if (irisPath === '/cr') {
            const headers = {
              accept: 'application/json, text/event-stream',
              'content-type': 'application/json',
              'x-api-key': process.env.CR_AGENT_KEY,
            };
            if (request.headers['mcp-session-id']) {
              headers['mcp-session-id'] = request.headers['mcp-session-id'];
            }
            return relay(
              response,
              `${process.env.CR_MCP_URL}${process.env.CR_MCP_PATH || '/mcp'}`,
              { method: 'POST', headers, body: JSON.stringify(body) },
              ['mcp-session-id'],
            );
          }

          if (irisPath === '/lc/search' || irisPath === '/lc/set' || irisPath === '/lc/flush') {
            const root = `${process.env.LC_URL}/v1/caches/${encodeURIComponent(process.env.LC_CACHE_ID)}`;
            const target = irisPath === '/lc/search'
              ? `${root}/entries/search`
              : irisPath === '/lc/set' ? `${root}/entries` : `${root}/flush`;
            return relay(response, target, {
              method: 'POST',
              headers: {
                authorization: `Bearer ${process.env.LC_TOKEN}`,
                'content-type': 'application/json',
              },
              body: JSON.stringify(body),
            });
          }

          if (irisPath === '/ram') {
            const relative = String(body.path || '').replace(/^\/+/, '');
            if (!relative || relative.includes('..')) {
              return send(response, 400, { error: 'A safe RAM path is required.' });
            }
            return relay(
              response,
              `${process.env.RAM_URL}/v1/stores/${encodeURIComponent(process.env.RAM_STORE_ID)}/${relative}`,
              {
                method: body.method || 'POST',
                headers: { 'content-type': 'application/json' },
                body: ['GET', 'HEAD'].includes(body.method) ? undefined : JSON.stringify(body.body || {}),
              },
            );
          }

          if (irisPath === '/openai') {
            return relay(response, 'https://api.openai.com/v1/chat/completions', {
              method: 'POST',
              headers: {
                authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
                'content-type': 'application/json',
              },
              body: JSON.stringify(body),
            });
          }
          return send(response, 404, { error: `Unknown Iris route: ${irisPath}` });
        } catch (error) {
          return send(response, 502, { error: error.message });
        }
      });
    },
  };
}

export default defineConfig({
  base: '/app/',
  plugins: [irisProxy()],
  server: {
    host: true,
    port: 3000,
    strictPort: true,
    allowedHosts: true,
    watch: { usePolling: true },
  },
});
