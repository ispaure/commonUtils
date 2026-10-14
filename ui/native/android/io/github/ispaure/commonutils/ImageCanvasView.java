package io.github.ispaure.commonutils;

import android.content.Context;
import android.graphics.Matrix;
import android.graphics.RectF;
import android.graphics.drawable.Drawable;
import android.view.MotionEvent;
import android.view.ScaleGestureDetector;
import androidx.appcompat.widget.AppCompatImageView;

/** Bounded per-page zoom; horizontal paging is admitted only at fit scale. */
public final class ImageCanvasView extends AppCompatImageView {
    public interface PageListener { void page(int direction); void toggleControls(); }
    private PageListener listener;
    private final Matrix matrix = new Matrix();
    private final ScaleGestureDetector detector;
    private float zoom = 1, base = 1, lastX, lastY, startX, startY;
    private boolean multiplePointers;
    public ImageCanvasView(Context context) {
        super(context);
        setScaleType(ScaleType.MATRIX);
        detector = new ScaleGestureDetector(context, new ScaleGestureDetector.SimpleOnScaleGestureListener() {
            @Override public boolean onScale(ScaleGestureDetector value) {
                float next = Math.max(1, Math.min(6, zoom * value.getScaleFactor()));
                matrix.postScale(next / zoom, next / zoom, value.getFocusX(), value.getFocusY());
                zoom = next;
                constrain();
                return true;
            }
        });
    }
    public void setPageListener(PageListener value) { listener = value; }
    public float getZoom() { return zoom; }
    public void setZoom(float value) {
        float next = Math.max(1, Math.min(6, value));
        matrix.postScale(next / zoom, next / zoom, getWidth() / 2f, getHeight() / 2f);
        zoom = next;
        constrain();
    }
    @Override protected void onSizeChanged(int w, int h, int oldw, int oldh) {
        super.onSizeChanged(w, h, oldw, oldh);
        fit();
    }
    @Override public void setImageDrawable(Drawable image) {
        super.setImageDrawable(image);
        // ImageView's constructor can call this before fields initialize.
        if (matrix != null) { zoom = 1; post(this::fit); }
    }
    private void fit() {
        Drawable image = getDrawable();
        if (image == null || getWidth() == 0 || getHeight() == 0) return;
        base = Math.min((float)getWidth() / image.getIntrinsicWidth(), (float)getHeight() / image.getIntrinsicHeight());
        float desired = zoom;
        zoom = 1;
        matrix.reset();
        matrix.postScale(base, base);
        constrain();
        if (desired > 1) setZoom(desired);
    }
    private void constrain() {
        Drawable image = getDrawable();
        if (image == null) return;
        RectF rect = new RectF(0, 0, image.getIntrinsicWidth(), image.getIntrinsicHeight());
        matrix.mapRect(rect);
        float dx = rect.width() <= getWidth() ? (getWidth() - rect.width()) / 2f - rect.left
            : rect.left > 0 ? -rect.left : rect.right < getWidth() ? getWidth() - rect.right : 0;
        float dy = rect.height() <= getHeight() ? (getHeight() - rect.height()) / 2f - rect.top
            : rect.top > 0 ? -rect.top : rect.bottom < getHeight() ? getHeight() - rect.bottom : 0;
        matrix.postTranslate(dx, dy);
        setImageMatrix(matrix);
    }
    @Override public boolean onTouchEvent(MotionEvent event) {
        float density = getResources().getDisplayMetrics().density;
        if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
            multiplePointers = false;
            startX = lastX = event.getX(); startY = lastY = event.getY();
            if (zoom <= 1.05f && (startX < 24*density || startX > getWidth()-24*density)) return false;
            getParent().requestDisallowInterceptTouchEvent(true);
        }
        if (event.getPointerCount() > 1) multiplePointers = true;
        detector.onTouchEvent(event);
        if (event.getActionMasked() == MotionEvent.ACTION_MOVE && !detector.isInProgress() && zoom > 1.05f) {
            matrix.postTranslate(event.getX()-lastX, event.getY()-lastY);
            constrain();
        }
        if (event.getActionMasked() == MotionEvent.ACTION_UP) {
            float dx = event.getX()-startX, dy = event.getY()-startY;
            float threshold = Math.max(32*density, Math.min(80*density, getWidth()*.12f));
            if (!multiplePointers && zoom <= 1.05f && Math.abs(dx) > threshold && Math.abs(dx) > Math.abs(dy)*1.5f && listener != null) listener.page(dx < 0 ? 1 : -1);
            else if (!multiplePointers && Math.abs(dx) < 12*density && Math.abs(dy) < 12*density) performClick();
            getParent().requestDisallowInterceptTouchEvent(false);
        } else if (event.getActionMasked() == MotionEvent.ACTION_CANCEL) {
            getParent().requestDisallowInterceptTouchEvent(false);
        } else {
            getParent().requestDisallowInterceptTouchEvent(true);
        }
        lastX = event.getX(); lastY = event.getY();
        return true;
    }
    @Override public boolean performClick() {
        super.performClick();
        if (listener != null) listener.toggleControls();
        return true;
    }
}
