package ai.memora.app;

import android.content.ContentUris;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Log;

import com.getcapacitor.JSObject;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.BooleanSupplier;

/**
 * One pass over the phone's documents, run from the background job with the app closed.
 * It does what the Index screen does: skip files whose size and revision are already indexed,
 * read the rest on the device, and store their masked text in the local index. It stops at the
 * time budget so Android does not kill the job; the next run carries on where this one ended.
 */
final class ScanRunner {
    private static final String TAG = "MemoraScan";
    private static final int PAGE = 100;

    private ScanRunner() {}

    static boolean hasAccess() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.R || Environment.isExternalStorageManager();
    }

    /** Returns true when files are left for the next run. */
    static boolean run(Context context, long budgetMillis, BooleanSupplier stopped) throws Exception {
        if (!hasAccess()) {
            Log.i(TAG, "storage access not granted; nothing to do");
            return false;
        }
        long deadline = System.currentTimeMillis() + budgetMillis;
        LocalIndex index = LocalIndex.open(context);
        Map<String, String> known = index.known();
        Extractor extractor = new Extractor(context);
        Uri collection = MediaStore.Files.getContentUri(MediaStore.VOLUME_EXTERNAL);
        Set<String> present = new HashSet<>();
        int added = 0, failed = 0, offset = 0;
        boolean complete = false;
        while (!stopped.getAsBoolean()) {
            List<Object[]> page = new ArrayList<>();
            try (Cursor c = FileDiscoveryPlugin.pagedQuery(context, collection, FileDiscoveryPlugin.selection(),
                    FileDiscoveryPlugin.selectionArgs(25L * 1024 * 1024, 0), PAGE, offset)) {
                if (c == null) throw new IllegalStateException("storage could not be listed");
                int id = c.getColumnIndexOrThrow(MediaStore.Files.FileColumns._ID);
                int name = c.getColumnIndexOrThrow(MediaStore.Files.FileColumns.DISPLAY_NAME);
                int size = c.getColumnIndexOrThrow(MediaStore.Files.FileColumns.SIZE);
                int date = c.getColumnIndexOrThrow(MediaStore.Files.FileColumns.DATE_MODIFIED);
                int generation = c.getColumnIndexOrThrow(MediaStore.MediaColumns.GENERATION_MODIFIED);
                int mime = c.getColumnIndexOrThrow(MediaStore.Files.FileColumns.MIME_TYPE);
                while (c.moveToNext()) {
                    page.add(new Object[] {
                        ContentUris.withAppendedId(collection, c.getLong(id)).toString(), c.getString(name),
                        c.getLong(size), c.getLong(date) * 1000L, Long.toString(c.getLong(generation)),
                        c.getString(mime) == null ? "application/octet-stream" : c.getString(mime)});
                }
            }
            for (Object[] f : page) {
                String uri = (String) f[0];
                present.add(uri);
                String fingerprint = f[2] + ":" + f[4];
                if (fingerprint.equals(known.get(uri))) continue;
                if (stopped.getAsBoolean() || System.currentTimeMillis() > deadline) {
                    Log.i(TAG, "budget used; added " + added + ", failed " + failed);
                    return true;
                }
                try {
                    JSObject extracted = extractor.extractNow(Uri.parse(uri), (String) f[5]);
                    org.json.JSONArray pages = extracted.getJSONArray("pages");
                    List<String> texts = new ArrayList<>();
                    for (int i = 0; i < pages.length(); i++) texts.add(pages.getJSONObject(i).optString("text", ""));
                    index.upsert(uri, (String) f[1], (String) f[5], (Long) f[2], (Long) f[3], fingerprint, texts);
                    added++;
                } catch (Extractor.Unsupported ignored) {
                    // A type nothing can read is left out, as on the Index screen.
                } catch (Exception error) {
                    failed++;
                    Log.w(TAG, "could not read one file: " + error.getClass().getSimpleName());
                }
            }
            if (page.size() < PAGE) { complete = true; break; }
            offset += page.size();
        }
        if (complete && !stopped.getAsBoolean()) index.prune(present);
        Log.i(TAG, "finished; added " + added + ", failed " + failed);
        return !complete;
    }
}
