package io.github.ispaure.commonutils;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.Matrix;
import android.graphics.RectF;
import android.graphics.drawable.Drawable;
import android.view.MotionEvent;
import android.view.Gravity;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.PopupWindow;
import android.view.ViewConfiguration;
import android.view.ScaleGestureDetector;
import androidx.appcompat.widget.AppCompatImageView;

/** Bounded per-page zoom; horizontal paging is admitted only at fit scale. */
public final class ImageCanvasView extends AppCompatImageView {
    public interface PageListener {
        void page(int direction);
        void toggleControls();
        default void magnifierZoom(int percent) {}
    }
    private PageListener listener;
    private final Matrix matrix = new Matrix();
    private final ScaleGestureDetector detector;
    private float zoom = 1, base = 1, lastX, lastY, startX, startY;
    private boolean multiplePointers, verticalPaging;
    public void setVerticalPaging(boolean value) { verticalPaging = value; }
    private boolean magnifierEnabled, lensActive, lensConsumed, touchActive;
    private int magnifierZoom = 190;
    private PopupWindow lensControls;
    private Button lensLess, lensMore;
    private final Paint lensPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path lensClip = new Path();
    private final Runnable hold = () -> {
        if (magnifierEnabled && touchActive && !multiplePointers && containsImage(lastX, lastY)) {
            lensActive = lensConsumed = true;
            showLensControls();
            invalidate();
        }
    };

    public void setMagnifierEnabled(boolean enabled) {
        magnifierEnabled = enabled;
        dismissMagnifier();
    }
    private void dismissMagnifier() {
        if (hold != null) removeCallbacks(hold);
        lensActive = false;
        if (lensControls != null) lensControls.dismiss();
        lensControls = null;
        lensLess = lensMore = null;
        invalidate();
    }
    private boolean containsImage(float x, float y) {
        Drawable image = getDrawable();
        if (image == null) return false;
        Matrix inverse = new Matrix();
        if (!matrix.invert(inverse)) return false;
        float[] point = {x - getPaddingLeft(), y - getPaddingTop()};
        inverse.mapPoints(point);
        return point[0] >= 0 && point[1] >= 0 && point[0] <= image.getIntrinsicWidth()
            && point[1] <= image.getIntrinsicHeight();
    }
    private RectF lensBounds() {
        float density = getResources().getDisplayMetrics().density;
        float factor = Math.max(1, Math.min(2, Math.min(getWidth(), getHeight()) / (400*density)));
        float width = Math.min(180*density*factor, getWidth()), height = Math.min(140*density*factor, getHeight());
        float left = Math.max(0, Math.min(lastX-width/2, getWidth()-width));
        float top = Math.max(0, Math.min(lastY-height-36*density + .045f*getHeight(), getHeight()-height));
        return new RectF(left, top, left+width, top+height);
    }
    private RectF lensControlsBounds() {
        float density = getResources().getDisplayMetrics().density;
        RectF lens = lensBounds();
        float left = Math.max(0, lens.left - 6*density);
        float right = Math.min(getWidth(), lens.right + 6*density);
        float top = Math.max(0, Math.min(lens.bottom - 24*density, getHeight() - 33*density));
        return new RectF(left, top, right, top + 33*density);
    }
    public int getMagnifierZoom() { return magnifierZoom; }
    public void setMagnifierZoom(int value) {
        if (value < 150 || value > 250 || (value-150)%20 != 0)
            throw new IllegalArgumentException("Magnifier zoom must be 150–250%, in 20% steps.");
        magnifierZoom = value;
        updateLensControls();
        invalidate();
    }
    private void changeMagnifierZoom(int direction) {
        int value = Math.max(150, Math.min(250, magnifierZoom + 20*direction));
        if (value == magnifierZoom) return;
        if (listener != null) listener.magnifierZoom(value);
        else setMagnifierZoom(value);
    }
    private void showLensControls() {
        if (getWindowToken() == null) return;
        Context context = getContext();
        float density = getResources().getDisplayMetrics().density;
        int side = Math.round(33*density);
        FrameLayout bar = new FrameLayout(context);
        lensLess = new Button(context);
        lensMore = new Button(context);
        for (Button button : new Button[]{lensLess, lensMore}) {
            button.setPadding(0, 0, 0, 0);
            button.setMinWidth(0); button.setMinimumWidth(0);
            button.setMinHeight(0); button.setMinimumHeight(0);
            button.setTextSize(18); button.setTextColor(Color.WHITE);
            button.setBackgroundColor(0xDD000000);
        }
        lensLess.setText("−"); lensMore.setText("+");
        lensLess.setContentDescription("Decrease magnifier zoom");
        lensMore.setContentDescription("Increase magnifier zoom");
        lensLess.setOnClickListener(view -> changeMagnifierZoom(-1));
        lensMore.setOnClickListener(view -> changeMagnifierZoom(1));
        bar.addView(lensLess, new FrameLayout.LayoutParams(side, side, Gravity.LEFT | Gravity.TOP));
        bar.addView(lensMore, new FrameLayout.LayoutParams(side, side, Gravity.RIGHT | Gravity.TOP));
        RectF rect = lensControlsBounds();
        lensControls = new PopupWindow(bar, Math.round(rect.width()), side, false);
        lensControls.setInputMethodMode(PopupWindow.INPUT_METHOD_NOT_NEEDED);
        // Route a second finger to the buttons without cancelling the held
        // image gesture or treating that finger as a pinch.
        lensControls.setSplitTouchEnabled(true);
        lensControls.setOutsideTouchable(false);
        lensControls.setClippingEnabled(true);
        int[] origin = new int[2];
        getLocationOnScreen(origin);
        lensControls.showAtLocation(this, Gravity.TOP | Gravity.LEFT,
            origin[0]+Math.round(rect.left), origin[1]+Math.round(rect.top));
        updateLensControls();
    }
    private void updateLensControls() {
        if (lensControls == null) return;
        lensLess.setEnabled(magnifierZoom > 150); lensMore.setEnabled(magnifierZoom < 250);
        lensLess.setAlpha(magnifierZoom > 150 ? 1f : .4f);
        lensMore.setAlpha(magnifierZoom < 250 ? 1f : .4f);
        RectF rect = lensControlsBounds();
        int[] origin = new int[2]; getLocationOnScreen(origin);
        float density = getResources().getDisplayMetrics().density;
        lensControls.update(origin[0]+Math.round(rect.left), origin[1]+Math.round(rect.top),
            Math.round(rect.width()), Math.round(33*density));
    }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        if (!lensActive || getDrawable() == null) return;
        float density = getResources().getDisplayMetrics().density;
        RectF rect = lensBounds();
        float height = rect.height();
        float offset = height/2 + 36*density - .045f*getHeight();
        float push = offset > 0 ? Math.max(0, Math.min(1, (lastY-(getHeight()-offset))/offset))
            : offset < 0 ? Math.max(0, Math.min(1, 1-lastY/-offset)) : 0;
        float sampleX = Math.max(0, Math.min(lastX, getWidth()));
        float sampleY = Math.max(0, Math.min(lastY-offset+push*offset, getHeight()));
        lensClip.reset();
        lensClip.addRoundRect(rect, 24*density, 24*density, Path.Direction.CW);
        int saved = canvas.save();
        canvas.clipPath(lensClip);
        canvas.drawColor(Color.BLACK);
        canvas.translate(rect.centerX(), rect.centerY());
        canvas.scale(magnifierZoom/100f, magnifierZoom/100f);
        // At the edges, dragging keeps moving the sample beyond the fixed lens.
        canvas.translate(-sampleX+getPaddingLeft(), -sampleY+getPaddingTop());
        canvas.concat(matrix);
        // Reuse original decoded pixels, rather than enlarging a screenshot.
        getDrawable().draw(canvas);
        canvas.restoreToCount(saved);
        lensPaint.setColor(Color.WHITE);
        lensPaint.setStyle(Paint.Style.STROKE);
        lensPaint.setStrokeWidth(2*density);
        canvas.drawRoundRect(rect, 24*density, 24*density, lensPaint);
    }
    @Override protected void onDetachedFromWindow() {
        touchActive = false;
        dismissMagnifier();
        super.onDetachedFromWindow();
    }
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
        dismissMagnifier();
        fit();
    }
    @Override public void setImageDrawable(Drawable image) {
        dismissMagnifier();
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
            dismissMagnifier();
            multiplePointers = lensConsumed = false;
            touchActive = true;
            startX = lastX = event.getX(); startY = lastY = event.getY();
            if (zoom <= 1.05f && (startX < 24*density || startX > getWidth()-24*density)) {
                touchActive = false;
                return false;
            }
            if (magnifierEnabled) postDelayed(hold, 400);
            getParent().requestDisallowInterceptTouchEvent(true);
        }
        if (event.getPointerCount() > 1) {
            multiplePointers = true;
            dismissMagnifier();
        }
        float slop = ViewConfiguration.get(getContext()).getScaledTouchSlop();
        if (!lensActive && (Math.abs(event.getX()-startX) > slop || Math.abs(event.getY()-startY) > slop)) removeCallbacks(hold);
        detector.onTouchEvent(event);
        if (event.getActionMasked() == MotionEvent.ACTION_MOVE && !detector.isInProgress() && zoom > 1.05f && !lensActive) {
            matrix.postTranslate(event.getX()-lastX, event.getY()-lastY);
            constrain();
        }
        if (event.getActionMasked() == MotionEvent.ACTION_UP) {
            float dx = event.getX()-startX, dy = event.getY()-startY;
            float threshold = Math.max(32*density, Math.min(80*density, getWidth()*.12f));
            float along = verticalPaging ? dy : dx, across = verticalPaging ? dx : dy;
            if (!lensConsumed && !multiplePointers && zoom <= 1.05f && Math.abs(along) > threshold && Math.abs(along) > Math.abs(across)*1.5f && listener != null) listener.page(along < 0 ? 1 : -1);
            else if (!lensConsumed && !multiplePointers && Math.abs(dx) < 12*density && Math.abs(dy) < 12*density) performClick();
            touchActive = false;
            dismissMagnifier();
            getParent().requestDisallowInterceptTouchEvent(false);
        } else if (event.getActionMasked() == MotionEvent.ACTION_CANCEL) {
            touchActive = false;
            dismissMagnifier();
            getParent().requestDisallowInterceptTouchEvent(false);
        } else {
            getParent().requestDisallowInterceptTouchEvent(true);
        }
        lastX = event.getX(); lastY = event.getY();
        if (lensActive) { updateLensControls(); invalidate(); }
        return true;
    }
    @Override public boolean performClick() {
        super.performClick();
        if (listener != null) listener.toggleControls();
        return true;
    }
}
