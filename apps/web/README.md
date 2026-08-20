# @memora/web

React PWA shell. Thin by design — all business logic lives in `apps/api` or
`packages/core` (see CLAUDE.md portability rules).

- Capture flows: designed at 375px first.
- Answer + citation flows: designed for a laptop.
- Never import a browser API inside `packages/core`.
