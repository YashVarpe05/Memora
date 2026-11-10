/*
 * Reading a document on the device itself.
 *
 * The file never leaves the phone: this plugin hashes it, runs ML Kit text recognition
 * (Latin and Devanagari, both bundled, no network) on images and on PDF pages rendered to
 * bitmaps, and hands the text back to JavaScript, which masks identifiers and sends only
 * text to the server. A type this plugin cannot read is REJECTED, never guessed, so the
 * caller can fall back to uploading the file.
 *
 * NOT YET VERIFIED ON A PHYSICAL DEVICE. Exercised on an Android emulator only.
 */

package ai.memora.app;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.pdf.PdfRenderer;
import android.net.Uri;
import android.os.ParcelFileDescriptor;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.devanagari.DevanagariTextRecognizerOptions;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@CapacitorPlugin(name = "TextExtraction")
public class TextExtractionPlugin extends Plugin {

    private static final long MAX_BYTES = 25L * 1024 * 1024;
    /** Longer sides are scaled down to this before recognition. Phone photos are 4000px+. */
    private static final int MAX_SIDE = 2200;
    private static final int MAX_PDF_PAGES = 40;
    private static final int PDF_PAGE_WIDTH = 1600;

    /** One document at a time: recognisers are heavy and a scan queues many files. */
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private TextRecognizer latin;
    private TextRecognizer devanagari;

    private synchronized void recognisers() {
        if (latin == null) {
            latin = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
            devanagari = TextRecognition.getClient(
                new DevanagariTextRecognizerOptions.Builder().build());
        }
    }

    @PluginMethod
    public void extract(PluginCall call) {
        final String path = call.getString("path");
        final String mimeType = call.getString("mimeType", "");
        if (path == null) {
            call.reject("path is required");
            return;
        }
        worker.execute(() -> {
            try {
                call.resolve(extractNow(Uri.parse(path), mimeType == null ? "" : mimeType));
            } catch (Unsupported error) {
                call.reject("unsupported: " + error.getMessage());
            } catch (Exception error) {
                call.reject("extract failed: " + error.getMessage(), error);
            }
        });
    }

    private static final class Unsupported extends Exception {
        Unsupported(String message) { super(message); }
    }

    private JSObject extractNow(Uri uri, String mimeType) throws Exception {
        final byte[] bytes = readAll(uri);
        final String hash = sha256(bytes);
        final String mime = mimeType.toLowerCase(Locale.ROOT);
        final JSArray pages = new JSArray();

        if (mime.equals("text/plain") || mime.equals("text/markdown")) {
            pages.put(page(1, new String(bytes, StandardCharsets.UTF_8)));
        } else if (mime.startsWith("image/")) {
            recognisers();
            pages.put(page(1, recognise(decodeSampled(bytes))));
        } else if (mime.equals("application/pdf")) {
            recognisers();
            renderPdf(uri, pages);
        } else {
            throw new Unsupported(mimeType.isEmpty() ? "unknown type" : mimeType);
        }

        JSObject result = new JSObject();
        result.put("contentHash", hash);
        result.put("byteSize", bytes.length);
        result.put("pages", pages);
        result.put("engine", "mlkit-latin+devanagari");
        return result;
    }

    private static JSObject page(int number, String text) {
        JSObject page = new JSObject();
        page.put("number", number);
        page.put("text", text);
        return page;
    }

    private byte[] readAll(Uri uri) throws Exception {
        try (InputStream input = getContext().getContentResolver().openInputStream(uri)) {
            if (input == null) throw new Exception("no stream");
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] chunk = new byte[8192];
            int read;
            while ((read = input.read(chunk)) != -1) {
                if (buffer.size() + read > MAX_BYTES) throw new Unsupported("larger than 25 MB");
                buffer.write(chunk, 0, read);
            }
            return buffer.toByteArray();
        }
    }

    private static String sha256(byte[] bytes) throws Exception {
        StringBuilder hex = new StringBuilder();
        for (byte b : MessageDigest.getInstance("SHA-256").digest(bytes)) {
            hex.append(String.format("%02x", b));
        }
        return hex.toString();
    }

    private static Bitmap decodeSampled(byte[] bytes) throws Exception {
        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(bytes, 0, bytes.length, bounds);
        int sample = 1;
        while (Math.max(bounds.outWidth, bounds.outHeight) / sample > MAX_SIDE) sample *= 2;
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inSampleSize = sample;
        Bitmap bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
        if (bitmap == null) throw new Unsupported("image could not be decoded");
        return bitmap;
    }

    private void renderPdf(Uri uri, JSArray pages) throws Exception {
        try (ParcelFileDescriptor fd = getContext().getContentResolver().openFileDescriptor(uri, "r");
             PdfRenderer renderer = new PdfRenderer(fd)) {
            int count = Math.min(renderer.getPageCount(), MAX_PDF_PAGES);
            for (int i = 0; i < count; i++) {
                try (PdfRenderer.Page pdfPage = renderer.openPage(i)) {
                    int height = Math.max(1,
                        Math.round(PDF_PAGE_WIDTH * (float) pdfPage.getHeight() / pdfPage.getWidth()));
                    Bitmap bitmap = Bitmap.createBitmap(PDF_PAGE_WIDTH, height, Bitmap.Config.ARGB_8888);
                    // PdfRenderer leaves transparent pixels; recognisers read them as black.
                    new Canvas(bitmap).drawColor(Color.WHITE);
                    pdfPage.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY);
                    pages.put(page(i + 1, recognise(bitmap)));
                    bitmap.recycle();
                }
            }
        }
    }

    /** Both recognisers, merged by line, so English and Devanagari text both survive. */
    private String recognise(Bitmap bitmap) throws Exception {
        InputImage image = InputImage.fromBitmap(bitmap, 0);
        String first = Tasks.await(latin.process(image)).getText();
        String second = Tasks.await(devanagari.process(image)).getText();
        Set<String> lines = new LinkedHashSet<>();
        for (String text : new String[] {first, second}) {
            for (String line : text.split("\\r?\\n")) {
                String trimmed = line.trim();
                if (!trimmed.isEmpty()) lines.add(trimmed);
            }
        }
        return String.join("\n", lines);
    }
}
