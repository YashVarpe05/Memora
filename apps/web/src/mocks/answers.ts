import type { Citation, GroundedAnswer, SourceType } from '@memora/core';

/**
 * Mock answers, typed from packages/core so the shape cannot drift from the real
 * contract. Replaced by the API in phase 5 - nothing here is imported by
 * production code paths.
 *
 * The fixtures deliberately mirror gold-set rows: a metadata-only query that a
 * naive pipeline fails, and the refusal that q006 grades.
 */

function citation(
  chunkId: string,
  sourceType: SourceType,
  title: string,
  snippet: string,
  score: number,
): Citation {
  return {
    chunkId,
    memoryId: chunkId.split(':')[0] ?? chunkId,
    sourceType,
    title,
    snippet,
    score,
    span: { start: 0, end: snippet.length },
  };
}

interface MockCase {
  match: RegExp;
  answer: GroundedAnswer;
}

const CASES: MockCase[] = [
  {
    // GOLD q001 - no content signal at all, pure metadata lookup.
    match: /professor|faculty|lecturer/i,
    answer: {
      answer:
        'Prof. Kulkarni sent you the DBMS Unit 3 notes on 4 March, attached to an email ' +
        'about the upcoming unit test. It covers normalization and transaction isolation.',
      refused: false,
      citations: [
        citation(
          'mem_a1:0',
          'email',
          'Unit test on Thursday - notes attached',
          'Attaching the Unit 3 notes we covered. Focus on normalization for the test.',
          0.91,
        ),
        citation(
          'mem_a2:3',
          'pdf',
          'dbms_unit3_notes.pdf',
          'Third normal form eliminates transitive dependency on the primary key.',
          0.87,
        ),
      ],
    },
  },
  {
    // GOLD q006 - never stored. A refusal is the passing answer.
    match: /bank account|password|aadhaar|credit card|pan number/i,
    answer: {
      answer:
        "I don't have that in your memories. Nothing you've added contains a bank account " +
        'number, and I will not guess one.',
      refused: true,
      refusalReason: 'no_evidence',
      citations: [],
    },
  },
  {
    // GOLD q002 - the phrase resolves to a date window before content search.
    match: /interview|HR/i,
    answer:
      {
        answer:
          'HR said the stipend is Rs 25,000/month and the internship runs 8 weeks from ' +
          '2 June. They also confirmed the offer letter would arrive within a week.',
        refused: false,
        citations: [
          citation(
            'mem_b7:2',
            'audio',
            'interview_recording_0412.m4a',
            'so the stipend is twenty-five thousand a month, and it is an eight week program',
            0.88,
          ),
          citation(
            'mem_b9:0',
            'email',
            'Re: Internship - next steps',
            'As discussed, your offer letter will reach you within the week.',
            0.79,
          ),
        ],
      },
  },
];

const WEAK_EVIDENCE: GroundedAnswer = {
  answer:
    "I found something related, but not enough to answer confidently. Here's the closest " +
    'match rather than a guess.',
  refused: true,
  refusalReason: 'weak_evidence',
  citations: [
    citation('mem_c2:1', 'note', 'notes_architecture.md', 'Retrieval runs in two stages.', 0.34),
  ],
};

export function mockAnswerFor(query: string): GroundedAnswer {
  return CASES.find((c) => c.match.test(query))?.answer ?? WEAK_EVIDENCE;
}

/** Every query the mock has a scripted answer for, surfaced as UI suggestions. */
export const SUGGESTED_QUERIES = [
  'the PDF a professor sent',
  'what HR said during the internship interview',
  "what's my bank account number",
] as const;
