# Local source-code graph

Graphify is an optional development tool for exploring LifeGather's source code. It is not part of the application, personal-memory storage, or Docker image.

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

Use this code-only, single-worker workflow: it performs local AST extraction without model calls, credentials, semantic document/media processing, or subagents. Disabling automatic refresh prevents Graphify from replacing existing assistant skills. Do not enable parallel agent extraction, install hooks, or overwrite repository instructions through its assistant installers.

The graph is a navigation aid, not authoritative proof of runtime behavior. Verify relevant source and tests; some supported files may yield no symbols. The initial scan found 200 nodes and 247 edges, and a query resolved backend settings, application creation, and related tests.
