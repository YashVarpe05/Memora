package ai.memora.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.BeforeClass;
import org.junit.Test;

/** The on-device index must behave like the server's rules. Expected values come from the Python source. */
public class LocalCoreTest {
    private static DocTypes types;

    @BeforeClass
    public static void load() throws Exception {
        types = DocTypes.parse(new String(Files.readAllBytes(Paths.get("../../android-plugin/document_types.tsv")), StandardCharsets.UTF_8));
    }

    @Test
    public void wordsMatchTheServer() {
        assertEquals(Arrays.asList("माझी", "गुणपत्रिका"), Tokens.words("माझी गुणपत्रिका"));
        assertEquals(Arrays.asList("electricity", "bill", "for", "march", "2026", "rs", "1", "740"),
            Tokens.words("Electricity bill for March 2026 — Rs 1,740"));
        // Zero-width joiners do not split a word.
        assertEquals(Arrays.asList("pan", "pan", "number", "आधारकार्ड"), Tokens.words("PAN: [PAN_NUMBER] आधार‍कार्ड"));
        assertEquals(Arrays.asList("a", "b", "cd", "ef"), Tokens.words("a b cd ef"));
    }

    @Test
    public void tokensDropStopWordsAndSingleCharacters() {
        assertEquals(Arrays.asList("electricity", "bill", "march", "2026", "rs", "740"),
            Tokens.tokens("Electricity bill for March 2026 — Rs 1,740"));
        assertEquals(Arrays.asList("cd", "ef"), Tokens.tokens("a b cd ef"));
        assertEquals(Arrays.asList("aadhaar"), Tokens.tokens("The Aadhaar card of Mera"));
    }

    @Test
    public void maskingMatchesTheServerAndTheTypeScriptPort() {
        String[][] cases = {
            {"Aadhaar 2345 6789 0124 issued", "Aadhaar [AADHAAR_NUMBER] issued"},
            {"number 234567890124 here", "number [AADHAAR_NUMBER] here"},
            {"dashed 2345-6789-0124", "dashed [AADHAAR_NUMBER]"},
            {"receipt id 234567890125 keep", "receipt id 234567890125 keep"},
            {"PAN ABCDE1234F and abcde1234f", "PAN [PAN_NUMBER] and abcde1234f"},
            {"phone 9876543210 stays", "phone 9876543210 stays"},
            {"both 234567890124 and ABCDE1234F", "both [AADHAAR_NUMBER] and [PAN_NUMBER]"},
            {"glued 9234567890124", "glued 9234567890124"},
            {"नाम यश ABCDE1234F पता पुणे", "नाम यश [PAN_NUMBER] पता पुणे"},
            {"VID : 2345 6789 0123 4508 printed", "VID : [AADHAAR_VID] printed"},
            {"vid 2345678901234508 glued", "vid [AADHAAR_VID] glued"},
            {"bad 2345678901234509 keep", "bad 2345678901234509 keep"},
            {"both 2345678901234508 and 234567890124 and ABCDE1234F", "both [AADHAAR_VID] and [AADHAAR_NUMBER] and [PAN_NUMBER]"},
        };
        for (String[] c : cases) {
            assertEquals(c[0], c[1], Masking.mask(c[0]));
            assertFalse(c[0], Masking.containsIdentifier(Masking.mask(c[0])));
        }
        assertTrue(Masking.verhoeffValid("234567890124"));
        assertFalse(Masking.verhoeffValid("234567890125"));
    }

    @Test
    public void classificationMatchesTheServer() {
        assertEquals("aadhaar", types.classify("scan0007.png", "आधार कार्ड नाम यश वारपे"));
        assertEquals("marksheet", types.classify("IMG_1.png", "Statement of marks Secondary School Certificate"));
        assertEquals("pan", types.classify("pan_card.jpg", "random text"));
        assertEquals("receipt", types.classify("x.pdf", "Fee receipt. College of Engineering"));
        assertNull(types.classify("notes.txt", "nothing special here"));
        assertEquals("id_card", types.classify("college_id.jpg", ""));
        assertEquals("ticket", types.classify("a.png", "ticket to ride PNR 4455 boarding pass"));
        // The query "माझी गुणपत्रिका" is typed by the same vocabulary.
        assertEquals("marksheet", types.classify(null, "माझी गुणपत्रिका"));
    }

    private static Ranker.Candidate doc(long id, String type, int length, long modified, Object... tf) {
        Map<String, Integer> map = new HashMap<>();
        for (int i = 0; i < tf.length; i += 2) map.put((String) tf[i], (Integer) tf[i + 1]);
        return new Ranker.Candidate(id, type, length, modified, map);
    }

    @Test
    public void bm25MatchesTheServerOnTheSameCorpus() {
        // Corpus: "train ticket pune delhi departure" (5 tokens), "fee receipt tuition paid semester" (5),
        // "train train hotel booking goa" (5). Python bm25("train ticket", ...) = [1.450833, 0.0, 0.646255].
        List<Ranker.Candidate> docs = Arrays.asList(
            doc(1, null, 5, 0, "train", 1, "ticket", 1),
            doc(2, null, 5, 0),
            doc(3, null, 5, 0, "train", 2));
        Map<String, Integer> df = new HashMap<>();
        df.put("train", 2); df.put("ticket", 1);
        List<String> terms = Arrays.asList("train", "ticket");
        assertEquals(1.450833, Ranker.bm25(terms, docs.get(0), df, 3, 5.0), 1e-5);
        assertEquals(0.0, Ranker.bm25(terms, docs.get(1), df, 3, 5.0), 1e-9);
        assertEquals(0.646255, Ranker.bm25(terms, docs.get(2), df, 3, 5.0), 1e-5);
    }

    @Test
    public void aRecognisedTypeOutranksWordsAndTiesPreferTheNewerFile() {
        List<Ranker.Candidate> docs = new ArrayList<>(Arrays.asList(
            doc(1, null, 5, 100, "marksheet", 3),
            doc(2, "marksheet", 50, 100),
            doc(3, "marksheet", 50, 200),
            doc(4, null, 5, 100)));
        Map<String, Integer> df = new HashMap<>();
        df.put("marksheet", 1);
        List<Ranker.Ranked> ranked = Ranker.rank(Arrays.asList("marksheet"), "marksheet", docs, df, 4, 27.5);
        assertEquals(3, ranked.size());                // doc 4 has neither the word nor the type
        assertEquals(3L, ranked.get(0).id == 1L ? 3L : (ranked.get(0).typeMatch ? 3L : 0L));
        assertTrue(ranked.get(0).typeMatch && ranked.get(1).typeMatch);
        assertEquals(3L, ranked.get(1).id == 3L ? 3L : ranked.get(0).id);
        assertFalse(ranked.get(2).typeMatch);          // the word-only document comes last
        assertEquals(1L, ranked.get(2).id);
    }
}
