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
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@CapacitorPlugin(name = "TextExtraction")
public class TextExtractionPlugin extends Plugin {

    /** One document at a time: recognisers are heavy and a scan queues many files. */
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private Extractor extractor;

    private synchronized Extractor extractor() {
        if (extractor == null) extractor = new Extractor(getContext());
        return extractor;
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
                call.resolve(extractor().extractNow(Uri.parse(path), mimeType == null ? "" : mimeType));
            } catch (Extractor.Unsupported error) {
                call.reject("unsupported: " + error.getMessage());
            } catch (Exception error) {
                call.reject("extract failed: " + error.getMessage(), error);
            }
        });
    }

    /**
     * Debug builds only. Runs each recogniser separately on one file and reports its text and
     * milliseconds, so the choice between them can be measured instead of guessed.
     */
    @PluginMethod
    public void benchmark(PluginCall call) {
        if ((getContext().getApplicationInfo().flags
                & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) == 0) {
            call.reject("benchmark is available only in debug builds");
            return;
        }
        final String path = call.getString("path");
        final String mimeType = call.getString("mimeType", "");
        if (path == null) {
            call.reject("path is required");
            return;
        }
        worker.execute(() -> {
            try {
                final Extractor ex = extractor();
                Uri uri = Uri.parse(path);
                String mime = mimeType == null ? "" : mimeType.toLowerCase(Locale.ROOT);
                ex.recognisers();
                ex.latinRecogniser();
                Bitmap bitmap;
                if (mime.startsWith("image/")) {
                    bitmap = ex.decodeSampled(ex.readAll(uri));
                } else if (mime.equals("application/pdf")) {
                    try (ParcelFileDescriptor fd =
                             getContext().getContentResolver().openFileDescriptor(uri, "r");
                         PdfRenderer renderer = new PdfRenderer(fd);
                         PdfRenderer.Page pdfPage = renderer.openPage(0)) {
                        int height = Math.max(1, Math.round(
                            Extractor.PDF_PAGE_WIDTH * (float) pdfPage.getHeight() / pdfPage.getWidth()));
                        bitmap = Bitmap.createBitmap(Extractor.PDF_PAGE_WIDTH, height, Bitmap.Config.ARGB_8888);
                        new Canvas(bitmap).drawColor(Color.WHITE);
                        pdfPage.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY);
                    }
                } else {
                    throw new Extractor.Unsupported(mime);
                }
                InputImage image = InputImage.fromBitmap(bitmap, 0);
                JSObject result = new JSObject();
                long t0 = System.nanoTime();
                String latinText = Tasks.await(ex.latin.process(image)).getText();
                long t1 = System.nanoTime();
                String devanagariText = Tasks.await(ex.devanagari.process(image)).getText();
                long t2 = System.nanoTime();
                result.put("latinText", latinText);
                result.put("latinMs", (t1 - t0) / 1_000_000);
                result.put("devanagariText", devanagariText);
                result.put("devanagariMs", (t2 - t1) / 1_000_000);
                call.resolve(result);
            } catch (Exception error) {
                call.reject("benchmark failed: " + error.getMessage(), error);
            }
        });
    }

}
