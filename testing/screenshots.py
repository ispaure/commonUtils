"""Capture a Toga native window; platform imports stay lazy."""
from .settings import SCREENSHOT_TIMEOUT, WINDOW_DRAW_TIMEOUT
from .waiting import wait_until


async def capture_window(app, path):
    """Capture the actual native window, including reparented navigation content."""
    import asyncio
    import os
    from ..runtime.platform import get_os, OS
    if get_os() is OS.IOS:
        from rubicon.objc import Block, objc_id
        from toga_iOS.libs import UIGraphicsImageRenderer
        from toga_iOS.images import nsdata_to_bytes
        native = app.main_window._impl.native
        renderer = UIGraphicsImageRenderer.alloc().initWithSize(native.bounds.size)
        def render(context):
            native.drawViewHierarchyInRect(native.bounds, afterScreenUpdates=True)
        data = nsdata_to_bytes(renderer.PNGDataWithActions(Block(render, None, objc_id)))
    else:
        from java import dynamic_proxy, jclass
        window = app._impl.native.getWindow()
        decor = window.getDecorView()
        await wait_until(lambda: decor.getWidth() > 0 and decor.getHeight() > 0,
                         timeout=WINDOW_DRAW_TIMEOUT,
                         message='The Android window did not acquire drawable bounds.')
        width, height = int(decor.getWidth()), int(decor.getHeight())
        Bitmap = jclass('android.graphics.Bitmap')
        bitmap = Bitmap.createBitmap(width, height, jclass('android.graphics.Bitmap$Config').ARGB_8888)
        output = jclass('java.io.ByteArrayOutputStream')()
        try:
            # View.draw uses a software canvas and omits accelerated WebView ink.
            # Copy the composited window instead, without blocking its UI thread.
            copied = asyncio.get_running_loop().create_future()
            class CopyResult(dynamic_proxy(jclass('android.view.PixelCopy$OnPixelCopyFinishedListener'))):
                def onPixelCopyFinished(self, result):
                    if not copied.done():
                        copied.set_result(int(result))
            listener = CopyResult()
            PixelCopy = jclass('android.view.PixelCopy')
            PixelCopy.request(window, bitmap, listener,
                              jclass('android.os.Handler')(jclass('android.os.Looper').getMainLooper()))
            result = await asyncio.wait_for(asyncio.shield(copied), SCREENSHOT_TIMEOUT)
            if result != int(PixelCopy.SUCCESS):
                raise OSError(f'The Android window screenshot failed: PixelCopy {result}.')
            if not bitmap.compress(jclass('android.graphics.Bitmap$CompressFormat').PNG, 100, output):
                raise OSError('The Android window screenshot could not be encoded.')
            data = bytes(int(value) & 255 for value in output.toByteArray())
        finally:
            output.close()
            bitmap.recycle()
    assert data.startswith(b'\x89PNG') and len(data) > 64, 'Native screenshot was empty'
    with path.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return path

