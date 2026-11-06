package io.github.ispaure.commonutils;

import android.app.UiModeManager;
import android.content.ContentResolver;
import android.database.ContentObserver;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.text.TextUtils;
import android.view.View;
import android.widget.TextView;
import java.util.Collections;
import java.util.Set;
import java.util.WeakHashMap;

/** Apply the current motion settings while a bound title is on screen. */
public final class TitleMotion extends ContentObserver implements View.OnAttachStateChangeListener {
    private static final String HIGH_CONTRAST = "high_text_contrast_enabled";
    private static final Set<TextView> titles = Collections.newSetFromMap(new WeakHashMap<>());
    private static boolean suppressed;
    private final TextView label;
    private Runnable removeContrastListener;

    private TitleMotion(TextView label) {
        super(new Handler(Looper.getMainLooper()));
        this.label = label;
    }

    public static void bind(TextView label) {
        if (!titles.add(label)) return;
        label.setSingleLine(true);
        TitleMotion observer = new TitleMotion(label);
        label.addOnAttachStateChangeListener(observer);
        if (label.isAttachedToWindow()) observer.onViewAttachedToWindow(label);
        else apply(label);
    }

    public static void setSuppressed(boolean enabled) {
        if (suppressed == enabled) return;
        suppressed = enabled;
        for (TextView title : titles) apply(title);
    }

    private static void apply(TextView label) {
        ContentResolver resolver = label.getContext().getContentResolver();
        boolean moving = !suppressed && (Build.VERSION.SDK_INT < 34
            || label.getContext().getSystemService(UiModeManager.class).getContrast() < 1f)
            && Settings.Secure.getInt(resolver, HIGH_CONTRAST, 0) == 0
            && Settings.Global.getFloat(resolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) > 0;
        label.setEllipsize(moving ? TextUtils.TruncateAt.MARQUEE : TextUtils.TruncateAt.MIDDLE);
        label.setHorizontalFadingEdgeEnabled(moving);
        label.setFadingEdgeLength(Math.round(8 * label.getResources().getDisplayMetrics().density));
        label.setMarqueeRepeatLimit(1);
        label.setSelected(moving);
    }

    @Override public void onViewAttachedToWindow(View view) {
        ContentResolver resolver = view.getContext().getContentResolver();
        resolver.registerContentObserver(Settings.Secure.getUriFor(HIGH_CONTRAST), false, this);
        resolver.registerContentObserver(Settings.Global.getUriFor(Settings.Global.ANIMATOR_DURATION_SCALE), false, this);
        if (Build.VERSION.SDK_INT >= 34) {
            UiModeManager manager = view.getContext().getSystemService(UiModeManager.class);
            UiModeManager.ContrastChangeListener listener = contrast -> apply(label);
            manager.addContrastChangeListener(view.getContext().getMainExecutor(), listener);
            removeContrastListener = () -> manager.removeContrastChangeListener(listener);
        }
        apply(label);
    }

    @Override public void onViewDetachedFromWindow(View view) {
        view.getContext().getContentResolver().unregisterContentObserver(this);
        if (removeContrastListener != null) {
            removeContrastListener.run();
            removeContrastListener = null;
        }
    }

    @Override public void onChange(boolean selfChange) {
        apply(label);
    }
}
