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

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.pdf.PdfRenderer;
import android.net.Uri;
import android.os.ParcelFileDescriptor;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
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
import java.util.Locale;


/** Reads a file on the device into text. Shared by the app screen and the background job. */
final class Extractor {
    private final Context context;

    Extractor(Context context) {
        this.context = context;
    }

    static final long MAX_BYTES = 25L * 1024 * 1024;
    /** Longer sides are scaled down to this before recognition. Phone photos are 4000px+. */
    static final int MAX_SIDE = 2200;
    static final int MAX_PDF_PAGES = 40;
    static final int PDF_PAGE_WIDTH = 1600;

    TextRecognizer latin;
    TextRecognizer devanagari;

    synchronized void recognisers() {
        if (devanagari == null) {
            devanagari = TextRecognition.getClient(
                new DevanagariTextRecognizerOptions.Builder().build());
        }
    }

    /** Only the debug benchmark compares against the Latin model. */
    synchronized void latinRecogniser() {
        if (latin == null) {
            latin = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
        }
    }

    static final class Unsupported extends Exception {
        Unsupported(String message) { super(message); }
    }

    JSObject extractNow(Uri uri, String mimeType) throws Exception {
        final byte[] bytes = readAll(uri);
        final String hash = sha256(bytes);
        final String mime = mimeType.toLowerCase(Locale.ROOT);
        final JSArray pages = new JSArray();

        if (mime.equals("text/plain") || mime.equals("text/markdown")) {
            pages.put(page(1, decodeText(bytes)));
        } else if (mime.startsWith("image/")) {
            recognisers();
            pages.put(page(1, recognise(decodeSampled(bytes))));
        } else if (mime.equals("application/pdf")) {
            recognisers();
            try {
                renderPdf(uri, pages);
            } catch (SecurityException | java.io.IOException error) {
                // Password-protected or damaged PDFs (bank statements, credit reports) cannot
                // be rendered. Leave them out of the index quietly; they would otherwise be
                // reported as a failure on every scan and can never be fixed from here.
                while (pages.length() > 0) pages.remove(pages.length() - 1);
            }
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

    /** Windows and WhatsApp exports are often UTF-16; read as UTF-8 they are full of NULs. */
    static String decodeText(byte[] bytes) {
        java.nio.charset.Charset charset = StandardCharsets.UTF_8;
        if (bytes.length >= 2 && (bytes[0] & 0xFF) == 0xFF && (bytes[1] & 0xFF) == 0xFE) {
            charset = StandardCharsets.UTF_16LE;
        } else if (bytes.length >= 2 && (bytes[0] & 0xFF) == 0xFE && (bytes[1] & 0xFF) == 0xFF) {
            charset = StandardCharsets.UTF_16BE;
        }
        return new String(bytes, charset).replace("\u0000", "").replace("\uFEFF", "");
    }

    static JSObject page(int number, String text) {
        JSObject page = new JSObject();
        page.put("number", number);
        page.put("text", text);
        return page;
    }

    byte[] readAll(Uri uri) throws Exception {
        try (InputStream input = context.getContentResolver().openInputStream(uri)) {
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

    static String sha256(byte[] bytes) throws Exception {
        StringBuilder hex = new StringBuilder();
        for (byte b : MessageDigest.getInstance("SHA-256").digest(bytes)) {
            hex.append(String.format("%02x", b));
        }
        return hex.toString();
    }

    static Bitmap decodeSampled(byte[] bytes) throws Exception {
        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(bytes, 0, bytes.length, bounds);
        int sample = 1;
        while (Math.max(bounds.outWidth, bounds.outHeight) / sample > MAX_SIDE) sample *= 2;
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inSampleSize = sample;
        Bitmap bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
        if (bitmap == null) throw new Unsupported("image could not be decoded");
        return upright(bitmap, bytes);
    }

    /**
     * Phone photos of documents are usually stored sideways with an EXIF rotation flag that
     * BitmapFactory ignores. Recognising the unrotated pixels reads almost nothing.
     */
    static Bitmap upright(Bitmap bitmap, byte[] bytes) {
        int degrees = 0;
        try (InputStream stream = new java.io.ByteArrayInputStream(bytes)) {
            int orientation = new android.media.ExifInterface(stream).getAttributeInt(
                android.media.ExifInterface.TAG_ORIENTATION,
                android.media.ExifInterface.ORIENTATION_NORMAL);
            if (orientation == android.media.ExifInterface.ORIENTATION_ROTATE_90) degrees = 90;
            else if (orientation == android.media.ExifInterface.ORIENTATION_ROTATE_180) degrees = 180;
            else if (orientation == android.media.ExifInterface.ORIENTATION_ROTATE_270) degrees = 270;
        } catch (Exception ignored) {
            return bitmap;
        }
        if (degrees == 0) return bitmap;
        android.graphics.Matrix matrix = new android.graphics.Matrix();
        matrix.postRotate(degrees);
        return Bitmap.createBitmap(bitmap, 0, 0, bitmap.getWidth(), bitmap.getHeight(), matrix, true);
    }

    void renderPdf(Uri uri, JSArray pages) throws Exception {
        try (ParcelFileDescriptor fd = context.getContentResolver().openFileDescriptor(uri, "r");
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

    /**
     * One pass with the Devanagari model, which reads Latin text as well as Devanagari.
     *
     * Measured 2026-11-11: on known-text images it matched the old two-pass rule (word
     * accuracy 0.97 vs 0.97; English 1.00, Hindi and Marathi 0.86-1.00, a Hindi-heading plus
     * English-body card 1.00 vs 0.86 for Latin alone). On 82 real files from a Galaxy S23 FE
     * the Latin model never found text the Devanagari model missed, and the two returned the
     * same number of words, at about 195 ms each. Running both cost 393 ms per image; this
     * costs about half, and no longer drops the English half of a bilingual document.
     */
    String recognise(Bitmap bitmap) throws Exception {
        return Tasks.await(devanagari.process(InputImage.fromBitmap(bitmap, 0))).getText().trim();
    }
}
