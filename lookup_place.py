#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
地点 → WGS-84 坐标查询器

为什么需要它：国内地图（腾讯/高德/百度）给的是 GCJ-02，手机定位要 WGS-84，
两者在郑州相差约 575 米。本脚本从 OpenStreetMap 取原始 WGS-84 坐标，
并同时给出 GCJ-02，方便你在地图上肉眼核对。

用法：
    python lookup_place.py "龙湖国际中心北楼"
    python lookup_place.py "二七广场" --city 郑州 --limit 5
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.parse
import urllib.request

API = "https://photon.komoot.io/api/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

PI = math.pi
A = 6378245.0
EE = 0.00669342162296594323


def out_of_china(lng: float, lat: float) -> bool:
    return not (73.66 < lng < 135.05 and 3.86 < lat < 53.55)


def _t_lat(x: float, y: float) -> float:
    r = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    r += (20 * math.sin(6 * x * PI) + 20 * math.sin(2 * x * PI)) * 2 / 3
    r += (20 * math.sin(y * PI) + 40 * math.sin(y / 3 * PI)) * 2 / 3
    r += (160 * math.sin(y / 12 * PI) + 320 * math.sin(y * PI / 30)) * 2 / 3
    return r


def _t_lng(x: float, y: float) -> float:
    r = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    r += (20 * math.sin(6 * x * PI) + 20 * math.sin(2 * x * PI)) * 2 / 3
    r += (20 * math.sin(x * PI) + 40 * math.sin(x / 3 * PI)) * 2 / 3
    r += (150 * math.sin(x / 12 * PI) + 300 * math.sin(x / 30 * PI)) * 2 / 3
    return r


def wgs2gcj(lng: float, lat: float) -> tuple[float, float]:
    if out_of_china(lng, lat):
        return lng, lat
    dlat, dlng = _t_lat(lng - 105.0, lat - 35.0), _t_lng(lng - 105.0, lat - 35.0)
    rad = lat / 180.0 * PI
    m = 1 - EE * math.sin(rad) ** 2
    s = math.sqrt(m)
    dlat = (dlat * 180.0) / ((A * (1 - EE)) / (m * s) * PI)
    dlng = (dlng * 180.0) / (A / s * math.cos(rad) * PI)
    return lng + dlng, lat + dlat


def dist_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def search(query: str, limit: int = 6) -> list[dict]:
    params = urllib.parse.urlencode({"q": query, "limit": limit})
    req = urllib.request.Request(API + "?" + params, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.loads(resp.read().decode("utf-8")).get("features", [])


def main() -> int:
    ap = argparse.ArgumentParser(description="地点 → WGS-84 坐标查询（数据源：OpenStreetMap）")
    ap.add_argument("place", nargs="+", help="地点名称，可加城市提高命中率")
    ap.add_argument("--limit", type=int, default=6)
    args = ap.parse_args()

    query = " ".join(args.place)
    try:
        feats = search(query, args.limit)
    except Exception as exc:  # noqa: BLE001
        print(f"[×] 查询失败：{exc}")
        print("    数据源 photon.komoot.io，需要能访问外网。")
        return 1

    if not feats:
        print(f"[!] 没找到「{query}」。换个说法试试，比如加上区/街道名。")
        return 2

    print(f'查询：「{query}」  共 {len(feats)} 条  （数据源 OpenStreetMap → 直接就是 WGS-84）')
    print("=" * 78)
    for f in feats:
        p, c = f["properties"], f["geometry"]["coordinates"]
        wlon, wlat = c[0], c[1]
        glon, glat = wgs2gcj(wlon, wlat)
        addr = "".join(x for x in (p.get("city"), p.get("district"),
                                   p.get("street"), p.get("housenumber")) if x)
        print(f"  {p.get('name') or '(无名)'}    [{p.get('osm_value') or p.get('type') or ''}]")
        if addr:
            print(f"    {addr}")
        print(f"    WGS-84  →  {wlat:.6f}, {wlon:.6f}      <-- 填给手机/直接用这个")
        print(f"    GCJ-02  →  {glat:.6f}, {glon:.6f}      （国内地图上核对用）")
        ext = p.get("extent")
        if ext:
            size_ew = dist_m(ext[0], (ext[1] + ext[3]) / 2, ext[2], (ext[1] + ext[3]) / 2)
            size_ns = dist_m((ext[0] + ext[2]) / 2, ext[1], (ext[0] + ext[2]) / 2, ext[3])
            print(f"    范围    →  东西 {size_ew:.0f} m × 南北 {size_ns:.0f} m")
        print(f"    经纬偏移 →  {dist_m(wlon, wlat, glon, glat):.1f} m（抄错 GCJ-02 就偏这么多）")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
