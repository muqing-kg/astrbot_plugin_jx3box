# -*- coding: utf-8 -*-
"""Scan item samples / live API for tip slot inventory per wiki category."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"
OUT_DIR = ROOT / "data" / "samples"

sys.path.insert(0, str(ROOT.parent))

FIELD_CANDIDATES = [
    "Name", "Quality", "BindType", "CanTrade", "EquipUsage", "TypeLabel", "IsEquip",
    "MaxStrengthLevel", "MaxDurability", "Level", "RequireLevel", "Requires",
    "attributes", "Diamonds", "Set", "Desc", "Recommend", "Appearance", "CanExterior",
    "CoolDown", "GetType", "GetSource", "furniture_attributes", "MaxExistTime",
    "MaxExistAmount", "Price", "WuCaiHtml", "BelongSchool", "MagicKind", "MagicType",
    "IconID", "Source", "AucGenre", "AucSubType", "SubType", "DetailType", "IsQuest", "flags",
]


def _truthy(v: Any) -> bool:
    if v is None or v is False:
        return False
    if v == "" or v == [] or v == {} or v == 0 or v == "0":
        return False
    return True


def _get_source_shape(gs: Any) -> str:
    if not gs:
        return "none"
    if isinstance(gs, str):
        return "str"
    if isinstance(gs, list):
        if not gs:
            return "list0"
        if all(isinstance(x, str) for x in gs):
            return "list_str"
        if all(isinstance(x, dict) for x in gs):
            keys = set()
            for x in gs:
                keys |= set(x.keys())
            return "list_dict:" + ",".join(sorted(keys)[:12])
        return "list_mixed"
    if isinstance(gs, dict):
        if all(isinstance(v, list) for v in gs.values()):
            return "tree_dict_lists"
        return "dict:" + ",".join(sorted(map(str, gs.keys()))[:12])
    return type(gs).__name__


def _attr_signature(attr: dict[str, Any]) -> str:
    t = str(attr.get("type") or "?")
    color = str(attr.get("color") or "")
    has_icon = "icon" if attr.get("icon_id") not in (None, "", 0, "0") else "noicon"
    lab = str(attr.get("label") or "")
    has_span = "span" if "<span" in lab else "plain"
    has_div = "div" if "<div" in lab else "nodiv"
    return f"{t}|{color}|{has_icon}|{has_span}|{has_div}"


def scan_group(items: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(items)
    field_freq = Counter()
    attr_sig = Counter()
    attr_type = Counter()
    icon_attr = Counter()
    gs_shape = Counter()
    type_label = Counter()
    source = Counter()
    require_keys = Counter()
    flags = Counter()
    set_n = furn_n = strength_gt0 = strength_zero = equip_usage = 0
    samples_with_horse_icon = []

    for it in items:
        if not isinstance(it, dict):
            continue
        for k in FIELD_CANDIDATES:
            if k in it and _truthy(it.get(k)):
                field_freq[k] += 1
        for k, v in it.items():
            if k not in FIELD_CANDIDATES and _truthy(v) and not str(k).startswith("_"):
                field_freq["+" + str(k)] += 1

        for a in it.get("attributes") or []:
            if not isinstance(a, dict):
                continue
            attr_sig[_attr_signature(a)] += 1
            t = str(a.get("type") or "?")
            attr_type[t] += 1
            if a.get("icon_id") not in (None, "", 0, "0"):
                icon_attr[t] += 1
                if len(samples_with_horse_icon) < 5:
                    samples_with_horse_icon.append(
                        "%s:%s:icon=%s" % (it.get("id"), it.get("Name"), a.get("icon_id"))
                    )

        gs_shape[_get_source_shape(it.get("GetSource"))] += 1
        type_label[str(it.get("TypeLabel") or "") or "(empty)"] += 1
        source[str(it.get("Source") or "") or "(empty)"] += 1

        req = it.get("Requires")
        if isinstance(req, dict):
            for rk in req:
                require_keys[str(rk)] += 1
        elif isinstance(req, list) and req:
            require_keys["__list__"] += 1

        fl = it.get("flags")
        if isinstance(fl, dict):
            for fk, fv in fl.items():
                if _truthy(fv):
                    flags[str(fk)] += 1

        if _truthy(it.get("Set")):
            set_n += 1
        if _truthy(it.get("furniture_attributes")):
            furn_n += 1
        ms = it.get("MaxStrengthLevel")
        try:
            msi = int(ms) if ms not in (None, "") else None
        except Exception:
            msi = None
        if msi is not None and msi > 0:
            strength_gt0 += 1
        elif ms in (0, "0"):
            strength_zero += 1
        if _truthy(it.get("EquipUsage")):
            equip_usage += 1

    slots = []

    def add_slot(slot_id, when, rate, note=""):
        slots.append({"id": slot_id, "when": when, "rate": round(rate, 3), "note": note})

    if n:
        add_slot("title", "always Name", field_freq.get("Name", 0) / n)
        add_slot("strength", "MaxStrengthLevel>0", strength_gt0 / n, "hide when null/0")
        add_slot("usage", "EquipUsage truthy", equip_usage / n)
        add_slot("bind", "BindType/CanTrade", field_freq.get("BindType", 0) / n)
        add_slot("exist_time", "MaxExistTime", field_freq.get("MaxExistTime", 0) / n)
        add_slot("type_label", "TypeLabel non-empty", field_freq.get("TypeLabel", 0) / n)
        add_slot("attr_block", "attributes[]", field_freq.get("attributes", 0) / n)
        if sum(icon_attr.values()):
            add_slot(
                "horse_attr_icon",
                "attributes with icon_id",
                min(1.0, sum(icon_attr.values()) / max(1, n)),
                "icon.jx3box.com + green title + body",
            )
        add_slot("diamonds", "Diamonds", field_freq.get("Diamonds", 0) / n)
        add_slot(
            "requires",
            "Requires/RequireLevel",
            max(field_freq.get("Requires", 0), field_freq.get("RequireLevel", 0)) / n,
        )
        add_slot("durability", "MaxDurability", field_freq.get("MaxDurability", 0) / n)
        add_slot("set", "Set", set_n / n)
        add_slot("desc", "Desc", field_freq.get("Desc", 0) / n)
        add_slot("level", "Level", field_freq.get("Level", 0) / n)
        add_slot("recommend", "Recommend", field_freq.get("Recommend", 0) / n)
        add_slot(
            "appearance",
            "Appearance/CanExterior",
            max(field_freq.get("Appearance", 0), field_freq.get("CanExterior", 0)) / n,
        )
        add_slot("cooldown", "CoolDown", field_freq.get("CoolDown", 0) / n)
        add_slot("get_type", "GetType", field_freq.get("GetType", 0) / n)
        add_slot("get_source", "GetSource", field_freq.get("GetSource", 0) / n)
        add_slot("furniture", "furniture_attributes", furn_n / n)
        add_slot("wucai", "WuCaiHtml", field_freq.get("WuCaiHtml", 0) / n)

    return {
        "n": n,
        "field_freq": field_freq.most_common(),
        "attr_types": attr_type.most_common(40),
        "attr_signatures": attr_sig.most_common(30),
        "icon_attr_types": icon_attr.most_common(),
        "get_source_shapes": gs_shape.most_common(),
        "type_labels": type_label.most_common(20),
        "sources": source.most_common(15),
        "require_keys": require_keys.most_common(20),
        "flags": flags.most_common(20),
        "set_n": set_n,
        "furn_n": furn_n,
        "strength_gt0": strength_gt0,
        "strength_zero": strength_zero,
        "equip_usage_n": equip_usage,
        "horse_icon_samples": samples_with_horse_icon,
        "proposed_slots": [s for s in slots if s["rate"] > 0],
    }


def load_local_items():
    by_cat = defaultdict(list)
    all_items = []
    seen = set()

    def add(it, cat=None):
        if not isinstance(it, dict):
            return
        iid = str(it.get("id") or it.get("ID") or "")
        key = iid or ("%s|%s" % (it.get("Name"), it.get("IconID")))
        if key in seen:
            if cat:
                by_cat[cat].append(it)
            return
        seen.add(key)
        all_items.append(it)
        if cat:
            by_cat[cat].append(it)

    p = SAMPLES / "item_category_expanded.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        for it in d.get("items") or []:
            add(it, str(it.get("category") or "未分类"))

    p = SAMPLES / "item_category_samples.json"
    if p.exists():
        for it in json.loads(p.read_text(encoding="utf-8")):
            add(it, str(it.get("category") or "未分类"))

    p = SAMPLES / "item_diverse_details_v2.json"
    if p.exists():
        for it in json.loads(p.read_text(encoding="utf-8")):
            add(it, None)

    p = SAMPLES / "item_diverse_details.json"
    if p.exists():
        for it in json.loads(p.read_text(encoding="utf-8")):
            add(it, None)

    return all_items, dict(by_cat)


def load_menu_tree():
    p = SAMPLES / "menus_raw.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    return list(((d.get("data") or {}).get("menus")) or [])


async def crawl_more(per_sub=8, client="std"):
    from astrbot_plugin_jx3box.http_client import HttpClient
    from astrbot_plugin_jx3box.jx3_api import Jx3Api, NODE

    http = HttpClient()
    await http.start()
    api = Jx3Api(http, client=client)
    report = {"menus": [], "items": [], "errors": [], "by_path": {}}

    try:
        # live menu_list needs auc_genre; use cached menus tree (covers all wiki cats)
        menus = load_menu_tree()
        if not menus:
            try:
                menu_payload = await http.get_json(
                    f"{NODE}/api/node/item/menu_list",
                    params={"client": client, "auc_genre": "1"},
                )
                menus = ((menu_payload or {}).get("data") or {}).get("menus") or []
            except Exception as e:
                report["errors"].append(f"menu_list: {e}")
                menus = []
        report["menus"] = menus

        for top in menus:
            tlabel = str(top.get("label") or top.get("name") or "?")
            top_genre = top.get("AucGenre")
            children = top.get("children") or []
            if not children:
                children = [top]
            for ch in children:
                clabel = str(ch.get("label") or ch.get("name") or tlabel)
                path = f"{tlabel}/{clabel}" if clabel != tlabel else tlabel
                genre = ch.get("AucGenre", top_genre)
                sub = ch.get("AucSubType", ch.get("sub"))
                query = dict(ch.get("query") or {})
                rows = []
                params = {
                    "client": client,
                    "per": per_sub,
                    "page": 1,
                }
                if genre not in (None, ""):
                    params["AucGenre"] = genre
                if sub not in (None, ""):
                    params["AucSubType"] = sub
                for k, v in query.items():
                    params[k] = v
                try:
                    data = await http.get_json(f"{NODE}/item/list", params=params)
                    payload = (data or {}).get("data") or {}
                    rows = payload.get("data") or payload.get("list") or payload.get("items") or []
                    if not isinstance(rows, list):
                        rows = []
                except Exception as e:
                    report["errors"].append(f"list {path}: {e}")
                    rows = []

                if len(rows) < max(2, per_sub // 2):
                    try:
                        kw_rows = await api.search_items(clabel, per=per_sub)
                        seen = {str(r.get("id") or r.get("ID")) for r in rows}
                        for r in kw_rows or []:
                            rid = str(r.get("id") or r.get("ID") or "")
                            if rid and rid not in seen:
                                rows.append(r)
                                seen.add(rid)
                    except Exception as e:
                        report["errors"].append(f"search {path}: {e}")

                details = []
                for row in rows[:per_sub]:
                    iid = str(row.get("id") or row.get("ID") or "")
                    if not iid:
                        continue
                    try:
                        detail = await api.get_item(iid)
                        if detail:
                            detail = dict(detail)
                            detail.setdefault("id", iid)
                            detail["_menu_path"] = path
                            detail["_category"] = tlabel
                            details.append(detail)
                            report["items"].append(detail)
                    except Exception as e:
                        report["errors"].append(f"get_item {iid}: {e}")
                report["by_path"][path] = {
                    "genre": genre,
                    "sub": sub,
                    "query": query,
                    "fetched": len(details),
                    "ids": [d.get("id") for d in details],
                }
                await asyncio.sleep(0.03)
    finally:
        await http.close()

    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crawl", action="store_true")
    ap.add_argument("--per-sub", type=int, default=6)
    ap.add_argument("--out", type=str, default=str(OUT_DIR / "tip_slot_inventory.json"))
    args = ap.parse_args()

    all_items, by_cat = load_local_items()
    crawl_info = {}
    if args.crawl:
        crawl_info = asyncio.run(crawl_more(per_sub=args.per_sub))
        for it in crawl_info.get("items") or []:
            cat = str(it.get("_category") or "抓取")
            by_cat.setdefault(cat, []).append(it)
            all_items.append(it)
        crawl_path = OUT_DIR / "tip_slot_crawl_raw.json"
        crawl_path.write_text(
            json.dumps(
                {
                    "by_path": crawl_info.get("by_path"),
                    "errors": crawl_info.get("errors"),
                    "item_count": len(crawl_info.get("items") or []),
                    "items": crawl_info.get("items") or [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    per_cat = {cat: scan_group(items) for cat, items in sorted(by_cat.items(), key=lambda x: x[0])}
    overall = scan_group(all_items)

    slot_union = {}
    for cat, sc in per_cat.items():
        for s in sc.get("proposed_slots") or []:
            ent = slot_union.setdefault(
                s["id"],
                {
                    "id": s["id"],
                    "when": s["when"],
                    "cats": [],
                    "max_rate": 0,
                    "note": s.get("note", ""),
                },
            )
            ent["cats"].append(cat)
            ent["max_rate"] = max(ent["max_rate"], float(s.get("rate") or 0))

    menus = load_menu_tree()
    menu_paths = []
    for top in menus:
        tlabel = str(top.get("label") or "?")
        chs = top.get("children") or []
        if not chs:
            menu_paths.append(tlabel)
        for ch in chs:
            menu_paths.append("%s/%s" % (tlabel, ch.get("label")))

    out = {
        "overall": {
            "unique_items_scanned": overall["n"],
            "field_freq": overall["field_freq"][:50],
            "attr_types": overall["attr_types"],
            "icon_attr_types": overall["icon_attr_types"],
            "get_source_shapes": overall["get_source_shapes"],
            "proposed_slots": overall["proposed_slots"],
        },
        "menu_paths": menu_paths,
        "per_category": per_cat,
        "slot_union": list(slot_union.values()),
        "crawl": {
            "enabled": bool(args.crawl),
            "paths": (crawl_info.get("by_path") if crawl_info else None),
            "errors_head": (crawl_info.get("errors") or [])[:30] if crawl_info else [],
            "fetched": len(crawl_info.get("items") or []) if crawl_info else 0,
        },
        "notes": [
            "rate = fraction of items in group where field/slot signal present",
            "horse_attr_icon only when attributes[].icon_id present",
            "category groups come from item_category_* samples + optional crawl _category",
        ],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("SCAN_OK items=%s cats=%s out=%s" % (overall["n"], len(per_cat), out_path))
    print("SLOT_UNION:")
    for s in sorted(slot_union.values(), key=lambda x: -x["max_rate"]):
        print(
            "  %-16s max_rate=%.2f cats=%s when=%s"
            % (s["id"], s["max_rate"], len(s["cats"]), s["when"])
        )
    print("PER_CAT n:")
    for cat, sc in per_cat.items():
        ids = [s["id"] for s in sc.get("proposed_slots") or []]
        print("  %s: n=%s slots=%s" % (cat, sc["n"], ids))
    if args.crawl:
        print(
            "CRAWL fetched=%s errors=%s"
            % (out["crawl"]["fetched"], len(crawl_info.get("errors") or []))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
