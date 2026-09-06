# Decisions

- SQLite is supported for fast local tests; Docker uses PostgreSQL/pgvector as specified.
- Lexical cosine similarity is the zero-download fallback. The optional sentence-transformer path can be enabled in deployments with the model cached.
- Batch work uses FastAPI background tasks; no extra queue is required for the hackathon scope.
- Markdown export is included; PDF remains an optional conversion step.

## Unified AI Security Architecture v2

- The request path is zero-API by construction: no external judge, so no provider outage can take the gateway down, no prompt under test leaves the host, and every verdict is reproducible. The optional AI jury survives on the response path only, off by default.
- The signature set stays at 19. Three exfiltration-channel seeds are caught by no signature; a twentieth would have hidden the more useful truth that this class is a response-gate problem.
- Audit segments are sealed when a run completes, because a run is the unit a reader wants to verify. Audit writes are best-effort and never break the security path.
- The air-gapped sandbox prefers a local quantized GGUF and falls back to a deterministic oracle. The active backend is named in /health, /sandbox, and every report, and the oracle's limits are stated rather than implied.
- Full spec-to-code mapping and the measured results: docs/unified-architecture-v2-ASBUILT.md.
