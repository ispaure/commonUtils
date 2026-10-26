"""Offline dropdown presentation for embedded HTML, without a toolkit dependency.

Native hosts continue to use their platform menus. WebViews embed these assets
once and create a WebDropdown for each command list; hosts own visibility and
command dispatch. CSS variables allow touch/desktop sizing and host palettes.
"""

DROPDOWN_CSS = r'''
[role=menu] [role=menuitem]{
  appearance:none;display:flex;align-items:center;gap:10px;width:100%;
  min-height:var(--dropdown-row-height,28px);padding:var(--dropdown-row-padding,6px 12px);
  margin:0;border:0;border-radius:0;box-shadow:none;background:transparent;
  color:inherit;font:inherit;text-align:left;cursor:pointer;
}
[role=menu] [role=menuitem]:disabled{opacity:.35;cursor:default}
[role=menu] [role=menuitem]:hover:not(:disabled),
[role=menu] [role=menuitem]:focus-visible{
  background:var(--dropdown-hover,#e3eaf7);outline-offset:-3px;
}
'''

DROPDOWN_SCRIPT = r'''
class WebDropdown {
  constructor(surface, trigger, {close, items = surface}) {
    this.surface = surface;
    this.trigger = trigger;
    this.items = items;
    this.close = close;
    this.active = false;
    trigger.setAttribute('aria-haspopup', 'menu');
    trigger.setAttribute('aria-expanded', 'false');
    surface.addEventListener('keydown', event => this.keydown(event));
  }
  entries() {
    return [...this.items.querySelectorAll('[role=menuitem]')]
      .filter(item => !item.disabled && item.getClientRects().length);
  }
  activate() {
    this.active = true;
    this.surface.setAttribute('role', 'menu');
    this.surface.setAttribute('aria-modal', 'false');
    this.trigger.setAttribute('aria-expanded', 'true');
    for (const item of this.items.querySelectorAll('button')) item.setAttribute('role', 'menuitem');
    this.entries()[0]?.focus();
  }
  deactivate() {
    this.active = false;
    this.trigger.setAttribute('aria-expanded', 'false');
  }
  keydown(event) {
    if (!this.active) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      this.close();
    } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      const items = this.entries();
      if (!items.length) return;
      event.preventDefault();
      event.stopPropagation();
      const index = items.indexOf(document.activeElement);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 :
        index < 0 ? (event.key === 'ArrowUp' ? items.length - 1 : 0) :
        (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      items[next].focus();
    }
  }
}
'''
