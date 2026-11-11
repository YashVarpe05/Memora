package ai.memora.app;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Word splitting for the on-device index: a port of services/lexical.py on the server, so a
 * word is a word the same way on both. Letters, digits and combining marks stay together
 * (Devanagari vowel signs are marks); everything else separates words.
 */
final class Tokens {
    private static final Set<String> STOP = new HashSet<>();

    private Tokens() {}

    static synchronized void setStopWords(Collection<String> words) {
        STOP.clear();
        STOP.addAll(words);
    }

    private static boolean keep(int codePoint) {
        switch (Character.getType(codePoint)) {
            case Character.UPPERCASE_LETTER:
            case Character.LOWERCASE_LETTER:
            case Character.TITLECASE_LETTER:
            case Character.MODIFIER_LETTER:
            case Character.OTHER_LETTER:
            case Character.DECIMAL_DIGIT_NUMBER:
            case Character.LETTER_NUMBER:
            case Character.OTHER_NUMBER:
            case Character.NON_SPACING_MARK:
            case Character.ENCLOSING_MARK:
            case Character.COMBINING_SPACING_MARK:
                return true;
            default:
                return false;
        }
    }

    static List<String> words(String text) {
        List<String> parts = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        String folded = Normalizer.normalize(text.toLowerCase(Locale.ROOT), Normalizer.Form.NFC);
        for (int i = 0; i < folded.length(); ) {
            int cp = folded.codePointAt(i);
            i += Character.charCount(cp);
            if (keep(cp)) {
                current.appendCodePoint(cp);
            } else if (cp != 0x200C && cp != 0x200D && current.length() > 0) {
                parts.add(current.toString());
                current.setLength(0);
            }
        }
        if (current.length() > 0) parts.add(current.toString());
        return parts;
    }

    static synchronized List<String> tokens(String text) {
        List<String> out = new ArrayList<>();
        for (String word : words(text)) {
            if (word.codePointCount(0, word.length()) > 1 && !STOP.contains(word)) out.add(word);
        }
        return out;
    }
}
