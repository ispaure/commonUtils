package io.github.ispaure.commonutils;

import android.content.Context;
import android.content.ClipData;
import android.view.DragEvent;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Rect;
import android.text.TextUtils;
import android.util.SparseArray;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.TouchDelegate;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;

/** A viewport-sized pool of rows. No Python callbacks are needed to bind text. */
public final class FileListView extends ListView {
    // Native dp/sp; consumers may override these before publishing rows.
    private int rowHeight = 48, bodyText = 17, captionText = 13, iconSize = 28;
    public interface Listener {
        void onActivate(int index, int generation);
        void onVisible(int index, int generation);
        void onContext(int index, int generation);
    }

    /** Optional tree interaction; indices are valid only for their source generation. */
    public interface TreeListener {
        void onToggle(int index, int generation);
        boolean onStartDrag(int index, int generation);
        boolean onCanDrop(int index, int generation);
        boolean onDrop(int index, int generation);
        void onEndDrag(int generation);
    }
    private TreeListener treeListener;
    private int[] depths = new int[0], disclosures = new int[0];
    private boolean[] landingRows = new boolean[0];
    private Bitmap landingIcon;
    private String dragToken;
    public void setTreeListener(TreeListener value) { treeListener = value; }
    public void setTreeRows(int[] indent, int[] expanded, boolean[] landing, Bitmap icon, String token) {
        if (indent.length != titles.length || expanded.length != titles.length || landing.length != titles.length)
            throw new IllegalArgumentException("Tree metadata must match the current rows");
        depths = indent; disclosures = expanded; landingRows = landing;
        landingIcon = icon; dragToken = token;
        rows.notifyDataSetChanged();
    }

    private Listener listener;
    private String[] titles = new String[0], subtitles = new String[0];
    private boolean[] folders = new boolean[0];
    private int generation;
    private Bitmap folderIcon, fileIcon;
    private final SparseArray<Bitmap> thumbnails = new SparseArray<>();
    private final Rows rows = new Rows();
    private int createdRows;
    private boolean observeRows;
    private boolean contextActions;
    private String rowKind = "File";
    private int textColor, mutedColor, surfaceColor, selectedTextColor, selectedColor, accentColor;
    private final Paint outline = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint rowDivider = new Paint();
    private boolean outlined;
    private final Path groupClip = new Path();
    private final RectF groupBounds = new RectF();

    public FileListView(Context context) {
        super(context);
        // Reserve the scrollbar width plus a small gap outside the row outlines.
        setScrollBarStyle(View.SCROLLBARS_OUTSIDE_INSET);
        setPadding(0, 0, dp(2), 0);
        setAdapter(rows);
        setChoiceMode(CHOICE_MODE_SINGLE);
        setHeaderDividersEnabled(false);
        setFooterDividersEnabled(false);
        setDivider(null);
        setDividerHeight(dp(1));
        setRecyclerListener(view -> scrub(view));
        setOnItemClickListener((parent, view, position, id) -> {
            selectRow(position);
            if (listener != null) listener.onActivate(position, generation);
        });
        setOnItemLongClickListener((parent, view, position, id) -> {
            if (!contextActions || !isEnabled()) return false;
            selectRow(position);
            if (listener != null) listener.onContext(position, generation);
            return true;
        });
    }

    public void setMetrics(int height, int body, int caption, int icon) {
        rowHeight = height; bodyText = body; captionText = caption; iconSize = icon;
    }

    public void setListener(Listener value) { listener = value; }
    public void setObserveRows(boolean enabled) { observeRows = enabled; }
    public void setContextActions(boolean enabled) {
        contextActions = enabled;
        invalidateViews();
    }
    public void setRowKind(String kind) { rowKind = kind; }
    public void setPalette(int text, int muted, int surface, int selectedText, int selected, int accent, int border, boolean highContrast) {
        textColor = text;
        mutedColor = muted;
        surfaceColor = surface;
        selectedTextColor = selectedText;
        selectedColor = selected;
        accentColor = accent;
        // Empty space below a short group belongs to the surrounding page.
        setBackgroundColor(android.graphics.Color.TRANSPARENT);
        rowDivider.setColor(border);
        outlined = highContrast;
        outline.setColor(border);
        outline.setStrokeWidth(dp(1));
        outline.setStyle(Paint.Style.STROKE);
        invalidateViews();
        invalidate();
    }

    private boolean clipGroup(Canvas canvas) {
        if (getChildCount() == 0) return false;
        float bottom = Math.min(getHeight(), getChildAt(getChildCount() - 1).getBottom());
        groupBounds.set(getListPaddingLeft(), 0, getWidth() - getListPaddingRight(), bottom);
        groupClip.reset();
        float radius = dp(16);
        groupClip.addRoundRect(groupBounds, radius, radius, Path.Direction.CW);
        canvas.clipPath(groupClip);
        return true;
    }

    @Override protected void onDraw(Canvas canvas) {
        int saved = canvas.save();
        if (clipGroup(canvas)) {
            canvas.drawColor(surfaceColor);
            super.onDraw(canvas);
        }
        canvas.restoreToCount(saved);
    }

    @Override protected void dispatchDraw(Canvas canvas) {
        int saved = canvas.save();
        if (clipGroup(canvas)) {
            super.dispatchDraw(canvas);
            for (int i = 0; i < getChildCount(); i++) {
                // Dataset position, not viewport position: never underline the
                // last item, including short, single-row and scrolled lists.
                if (getFirstVisiblePosition() + i >= titles.length - 1) break;
                int bottom = getChildAt(i).getBottom();
                canvas.drawRect(getListPaddingLeft() + dp(8), bottom,
                        getWidth() - getListPaddingRight() - dp(8),
                        bottom + getDividerHeight(), rowDivider);
            }
        }
        canvas.restoreToCount(saved);
        if (outlined && getChildCount() > 0) {
            // Enclose short lists at their last row; long lists frame the viewport.
            float halfStroke = outline.getStrokeWidth() / 2f;
            float bottom = Math.min(getHeight(), getChildAt(getChildCount() - 1).getBottom());
            canvas.drawRoundRect(getListPaddingLeft() + halfStroke, halfStroke,
                    getWidth() - getListPaddingRight() - halfStroke,
                    bottom - halfStroke, dp(16) - halfStroke, dp(16) - halfStroke, outline);
        }
    }
    private boolean[] hiddenRows = new boolean[0];

    public void setRows(String[] names, String[] descriptions, boolean[] directories, int revision) {
        // Invalidate both attached and scrapped cells so private names/icons
        // cannot survive a lock, close, or provider change in the recycler.
        for (int i = 0; i < getChildCount(); i++) scrub(getChildAt(i));
        titles = names;
        subtitles = descriptions;
        folders = directories;
        hiddenRows = new boolean[names.length];
        depths = new int[0]; disclosures = new int[0]; landingRows = new boolean[0];
        landingIcon = null; dragToken = null;
        generation = revision;
        thumbnails.clear();
        clearChoices();
        rows.notifyDataSetChanged();
        setSelection(0);
        invalidateViews();
    }

    public void setHiddenRows(boolean[] hidden) {
        hiddenRows = hidden;
        rows.notifyDataSetChanged();
        invalidateViews();
    }

    public void setIcons(Bitmap folder, Bitmap file) {
        folderIcon = folder;
        fileIcon = file;
    }

    public void setRowIcon(int index, Bitmap image, int revision) {
        if (revision != generation || index < 0 || index >= titles.length) return;
        if (image == null) thumbnails.remove(index);
        else thumbnails.put(index, image);
        // Keep decoded previews bounded; ordinary rows share two bitmaps.
        while (thumbnails.size() > 64) thumbnails.removeAt(0);
        int visible = index - getFirstVisiblePosition();
        if (visible >= 0 && visible < getChildCount()) {
            Holder holder = (Holder) getChildAt(visible).getTag();
            holder.preview = image != null;
            holder.icon.setImageBitmap(image != null ? image : defaultIcon(index));
            paint(getChildAt(visible), isItemChecked(index));
        }
    }

    public void selectRow(int position) {
        clearChoices();
        if (position >= 0 && position < titles.length) setItemChecked(position, true);
        for (int i = 0; i < getChildCount(); i++) {
            View view = getChildAt(i);
            boolean selected = getFirstVisiblePosition() + i == position;
            view.setActivated(selected);
            paint(view, selected);
        }
    }

    public int getCreatedRowCount() { return createdRows; }

    private Holder visibleHolder(int index, int revision) {
        if (revision != generation) return null;
        int child = index - getFirstVisiblePosition();
        if (child < 0 || child >= getChildCount()) return null;
        Holder holder = (Holder) getChildAt(child).getTag();
        return holder != null && holder.index == index && holder.revision == revision ? holder : null;
    }

    /** Current visible controls only; never exposes a recycled or replaced row. */
    public View getRowTitleView(int index, int revision) {
        Holder holder = visibleHolder(index, revision);
        return holder == null ? null : holder.title;
    }
    public View getRowActionView(int index, int revision) {
        Holder holder = visibleHolder(index, revision);
        return holder == null ? null : holder.actions;
    }
    public View getRowDisclosureView(int index, int revision) {
        Holder holder = visibleHolder(index, revision);
        return holder == null ? null : holder.disclosure;
    }
    public View getRowIconView(int index, int revision) {
        Holder holder = visibleHolder(index, revision);
        return holder == null ? null : holder.icon;
    }

    public int getVerticalPosition() {
        View first = getChildAt(0);
        return first == null ? 0 : Math.max(0,
                getFirstVisiblePosition() * rowStride() - first.getTop() + getPaddingTop());
    }

    public int getMaxVerticalPosition() {
        return Math.max(0, titles.length * dp(rowHeight)
                + Math.max(0, titles.length - 1) * getDividerHeight() - getHeight()
                + getPaddingTop() + getPaddingBottom());
    }

    public void setVerticalPosition(int value) {
        int position = Math.max(0, Math.min(value, getMaxVerticalPosition()));
        int height = rowStride();
        setSelectionFromTop(position / height, -(position % height));
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private int rowStride() {
        return dp(rowHeight) + getDividerHeight();
    }

    private void scrub(View view) {
        Holder holder = (Holder) view.getTag();
        if (holder == null) return;
        holder.index = -1;
        holder.title.setText("");
        if (holder.disclosure != null) {
            holder.disclosure.setOnClickListener(null);
            holder.disclosure.setContentDescription("");
        }
        holder.icon.setOnLongClickListener(null);
        view.setOnDragListener(null);
        holder.subtitle.setText("");
        holder.icon.setImageDrawable(null);
        holder.actions.setOnClickListener(null);
        holder.actions.setContentDescription("");
        view.setContentDescription("");
    }

    private void paint(View view, boolean selected) {
        Holder holder = (Holder) view.getTag();
        int foreground = holder.hidden
            ? (selected && outlined ? (selectedTextColor & 0x00ffffff) | 0xb3000000 : mutedColor)
            : selected ? selectedTextColor : textColor;
        view.setBackgroundColor(selected ? selectedColor : surfaceColor);
        holder.title.setTextColor(foreground);
        holder.subtitle.setTextColor(selected ? foreground : mutedColor);
        holder.actions.setTextColor(selected ? foreground : accentColor);
        if (holder.disclosure != null) holder.disclosure.setTextColor(selected ? foreground : accentColor);
        if (holder.preview) holder.icon.clearColorFilter();
        else holder.icon.setColorFilter(selected ? foreground : accentColor);
    }

    private static final class Holder {
        ImageView icon;
        TextView title, subtitle, actions, disclosure;
        int index = -1, revision;
        boolean preview, hidden;
    }

    private final class ActionRow extends LinearLayout {
        View action;
        TouchDelegate actionTouch;

        ActionRow(Context context) { super(context); }

        @Override protected void onLayout(boolean changed, int l, int t, int r, int b) {
            super.onLayout(changed, l, t, r, b);
            actionTouch = null;
            if (action != null && action.getVisibility() == View.VISIBLE) {
                Rect hit = new Rect();
                action.getHitRect(hit);
                hit.left = hit.right - dp(rowHeight);
                actionTouch = new TouchDelegate(hit, action);
            }
        }

        @Override public boolean dispatchTouchEvent(MotionEvent event) {
            // The action owns a full row-height-wide slot, separate from the filename.
            if (contextActions && FileListView.this.isEnabled() && actionTouch != null
                    && actionTouch.onTouchEvent(event)) return true;
            return super.dispatchTouchEvent(event);
        }
    }

    private boolean validTreeRow(Holder holder, int index, int revision) {
        return isEnabled() && treeListener != null && holder.revision == revision && revision == generation
                && holder.index == index && index >= 0 && index < titles.length;
    }

    private Bitmap defaultIcon(int index) {
        return index < landingRows.length && landingRows[index] && landingIcon != null
                ? landingIcon : folders[index] ? folderIcon : fileIcon;
    }

    private final class Rows extends BaseAdapter {
        @Override public int getCount() { return titles.length; }
        @Override public Object getItem(int position) { return titles[position]; }
        @Override public long getItemId(int position) { return position; }

        @Override public View getView(int position, View recycled, ViewGroup parent) {
            Holder holder;
            if (recycled == null) {
                createdRows++;
                ActionRow row = new ActionRow(getContext());
                row.setGravity(Gravity.CENTER_VERTICAL);
                row.setPadding(dp(8), 0, dp(4), 0);
                row.setLayoutParams(new ListView.LayoutParams(-1, dp(rowHeight)));
                android.util.TypedValue background = new android.util.TypedValue();
                getContext().getTheme().resolveAttribute(android.R.attr.activatedBackgroundIndicator,
                        background, true);
                if (background.resourceId != 0) row.setBackgroundResource(background.resourceId);
                holder = new Holder();
                holder.icon = new ImageView(getContext());
                holder.icon.setScaleType(ImageView.ScaleType.FIT_CENTER);
                holder.icon.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
                row.addView(holder.icon, new LinearLayout.LayoutParams(dp(iconSize), dp(iconSize)));
                LinearLayout text = new LinearLayout(getContext());
                text.setOrientation(LinearLayout.VERTICAL);
                text.setPadding(dp(6), 0, dp(4), 0);
                holder.title = new TextView(getContext());
                holder.title.setSingleLine(true);
                holder.title.setEllipsize(TextUtils.TruncateAt.MIDDLE);
                holder.title.setTextSize(bodyText);
                holder.subtitle = new TextView(getContext());
                holder.subtitle.setSingleLine(true);
                holder.subtitle.setTextSize(captionText);
                text.addView(holder.title);
                text.addView(holder.subtitle);
                row.addView(text, new LinearLayout.LayoutParams(0, -2, 1));
                holder.actions = new Button(getContext(), null, android.R.attr.borderlessButtonStyle);
                holder.actions.setText("⋯");
                holder.actions.setTextSize(24);
                holder.actions.setGravity(Gravity.CENTER);
                holder.actions.setPadding(0, 0, 0, 0);
                holder.actions.setMinWidth(0);
                holder.actions.setMinimumWidth(0);
                holder.actions.setFocusable(false);
                holder.actions.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);
                row.addView(holder.actions, new LinearLayout.LayoutParams(dp(rowHeight), -1));
                row.action = holder.actions;
                row.setTag(holder);
                recycled = row;
            } else holder = (Holder) recycled.getTag();
            holder.index = position;
            holder.revision = generation;
            int depth = position < depths.length ? Math.max(0, Math.min(32, depths[position])) : 0;
            recycled.setPadding(dp(8 + depth * 12), 0, dp(4), 0);
            int expanded = position < disclosures.length ? disclosures[position] : -1;
            boolean landing = position < landingRows.length && landingRows[position];
            if (expanded >= 0 && holder.disclosure == null) {
                holder.disclosure = new Button(getContext(), null, android.R.attr.borderlessButtonStyle);
                holder.disclosure.setTextSize(22);
                holder.disclosure.setPadding(0, 0, 0, 0);
                holder.disclosure.setMinWidth(0);
                holder.disclosure.setMinimumWidth(0);
                holder.disclosure.setFocusable(false);
                ((LinearLayout) recycled).addView(holder.disclosure, 1,
                        new LinearLayout.LayoutParams(dp(32), -1));
            }
            final int treeRevision = generation;
            final Holder bound = holder;
            if (holder.disclosure != null) {
                holder.disclosure.setVisibility(expanded < 0 ? View.GONE : View.VISIBLE);
                holder.disclosure.setText(expanded == 1 ? "⌄" : "›");
                holder.disclosure.setContentDescription((expanded == 1 ? "Collapse " : "Expand ") + titles[position]);
                holder.disclosure.setOnClickListener(view -> {
                    if (validTreeRow(bound, position, treeRevision) && expanded >= 0)
                        treeListener.onToggle(bound.index, bound.revision);
                });
            }
            holder.title.setPaintFlags(landing ? holder.title.getPaintFlags() | Paint.UNDERLINE_TEXT_FLAG
                    : holder.title.getPaintFlags() & ~Paint.UNDERLINE_TEXT_FLAG);
            holder.icon.setOnLongClickListener(depths.length == 0 ? null : view -> {
                if (!validTreeRow(bound, position, treeRevision) || dragToken == null
                        || !treeListener.onStartDrag(bound.index, bound.revision)) return false;
                boolean started = view.startDragAndDrop(ClipData.newPlainText(dragToken, ""),
                        new View.DragShadowBuilder(view), null, 0);
                if (!started && treeListener != null) treeListener.onEndDrag(generation);
                return started;
            });
            recycled.setOnDragListener(depths.length == 0 ? null : (view, event) -> {
                if (!validTreeRow(bound, position, treeRevision)) return false;
                if (event.getAction() == DragEvent.ACTION_DRAG_ENDED) {
                    treeListener.onEndDrag(bound.revision);
                    paint(view, isItemChecked(bound.index));
                    return true;
                }
                if (dragToken == null || event.getClipDescription() == null
                        || !dragToken.contentEquals(event.getClipDescription().getLabel())) return false;
                if (event.getAction() == DragEvent.ACTION_DRAG_STARTED) return true;
                if (!folders[bound.index]) return false;
                if (event.getAction() == DragEvent.ACTION_DRAG_ENTERED
                        || event.getAction() == DragEvent.ACTION_DRAG_LOCATION) {
                    paint(view, treeListener.onCanDrop(bound.index, bound.revision));
                } else if (event.getAction() == DragEvent.ACTION_DROP) {
                    return treeListener.onDrop(bound.index, bound.revision);
                } else if (event.getAction() == DragEvent.ACTION_DRAG_EXITED) {
                    paint(view, isItemChecked(bound.index));
                }
                return true;
            });
            holder.title.setText(titles[position]);
            holder.hidden = position < hiddenRows.length && hiddenRows[position];
            holder.subtitle.setText(subtitles[position]);
            holder.subtitle.setVisibility(subtitles[position].isEmpty() ? View.GONE : View.VISIBLE);
            holder.icon.setImageBitmap(thumbnails.get(position,
                    defaultIcon(position)));
            holder.preview = thumbnails.get(position) != null;
            holder.actions.setVisibility(contextActions ? View.VISIBLE : View.GONE);
            holder.actions.setContentDescription((depths.length > 0 ? "Actions for " : "Select ") + titles[position]);
            final int revision = generation;
            holder.actions.setOnClickListener(view -> {
                if (contextActions && FileListView.this.isEnabled() && generation == revision && listener != null) {
                    selectRow(position);
                    listener.onContext(position, revision);
                }
            });
            recycled.setActivated(isItemChecked(position));
            paint(recycled, isItemChecked(position));
            recycled.setContentDescription(titles[position] + (folders[position] ? ". Folder" : ". " + rowKind));
            if (listener != null && observeRows) listener.onVisible(position, generation);
            return recycled;
        }
    }
}
