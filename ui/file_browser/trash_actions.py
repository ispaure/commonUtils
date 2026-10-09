"""Browser removal confirmations and safe Trash / Recycle Bin fallback UX."""
from .. import pyside as qt
from ...file_removal import removal_plan, remove_items


class TrashActionsMixin:
    def delete_selected(self):
        # A Delete key in a search field or inline rename editor edits text.
        focus = qt.QApplication.focusWidget()
        if isinstance(focus, (qt.QLineEdit, qt.QTextEdit, qt.QPlainTextEdit)):
            return
        self.delete(self.browser.selected_objects())

    def delete(self, selection):
        if not selection or self.busy or self.browser.stopping:
            return
        try:
            plan = removal_plan(item.path for item in selection)
        except (OSError, ValueError) as error:
            self._error(str(error))
            return
        if plan and self._confirm_removal(plan):
            self._start_removal(plan)

    def _confirm_removal(self, plan, *, permanent=False):
        box = qt.QMessageBox(self.browser)
        box.setIcon(qt.QMessageBox.Icon.Warning if permanent else qt.QMessageBox.Icon.Question)
        box.setWindowTitle('Delete permanently?' if permanent else 'Move to Trash / Recycle Bin?')
        box.setTextFormat(qt.Qt.TextFormat.PlainText)
        names = '\n'.join(item.path.name for item in plan[:8])
        if len(plan) > 8:
            names += f'\n…and {len(plan) - 8} more'
        box.setText(f'{"Permanently delete" if permanent else "Move"} {len(plan)} selected '
                    f'item{"s" if len(plan) != 1 else ""}{"" if permanent else " to the system Trash / Recycle Bin"}?\n\n{names}')
        box.setInformativeText('This cannot be undone. Selected folders and everything inside them will be deleted.'
            if permanent else 'Selected folders include their contents. If this location does not support Trash '
            '(for example, some network drives), the items will be left in place.')
        box.setDetailedText('\n'.join(str(item.path) for item in plan))
        confirm = box.addButton('Delete permanently' if permanent else 'Move to Trash', qt.QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton(qt.QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        box.exec()
        return box.clickedButton() == confirm

    @staticmethod
    def _system_trash(path):
        file = qt.QFile(str(path))
        if not file.moveToTrash():
            raise OSError('System Trash / Recycle Bin is unavailable for this item. '
                          'The location may not support it, or you may lack permission. ' + file.errorString())
        return True

    def _start_removal(self, plan, *, permanent=False):
        if self.busy or self.browser.stopping:
            return
        self._removal_plan = plan
        self._removal_permanent = permanent
        self._operation_kind = 'remove'
        self.browser.model.setReadOnly(True)
        self.task.start(lambda report, cancelled: remove_items(plan, trash=self._system_trash,
            permanent=permanent, report=report, cancelled=cancelled),
            message='Deleting permanently…' if permanent else 'Moving to Trash / Recycle Bin…')

    def _removal_completed(self, result, error):
        plan = self._removal_plan
        if not self.browser.stopping:
            self.browser.refresh_changed(tuple(item.path.parent for item in plan))
            if result:
                from .file_actions import prune_cut_clipboard
                prune_cut_clipboard(result.completed)
                for path in result.completed:
                    self.browser.model.invalidate(path)
                    self.browser.views.covers.invalidate(path)
                if self.browser.index_search.active:
                    self.browser.index_search.refresh()
            if error:
                self._error(error)
            elif result and result.failures:
                message = '\n'.join(f'{path.name}: {issue}' for path, issue in result.failures)
                if self._removal_permanent or result.cancelled:
                    self._error(message)
                else:
                    box = qt.QMessageBox(self.browser)
                    box.setWindowTitle('Some items could not be moved to Trash')
                    box.setIcon(qt.QMessageBox.Icon.Warning)
                    box.setTextFormat(qt.Qt.TextFormat.PlainText)
                    box.setText('The following items were left in place. You can keep them, or review a permanent deletion.')
                    box.setDetailedText(message)
                    review = box.addButton('Review permanent deletion…', qt.QMessageBox.ButtonRole.DestructiveRole)
                    keep = box.addButton('Keep items', qt.QMessageBox.ButtonRole.RejectRole)
                    box.setDefaultButton(keep)
                    box.setEscapeButton(keep)
                    box.exec()
                    failed = {path for path, issue in result.failures}
                    remaining = tuple(item for item in plan if item.path in failed)
                    if box.clickedButton() == review and self._confirm_removal(remaining, permanent=True):
                        self._start_removal(remaining, permanent=True)
        self.browser._maybe_idle()
