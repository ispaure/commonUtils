package io.github.ispaure.commonutils;

import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.Paint;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.text.Editable;
import android.text.Layout;
import android.text.Spanned;
import android.text.TextWatcher;
import android.text.style.ForegroundColorSpan;
import android.view.View;
import android.view.ViewTreeObserver;
import android.view.inputmethod.BaseInputConnection;
import android.view.inputmethod.EditorInfo;
import android.widget.EditText;
import java.util.ArrayList;
import java.util.Arrays;

/** Presentation attached to the existing native editor: no replacement text/IME. */
public final class CodeEditorSupport implements TextWatcher,
        View.OnLayoutChangeListener, ViewTreeObserver.OnScrollChangedListener {
    private final EditText editor;
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final ArrayList<ForegroundColorSpan> colours = new ArrayList<>();
    private final Drawable gutter;
    private int[] starts = {0};
    private int width;
    private final int originalLeft;

    public CodeEditorSupport(EditText editor) {
        this.editor = editor;
        originalLeft = editor.getPaddingLeft();
        editor.setTypeface(Typeface.MONOSPACE);
        // Keep IME composition; disable prose corrections and smart suggestions.
        editor.setInputType(android.text.InputType.TYPE_CLASS_TEXT
            | android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE
            | android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        // A landscape IME must resize the hosted editor, not replace it with
        // Android's separate fullscreen extraction window and hide its toolbar.
        editor.setImeOptions(editor.getImeOptions()
            | EditorInfo.IME_FLAG_NO_EXTRACT_UI | EditorInfo.IME_FLAG_NO_FULLSCREEN);
        gutter = new Drawable() {
            @Override public void draw(Canvas canvas) { drawGutter(canvas); }
            @Override public void setAlpha(int alpha) {}
            @Override public void setColorFilter(ColorFilter filter) {}
            @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }
        };
        editor.getOverlay().add(gutter);
        editor.addTextChangedListener(this);
        editor.addOnLayoutChangeListener(this);
        editor.getViewTreeObserver().addOnScrollChangedListener(this);
        changed();
    }
    private void changed() {
        CharSequence text = editor.getText();
        int count = 1;
        for (int i = 0; i < text.length(); i++) if (text.charAt(i) == '\n') count++;
        starts = new int[count];
        for (int i = 0, n = 1; i < text.length(); i++)
            if (text.charAt(i) == '\n') starts[n++] = i + 1;
        paint.setTypeface(Typeface.MONOSPACE);
        paint.setTextSize(editor.getTextSize() * .85f);
        width = Math.max((int)(40 * editor.getResources().getDisplayMetrics().density),
            (int)paint.measureText(Integer.toString(count)) + originalLeft * 2 + 12);
        if (editor.getPaddingLeft() != width)
            editor.setPadding(width, editor.getPaddingTop(), editor.getPaddingRight(), editor.getPaddingBottom());
        refresh();
    }
    public boolean isComposing() {
        return BaseInputConnection.getComposingSpanStart(editor.getText()) >= 0;
    }
    public boolean isDark() {
        int c = editor.getCurrentTextColor();
        return ((c >> 16 & 255) + (c >> 8 & 255) + (c & 255)) > 420;
    }
    public void syntax(int[] beginnings, int[] endings, int[] rgb) {
        if (isComposing()) return;
        Editable text = editor.getText();
        for (ForegroundColorSpan span : colours) text.removeSpan(span);
        colours.clear();
        for (int i = 0; i < beginnings.length; i++) {
            if (beginnings[i] < 0 || endings[i] > text.length() || endings[i] <= beginnings[i]) continue;
            ForegroundColorSpan span = new ForegroundColorSpan(0xff000000 | rgb[i]);
            colours.add(span);
            text.setSpan(span, beginnings[i], endings[i], Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        }
        refresh();
    }
    private void refresh() {
        gutter.setBounds(0, 0, editor.getWidth(), editor.getHeight());
        gutter.invalidateSelf();
    }
    private void drawGutter(Canvas canvas) {
        Layout layout = editor.getLayout();
        if (layout == null) return;
        paint.setTypeface(Typeface.MONOSPACE);
        paint.setTextSize(editor.getTextSize() * .85f);
        paint.setColor(editor.getCurrentTextColor());
        paint.setAlpha(150);
        int top = editor.getScrollY() - editor.getTotalPaddingTop();
        int first = layout.getLineForVertical(Math.max(0, top));
        int last = layout.getLineForVertical(top + editor.getHeight());
        for (int row = first; row <= last; row++) {
            int offset = layout.getLineStart(row);
            int logical = Arrays.binarySearch(starts, offset);
            if (logical < 0) continue; // Wrapped continuations have no second number.
            String number = Integer.toString(logical + 1);
            float y = editor.getTotalPaddingTop() + layout.getLineBaseline(row) - editor.getScrollY();
            canvas.drawText(number, width - originalLeft - 8 - paint.measureText(number), y, paint);
        }
        paint.setAlpha(65);
        canvas.drawLine(width - 4, 0, width - 4, editor.getHeight(), paint);
    }
    @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
    @Override public void onTextChanged(CharSequence s, int start, int before, int count) {}
    @Override public void afterTextChanged(Editable text) { changed(); }
    @Override public void onScrollChanged() { refresh(); }
    @Override public void onLayoutChange(View v, int l, int t, int r, int b,
            int oldL, int oldT, int oldR, int oldB) { refresh(); }
    public void dispose() {
        editor.removeTextChangedListener(this);
        editor.removeOnLayoutChangeListener(this);
        if (editor.getViewTreeObserver().isAlive())
            editor.getViewTreeObserver().removeOnScrollChangedListener(this);
        editor.getOverlay().remove(gutter);
        colours.clear();
    }
}
