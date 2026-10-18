# -*- coding: utf-8 -*-
"""Wallpaper Peel —— 读取 Wallpaper Engine 已安装壁纸，画廊预览，勾选导出。

启动: WallpaperPeel.exe   或   .venv\\Scripts\\python.exe wallpaper_peel.py
仅用标准库；装了 Pillow 会自动用于生成缩略图（更快更省内存）。
"""
import ctypes
import json
import os
import re
import struct
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

FROZEN = getattr(sys, 'frozen', False)
BASE = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(BASE, 'web')
DATA = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'WallpaperPeel')
CACHE = os.path.join(DATA, 'cache') if FROZEN else os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')
CACHE_FULL = os.path.join(CACHE, 'full')
CACHE_THUMB = os.path.join(CACHE, 'thumb')
SETTINGS = os.path.join(DATA if FROZEN else os.path.dirname(os.path.abspath(__file__)), 'settings.json')

# 从旧名字 WallpaperLib 迁移缓存，避免重新解包
if FROZEN:
    for _name in ('WallVault', 'WallpaperLib'):
        _old = os.path.join(os.path.dirname(DATA), _name)
        if os.path.isdir(_old) and not os.path.isdir(DATA):
            try:
                os.rename(_old, DATA)
                break
            except Exception:
                pass

for d in (CACHE_FULL, CACHE_THUMB):
    os.makedirs(d, exist_ok=True)

try:
    from PIL import Image
    HAS_PIL = True
except Exception:
    HAS_PIL = False

PORT_CANDIDATES = [7788, 7789, 7790, 8899]


# ---------------------------------------------------------------- pkg 解析

def parse_pkg(blob):
    magic_len = struct.unpack('<i', blob[0:4])[0]
    pos = 4 + magic_len
    count = struct.unpack('<i', blob[pos:pos + 4])[0]
    pos += 4
    entries = []
    for _ in range(count):
        plen = struct.unpack('<i', blob[pos:pos + 4])[0]
        pos += 4
        name = blob[pos:pos + plen].decode('utf-8', 'replace').rstrip('\x00')
        pos += plen
        off, ln = struct.unpack('<ii', blob[pos:pos + 8])
        pos += 8
        entries.append((name, off, ln))
    return pos, entries


def jpeg_dims(b):
    if b[:2] != b'\xff\xd8':
        return None
    i = 2
    while i < len(b) - 9:
        if b[i] != 0xFF:
            return None
        m = b[i + 1]
        if m in (0xD9, 0xDA):
            return None
        if 0xD0 <= m <= 0xD7 or m == 0x01:
            i += 2
            continue
        seglen = struct.unpack('>H', b[i + 2:i + 4])[0]
        if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack('>HH', b[i + 5:i + 9])
            return w, h
        i += 2 + seglen
    return None


def carve_images(data):
    """从 .tex 容器里抠出内嵌的 JPEG / PNG（作者原始码流）"""
    out = []
    start = 0
    while True:
        i = data.find(b'\xff\xd8\xff', start)
        if i == -1:
            break
        start = i + 2
        tail = data.find(b'\xff\xd9', i)
        if tail == -1:
            continue
        stream = data[i:tail + 2]
        d = jpeg_dims(stream)
        if d and d[0] >= 640:
            out.append((d[0] * d[1], d, stream, 'jpg'))
    start = 0
    while True:
        i = data.find(b'\x89PNG\r\n\x1a\n', start)
        if i == -1:
            break
        start = i + 1
        j = data.find(b'IEND', i)
        if j == -1:
            continue
        stream = data[i:j + 8]
        if len(stream) > 40 and stream[12:16] == b'IHDR':
            d = struct.unpack('>II', stream[16:24])
            if d[0] >= 640:
                out.append((d[0] * d[1], d, stream, 'png'))
    out.sort(key=lambda t: -t[0])
    return out


def extract_from_pkg(pkg_path):
    blob = open(pkg_path, 'rb').read()
    base, entries = parse_pkg(blob)
    texes = sorted([(n, o, l) for n, o, l in entries if n.lower().endswith('.tex')], key=lambda t: -t[2])
    for name, off, ln in texes:
        imgs = carve_images(blob[base + off:base + off + ln])
        if imgs:
            return imgs[0][2], imgs[0][3], imgs[0][1]
    return None


# ---------------------------------------------------------------- 扫描壁纸库

def load_settings():
    try:
        return json.load(open(SETTINGS, encoding='utf-8'))
    except Exception:
        return {}


def save_settings(s):
    try:
        os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
        with open(SETTINGS, 'w', encoding='utf-8') as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def find_roots():
    roots = []
    # 1. 用户手动指定的目录优先
    for p in load_settings().get('roots', []):
        p = os.path.normpath(p)
        if os.path.isdir(p) and p not in roots:
            roots.append(p)
    # 2. 从 Wallpaper Engine 配置里推断（最准）
    cfg_candidates = []
    for drive in 'CDEFGH':
        cfg_candidates.append(fr'{drive}:\Steam\steamapps\common\wallpaper_engine\config.json')
        cfg_candidates.append(fr'{drive}:\SteamLibrary\steamapps\common\wallpaper_engine\config.json')
        cfg_candidates.append(fr'{drive}:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine\config.json')
    for cfg in cfg_candidates:
        if not os.path.exists(cfg):
            continue
        try:
            raw = open(cfg, 'rb').read().decode('utf-8', 'replace')
        except Exception:
            continue
        for m in re.finditer(r'"file"\s*:\s*"([^"]*?/431960/[^"]*)"', raw):
            p = m.group(1).replace('\\\\', '\\')
            root = os.path.normpath(p.split('/431960/')[0] + '/431960')
            if os.path.isdir(root) and root not in roots:
                roots.append(root)
    # 3. 兜底扫盘
    if not roots:
        for drive in 'CDEFGH':
            for mid in ('Steam', 'SteamLibrary', 'Games\\Steam', 'Program Files (x86)\\Steam'):
                p = os.path.normpath(fr'{drive}:\{mid}\steamapps\workshop\content\431960')
                if os.path.isdir(p) and p not in roots:
                    roots.append(p)
    return roots


def human(n):
    return f"{n/1048576:.1f} MB" if n > 1048576 else f"{n/1024:.0f} KB"


def mp4_dims(path):
    """读 mp4 的 tkhd 盒子拿分辨率（moov 可能在文件头也可能在尾部）"""
    try:
        size = os.path.getsize(path)
        chunks = []
        with open(path, 'rb') as f:
            chunks.append(f.read(1 << 20))
            if size > (3 << 20):
                f.seek(max(0, size - (2 << 20)))
                chunks.append(f.read())
        for data in chunks:
            i = data.find(b'tkhd')
            if i < 0:
                continue
            ver = data[i + 4]
            off = i + (80 if ver == 0 else 92)
            w = struct.unpack('>I', data[off:off + 4])[0] >> 16
            h = struct.unpack('>I', data[off + 4:off + 8])[0] >> 16
            if 0 < w < 20000 and 0 < h < 20000:
                return (w, h)
    except Exception:
        pass
    return (0, 0)


def scan():
    roots = find_roots()
    items = []
    for root in roots:
        for wid in sorted(os.listdir(root)):
            folder = os.path.join(root, wid)
            if not os.path.isdir(folder):
                continue
            pj = os.path.join(folder, 'project.json')
            meta = {}
            if os.path.exists(pj):
                try:
                    meta = json.load(open(pj, encoding='utf-8'))
                except Exception:
                    try:
                        meta = json.loads(open(pj, 'rb').read().decode('utf-8', 'replace'))
                    except Exception:
                        meta = {}
            wtype = (meta.get('type') or '').lower()
            title = meta.get('title') or wid
            files = os.listdir(folder)
            pkgs = [f for f in files if f.lower().endswith('.pkg')]
            mp4s = [f for f in files if f.lower().endswith('.mp4')]
            preview = next((f for f in files if f.lower().startswith('preview')), None)

            item = {
                'id': wid,
                'title': title,
                'type': wtype or ('video' if mp4s else 'scene'),
                'tags': meta.get('tags') or [],
                'workshopid': meta.get('workshopid') or wid,
                'preview': preview,
                'folder': folder,
                'savable': False,
                'kind': None,
                'w': 0, 'h': 0,
                'bytes': 0,
                'size': '',
            }

            cache_meta = os.path.join(CACHE, f'{wid}.json')
            if os.path.exists(cache_meta):
                try:
                    item.update(json.load(open(cache_meta, encoding='utf-8')))
                except Exception:
                    pass

            # 校验缓存是否仍然有效（缓存目录可能被清掉）
            if item.get('savable'):
                if item.get('kind') == 'image':
                    if not os.path.exists(os.path.join(CACHE_FULL, f"{wid}.{item.get('ext', 'jpg')}")):
                        item['savable'] = False
                elif item.get('kind') == 'video':
                    item['src'] = os.path.join(folder, max(mp4s, key=lambda f: os.path.getsize(os.path.join(folder, f)))) if mp4s else None
                    if not item['src']:
                        item['savable'] = False

            if not item['savable']:
                if pkgs:
                    try:
                        got = extract_from_pkg(os.path.join(folder, pkgs[0]))
                    except Exception:
                        got = None
                    if got:
                        stream, ext, dims = got
                        dst = os.path.join(CACHE_FULL, f'{wid}.{ext}')
                        open(dst, 'wb').write(stream)
                        item.update({'savable': True, 'kind': 'image', 'ext': ext,
                                     'w': dims[0], 'h': dims[1], 'bytes': len(stream),
                                     'size': human(len(stream))})
                elif mp4s:
                    src = os.path.join(folder, max(mp4s, key=lambda f: os.path.getsize(os.path.join(folder, f))))
                    vw, vh = mp4_dims(src)
                    item.update({'savable': True, 'kind': 'video', 'ext': 'mp4',
                                 'bytes': os.path.getsize(src), 'size': human(os.path.getsize(src)),
                                 'src': src, 'w': vw, 'h': vh})
                with open(cache_meta, 'w', encoding='utf-8') as f:
                    json.dump({k: item[k] for k in ('savable', 'kind', 'ext', 'w', 'h', 'bytes', 'size')}, f)
            elif item.get('kind') == 'video' and not item.get('src'):
                item['src'] = os.path.join(folder, max(mp4s, key=lambda f: os.path.getsize(os.path.join(folder, f))))
            items.append(item)

    items.sort(key=lambda i: -(i['w'] * i['h'] if i['w'] else 0))
    return roots, items


def thumb_path(item):
    dst = os.path.join(CACHE_THUMB, f"{item['id']}.jpg")
    if os.path.exists(dst):
        return dst
    src = None
    if item.get('kind') == 'image':
        src = os.path.join(CACHE_FULL, f"{item['id']}.{item['ext']}")
    elif item.get('preview'):
        src = os.path.join(item['folder'], item['preview'])
    if src and os.path.exists(src) and HAS_PIL:
        try:
            im = Image.open(src)
            im = im.convert('RGB')
            im.thumbnail((720, 720))
            im.save(dst, 'JPEG', quality=82)
            return dst
        except Exception:
            pass
    return src


# ---------------------------------------------------------------- 导出 & 设置壁纸

def safe_name(s):
    return re.sub(r'[\\/:*?"<>|\r\n\t]', '_', s).strip()[:80] or 'wallpaper'


def export_items(ids, outdir, items):
    outdir = os.path.expandvars(os.path.expanduser(outdir or ''))
    if not outdir:
        outdir = os.path.join(os.path.expanduser('~'), 'Pictures', 'WallpaperEngine导出')
    os.makedirs(outdir, exist_ok=True)
    by_id = {i['id']: i for i in items}
    results = []
    for wid in ids:
        it = by_id.get(wid)
        if not it or not it['savable']:
            results.append({'id': wid, 'ok': False, 'msg': '该壁纸没有可导出的素材'})
            continue
        try:
            if it['kind'] == 'image':
                src = os.path.join(CACHE_FULL, f"{wid}.{it['ext']}")
                dst = os.path.join(outdir, f"{safe_name(it['title'])}.{it['ext']}")
            else:
                src = it['src']
                dst = os.path.join(outdir, f"{safe_name(it['title'])}.mp4")
            n = 1
            while os.path.exists(dst):
                stem, ext = os.path.splitext(dst)
                dst = f"{stem} ({n}){ext}"
                n += 1
            with open(src, 'rb') as fi, open(dst, 'wb') as fo:
                while True:
                    chunk = fi.read(1 << 20)
                    if not chunk:
                        break
                    fo.write(chunk)
            results.append({'id': wid, 'ok': True, 'path': dst, 'msg': os.path.basename(dst)})
        except Exception as e:
            results.append({'id': wid, 'ok': False, 'msg': str(e)})
    return outdir, results


def set_wallpaper(path):
    SPI_SETDESKWALLPAPER = 20
    SPIF_UPDATEINIFILE, SPIF_SENDCHANGE = 1, 2
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, ctypes.c_wchar_p(path), SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
    return bool(ok)


# ---------------------------------------------------------------- HTTP

STATE = {'roots': [], 'items': [], 'lock': threading.Lock()}


def rescan():
    roots, items = scan()
    STATE['roots'], STATE['items'] = roots, items
    return len(items)


class Handler(BaseHTTPRequestHandler):
    server_version = 'WallpaperPeel/1.0'

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ctype):
        try:
            data = open(path, 'rb').read()
        except Exception:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'max-age=600')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        p = url.path
        if p in ('/', '/index.html'):
            return self._file(os.path.join(WEB, 'index.html'), 'text/html; charset=utf-8')
        if p == '/api/list':
            with STATE['lock']:
                items = [{k: v for k, v in i.items() if k not in ('folder', 'src')} for i in STATE['items']]
            return self._json({'roots': STATE['roots'], 'items': items, 'hasPil': HAS_PIL,
                               'outdir': os.path.join(os.path.expanduser('~'), 'Pictures', 'WallpaperEngine导出')})
        if p.startswith('/api/thumb/'):
            wid = p.rsplit('/', 1)[-1]
            it = next((i for i in STATE['items'] if i['id'] == wid), None)
            if not it:
                self.send_error(404)
                return
            tp = thumb_path(it)
            if not tp or not os.path.exists(tp):
                self.send_error(404)
                return
            ctype = 'image/jpeg' if tp.lower().endswith(('.jpg', '.jpeg')) else \
                'image/png' if tp.lower().endswith('.png') else \
                'image/gif' if tp.lower().endswith('.gif') else 'application/octet-stream'
            return self._file(tp, ctype)
        if p.startswith('/api/full/'):
            wid = p.rsplit('/', 1)[-1]
            it = next((i for i in STATE['items'] if i['id'] == wid), None)
            if not it or it.get('kind') != 'image':
                self.send_error(404)
                return
            full = os.path.join(CACHE_FULL, f"{wid}.{it['ext']}")
            return self._file(full, 'image/png' if it['ext'] == 'png' else 'image/jpeg')
        self.send_error(404)

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        n = int(self.headers.get('Content-Length') or 0)
        try:
            payload = json.loads(self.rfile.read(n) or b'{}')
        except Exception:
            payload = {}

        if url.path == '/api/export':
            ids = payload.get('ids') or []
            with STATE['lock']:
                items = STATE['items']
            outdir, results = export_items(ids, payload.get('dir'), items)
            ok = sum(1 for r in results if r['ok'])
            return self._json({'outdir': outdir, 'ok': ok, 'total': len(results), 'results': results})

        if url.path == '/api/set':
            wid = payload.get('id')
            it = next((i for i in STATE['items'] if i['id'] == wid), None)
            if not it or it.get('kind') != 'image':
                return self._json({'ok': False, 'msg': '只有图片可以设为桌面壁纸'}, 400)
            src = os.path.join(CACHE_FULL, f"{wid}.{it['ext']}")
            ok = set_wallpaper(src)
            return self._json({'ok': ok, 'msg': '已设为桌面背景' if ok else '设置失败'})

        if url.path == '/api/open':
            target = payload.get('path')
            if target and os.path.exists(target):
                os.startfile(target)
                return self._json({'ok': True})
            return self._json({'ok': False, 'msg': '路径不存在'}, 400)

        if url.path == '/api/rescan':
            n = rescan()
            return self._json({'ok': True, 'count': n})

        if url.path == '/api/addroot':
            raw = (payload.get('path') or '').strip().strip('"')
            cand = os.path.normpath(os.path.expandvars(os.path.expanduser(raw)))
            # 允许直接选父目录（content），自动补 431960
            if os.path.isdir(os.path.join(cand, '431960')):
                cand = os.path.join(cand, '431960')
            ok = os.path.isdir(cand) and any(
                os.path.isdir(os.path.join(cand, d)) and d.isdigit() for d in os.listdir(cand))
            if not ok:
                return self._json({'ok': False, 'msg': '这个目录里没有壁纸（应为 ...\\431960）'})
            s = load_settings()
            roots = s.get('roots') or []
            if cand not in roots:
                roots.append(cand)
            s['roots'] = roots
            save_settings(s)
            n = rescan()
            return self._json({'ok': True, 'count': n, 'roots': STATE['roots']})

        if url.path == '/api/removeroot':
            raw = (payload.get('path') or '').strip()
            s = load_settings()
            s['roots'] = [r for r in (s.get('roots') or []) if os.path.normpath(r) != os.path.normpath(raw)]
            save_settings(s)
            n = rescan()
            return self._json({'ok': True, 'count': n})

        self.send_error(404)


def main():
    if os.name == 'nt':
        try:
            os.system('title Wallpaper Peel v1.0')
        except Exception:
            pass
    print('=' * 52)
    print('  Wallpaper Peel  v1.0   —— Wallpaper Engine 壁纸原图导出')
    print('=' * 52)
    print('扫描壁纸库…')
    n = rescan()
    for r in STATE['roots']:
        print('  发现:', r)
    if not STATE['roots']:
        print('  没自动找到壁纸库。打开页面后点「指定目录」手动选一下。')
    print(f'  共 {n} 个壁纸  |  缩略图加速: {"开" if HAS_PIL else "关"}')

    srv = None
    for port in PORT_CANDIDATES:
        try:
            srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
            break
        except OSError:
            continue
    if not srv:
        print('端口都被占用，退出')
        return
    url = f'http://127.0.0.1:{srv.server_address[1]}/'
    print(f'\n  Wallpaper Peel 已启动: {url}\n  关闭此窗口即停止服务\n')
    try:
        import webbrowser
        if '--no-open' not in sys.argv:
            webbrowser.open(url)
    except Exception:
        pass
    srv.serve_forever()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            input('\n出错了，把上面的信息发给开发者。按回车退出…')
        except Exception:
            pass
