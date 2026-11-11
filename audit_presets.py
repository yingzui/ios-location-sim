# -*- coding: utf-8 -*-
"""预置点全量审计：对每个坐标做反向地理编码，看它究竟落在哪个具名地物上。"""
import json
import math
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

PRESETS = [
    ("郑州·龙湖国际中心北楼", 34.794605, 113.727719),
    ("郑州·二七广场",      34.752849, 113.659807),
    ("洛阳·龙门石窟",      34.557115, 112.470711),
    ("安阳·殷墟博物馆",    36.120520, 114.324346),
    ("北京·天安门",        39.907359, 116.391263),
    ("上海·外滩",          31.239323, 121.485561),
    ("深圳·市民中心",      22.546373, 114.054522),
    ("中国香港·中环",      22.281700, 114.158800),
    ("东京·东京塔",        35.658449, 139.745536),
    ("纽约·自由女神",      40.689253, -74.044548),
]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def dist_m(lon1, lat1, lon2, lat2):
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def reverse(lat, lon, limit=4):
    u = (f"https://photon.komoot.io/reverse?lat={lat}&lon={lon}&limit={limit}")
    return get(u).get("features", [])


print("=" * 100)
print("预置点全量审计 —— 反向地理编码：这个坐标最近落在哪个具名地物上")
print("=" * 100)
for name, la, lo in PRESETS:
    try:
        fs = reverse(la, lo)
    except Exception as e:  # noqa: BLE001
        print(f"\n{name}\n  [!] 查询失败：{e}")
        continue
    print(f"\n{name}   ({la:.6f}, {lo:.6f})")
    if not fs:
        print("    附近没有具名地物（可能是建成区/海域/景区内部）")
        continue
    for f in fs[:3]:
        p = f["properties"]
        c = f["geometry"]["coordinates"]
        d = dist_m(lo, la, c[0], c[1])
        desc = "".join(x for x in (p.get("city"), p.get("district"),
                                   p.get("street")) if x)
        print(f"    {d:7.0f} m  {str(p.get('name') or '(无名)'):22s} "
              f"[{p.get('osm_value') or p.get('type') or ''}] {desc}")
    time.sleep(0.3)
