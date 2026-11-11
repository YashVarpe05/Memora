package ai.memora.app;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Identifier masking on the phone: a port of services/masking.py and packages/core masking.ts.
 * Aadhaar numbers and the 16-digit Virtual ID need a valid Verhoeff check digit (a false
 * positive silently destroys findable text); PAN is a fixed pattern. Everything stored in the
 * on-device index passes through here first.
 */
final class Masking {
    static final String AADHAAR = "[AADHAAR_NUMBER]";
    static final String VID = "[AADHAAR_VID]";
    static final String PAN = "[PAN_NUMBER]";

    private static final Pattern AADHAAR_RE =
        Pattern.compile("(?<!\\d)([2-9]\\d{3})[ -]?(\\d{4})[ -]?(\\d{4})(?!\\d)");
    private static final Pattern VID_RE =
        Pattern.compile("(?<!\\d)([2-9]\\d{3})[ -]?(\\d{4})[ -]?(\\d{4})[ -]?(\\d{4})(?!\\d)");
    private static final Pattern PAN_RE =
        Pattern.compile("(?<![A-Z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Z0-9])");

    private static final int[][] D = {
        {0, 1, 2, 3, 4, 5, 6, 7, 8, 9}, {1, 2, 3, 4, 0, 6, 7, 8, 9, 5},
        {2, 3, 4, 0, 1, 7, 8, 9, 5, 6}, {3, 4, 0, 1, 2, 8, 9, 5, 6, 7},
        {4, 0, 1, 2, 3, 9, 5, 6, 7, 8}, {5, 9, 8, 7, 6, 0, 4, 3, 2, 1},
        {6, 5, 9, 8, 7, 1, 0, 4, 3, 2}, {7, 6, 5, 9, 8, 2, 1, 0, 4, 3},
        {8, 7, 6, 5, 9, 3, 2, 1, 0, 4}, {9, 8, 7, 6, 5, 4, 3, 2, 1, 0},
    };
    private static final int[][] P = {
        {0, 1, 2, 3, 4, 5, 6, 7, 8, 9}, {1, 5, 7, 6, 2, 8, 3, 0, 9, 4},
        {5, 8, 0, 3, 7, 9, 6, 1, 4, 2}, {8, 9, 1, 6, 0, 4, 3, 5, 2, 7},
        {9, 4, 5, 3, 1, 2, 6, 8, 7, 0}, {4, 2, 8, 6, 5, 7, 3, 9, 0, 1},
        {2, 7, 9, 3, 8, 0, 6, 4, 1, 5}, {7, 0, 4, 6, 9, 1, 3, 2, 5, 8},
    };

    private Masking() {}

    static boolean verhoeffValid(String digits) {
        if (digits.isEmpty()) return false;
        int checksum = 0;
        for (int i = 0; i < digits.length(); i++) {
            char c = digits.charAt(digits.length() - 1 - i);
            if (c < '0' || c > '9') return false;
            checksum = D[checksum][P[i % 8][c - '0']];
        }
        return checksum == 0;
    }

    private static final class Span {
        final int start, end;
        final String token;
        Span(int start, int end, String token) { this.start = start; this.end = end; this.token = token; }
    }

    private static List<Span> spans(String text) {
        List<Span> spans = new ArrayList<>();
        Matcher m = AADHAAR_RE.matcher(text);
        while (m.find()) {
            if (verhoeffValid(m.group(1) + m.group(2) + m.group(3))) spans.add(new Span(m.start(), m.end(), AADHAAR));
        }
        m = VID_RE.matcher(text);
        while (m.find()) {
            if (verhoeffValid(m.group(1) + m.group(2) + m.group(3) + m.group(4))) spans.add(new Span(m.start(), m.end(), VID));
        }
        m = PAN_RE.matcher(text);
        while (m.find()) spans.add(new Span(m.start(), m.end(), PAN));
        Collections.sort(spans, (a, b) -> Integer.compare(a.start, b.start));
        return spans;
    }

    static boolean containsIdentifier(String text) {
        return !spans(text).isEmpty();
    }

    /** Replace identifiers with type tokens; an overlapping match keeps the first. */
    static String mask(String text) {
        StringBuilder out = new StringBuilder();
        int cursor = 0;
        for (Span span : spans(text)) {
            if (span.start < cursor) continue;
            out.append(text, cursor, span.start).append(span.token);
            cursor = span.end;
        }
        return out.append(text.substring(cursor)).toString();
    }
}
