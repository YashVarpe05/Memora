/*
 * UNVERIFIED ON DEVICE. Written without an Android SDK, a build, or a phone.
 *
 * This file must be copied into the generated Android project after `npx cap add android`
 * — see docs/ANDROID-SETUP.md. It does not compile as it stands here, because the
 * generated project supplies the Capacitor classes it imports.
 *
 * WHAT HAS TO BE CHECKED ON A REAL PHONE:
 *   1. Whether MANAGE_EXTERNAL_STORAGE actually returns granted after the settings
 *      round-trip. The permission is granted from a full-screen system Settings page,
 *      not a dialog, and the app resumes without a callback — so the check is on resume.
 *   2. Whether MediaStore returns files outside the media collections (PDFs in
 *      Downloads/). MediaStore.Files should, but "should" is why this is a checklist.
 *   3. Scan time on a real gallery. Thousands of rows through a ContentResolver cursor
 *      is fast in principle and unmeasured here.
 *   4. Whether reading bytes by path still works, or whether a content:// URI is
 *      required on the target API level.
 */

package ai.memora.app;

import android.content.ContentUris;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
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
import java.util.Locale;

@CapacitorPlugin(name = "FileDiscovery")
public class FileDiscoveryPlugin extends Plugin {

    /** Metadata only. Bytes are read later, and only for files that survive filtering. */
    private static final String[] PROJECTION = {
        MediaStore.Files.FileColumns._ID,
        MediaStore.Files.FileColumns.DISPLAY_NAME,
        MediaStore.Files.FileColumns.SIZE,
        MediaStore.Files.FileColumns.DATE_MODIFIED,
        MediaStore.Files.FileColumns.MIME_TYPE
    };

    @PluginMethod
    public void isSupported(PluginCall call) {
        JSObject result = new JSObject();
        result.put("supported", true);
        call.resolve(result);
    }

    /**
     * MANAGE_EXTERNAL_STORAGE is granted from a Settings page, not a dialog. There is no
     * result callback, so the caller re-checks after the app resumes.
     *
     * This permission is RESTRICTED on the Play Store and would block publication. It is
     * acceptable here only because the deliverable is a sideloaded APK. See PRODUCT.md.
     */
    @PluginMethod
    public void requestPermission(PluginCall call) {
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
            // "prompt" rather than "denied": the user is now on the Settings page and the
            // outcome is unknown until they come back.
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
     * One page of candidates, newest first.
     *
     * Paged rather than streamed: Capacitor bridges a single JSON result per call, so the
     * TypeScript side turns repeated calls into the async iterable the FileDiscovery
     * interface promises.
     */
    @PluginMethod
    public void scan(PluginCall call) {
        int limit = call.getInt("limit", 500);
        long since = call.getLong("since", 0L);
        long maxBytes = call.getLong("maxBytes", 25L * 1024 * 1024);
        int offset = call.getInt("offset", 0);

        // DATE_MODIFIED is in SECONDS, not milliseconds. Mixing the two silently makes
        // every incremental scan a full scan, or skips everything.
        long sinceSeconds = since / 1000L;

        String selection =
            MediaStore.Files.FileColumns.SIZE + " > 0 AND "
            + MediaStore.Files.FileColumns.SIZE + " <= ? AND "
            + MediaStore.Files.FileColumns.DATE_MODIFIED + " > ? AND ("
            + MediaStore.Files.FileColumns.MIME_TYPE + " LIKE 'image/%' OR "
            + MediaStore.Files.FileColumns.MIME_TYPE + " = 'application/pdf')";

        String[] args = { String.valueOf(maxBytes), String.valueOf(sinceSeconds) };
        String order = MediaStore.Files.FileColumns.DATE_MODIFIED + " DESC LIMIT "
            + limit + " OFFSET " + offset;

        JSArray files = new JSArray();
        Uri collection = MediaStore.Files.getContentUri(MediaStore.VOLUME_EXTERNAL);

        try (Cursor cursor = getContext().getContentResolver()
                .query(collection, PROJECTION, selection, args, order)) {
            if (cursor != null) {
                int idCol = cursor.getColumnIndexOrThrow(MediaStore.Files.FileColumns._ID);
                int nameCol = cursor.getColumnIndexOrThrow(MediaStore.Files.FileColumns.DISPLAY_NAME);
                int sizeCol = cursor.getColumnIndexOrThrow(MediaStore.Files.FileColumns.SIZE);
                int dateCol = cursor.getColumnIndexOrThrow(MediaStore.Files.FileColumns.DATE_MODIFIED);
                int mimeCol = cursor.getColumnIndexOrThrow(MediaStore.Files.FileColumns.MIME_TYPE);

                while (cursor.moveToNext()) {
                    JSObject file = new JSObject();
                    Uri uri = ContentUris.withAppendedId(collection, cursor.getLong(idCol));
                    file.put("path", uri.toString());
                    file.put("name", cursor.getString(nameCol));
                    file.put("size", cursor.getLong(sizeCol));
                    // Back to milliseconds for the TypeScript side.
                    file.put("modifiedAt", cursor.getLong(dateCol) * 1000L);
                    String mime = cursor.getString(mimeCol);
                    file.put("mimeType", mime == null ? "application/octet-stream" : mime);
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

    /** Bytes for one file, base64 for the bridge. Called only after filtering and dedup. */
    @PluginMethod
    public void read(PluginCall call) {
        String path = call.getString("path");
        if (path == null) {
            call.reject("path is required");
            return;
        }
        try (InputStream input = getContext().getContentResolver().openInputStream(Uri.parse(path))) {
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] chunk = new byte[8192];
            int read;
            while ((read = input.read(chunk)) != -1) {
                buffer.write(chunk, 0, read);
            }
            JSObject result = new JSObject();
            result.put("data", android.util.Base64.encodeToString(
                buffer.toByteArray(), android.util.Base64.NO_WRAP));
            call.resolve(result);
        } catch (Exception error) {
            call.reject("read failed: " + error.getMessage(), error);
        }
    }
}
