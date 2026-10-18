# -*- coding: utf-8 -*-
"""直连 PyPI 下 wheel（本机 pip 走不通时用）"""
import json
import os
import re
import ssl
import sys
import urllib.request

WHEELS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wheels')
os.makedirs(WHEELS, exist_ok=True)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

PY = '313'
PLATS = ('win_amd64', 'any')
SEEN = {}


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'pip/24.0'})
    with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
        return r.read()


def pick_file(files):
    names = [f for f in files if f['filename'].endswith('.whl')]
    def score(f):
        n = f['filename']
        s = 0
        if f'cp{PY}' in n:
            s += 100
        if 'abi3' in n:
            s += 60
        if 'py3-none' in n or 'py2.py3' in n:
            s += 50
        if 'win_amd64' in n:
            s += 40
        elif 'any' in n:
            s += 10
        if 'musllinux' in n or 'manylinux' in n or 'macosx' in n:
            s -= 100
        return s
    names.sort(key=score, reverse=True)
    return names[0] if names else None


def deps_of(meta):
    out = []
    for d in meta.get('requires_dist') or []:
        if 'extra ==' in d:
            continue
        name = re.split(r'[<>=!;\[ ]', d.strip())[0].strip()
        m = re.search(r'sys_platform\s*==\s*[\'"](\w+)[\'"]', d)
        if m and m.group(1) != 'win32':
            continue
        if re.search(r'sys_platform\s*!=\s*[\'"]win32[\'"]', d):
            continue
        pv = re.search(r'python_version\s*([<>=]+)\s*[\'"](\d+\.\d+)[\'"]', d)
        if pv:
            want = float(pv.group(2))
            have = float(f'{sys.version_info.major}.{sys.version_info.minor}')
            op = pv.group(1)
            ok = {'>=': have >= want, '<': have < want, '>': have > want,
                  '<=': have <= want, '==': have == want}.get(op, True)
            if not ok:
                continue
        if name and name.lower() not in SEEN:
            out.append(name)
    return out


queue = sys.argv[1:] or ['pyinstaller', 'pillow']
while queue:
    name = queue.pop(0)
    if name.lower() in SEEN:
        continue
    SEEN[name.lower()] = True
    try:
        data = json.loads(fetch(f'https://pypi.org/pypi/{name}/json'))
    except Exception as e:
        print(f'  ✗ {name}: {e}')
        continue
    info = data['info']
    f = pick_file(data['urls'])
    if not f:
        print(f'  - {name}: 没有合适 wheel（跳过）')
        continue
    url, fn = f['url'], f['filename']
    dst = os.path.join(WHEELS, fn)
    if not os.path.exists(dst):
        blob = fetch(url)
        open(dst, 'wb').write(blob)
        print(f'  ✓ {fn}  {len(blob)//1024}KB')
    else:
        print(f'  = {fn} (已存在)')
    queue.extend(deps_of(info))
print('done ->', WHEELS)
