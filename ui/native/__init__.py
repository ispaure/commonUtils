"""Optional native adapters and lazy desktop dialogs; imports load no toolkit."""


def _desktop_dialogs():
    # Preserve the existing desktop backend beside the new native adapter package.
    import importlib.util
    from pathlib import Path
    import sys
    name = __package__.rsplit('.', 1)[0] + '._native_dialogs'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent.parent / 'native.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    return sys.modules[name]


def display_msg_box_ok(title: str, message: str) -> bool:
    return _desktop_dialogs().display_msg_box_ok(title, message)


def display_msg_box_ok_cancel(title: str, message: str) -> bool:
    return _desktop_dialogs().display_msg_box_ok_cancel(title, message)
