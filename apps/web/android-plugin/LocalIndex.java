package ai.memora.app;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * The phone's own search index: masked text, a document type and an FTS4 table of pre-split
 * words, all in a private SQLite file. Nothing leaves the device. The words are split by
 * Tokens (the server's rules) and the FTS "simple" tokenizer treats every non-ASCII code point
 * as a letter, so Hindi and Marathi words stay whole.
 */
final class LocalIndex extends SQLiteOpenHelper {
    private static final int MAX_BODY = 120_000;
    private static final int MAX_TOKEN_TEXT = 240_000;
    private static LocalIndex instance;

    private final DocTypes types;

    static final class Hit {
        long id;
        String uri, name, mime, title, docType, snippet;
        long size;
        int page;
        double score;
        boolean lexical, typeMatch;
    }

    static synchronized LocalIndex open(Context context) throws Exception {
        if (instance == null) {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (InputStream in = context.getAssets().open("document_types.tsv")) {
                byte[] buffer = new byte[8192];
                int read;
                while ((read = in.read(buffer)) != -1) bytes.write(buffer, 0, read);
            }
            DocTypes types = DocTypes.parse(new String(bytes.toByteArray(), StandardCharsets.UTF_8));
            instance = new LocalIndex(context.getApplicationContext(), types);
        }
        return instance;
    }

    private LocalIndex(Context context, DocTypes types) {
        super(context, "memora-local-index.db", null, 1);
        this.types = types;
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE docs (id INTEGER PRIMARY KEY AUTOINCREMENT, uri TEXT NOT NULL UNIQUE,"
            + " name TEXT NOT NULL, mime TEXT, size INTEGER, modified INTEGER, fingerprint TEXT,"
            + " doc_type TEXT, title TEXT, body TEXT, ntokens INTEGER NOT NULL, indexed_at INTEGER)");
        db.execSQL("CREATE INDEX docs_type ON docs(doc_type)");
        db.execSQL("CREATE VIRTUAL TABLE fts USING fts4(tokens, tokenize=simple)");
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        // Version 1 only. The index is a cache of the files: a rescan rebuilds it.
    }

    private static String stem(String name) {
        int dot = name.lastIndexOf('.');
        return dot > 0 ? name.substring(0, dot) : name;
    }

    /** Index one file. Text is masked before anything is stored. Returns {id, docType}. */
    synchronized Object[] upsert(String uri, String name, String mime, long size, long modified,
                                 String fingerprint, List<String> pages) {
        List<String> masked = new ArrayList<>();
        for (String page : pages) masked.add(Masking.mask(page));
        String body = String.join("\f", masked);
        if (body.length() > MAX_BODY) body = body.substring(0, MAX_BODY);
        String docType = types.classify(name, masked.isEmpty() ? "" : masked.get(0));
        List<String> tokens = Tokens.tokens(stem(name));
        tokens.addAll(Tokens.tokens(body));
        String tokenText = String.join(" ", tokens);
        if (tokenText.length() > MAX_TOKEN_TEXT) tokenText = tokenText.substring(0, MAX_TOKEN_TEXT);
        SQLiteDatabase db = getWritableDatabase();
        db.beginTransaction();
        try {
            Cursor existing = db.rawQuery("SELECT id FROM docs WHERE uri = ?", new String[] {uri});
            try {
                if (existing.moveToFirst()) {
                    long id = existing.getLong(0);
                    db.delete("fts", "docid = ?", new String[] {String.valueOf(id)});
                    db.delete("docs", "id = ?", new String[] {String.valueOf(id)});
                }
            } finally {
                existing.close();
            }
            ContentValues row = new ContentValues();
            row.put("uri", uri);
            row.put("name", name);
            row.put("mime", mime);
            row.put("size", size);
            row.put("modified", modified);
            row.put("fingerprint", fingerprint);
            row.put("doc_type", docType);
            row.put("title", stem(name));
            row.put("body", body);
            row.put("ntokens", tokens.size());
            row.put("indexed_at", System.currentTimeMillis());
            long id = db.insertOrThrow("docs", null, row);
            ContentValues index = new ContentValues();
            index.put("docid", id);
            index.put("tokens", tokenText);
            db.insertOrThrow("fts", null, index);
            db.setTransactionSuccessful();
            return new Object[] {id, docType};
        } finally {
            db.endTransaction();
        }
    }

    synchronized Map<String, String> known() {
        Map<String, String> out = new LinkedHashMap<>();
        Cursor c = getReadableDatabase().rawQuery("SELECT uri, fingerprint FROM docs", null);
        try {
            while (c.moveToNext()) out.put(c.getString(0), c.getString(1));
        } finally {
            c.close();
        }
        return out;
    }

    synchronized int count() {
        Cursor c = getReadableDatabase().rawQuery("SELECT count(*) FROM docs", null);
        try {
            return c.moveToFirst() ? c.getInt(0) : 0;
        } finally {
            c.close();
        }
    }

    /** Remove every document whose file is no longer on the device. */
    synchronized int prune(Set<String> present) {
        SQLiteDatabase db = getWritableDatabase();
        List<Long> gone = new ArrayList<>();
        Cursor c = db.rawQuery("SELECT id, uri FROM docs", null);
        try {
            while (c.moveToNext()) if (!present.contains(c.getString(1))) gone.add(c.getLong(0));
        } finally {
            c.close();
        }
        db.beginTransaction();
        try {
            for (long id : gone) {
                db.delete("fts", "docid = ?", new String[] {String.valueOf(id)});
                db.delete("docs", "id = ?", new String[] {String.valueOf(id)});
            }
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
        return gone.size();
    }

    synchronized void clear() {
        SQLiteDatabase db = getWritableDatabase();
        db.delete("fts", null, null);
        db.delete("docs", null, null);
    }

    private int matchCount(SQLiteDatabase db, String term) {
        Cursor c = db.rawQuery("SELECT count(*) FROM fts WHERE fts MATCH ?", new String[] {"\"" + term + "\""});
        try {
            return c.moveToFirst() ? c.getInt(0) : 0;
        } finally {
            c.close();
        }
    }

    synchronized List<Hit> search(String query, int limit) {
        List<String> terms = new ArrayList<>(new LinkedHashSet<>(Tokens.tokens(query)));
        String wanted = types.classify(null, query);
        List<Hit> hits = new ArrayList<>();
        if (terms.isEmpty() && wanted == null) return hits;
        SQLiteDatabase db = getReadableDatabase();

        Set<Long> ids = new LinkedHashSet<>();
        if (!terms.isEmpty()) {
            List<String> quoted = new ArrayList<>();
            for (String t : terms) quoted.add("\"" + t + "\"");
            Cursor c = db.rawQuery("SELECT docid FROM fts WHERE fts MATCH ? LIMIT 3000", new String[] {String.join(" OR ", quoted)});
            try {
                while (c.moveToNext()) ids.add(c.getLong(0));
            } finally {
                c.close();
            }
        }
        if (wanted != null) {
            Cursor c = db.rawQuery("SELECT id FROM docs WHERE doc_type = ? LIMIT 1000", new String[] {wanted});
            try {
                while (c.moveToNext()) ids.add(c.getLong(0));
            } finally {
                c.close();
            }
        }
        if (ids.isEmpty()) return hits;

        Map<String, Integer> df = new HashMap<>();
        for (String t : terms) df.put(t, matchCount(db, t));
        int documents = 0;
        double average = 1.0;
        Cursor stats = db.rawQuery("SELECT count(*), avg(ntokens) FROM docs", null);
        try {
            if (stats.moveToFirst()) { documents = stats.getInt(0); average = stats.getDouble(1); }
        } finally {
            stats.close();
        }

        Set<String> termSet = new HashSet<>(terms);
        List<Ranker.Candidate> candidates = new ArrayList<>();
        List<Long> all = new ArrayList<>(ids);
        for (int start = 0; start < all.size(); start += 250) {
            List<Long> batch = all.subList(start, Math.min(all.size(), start + 250));
            StringBuilder marks = new StringBuilder();
            String[] args = new String[batch.size()];
            for (int i = 0; i < batch.size(); i++) { marks.append(i == 0 ? "?" : ",?"); args[i] = String.valueOf(batch.get(i)); }
            Cursor c = db.rawQuery("SELECT d.id, d.doc_type, d.ntokens, d.modified, f.tokens FROM docs d JOIN fts f ON f.docid = d.id"
                + " WHERE d.id IN (" + marks + ")", args);
            try {
                while (c.moveToNext()) {
                    Map<String, Integer> tf = new HashMap<>();
                    for (String token : c.getString(4).split(" ")) if (termSet.contains(token)) tf.merge(token, 1, Integer::sum);
                    candidates.add(new Ranker.Candidate(c.getLong(0), c.getString(1), c.getInt(2), c.getLong(3), tf));
                }
            } finally {
                c.close();
            }
        }
        List<Ranker.Ranked> ranked = Ranker.rank(terms, wanted, candidates, df, documents, average);
        for (Ranker.Ranked r : ranked.subList(0, Math.min(limit, ranked.size()))) {
            Cursor c = db.rawQuery("SELECT uri, name, mime, size, title, doc_type, body FROM docs WHERE id = ?", new String[] {String.valueOf(r.id)});
            try {
                if (!c.moveToFirst()) continue;
                Hit hit = new Hit();
                hit.id = r.id; hit.uri = c.getString(0); hit.name = c.getString(1); hit.mime = c.getString(2);
                hit.size = c.getLong(3); hit.title = c.getString(4); hit.docType = c.getString(5);
                hit.score = r.score; hit.lexical = r.lexical; hit.typeMatch = r.typeMatch;
                locate(c.getString(6), terms, hit);
                hits.add(hit);
            } finally {
                c.close();
            }
        }
        return hits;
    }

    /** The first page that holds a query word, and a short excerpt around it. */
    private static void locate(String body, List<String> terms, Hit hit) {
        String[] pages = body == null ? new String[] {""} : body.split("\f", -1);
        hit.page = 1;
        String text = pages.length > 0 ? pages[0] : "";
        int at = -1;
        for (int p = 0; p < pages.length && at < 0; p++) {
            String lower = pages[p].toLowerCase(Locale.ROOT);
            for (String term : terms) {
                int found = lower.indexOf(term);
                if (found >= 0) { at = found; hit.page = p + 1; text = pages[p]; break; }
            }
        }
        String flat = text.replaceAll("\\s+", " ").trim();
        if (at < 0 || flat.length() <= 240) {
            hit.snippet = flat.length() > 240 ? flat.substring(0, 240) + "…" : flat;
            return;
        }
        int start = Math.max(0, Math.min(at, flat.length()) - 80);
        int end = Math.min(flat.length(), start + 240);
        hit.snippet = (start > 0 ? "…" : "") + flat.substring(start, end) + (end < flat.length() ? "…" : "");
    }
}
