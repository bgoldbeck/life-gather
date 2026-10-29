# Streamlined AI Assistant and MCP Integration

## Summary

Streamline the user-facing AI experience in LifeGather by:
1. Defaulting the chat dock to collapsed (off) on all screens so main views render full-width.
2. Adding a clear, expandable "AI assistant" toggle button on the dock rail.
3. Streamlining the assistant panel to focus purely on the AI assistant, removing the cluttered 11-mode Action dropdown ("Local assistant (no AI)", "Save memory", "Keyword search", "Request email scan", "Review receipt photo", etc.).
4. Hiding the confusing "Private credentials" form and vault key warning from Settings, replacing it with an easy MCP connection section.
5. Providing an easy stdio MCP adapter (`scripts/mcp/lifegather_mcp.py`) so external assistants (Google Antigravity, Claude Desktop, Cursor) can query LifeGather's memory graph with zero friction.

## Acceptance Criteria

1. On clean load, the assistant dock defaults to collapsed (`collapsed: true`), allowing main page views to occupy full width.
2. An "AI assistant" button/tab on the dock rail allows expanding and collapsing the assistant panel.
3. The assistant panel shows a clean conversation interface without the noisy Action select dropdown.
4. Settings does not display the disabled Private credentials form or vault key warning.
5. Existing frontend and backend unit tests continue to pass with updated test expectations.
