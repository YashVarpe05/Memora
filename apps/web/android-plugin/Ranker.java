package ai.memora.app;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * Ordering for the on-device index. BM25 with the server's constants (services/lexical.py), plus
 * the rule the server's search follows: a document whose recognised type is the type the query
 * asked for ranks above any document that merely contains the words.
 */
final class Ranker {
    static final class Candidate {
        final long id;
        final String docType;
        final int length;
        final long modified;
        final Map<String, Integer> termFrequency;

        Candidate(long id, String docType, int length, long modified, Map<String, Integer> termFrequency) {
            this.id = id; this.docType = docType; this.length = length; this.modified = modified; this.termFrequency = termFrequency;
        }
    }

    static final class Ranked {
        final long id;
        final double score;
        final boolean lexical;
        final boolean typeMatch;

        Ranked(long id, double score, boolean lexical, boolean typeMatch) {
            this.id = id; this.score = score; this.lexical = lexical; this.typeMatch = typeMatch;
        }
    }

    private static final double TYPE_BONUS = 1000.0;

    private Ranker() {}

    static double bm25(List<String> terms, Candidate doc, Map<String, Integer> documentFrequency, int documents, double averageLength) {
        double score = 0.0;
        double average = averageLength > 0 ? averageLength : 1.0;
        for (String term : terms) {
            Integer f = doc.termFrequency.get(term);
            if (f == null || f == 0) continue;
            int df = documentFrequency.containsKey(term) ? documentFrequency.get(term) : 0;
            double idf = Math.log(1 + (documents - df + 0.5) / (df + 0.5));
            score += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * doc.length / average));
        }
        return score;
    }

    static List<Ranked> rank(List<String> terms, String wantedType, List<Candidate> candidates,
                             Map<String, Integer> documentFrequency, int documents, double averageLength) {
        List<String> unique = new ArrayList<>(new java.util.LinkedHashSet<>(terms));
        final Map<Long, Long> modified = new java.util.HashMap<>();
        List<Ranked> ranked = new ArrayList<>();
        for (Candidate doc : candidates) {
            double lexical = bm25(unique, doc, documentFrequency, documents, averageLength);
            boolean typeMatch = wantedType != null && wantedType.equals(doc.docType);
            if (lexical <= 0 && !typeMatch) continue;
            ranked.add(new Ranked(doc.id, lexical + (typeMatch ? TYPE_BONUS : 0.0), lexical > 0, typeMatch));
            modified.put(doc.id, doc.modified);
        }
        // Higher score first; among equals the newer file first, then the lower id.
        Collections.sort(ranked, (a, b) -> {
            int byScore = Double.compare(b.score, a.score);
            if (byScore != 0) return byScore;
            int byDate = Long.compare(modified.get(b.id), modified.get(a.id));
            return byDate != 0 ? byDate : Long.compare(a.id, b.id);
        });
        return ranked;
    }
}
