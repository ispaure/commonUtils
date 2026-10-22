"""Native document selection for the pinned Toga 0.5.7 mobile backends."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from ...runtime.platform import get_os, OS
from ...runtime.resources.documents import AndroidDocuments, IOSDocuments, LocalDocuments

_ios_delegate_class = None
_ios_pickers = {}


def cancel_document_picker(window):
    """Cancel a pending Apple picker when its owning window disconnects."""
    picker = _ios_pickers.get(window.id)
    if picker is not None:
        picker[0].cancel()


async def pick_document(app, *, title='Open document'):
    current = get_os()
    if current is OS.ANDROID:
        from java import jclass
        Intent = jclass('android.content.Intent')
        Activity = jclass('android.app.Activity')
        intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType('*/*')
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        future = asyncio.get_running_loop().create_future()
        def complete(code, data):
            if not future.done():
                future.set_result(data.getData() if code == Activity.RESULT_OK and data else None)
        app._impl.start_activity(intent, on_complete=complete)
        uri = await future
        return (AndroidDocuments(app._impl.native.getContentResolver()), uri) if uri else None
    if current is OS.IOS:
        return await pick_ios(app)
    import toga
    path = await app.main_window.dialog(toga.OpenFileDialog(title))
    return (LocalDocuments(), path) if path else None


async def pick_ios(app, export_path=None):
    global _ios_delegate_class
    from rubicon.objc import ObjCClass, ObjCProtocol, objc_method
    key = app.main_window.id
    if key in _ios_pickers:
        raise RuntimeError('A document picker is already open in this window.')
    if _ios_delegate_class is None:
        NSObject = ObjCClass('NSObject')
        class CommonUtilsDocumentPickerDelegate(NSObject, protocols=(ObjCProtocol('UIDocumentPickerDelegate'),)):
            @objc_method
            def documentPicker_didPickDocumentsAtURLs_(self, picker, urls) -> None:
                if not self.future.done():
                    self.future.set_result(urls[0] if len(urls) else None)

            @objc_method
            def documentPickerWasCancelled_(self, picker) -> None:
                if not self.future.done():
                    self.future.set_result(None)
        _ios_delegate_class = CommonUtilsDocumentPickerDelegate
    # Open mode returns a scoped source URL. The adapter copies its bytes into
    # private storage while access is held, so no permission/bookmark is retained.
    if export_path is None:
        picker = ObjCClass('UIDocumentPickerViewController').alloc().initWithDocumentTypes(
            ['public.data'], inMode=1)
    else:
        url = ObjCClass('NSURL').fileURLWithPath(str(export_path))
        picker = ObjCClass('UIDocumentPickerViewController').alloc().initWithURL(url, inMode=2)
    delegate = _ios_delegate_class.alloc().init()
    picker.delegate = delegate
    picker.allowsMultipleSelection = False
    future = asyncio.get_running_loop().create_future()
    delegate.future = future
    _ios_pickers[key] = (future, delegate, picker)
    try:
        controller = app.main_window._impl.native.rootViewController
        while controller.presentedViewController:
            controller = controller.presentedViewController
        controller.presentViewController(picker, animated=True, completion=None)
        url = await future
        if export_path is not None:
            return url is not None
        return (IOSDocuments(), url) if url is not None else None
    finally:
        _ios_pickers.pop(key, None)


async def export_stream(app, name, open_source, *, mime_type='application/octet-stream'):
    if not name or Path(name).name != name or '\\' in name or '\x00' in name or name in {'.', '..'}:
        raise ValueError('Choose a document file name.')
    current = get_os()
    if current is OS.ANDROID:
        from java import jclass, jarray, jbyte
        Intent = jclass('android.content.Intent')
        Activity = jclass('android.app.Activity')
        intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType(mime_type)
        intent.putExtra(Intent.EXTRA_TITLE, name)
        intent.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        future = asyncio.get_running_loop().create_future()
        def complete(code, data):
            if not future.done():
                future.set_result(data.getData() if code == Activity.RESULT_OK and data else None)
        app._impl.start_activity(intent, on_complete=complete)
        uri = await future
        if uri is None:
            return False
        def write():
            stream = app._impl.native.getContentResolver().openOutputStream(uri, 'wt')
            if stream is None:
                raise OSError('The selected provider did not open a writable document.')
            try:
                with open_source() as source:
                    while chunk := source.read(65536):
                        stream.write(jarray(jbyte)([value if value < 128 else value - 256 for value in chunk]))
                stream.flush()
            finally:
                stream.close()
        await asyncio.to_thread(write)
        return True
    if current is OS.IOS:
        with TemporaryDirectory(prefix='export-', dir=app.paths.data) as directory:
            path = Path(directory) / name
            await asyncio.to_thread(_copy_export, open_source, path)
            return await pick_ios(app, path)
    import toga
    path = await app.main_window.dialog(toga.SaveFileDialog('Export document copy', suggested_filename=name))
    if path is None:
        return False
    await asyncio.to_thread(_copy_export, open_source, path)
    return True


def _copy_export(open_source, path):
    import os
    from ...runtime.streams import copy_stream
    from tempfile import NamedTemporaryFile
    path = Path(path)
    temporary = None
    try:
        with open_source() as source, NamedTemporaryFile(dir=path.parent, prefix='.export-', delete=False) as output:
            temporary = Path(output.name)
            copy_stream(source, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
