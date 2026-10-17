# Local source-code graph

Graphify is the repository's source relationship navigation tool. Consult it for code discovery and relationship searches as specified in `AGENTS.md`. It is not part of the application, personal-memory storage, or Docker image.

Tested version: `graphifyy==0.9.92`, installed in an isolated uv tool environment:

```powershell
uv tool install graphifyy==0.9.92
```

From the repository root, build and query a local graph:

```powershell
$env:GRAPHIFY_NO_AUTO_REFRESH = '1'
graphify extract . --code-only --max-workers 1 --max-concurrency 1 --no-cluster
graphify export html
graphify query 'create_app Settings' --budget 1500
```

Open `graphify-out/graph.html` to explore the graph. Regenerate it after source changes. Outputs are ignored by Git.

For behavior or relationship searches, start with a scoped `graphify query`, then read the matching source and tests. Use `rg` first for exact text, identifiers, and file paths, and as a fallback when graph coverage is incomplete. A graph miss does not establish that code is absent.

Refresh after completing and verifying each feature that changes code, and after major refactors, file moves/renames, or dependency/import restructuring. Also refresh before using a missing or stale graph. Run the extraction and HTML export commands above sequentially and check that both succeed; report failures and fall back to source searches. Documentation and visual-reference updates do not require extraction. No automatic hooks are installed, and no Docker operation is involved.

Use this code-only, single-worker workflow: it performs local AST extraction without model calls, credentials, semantic document/media processing, or subagents. Disabling automatic refresh prevents Graphify from replacing existing assistant skills. Do not enable parallel agent extraction, install hooks, or overwrite repository instructions through its assistant installers.

The graph is a navigation aid, not authoritative proof of runtime behavior. Verify relevant source and tests; some supported files may yield no symbols. The initial scan found 200 nodes and 247 edges, and a query resolved backend settings, application creation, and related tests.
