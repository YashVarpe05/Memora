# Local multilingual semantic search
User authorized implementation on 2026-11-06. Add actual multilingual E5 embeddings
with query/passage prefixes, normalized 768-dimensional vectors, model provenance and
compatibility filtering. Backfill existing masked chunks resumably without deleting files.
Keep lexical retrieval during model failures. Enable local web trial after real-model
verification; report unavailable downloads honestly. Test semantic-only descriptions,
model isolation, resume/idempotency, masking and existing API/browser flows.
