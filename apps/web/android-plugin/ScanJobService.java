package ai.memora.app;

import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;
import android.util.Log;

/**
 * The background scan. Android runs this on its own schedule (about every six hours, only
 * when the battery is not low), even when Memora is closed, so new files become searchable
 * without opening the app.
 */
public class ScanJobService extends JobService {
    static final int JOB_ID = 4201;
    private static final long BUDGET_MILLIS = 8 * 60 * 1000L;
    private volatile boolean stopped;

    static void schedule(Context context, boolean enabled) {
        JobScheduler scheduler = context.getSystemService(JobScheduler.class);
        if (!enabled) { scheduler.cancel(JOB_ID); return; }
        if (scheduler.getPendingJob(JOB_ID) != null) return;
        scheduler.schedule(new JobInfo.Builder(JOB_ID, new ComponentName(context, ScanJobService.class))
            .setPeriodic(6 * 60 * 60 * 1000L)
            .setRequiresBatteryNotLow(true)
            .setPersisted(true)
            .build());
    }

    @Override
    public boolean onStartJob(JobParameters params) {
        stopped = false;
        new Thread(() -> {
            boolean more = false;
            try {
                more = ScanRunner.run(getApplicationContext(), BUDGET_MILLIS, () -> stopped);
            } catch (Throwable error) {
                Log.w("MemoraScan", "background scan failed: " + error.getClass().getSimpleName());
            }
            jobFinished(params, more);
        }, "memora-scan").start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        stopped = true;
        return true;
    }
}
