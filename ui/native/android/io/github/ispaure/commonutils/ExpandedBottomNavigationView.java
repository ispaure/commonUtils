package io.github.ispaure.commonutils;

import android.content.Context;
import android.view.View;
import com.google.android.material.bottomnavigation.BottomNavigationView;
import com.google.android.material.bottomnavigation.BottomNavigationMenuView;
import com.google.android.material.navigation.NavigationBarMenuView;

/** Up to seven compact destinations; avoids Material 1.12's five-width array. */
public final class ExpandedBottomNavigationView extends BottomNavigationView {
    public ExpandedBottomNavigationView(Context context) { super(context); }
    @Override public int getMaxItemCount() { return 7; }
    @Override protected NavigationBarMenuView createNavigationBarMenuView(Context context) {
        return new ExpandedMenu(context);
    }
    private static final class ExpandedMenu extends BottomNavigationMenuView {
        ExpandedMenu(Context context) { super(context); }
        @Override protected void onMeasure(int widthSpec, int heightSpec) {
            int count = 0;
            for (int i = 0; i < getChildCount(); i++) if (getChildAt(i).getVisibility() != GONE) count++;
            int width = MeasureSpec.getSize(widthSpec);
            int height = resolveSize(Math.round(64 * getResources().getDisplayMetrics().density), heightSpec);
            int cell = count == 0 ? width : width / count;
            for (int i = 0; i < getChildCount(); i++) {
                View child = getChildAt(i);
                if (child.getVisibility() != GONE) child.measure(
                    MeasureSpec.makeMeasureSpec(cell, MeasureSpec.EXACTLY),
                    MeasureSpec.makeMeasureSpec(height, MeasureSpec.EXACTLY));
            }
            setMeasuredDimension(width, height);
        }
        @Override protected void onLayout(boolean changed, int left, int top, int right, int bottom) {
            boolean rtl = getLayoutDirection() == LAYOUT_DIRECTION_RTL;
            int offset = 0;
            for (int i = 0; i < getChildCount(); i++) {
                View child = getChildAt(i);
                if (child.getVisibility() == GONE) continue;
                int width = child.getMeasuredWidth();
                int x = rtl ? getWidth() - offset - width : offset;
                child.layout(x, 0, x + width, getHeight());
                offset += width;
            }
        }
    }
}
