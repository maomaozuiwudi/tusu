# Windows 原生文件拖拽支持（纯ctypes，零依赖）
import ctypes
from ctypes import wintypes, WINFUNCTYPE

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32

WM_DROPFILES = 0x0233
GWL_WNDPROC = -4

SetWindowLongPtrW = user32.SetWindowLongPtrW
SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LPARAM]
SetWindowLongPtrW.restype = wintypes.LPARAM

_WNDPROC_TYPE = WINFUNCTYPE(wintypes.LPARAM, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)
_CallWindowProc = user32.CallWindowProcW
_CallWindowProc.argtypes = [wintypes.LPARAM, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM]
_CallWindowProc.restype = wintypes.LPARAM

_drop_callback = None
_orig_wndproc = None
_new_wndproc_ref = None


def _file_drop_proc(hwnd, msg, wp, lp):
    if msg == WM_DROPFILES:
        count = shell32.DragQueryFileW(wp, 0xFFFFFFFF, None, 0)
        files = []
        for i in range(count):
            size = shell32.DragQueryFileW(wp, i, None, 0)
            buf = ctypes.create_unicode_buffer(size + 1)
            shell32.DragQueryFileW(wp, i, buf, size + 1)
            files.append(buf.value)
        shell32.DragFinish(wp)
        if _drop_callback and files:
            _drop_callback(files)
        return 0
    return _CallWindowProc(_orig_wndproc, hwnd, msg, wp, lp)


def enable_drop(tk_widget, callback):
    global _drop_callback, _orig_wndproc, _new_wndproc_ref

    tk_widget.update_idletasks()
    hwnd = int(tk_widget.winfo_id())
    if not hwnd:
        tk_widget.after(100, lambda: enable_drop(tk_widget, callback))
        return

    _drop_callback = callback
    shell32.DragAcceptFiles(hwnd, True)

    if _orig_wndproc is None:
        _new_wndproc_ref = _WNDPROC_TYPE(_file_drop_proc)
        ptr = ctypes.cast(_new_wndproc_ref, ctypes.c_void_p)
        _orig_wndproc = SetWindowLongPtrW(hwnd, GWL_WNDPROC, ptr.value)
