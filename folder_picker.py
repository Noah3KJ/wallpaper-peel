# -*- coding: utf-8 -*-
"""Windows 原生"选择文件夹"对话框。

优先用 IFileDialog（现代资源管理器样式，FOS_PICKFOLDERS），
失败时退回 SHBrowseForFolder（老式树状对话框）。
两者都是纯 ctypes，不需要 tkinter / pywin32。
"""
import ctypes
import os
from ctypes import POINTER, byref, c_int, c_long, c_void_p, c_wchar_p
from ctypes import wintypes

FOS_PICKFOLDERS = 0x00000020
FOS_FORCEFILESYSTEM = 0x00000040
FOS_PATHMUSTEXIST = 0x00000008
FOS_NOCHANGEDIR = 0x00000008 * 0  # 占位，保持可读
SIGDN_FILESYSPATH = 0x80058000
CLSCTX_INPROC_SERVER = 1
COINIT_APARTMENTTHREADED = 2

BIF_RETURNONLYFSDIRS = 0x00000001
BIF_NEWDIALOGSTYLE = 0x00000040
BIF_EDITBOX = 0x00000010


class GUID(ctypes.Structure):
    _fields_ = [('Data1', ctypes.c_ulong),
                ('Data2', ctypes.c_ushort),
                ('Data3', ctypes.c_ushort),
                ('Data4', ctypes.c_ubyte * 8)]


class BROWSEINFOW(ctypes.Structure):
    _fields_ = [('hwndOwner', wintypes.HWND),
                ('pidlRoot', c_void_p),
                ('pszDisplayName', wintypes.LPWSTR),
                ('lpszTitle', wintypes.LPCWSTR),
                ('ulFlags', ctypes.c_uint),
                ('lpfn', c_void_p),
                ('lParam', ctypes.c_ssize_t),
                ('iImage', ctypes.c_int)]


def _guid(text):
    g = GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(text), byref(g))
    return g


def _vtable(obj_ptr):
    return ctypes.cast(obj_ptr, POINTER(POINTER(c_void_p)))[0]


def _fn(vt, index, restype, *argtypes):
    proto = ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)
    return proto(vt[index])


def _best_existing(path):
    """把不存在的路径回溯到最近一个真实存在的祖先"""
    p = os.path.abspath(path) if path else os.path.expanduser('~')
    while p and not os.path.isdir(p):
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return p if os.path.isdir(p) else ''


def _pick_modern(initial, title):
    ole32 = ctypes.windll.ole32
    shell32 = ctypes.windll.shell32
    hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    try:
        clsid = _guid('{DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7}')      # CLSID_FileOpenDialog
        iid = _guid('{d57c7288-d4ad-4768-be02-9d969532d960}')         # IID_IFileOpenDialog
        pdlg = c_void_p()
        hr = ole32.CoCreateInstance(byref(clsid), None, CLSCTX_INPROC_SERVER,
                                    byref(iid), byref(pdlg))
        if hr != 0 or not pdlg:
            return None             # 交给老式对话框兜底
        try:
            vt = _vtable(pdlg)
            set_options = _fn(vt, 9, c_long, wintypes.DWORD)
            set_folder = _fn(vt, 12, c_long, c_void_p)
            set_title = _fn(vt, 17, c_long, c_wchar_p)
            show = _fn(vt, 3, c_long, wintypes.HWND)
            get_result = _fn(vt, 20, c_long, POINTER(c_void_p))

            set_options(pdlg, FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST)
            if title:
                set_title(pdlg, title)

            start = _best_existing(initial)
            if start:
                iid_si = _guid('{43826d1e-e718-42ee-bc55-a1e261c37bfe}')   # IID_IShellItem
                psi = c_void_p()
                if shell32.SHCreateItemFromParsingName(
                        c_wchar_p(start), None, byref(iid_si), byref(psi)) == 0 and psi:
                    set_folder(pdlg, psi)
                    _fn(_vtable(psi), 2, ctypes.c_ulong)(psi)              # Release

            if show(pdlg, None) != 0:
                return ''           # 用户取消
            psi_out = c_void_p()
            if get_result(pdlg, byref(psi_out)) != 0 or not psi_out:
                return ''
            buf = c_wchar_p()
            get_name = _fn(_vtable(psi_out), 5, c_long, c_int, POINTER(c_wchar_p))
            ok = get_name(psi_out, SIGDN_FILESYSPATH, byref(buf)) == 0
            _fn(_vtable(psi_out), 2, ctypes.c_ulong)(psi_out)
            path = buf.value if ok else ''
            if path:
                try:
                    ole32.CoTaskMemFree(buf)
                except Exception:
                    pass
            return path or ''
        finally:
            _fn(_vtable(pdlg), 2, ctypes.c_ulong)(pdlg)
    finally:
        if hr is not None:
            try:
                ole32.CoUninitialize()
            except Exception:
                pass


def _pick_legacy(initial, title):
    """老式 SHBrowseForFolder，作为兜底"""
    ole32 = ctypes.windll.ole32
    shell32 = ctypes.windll.shell32
    ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    buf = ctypes.create_unicode_buffer(1024)
    bi = BROWSEINFOW()
    bi.hwndOwner = None
    bi.pszDisplayName = buf
    bi.lpszTitle = title or '选择文件夹'
    bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE | BIF_EDITBOX
    try:
        pidl = shell32.SHBrowseForFolderW(byref(bi))
        if not pidl:
            return ''
        out = ctypes.create_unicode_buffer(1024)
        ok = shell32.SHGetPathFromIDListW(pidl, out)
        ole32.CoTaskMemFree(pidl)
        return out.value if ok else ''
    finally:
        try:
            ole32.CoUninitialize()
        except Exception:
            pass


def pick_folder(initial='', title='请选择文件夹'):
    """返回选中的目录；取消返回空字符串；全部失败返回 None"""
    try:
        r = _pick_modern(initial, title)
        if r:
            return r
        if r == '':             # 取消（对话框正常弹出）
            return ''
    except Exception:
        pass
    try:
        r = _pick_legacy(initial, title)
        return r if r else ''
    except Exception:
        return None


if __name__ == '__main__':
    import sys
    start = sys.argv[1] if len(sys.argv) > 1 else ''
    t = sys.argv[2] if len(sys.argv) > 2 else '请选择文件夹'
    res = pick_folder(start, t)
    print('' if res is None else res)
