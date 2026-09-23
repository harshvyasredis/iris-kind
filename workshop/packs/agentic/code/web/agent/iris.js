function parseMcp(text) {
  if (!text) return {};
  if (!text.startsWith('event:') && !text.startsWith('data:')) return JSON.parse(text);
  const data = text
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trim())
    .filter((line) => line && line !== '[DONE]');
  return data.length ? JSON.parse(data.at(-1)) : {};
}

async function mcp(message, sessionId) {
  const response = await fetch('/app/iris/cr', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'application/json, text/event-stream',
      ...(sessionId ? { 'mcp-session-id': sessionId } : {}),
    },
    body: JSON.stringify(message),
  });
  if (!response.ok) throw new Error(`Context Retriever returned ${response.status}`);
  return {
    message: parseMcp(await response.text()),
    sessionId: response.headers.get('mcp-session-id') || sessionId,
  };
}

function argumentsFor(tool, { query, filters, limit }) {
  const properties = tool.inputSchema?.properties || {};
  const args = {};
  for (const name of Object.keys(properties)) {
    const normalized = name.toLowerCase();
    if (['query', 'q', 'search', 'search_text', 'searchtext', 'text', 'prompt'].includes(normalized)) {
      args[name] = query;
    } else if (['limit', 'top_k', 'topk', 'k'].includes(normalized)) {
      args[name] = limit;
    } else if (normalized.includes('filter')) {
      args[name] = filters;
    } else if (Object.hasOwn(filters, name)) {
      args[name] = filters[name];
    }
  }
  if (!Object.keys(args).length) args.query = query;
  return args;
}

function decodeToolResult(result) {
  const content = result?.content || result?.result?.content || [];
  const texts = content.map((item) => item.text).filter(Boolean);
  if (!texts.length) return result;
  try {
    return JSON.parse(texts.join('\n'));
  } catch {
    return texts.join('\n');
  }
}

export async function searchContext({ entity, query, filters = {}, limit = 3 }) {
  let sequence = 1;
  const initialized = await mcp({
    jsonrpc: '2.0',
    id: sequence++,
    method: 'initialize',
    params: {
      protocolVersion: '2025-03-26',
      capabilities: {},
      clientInfo: { name: 'gateway-arena', version: '1.0.0' },
    },
  });
  const listed = await mcp(
    { jsonrpc: '2.0', id: sequence++, method: 'tools/list', params: {} },
    initialized.sessionId,
  );
  const tools = listed.message?.result?.tools || [];
  const entityName = entity.toLowerCase();
  const tagConditions = Object.entries(filters).map(([field, value]) => ({
    field,
    value: String(value),
  }));
  let tool;
  let toolArguments;
  if (tagConditions.length) {
    tool = tools.find((candidate) => candidate.name === `filter_${entityName}`);
    toolArguments = { tag_conditions: tagConditions, limit };
  } else {
    tool = tools.find((candidate) => {
      const name = candidate.name.toLowerCase();
      return name.includes(entityName) && name.startsWith('search_');
    });
    toolArguments = tool ? argumentsFor(tool, { query, filters, limit }) : {};
  }
  if (!tool) throw new Error(`No Context Retriever tool found for ${entity}`);

  const called = await mcp(
    {
      jsonrpc: '2.0',
      id: sequence,
      method: 'tools/call',
      params: {
        name: tool.name,
        arguments: toolArguments,
      },
    },
    initialized.sessionId,
  );
  if (called.message?.error) throw new Error(called.message.error.message);
  return decodeToolResult(called.message?.result);
}

async function jsonPost(path, body) {
  const response = await fetch(`/app/iris/${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `${path} returned ${response.status}`);
  return result;
}

export const langCache = {
  search: (body) => jsonPost('lc/search', body),
  set: (body) => jsonPost('lc/set', body),
};

export const agentMemory = {
  request: (path, body = {}, method = 'POST') =>
    jsonPost('ram', { path, body, method }),
};

export async function answerWithContext(question, context) {
  return jsonPost('openai', {
    model: 'gpt-4o',
    temperature: 0,
    max_tokens: 180,
    messages: [
      {
        role: 'system',
        content: (
          'Answer only from the supplied gateway context. Cite record ids. ' +
          'If the context is insufficient, say so.'
        ),
      },
      {
        role: 'user',
        content: `Question:\n${question}\n\nGateway context:\n${context}`,
      },
    ],
  });
}
