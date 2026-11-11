package ai.memora.app;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** The phone's own searchable index. See LocalIndex; this only exposes it to the app. */
@CapacitorPlugin(name = "LocalIndex")
public class LocalIndexPlugin extends Plugin {
    private final ExecutorService worker = Executors.newSingleThreadExecutor();

    private interface Job { void run() throws Exception; }

    private void async(PluginCall call, Job job) {
        worker.execute(() -> {
            try {
                job.run();
            } catch (Exception error) {
                call.reject("local index failed: " + error.getMessage(), error);
            }
        });
    }

    @PluginMethod
    public void upsert(PluginCall call) {
        async(call, () -> {
            String uri = call.getString("uri");
            String name = call.getString("name");
            if (uri == null || name == null) { call.reject("uri and name are required"); return; }
            List<String> pages = new ArrayList<>();
            JSONArray array = call.getArray("pages");
            if (array != null) for (int i = 0; i < array.length(); i++) pages.add(array.getJSONObject(i).optString("text", ""));
            Object[] done = LocalIndex.open(getContext()).upsert(uri, name, call.getString("mimeType", ""),
                call.getLong("size", 0L), call.getLong("modified", 0L), call.getString("fingerprint", ""), pages);
            JSObject result = new JSObject();
            result.put("id", (Long) done[0]);
            result.put("docType", (String) done[1]);
            call.resolve(result);
        });
    }

    @PluginMethod
    public void known(PluginCall call) {
        async(call, () -> {
            JSObject files = new JSObject();
            for (Map.Entry<String, String> e : LocalIndex.open(getContext()).known().entrySet()) files.put(e.getKey(), e.getValue());
            JSObject result = new JSObject();
            result.put("files", files);
            call.resolve(result);
        });
    }

    @PluginMethod
    public void stats(PluginCall call) {
        async(call, () -> {
            JSObject result = new JSObject();
            result.put("documents", LocalIndex.open(getContext()).count());
            call.resolve(result);
        });
    }

    @PluginMethod
    public void prune(PluginCall call) {
        async(call, () -> {
            Set<String> present = new HashSet<>();
            JSONArray array = call.getArray("present");
            if (array != null) for (int i = 0; i < array.length(); i++) present.add(array.getString(i));
            JSObject result = new JSObject();
            result.put("removed", LocalIndex.open(getContext()).prune(present));
            call.resolve(result);
        });
    }

    @PluginMethod
    public void scheduleBackground(PluginCall call) {
        ScanJobService.schedule(getContext(), Boolean.TRUE.equals(call.getBoolean("enabled", true)));
        call.resolve();
    }

    @PluginMethod
    public void clear(PluginCall call) {
        async(call, () -> { LocalIndex.open(getContext()).clear(); call.resolve(); });
    }

    @PluginMethod
    public void search(PluginCall call) {
        async(call, () -> {
            String query = call.getString("query", "");
            int limit = Math.max(1, Math.min(call.getInt("limit", 10), 50));
            JSArray results = new JSArray();
            for (LocalIndex.Hit hit : LocalIndex.open(getContext()).search(query, limit)) {
                JSObject r = new JSObject();
                r.put("id", hit.id);
                r.put("uri", hit.uri);
                r.put("name", hit.name);
                r.put("mime", hit.mime);
                r.put("size", hit.size);
                r.put("title", hit.title);
                r.put("docType", hit.docType == null ? JSONObject.NULL : hit.docType);
                r.put("snippet", hit.snippet);
                r.put("page", hit.page);
                r.put("score", hit.score);
                r.put("lexical", hit.lexical);
                r.put("typeMatch", hit.typeMatch);
                results.put(r);
            }
            JSObject result = new JSObject();
            result.put("results", results);
            call.resolve(result);
        });
    }
}
