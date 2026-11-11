package ai.memora.app;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * What kind of document this is: a port of services/document_type.py, driven by
 * document_types.tsv (exported from the Python source, with a test that fails on drift).
 * Rule-based on purpose: it costs nothing, runs offline, and fails in ways that can be read off
 * the vocabulary. Only the head of the text is read; contents win over a misleading filename.
 */
final class DocTypes {
    private final Map<String, List<String>> vocabulary = new LinkedHashMap<>();

    static DocTypes parse(String tsv) {
        DocTypes types = new DocTypes();
        List<String> stop = new ArrayList<>();
        for (String line : tsv.split("\n")) {
            if (line.isEmpty() || line.startsWith("#")) continue;
            String[] cells = line.split("\t", -1);
            if (cells[0].equals("S") && cells.length >= 2) {
                stop.add(cells[1]);
            } else if (cells[0].equals("T") && cells.length >= 3) {
                List<String> aliases = new ArrayList<>();
                for (String alias : cells[2].split("\\|")) aliases.add(" " + String.join(" ", Tokens.words(alias)) + " ");
                types.vocabulary.put(cells[1], aliases);
            }
        }
        Tokens.setStopWords(stop);
        return types;
    }

    private static String haystack(String... parts) {
        StringBuilder joined = new StringBuilder();
        for (String part : parts) if (part != null && !part.isEmpty()) joined.append(part.toLowerCase(java.util.Locale.ROOT)).append(' ');
        return joined.toString().trim().replaceAll("[_\\-.]+", " ");
    }

    /** The label, or null for "no recognised type", which is the common case. */
    String classify(String filename, String text) {
        String head = text == null ? "" : text.substring(0, Math.min(text.length(), 1500));
        for (String hay : new String[] {haystack(head), haystack(filename)}) {
            String normalized = " " + String.join(" ", Tokens.words(hay)) + " ";
            for (Map.Entry<String, List<String>> entry : vocabulary.entrySet()) {
                for (String alias : entry.getValue()) {
                    if (normalized.contains(alias)) return entry.getKey();
                }
            }
        }
        return null;
    }
}
