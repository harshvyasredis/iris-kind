# Continue and MCP

1. In the workbench, show the **Code** panel (VS Code).
2. Open the Continue chat view.
3. Ask: `List your MCP tools.`

You should see Agent Memory and LangCache tools. Context Retriever appears
only when that chart was installed.

The assistant model uses `OPENAI_API_KEY` from the Kind lab. MCP servers
talk to Iris over in-cluster DNS; you do not port-forward from this VS Code.
