# Memora AI — Product Definition

*Read this before writing any code. This file defines what "working" means.*

---

## The problem

People's information is spread across tools that don't know about each other: email, cloud drives, notes, calendars, PDFs, code repos, voice recordings. Each app searches only its own silo, and only by keyword.

After a few months, finding one specific thing becomes slow and frustrating — not because the thing is lost, but because you remember it the way a *person* remembers: "that PDF a professor sent," "what HR said during the internship interview." You remember **who, when, and roughly what**. You don't remember filenames, subject lines, or which app it was in.

**Memora AI is a system that accepts a human-shaped question and returns the right memory, with proof of where it came from.**

---

## The hero queries

These are the acceptance tests for the entire project. If these don't work, nothing else matters.

| # | Query | What makes it hard |
|---|---|---|
| 1 | "the PDF a professor sent" | **No content in the query at all.** This is a pure metadata lookup: sender role, file type, attachment. Vector search alone returns noise. |
| 2 | "what HR said during the internship interview" | **Vague temporal reference.** "The internship interview" must resolve to a date range (from calendar or an email thread) before content search is meaningful. |
| 3 | "the link someone shared about the hackathon last month" | Cross-source (chat + email), relative time, extract-a-link intent. |
| 4 | "when did I last talk to Prof. Kulkarni about the project" | Entity resolution across sources — the same person appears with different names/emails. |
| 5 | "what's my bank account number" (when it was never stored) | **Must refuse.** Answering from model knowledge instead of user data is a failure. |

**The insight these encode:** most personal-memory queries are *metadata queries wearing semantic clothing*. Retrieval must understand the question and filter first, then search semantically inside what's left. A pipeline that goes straight to vector similarity will fail queries 1, 2, and 4 while looking great on generic content questions.

---

## Retrieval contract

Every query goes through two stages:

**Stage 1 — Query understanding.** One LLM call converts the natural-language question into:

```json
{
  "filters": {
    "sender": "professor | <name> | null",
    "source_type": ["email", "pdf", "audio", "note", "calendar", "code"],
    "date_range": { "from": "...", "to": "..." },
    "has_attachment": true,
    "entities": ["..."]
  },
  "semantic_query": "the part that actually needs meaning-based search",
  "needs_time_resolution": "the internship interview"
}
```

If `needs_time_resolution` is set, resolve the phrase against calendar events and email threads **before** retrieving.

**Stage 2 — Filtered hybrid retrieval.** Apply filters, then dense + BM25 with RRF fusion inside the filtered set. Return chunks with parent context.

**Never skip stage 1.** It is the difference between this project and a document chatbot.

---

## What "working" means

- Every answer cites specific source memories. Clicking a citation opens the source with the exact span highlighted.
- When retrieval is weak, the system says it doesn't have that — it never fills gaps from model knowledge.
- Memories organize themselves. The user files nothing: entities, tags, and timeline are extracted automatically.
- A user can only ever retrieve their own memories. Enforced at the database, not just in application code.
- Deleting the account removes rows, vectors, and files — and this is demonstrable.

---

## What this is NOT

- Not a note-taking app. Memora doesn't ask users to write anything.
- Not an always-on screen recorder. Capture is deliberate and consented.
- Not a general chatbot. If the answer isn't in the user's memories, the correct response is "I don't have that."
- Not a document QA tool. Upload-only would make this NotebookLM. **At least one live connector (Gmail) is required** — the problem being solved is that data is already scattered, so requiring manual gathering sidesteps the problem rather than fixing it.

---

## Honest novelty claims

Do **not** claim novelty on: RAG over personal data, citations, multimodal ingestion, hybrid vector+relational storage. All of these shipped in products before 2026.

Defensible claims:

1. **Query understanding for personal memory** — resolving vague human references ("during the interview," "a professor") into retrieval constraints. This has no good public benchmark, which is the opportunity.
2. **Privacy-first per-owner isolation** — database-enforced, with working export and verifiable erasure.
3. **Self-organizing memory** — timeline and entity graph built without user filing.

Claims 1 and 2 can both be demonstrated on stage in under a minute. Lead with them.

---

## Non-negotiable scope

If the schedule slips, cut in this order: reranking → query transformation → extra connectors → entity resolution → React Native.

Never cut: Gmail connector, query understanding, citations, per-user isolation, the evaluation harness.
