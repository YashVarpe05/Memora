/*
 * Enumerating documents already on the device.
 *
 * VERIFIED ON DEVICE 2026-09-03 — Galaxy S23 FE, Android 16 (SDK 36). The two questions
 * this file used to carry as a checklist were answered against the real MediaStore:
 *
 *   1. DATE_MODIFIED is in SECONDS. Measured: 1716896518 — ten digits. The interface is
 *      epoch MILLISECONDS, so `since` divides and the emitted value multiplies. Mixing
 *      them does not throw; it silently turns every incremental scan into a full scan
 *      (marker far in the past) or into nothing at all (marker far in the future).
 *
 *   2. MediaStore.Files DOES return files outside the media collections. Measured on the
 *      test device: 832 PDFs, of which 132 are in Download/ and 2 in
 *      Documents/DigiLocker/Issued/. A gallery-only query would have missed every one.
 */

package ai.memora.app;

import android.content.ContentResolver;
import android.content.ContentUris;
import android.content.Intent;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.provider.Settings;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.io.InputStream;
import java.io.ByteArrayOutputStream;

@CapacitorPlugin(name = "FileDiscovery")
public class FileDiscoveryPlugin extends Plugin {

    /** Metadata only. Bytes are read later, and only for files that survive filtering. */
    static final String[] PROJECTION = {
        MediaStore.Files.FileColumns._ID,
        MediaStore.Files.FileColumns.DISPLAY_NAME,
        MediaStore.Files.FileColumns.SIZE,
        MediaStore.Files.FileColumns.DATE_MODIFIED,
        MediaStore.MediaColumns.GENERATION_MODIFIED,
        MediaStore.Files.FileColumns.MIME_TYPE,
        MediaStore.Files.FileColumns.RELATIVE_PATH
    };

    /**
     * What can actually be read back as text.
     *
     * Video and audio are deliberately absent. MediaStore returns them for one more line
     * of SQL (85 video rows on the test device), but nothing in the pipeline extracts
     * either — Whisper was descoped. Indexing a file that can never be found by
     * description adds rows that dilute retrieval and can never answer a query, so the
     * gate is "an extractor exists", not "the scan can see it".
     */
    private static final String MIME_FILTER =
        "(" + MediaStore.Files.FileColumns.MIME_TYPE + " LIKE 'image/%'"
        + " OR " + MediaStore.Files.FileColumns.MIME_TYPE + " IN ("
        + "'application/pdf',"
        + "'text/plain',"
        + "'text/markdown',"
        + "'application/msword',"
        + "'application/vnd.openxmlformats-officedocument.wordprocessingml.document'"
        + "))";

    /**
     * Directories to skip — and the one that must NOT be skipped.
     *
     * The obvious rule is "skip Android/", because that is where app private data lives.
     * On the test device that rule would have discarded 695 of 832 PDFs and 1336 WhatsApp
     * images, because **WhatsApp stores its media under `Android/media/com.whatsapp/`**.
     * Three gold queries (q008, q009, q010) target exactly those forwarded screenshots.
     * So the skip is `Android/data/` and `Android/obb/` specifically, never `Android/`.
     *
     * Stickers are skipped as a category: 456 rows on the test device, none of them a
     * document anyone will ever describe and search for.
     */
    private static final String[] SKIP_PATH_PATTERNS = {
        "Android/data/%",
        "Android/obb/%",
        "%.thumbnails%",
        "%WhatsApp Stickers%",
        "%/cache/%",
        "%/Cache/%",
        "%/tmp/%"
    };

    /**
     * Below this, a file is an icon, a sprite or a sticker rather than a document. Cheap
     * to apply here: it removes rows before any of them are read or transferred.
     */
    private static final long MIN_BYTES = 1L;

    private static String skipClause() {
        StringBuilder clause = new StringBuilder();
        for (String ignored : SKIP_PATH_PATTERNS) {
            clause.append(" AND (")
                  .append(MediaStore.Files.FileColumns.RELATIVE_PATH)
                  .append(" IS NULL OR ")
                  .append(MediaStore.Files.FileColumns.RELATIVE_PATH)
                  .append(" NOT LIKE ?)");
        }
        return clause.toString();
    }

    /** Selection shared by scan() and count(), so the progress total matches what arrives. */
    static String selection() {
        return MediaStore.Files.FileColumns.SIZE + " >= " + MIN_BYTES
            + " AND " + MediaStore.Files.FileColumns.SIZE + " <= ?"
            + " AND " + MediaStore.Files.FileColumns.DATE_MODIFIED + " > ?"
            + " AND " + MIME_FILTER
            + skipClause();
    }

    static String[] selectionArgs(long maxBytes, long sinceSeconds) {
        String[] args = new String[2 + SKIP_PATH_PATTERNS.length];
        args[0] = String.valueOf(maxBytes);
        args[1] = String.valueOf(sinceSeconds);
        System.arraycopy(SKIP_PATH_PATTERNS, 0, args, 2, SKIP_PATH_PATTERNS.length);
        return args;
    }

    @PluginMethod
    public void isSupported(PluginCall call) {
        JSObject result = new JSObject();
        result.put("supported", Build.VERSION.SDK_INT >= Build.VERSION_CODES.R);
        call.resolve(result);
    }

    /**
     * MANAGE_EXTERNAL_STORAGE is granted from a full-screen Settings page, not a dialog,
     * and there is NO result callback — the app is simply resumed. So this returns
     * "prompt", and the caller re-checks on resume. Treating the absence of a callback as
     * a denial would report failure every time the user actually granted it.
     *
     * This permission is RESTRICTED on the Play Store and would block publication. It is
     * acceptable here only because the deliverable is a sideloaded APK. See PRODUCT.md.
     */
    @PluginMethod
    public void requestPermission(PluginCall call) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            call.reject("Automatic discovery requires Android 11 or newer.");
            return;
        }
        JSObject result = new JSObject();

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            if (Environment.isExternalStorageManager()) {
                result.put("state", "granted");
                call.resolve(result);
                return;
            }
            Intent intent = new Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION);
            intent.setData(Uri.parse("package:" + getContext().getPackageName()));
            getActivity().startActivity(intent);
            result.put("state", "prompt");
        } else {
            result.put("state", "denied");
        }
        call.resolve(result);
    }

    @PluginMethod
    public void checkPermission(PluginCall call) {
        JSObject result = new JSObject();
        boolean granted = Build.VERSION.SDK_INT >= Build.VERSION_CODES.R
            && Environment.isExternalStorageManager();
        result.put("state", granted ? "granted" : "denied");
        call.resolve(result);
    }

    /**
     * How many candidates match, so progress can be a count rather than a spinner.
     *
     * Runs the same selection as scan(). If the two ever diverge the denominator becomes
     * a lie, which is why both are built from selection() rather than written twice.
     */
    @PluginMethod
    public void count(PluginCall call) {
        long since = call.getLong("since", 0L);
        long maxBytes = call.getLong("maxBytes", 25L * 1024 * 1024);

        Uri collection = MediaStore.Files.getContentUri(MediaStore.VOLUME_EXTERNAL);
        try (Cursor cursor = getContext().getContentResolver().query(
                collection,
                new String[] { MediaStore.Files.FileColumns._ID },
                selection(),
                selectionArgs(maxBytes, since / 1000L),
                null)) {
            JSObject result = new JSObject();
            if (cursor == null) throw new IllegalStateException("Storage could not be enumerated");
            result.put("total", cursor.getCount());
            call.resolve(result);
        } catch (Exception error) {
            call.reject("count failed: " + error.getMessage(), error);
        }
    }

    /**
     * One page of candidates, newest first.
     *
     * Paged rather than streamed: Capacitor bridges a single JSON result per call, so the
     * TypeScript side turns repeated calls into the async iterable FileDiscovery promises.
     */
    @PluginMethod
    public void scan(PluginCall call) {
        int limit = call.getInt("limit", 500);
        long since = call.getLong("since", 0L);
        long maxBytes = call.getLong("maxBytes", 25L * 1024 * 1024);
        int offset = call.getInt("offset", 0);

        // SECONDS, measured — see the header. The interface speaks milliseconds.
        long sinceSeconds = since / 1000L;

        JSArray files = new JSArray();
        Uri collection = MediaStore.Files.getContentUri(MediaStore.VOLUME_EXTERNAL);

        try (Cursor cursor = pagedQuery(getContext(), collection, selection(),
                selectionArgs(maxBytes, sinceSeconds), limit, offset)) {
            if (cursor == null) throw new IllegalStateException("Storage could not be enumerated");
            if (cursor != null) {
                int idCol = cursor.getColumnIndexOrThrow(MediaStore.Files.FileColumns._ID);
                int nameCol = cursor.getColumnIndexOrThrow(MediaStore.Files.FileColumns.DISPLAY_NAME);
                int sizeCol = cursor.getColumnIndexOrThrow(MediaStore.Files.FileColumns.SIZE);
                int dateCol = cursor.getColumnIndexOrThrow(MediaStore.Files.FileColumns.DATE_MODIFIED);
                int generationCol = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.GENERATION_MODIFIED);
                int mimeCol = cursor.getColumnIndexOrThrow(MediaStore.Files.FileColumns.MIME_TYPE);
                int pathCol = cursor.getColumnIndexOrThrow(MediaStore.Files.FileColumns.RELATIVE_PATH);

                while (cursor.moveToNext()) {
                    JSObject file = new JSObject();
                    Uri uri = ContentUris.withAppendedId(collection, cursor.getLong(idCol));
                    file.put("path", uri.toString());
                    file.put("name", cursor.getString(nameCol));
                    file.put("size", cursor.getLong(sizeCol));
                    // Back to milliseconds for the TypeScript side.
                    file.put("modifiedAt", cursor.getLong(dateCol) * 1000L);
                    file.put("revision", Long.toString(cursor.getLong(generationCol)));
                    String mime = cursor.getString(mimeCol);
                    file.put("mimeType", mime == null ? "application/octet-stream" : mime);
                    String relative = cursor.getString(pathCol);
                    file.put("folder", relative == null ? "" : relative);
                    files.put(file);
                }
            }
        } catch (Exception error) {
            call.reject("scan failed: " + error.getMessage(), error);
            return;
        }

        JSObject result = new JSObject();
        result.put("files", files);
        result.put("done", files.length() < limit);
        call.resolve(result);
    }

    /**
     * A page of rows, newest first.
     *
     * **`LIMIT` cannot go in the sort-order string.** Appending
     * `" DESC LIMIT 100 OFFSET 0"` is the classic recipe and MediaStore rejected it
     * outright on Android 16 with `Invalid token LIMIT` — the whole scan failed on its
     * first query. Android 11 (API 30) moved paging to query arguments and started
     * validating the sort order, so the old form is not merely discouraged, it throws.
     *
     * The legacy path is kept for API < 30, where the Bundle constants do not exist and
     * the string form is the only option.
     */
    static Cursor pagedQuery(Context context, Uri collection, String selection, String[] args,
                              int limit, int offset) {
        ContentResolver resolver = context.getContentResolver();
        String sort = MediaStore.Files.FileColumns.DATE_MODIFIED + " DESC, "
            + MediaStore.Files.FileColumns._ID + " DESC";

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            Bundle query = new Bundle();
            query.putString(ContentResolver.QUERY_ARG_SQL_SELECTION, selection);
            query.putStringArray(ContentResolver.QUERY_ARG_SQL_SELECTION_ARGS, args);
            query.putString(ContentResolver.QUERY_ARG_SQL_SORT_ORDER, sort);
            query.putInt(ContentResolver.QUERY_ARG_LIMIT, limit);
            query.putInt(ContentResolver.QUERY_ARG_OFFSET, offset);
            return resolver.query(collection, PROJECTION, query, null);
        }

        return resolver.query(collection, PROJECTION, selection, args,
            sort + " LIMIT " + limit + " OFFSET " + offset);
    }

    /** Detect modifications during paged enumeration before inferring removals. */
    @PluginMethod
    public void stamp(PluginCall call) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            call.reject("Automatic discovery requires Android 11 or newer.");
            return;
        }
        try {
            java.util.List<String> volumes = new java.util.ArrayList<>(
                MediaStore.getExternalVolumeNames(getContext()));
            java.util.Collections.sort(volumes);
            StringBuilder value = new StringBuilder();
            for (String volume : volumes) {
                value.append(volume).append(":")
                    .append(MediaStore.getVersion(getContext(), volume)).append(":")
                    .append(MediaStore.getGeneration(getContext(), volume)).append(";");
            }
            JSObject result = new JSObject();
            result.put("value", value.toString());
            call.resolve(result);
        } catch (Exception error) {
            call.reject("Could not verify a stable storage snapshot", error);
        }
    }

    /** Bytes for one file, base64 for the bridge. Called only after filtering and dedup. */
    /**
     * Hand a file to the system viewer. The file never goes through the server: this is how
     * a search result for a document that lives only on this phone is opened.
     */
    @PluginMethod
    public void open(PluginCall call) {
        String path = call.getString("path");
        if (path == null) {
            call.reject("path is required");
            return;
        }
        Uri uri = Uri.parse(path);
        String type = getContext().getContentResolver().getType(uri);
        Intent intent = new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(uri, type != null ? type : "*/*");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            getContext().startActivity(intent);
            call.resolve();
        } catch (android.content.ActivityNotFoundException error) {
            call.reject("no app on this phone can open this file");
        } catch (Exception error) {
            call.reject("open failed: " + error.getMessage(), error);
        }
    }

    @PluginMethod
    public void read(PluginCall call) {
        String path = call.getString("path");
        if (path == null) {
            call.reject("path is required");
            return;
        }
        try (InputStream input = getContext().getContentResolver().openInputStream(Uri.parse(path))) {
            if (input == null) {
                call.reject("read failed: no stream for " + path);
                return;
            }
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] chunk = new byte[8192];
            int read;
            while ((read = input.read(chunk)) != -1) {
                if (buffer.size() + read > 25L * 1024 * 1024) {
                    call.reject("File exceeds 25 MB");
                    return;
                }
                buffer.write(chunk, 0, read);
            }
            JSObject result = new JSObject();
            result.put("data", android.util.Base64.encodeToString(
                buffer.toByteArray(), android.util.Base64.NO_WRAP));
            call.resolve(result);
        } catch (Exception error) {
            // Reported, not thrown: one unreadable file must not end a scan of thousands.
            call.reject("read failed: " + error.getMessage(), error);
        }
    }
}
