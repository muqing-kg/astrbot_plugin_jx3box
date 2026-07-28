# -*- coding: utf-8 -*-
"""Build trusted tip slot inventory + per-family schema from local samples.

Does NOT use the polluted item/list crawl. Categories come from menus_raw
AucGenre / TypeLabel / IsQuest, then optional search-validated live crawl.
"""
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
sys.path.insert(0, str(ROOT.parent))

GENRE_LABEL = {
    "-1": "任务",
    "1": "兵刃",
    "2": "暗器",
    "3": "服饰",
    "4": "饰物",
    "5": "坐骑",
    "6": "包裹",
    "7": "秘笈",
    "8": "配方",
    "9": "消耗品",
    "10": "材料",
    "12": "书籍",
    "13": "物品强化",
    "14": "帮会产物",
    "15": "宝石",
    "16": "宝箱",
    "20": "其他",
    "21": "家具",
    "22": "外观/奇趣",
    "26": "扩展装备",
    "0": "未知Genre0",
    "99": "扩展99",
    "None": "无Genre",
}

FAMILY_OF_GENRE = {
    "1": "weapon",
    "2": "weapon_ranged",
    "3": "equip_armor",
    "4": "equip_trinket",
    "5": "mount",
    "6": "bag",
    "7": "book_secret",
    "8": "recipe",
    "9": "consumable",
    "10": "material",
    "12": "book_read",
    "13": "enhance",
    "14": "guild_product",
    "15": "gem",
    "16": "box",
    "20": "other",
    "21": "furniture",
    "22": "appearance_or_pet",
    "26": "equip_extended",
    "-1": "quest_item",
    "0": "unknown",
    "99": "other_ext",
    "None": "untyped",
}

LOGIC_SLOTS = [
    ("title", "Name always"),
    ("strength", "MaxStrengthLevel > 0 only"),
    ("usage", "EquipUsage + icon sprite"),
    ("bind", "BindType / CanTrade"),
    ("exist_time", "MaxExistTime"),
    ("type_label", "TypeLabel (hidden for mount/pet hangers)"),
    ("furniture_meta", "furniture_attributes body fields"),
    ("attr_plain", "attributes[] without icon_id"),
    ("horse_attr_icon", "attributes[] with icon_id (atHorseAttribute)"),
    ("diamonds", "Diamonds holes / wucai hint"),
    ("requires", "Requires / RequireLevel / camp"),
    ("durability", "MaxDurability on true equip"),
    ("set", "Set name + siblings + set attrs"),
    ("desc", "Desc rich text"),
    ("level", "Level quality"),
    ("recommend", "Recommend schools"),
    ("appearance", "Appearance / CanExterior"),
    ("cooldown", "CoolDown"),
    ("get_type", "GetType source type"),
    ("get_source", "GetSource tree/list"),
    ("furniture_limit", "furniture_attributes.limit"),
    ("wucai", "WuCaiHtml rare"),
]

# These fields are safe when absent and should not be denied merely because a
# finite sample set did not happen to contain them for a family.
SAFE_OPTIONAL_SLOTS = {"get_type", "get_source"}


def _truthy(v: Any) -> bool:
    if v is None or v is False:
        return False
    if v == "" or v == [] or v == {} or v == 0 or v == "0":
        return False
    return True


def _genre_key(it: dict[str, Any]) -> str:
    if _truthy(it.get("IsQuest")):
        return "-1"
    g = it.get("AucGenre")
    if g is None or g == "" or str(g).lower() == "none":
        return "None"
    return str(g)


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
            keys: set[str] = set()
            for x in gs:
                keys |= set(x.keys())
            return "list_dict:" + ",".join(sorted(keys)[:12])
        return "list_mixed"
    if isinstance(gs, dict):
        return "dict:" + ",".join(sorted(map(str, gs.keys()))[:12])
    return type(gs).__name__


def _item_id(it: dict[str, Any]) -> str:
    return str(it.get("id") or it.get("ID") or it.get("idKey") or "")


def scan_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(items)
    field_freq: Counter[str] = Counter()
    attr_type: Counter[str] = Counter()
    icon_attr: Counter[str] = Counter()
    gs_shape: Counter[str] = Counter()
    type_label: Counter[str] = Counter()
    require_keys: Counter[str] = Counter()
    strength_gt0 = strength_zero = 0
    horse_icon_items = 0
    horse_samples: list[str] = []
    slot_hits: Counter[str] = Counter()

    for it in items:
        if not isinstance(it, dict):
            continue
        present = {
            "Name": _truthy(it.get("Name")),
            "MaxStrengthLevel": _truthy(it.get("MaxStrengthLevel")),
            "EquipUsage": _truthy(it.get("EquipUsage")),
            "BindType": _truthy(it.get("BindType")) or it.get("CanTrade") is not None,
            "MaxExistTime": _truthy(it.get("MaxExistTime")),
            "TypeLabel": _truthy(it.get("TypeLabel")),
            "attributes": _truthy(it.get("attributes")),
            "Diamonds": _truthy(it.get("Diamonds")),
            "Requires": _truthy(it.get("Requires")) or _truthy(it.get("RequireLevel")),
            "MaxDurability": _truthy(it.get("MaxDurability")),
            "Set": _truthy(it.get("Set")),
            "Desc": _truthy(it.get("Desc")),
            "Level": _truthy(it.get("Level")),
            "Recommend": _truthy(it.get("Recommend")),
            "Appearance": _truthy(it.get("Appearance")) or _truthy(it.get("CanExterior")),
            "CoolDown": _truthy(it.get("CoolDown")),
            "GetType": _truthy(it.get("GetType")),
            "GetSource": _truthy(it.get("GetSource")),
            "furniture_attributes": _truthy(it.get("furniture_attributes")),
            "WuCaiHtml": _truthy(it.get("WuCaiHtml")),
            "IsEquip": _truthy(it.get("IsEquip")),
            "Price": _truthy(it.get("Price")),
            "MaxExistAmount": _truthy(it.get("MaxExistAmount")),
        }
        for k, ok in present.items():
            if ok:
                field_freq[k] += 1

        ms = it.get("MaxStrengthLevel")
        try:
            msi = int(ms) if ms not in (None, "") else None
        except Exception:
            msi = None
        if msi is not None and msi > 0:
            strength_gt0 += 1
            slot_hits["strength"] += 1
        elif ms in (0, "0"):
            strength_zero += 1

        has_icon_attr = False
        has_plain_attr = False
        for a in it.get("attributes") or []:
            if not isinstance(a, dict):
                continue
            t = str(a.get("type") or "?")
            attr_type[t] += 1
            if a.get("icon_id") not in (None, "", 0, "0"):
                icon_attr[t] += 1
                has_icon_attr = True
            else:
                has_plain_attr = True
        if has_icon_attr:
            horse_icon_items += 1
            slot_hits["horse_attr_icon"] += 1
            if len(horse_samples) < 6:
                horse_samples.append("%s:%s" % (_item_id(it), it.get("Name")))
        if has_plain_attr:
            slot_hits["attr_plain"] += 1

        gs_shape[_get_source_shape(it.get("GetSource"))] += 1
        type_label[str(it.get("TypeLabel") or "") or "(empty)"] += 1
        req = it.get("Requires")
        if isinstance(req, dict):
            for rk in req:
                require_keys[str(rk)] += 1

        if present["Name"]:
            slot_hits["title"] += 1
        if present["EquipUsage"]:
            slot_hits["usage"] += 1
        if present["BindType"]:
            slot_hits["bind"] += 1
        if present["MaxExistTime"]:
            slot_hits["exist_time"] += 1
        if present["TypeLabel"]:
            slot_hits["type_label"] += 1
        if present["furniture_attributes"]:
            slot_hits["furniture_meta"] += 1
            fa = it.get("furniture_attributes") or {}
            if isinstance(fa, dict) and _truthy(fa.get("limit")):
                slot_hits["furniture_limit"] += 1
        if present["Diamonds"]:
            slot_hits["diamonds"] += 1
        if present["Requires"]:
            slot_hits["requires"] += 1
        if present["MaxDurability"]:
            slot_hits["durability"] += 1
        if present["Set"]:
            slot_hits["set"] += 1
        if present["Desc"]:
            slot_hits["desc"] += 1
        if present["Level"]:
            slot_hits["level"] += 1
        if present["Recommend"]:
            slot_hits["recommend"] += 1
        if present["Appearance"]:
            slot_hits["appearance"] += 1
        if present["CoolDown"]:
            slot_hits["cooldown"] += 1
        if present["GetType"]:
            slot_hits["get_type"] += 1
        if present["GetSource"]:
            slot_hits["get_source"] += 1
        if present["WuCaiHtml"]:
            slot_hits["wucai"] += 1

    rates = {sid: round(slot_hits.get(sid, 0) / n, 3) if n else 0.0 for sid, _ in LOGIC_SLOTS}
    proposed = [{"id": sid, "when": when, "rate": rates[sid]} for sid, when in LOGIC_SLOTS if rates.get(sid, 0) > 0]
    return {
        "n": n,
        "slot_rates": rates,
        "proposed_slots": proposed,
        "field_freq": field_freq.most_common(),
        "attr_types": attr_type.most_common(25),
        "icon_attr_types": icon_attr.most_common(),
        "get_source_shapes": gs_shape.most_common(),
        "type_labels": type_label.most_common(15),
        "require_keys": require_keys.most_common(15),
        "strength_gt0": strength_gt0,
        "strength_zero": strength_zero,
        "horse_icon_items": horse_icon_items,
        "horse_samples": horse_samples,
    }


def load_all_local() -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}

    def add(it: dict[str, Any]) -> None:
        if not isinstance(it, dict):
            return
        iid = _item_id(it)
        if not iid:
            return
        prev = by_id.get(iid)
        if prev is None or len(it.keys()) >= len(prev.keys()):
            by_id[iid] = it

    for name in (
        "item_diverse_details_v2.json",
        "item_diverse_details.json",
        "item_category_expanded.json",
        "item_category_samples.json",
        "item_tip_samples.json",
        "item_detail_samples.json",
        "fengyu_songge.json",
    ):
        p = SAMPLES / name
        if not p.exists():
            continue
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            for it in raw:
                add(it)
        elif isinstance(raw, dict):
            if isinstance(raw.get("items"), list):
                for it in raw["items"]:
                    add(it)
            elif _item_id(raw):
                add(raw)
    return list(by_id.values())


def load_menus() -> list[dict[str, Any]]:
    p = SAMPLES / "menus_raw.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    return list(((d.get("data") or {}).get("menus")) or d.get("menus") or [])


def match_menu_path(it: dict[str, Any], menus: list[dict[str, Any]]) -> str:
    g = _genre_key(it)
    if g == "-1":
        return "任务/任务物品"
    sub = it.get("AucSubType")
    try:
        sub_s = str(int(sub)) if sub not in (None, "") else None
    except Exception:
        sub_s = str(sub) if sub not in (None, "") else None
    for top in menus:
        if str(top.get("AucGenre")) != g:
            continue
        tlabel = str(top.get("label") or "?")
        children = top.get("children") or []
        if not children:
            return tlabel
        for ch in children:
            ch_sub = ch.get("AucSubType")
            try:
                ch_s = str(int(ch_sub)) if ch_sub not in (None, "") else None
            except Exception:
                ch_s = str(ch_sub) if ch_sub not in (None, "") else None
            if sub_s is not None and ch_s is not None and sub_s == ch_s:
                return "%s/%s" % (tlabel, ch.get("label"))
        return tlabel
    return GENRE_LABEL.get(g, g)


def family_of(it: dict[str, Any]) -> str:
    g = _genre_key(it)
    fam = FAMILY_OF_GENRE.get(g, "other")
    tl = str(it.get("TypeLabel") or "")
    name = str(it.get("Name") or "")
    if g == "5":
        if "饰" in tl or "幼崽" in tl:
            return "mount_gear"
        return "mount"
    if g == "22":
        if "挂宠" in name or "挂宠" in tl or "宠物" in tl:
            return "hang_pet"
        if "坐骑" in tl or "奇趣" in name:
            return "mount_curious"
        return "appearance"
    if g == "4" and any(x in tl for x in ("挂件", "披风")):
        return "appearance_hanger"
    if g == "26":
        try:
            if int(it.get("AucSubType") or -1) == 3:
                return "weapon"
        except Exception:
            pass
        return "equip_extended"
    if _truthy(it.get("furniture_attributes")) or g == "21":
        return "furniture"
    return fam


def build_schema_draft(per_family: dict[str, dict[str, Any]]) -> dict[str, Any]:
    order = [s[0] for s in LOGIC_SLOTS]
    out = {}
    for fam, sc in sorted(per_family.items()):
        rates = sc.get("slot_rates") or {}
        slots = []
        for sid in order:
            r = float(rates.get(sid) or 0)
            if r <= 0 and sid not in SAFE_OPTIONAL_SLOTS:
                continue
            slots.append(
                {
                    "id": sid,
                    "rate": r,
                    "required": r >= 0.95,
                    "omit_if_empty": True,
                    "note": dict(LOGIC_SLOTS).get(sid, ""),
                }
            )
        out[fam] = {
            "n": sc.get("n"),
            "slots": slots,
            "horse_icon_items": sc.get("horse_icon_items"),
            "type_labels_top": sc.get("type_labels"),
        }
    return out


async def crawl_search_validated(per_path: int = 3, client: str = "std") -> dict[str, Any]:
    from astrbot_plugin_jx3box.http_client import HttpClient
    from astrbot_plugin_jx3box.jx3_api import Jx3Api, NODE

    menus = load_menus()
    http = HttpClient()
    await http.start()
    api = Jx3Api(http, client=client)
    report: dict[str, Any] = {"items": [], "by_path": {}, "errors": [], "skipped": []}
    try:
        for top in menus:
            tlabel = str(top.get("label") or "?")
            top_g = str(top.get("AucGenre"))
            children = top.get("children") or [top]
            for ch in children:
                clabel = str(ch.get("label") or tlabel)
                path = "%s/%s" % (tlabel, clabel) if clabel != tlabel else tlabel
                expect_g = str(ch.get("AucGenre") or top_g)
                expect_sub = ch.get("AucSubType")
                query = dict(ch.get("query") or {})
                keywords = [clabel, tlabel]
                if clabel == "材料物品":
                    keywords = ["矿石", "布料", "药材", "木材"]
                if "IsQuest" in query:
                    keywords = ["任务", "信", "令牌"]
                got: list[dict[str, Any]] = []
                seen: set[str] = set()
                for kw in keywords:
                    try:
                        data = await http.get_json(
                            f"{NODE}/item/search",
                            params={"keyword": kw, "client": client, "per": 40},
                        )
                        rows = (((data or {}).get("data") or {}).get("data")) or []
                    except Exception as e:
                        report["errors"].append("search %s %s: %s" % (path, kw, e))
                        rows = []
                    for row in rows:
                        rid = str(row.get("id") or row.get("ID") or "")
                        if not rid or rid in seen:
                            continue
                        rg = row.get("AucGenre")
                        if rg is not None and expect_g not in ("None", "", None) and str(rg) != expect_g:
                            if expect_g != "-1":
                                continue
                        try:
                            detail = await api.get_item(rid)
                        except Exception as e:
                            report["errors"].append("get %s: %s" % (rid, e))
                            continue
                        if not detail:
                            continue
                        detail = dict(detail)
                        detail.setdefault("id", rid)
                        dg = _genre_key(detail)
                        ok = False
                        if expect_g == "-1":
                            ok = _truthy(detail.get("IsQuest")) or dg == "-1"
                        elif expect_g in ("10",):
                            ok = dg == "10" or str(detail.get("TypeLabel") or "") == "材料"
                        else:
                            ok = dg == expect_g
                            if ok and expect_sub not in (None, "", "-1"):
                                try:
                                    ok = int(detail.get("AucSubType")) == int(expect_sub)
                                except Exception:
                                    ok = str(detail.get("AucSubType")) == str(expect_sub)
                        if not ok:
                            continue
                        seen.add(rid)
                        detail["_menu_path"] = path
                        detail["_category"] = tlabel
                        got.append(detail)
                        report["items"].append(detail)
                        if len(got) >= per_path:
                            break
                    if len(got) >= per_path:
                        break
                    await asyncio.sleep(0.05)
                report["by_path"][path] = {
                    "expect_genre": expect_g,
                    "expect_sub": expect_sub,
                    "fetched": len(got),
                    "ids": [_item_id(x) for x in got],
                }
                if len(got) == 0:
                    report["skipped"].append(path)
                await asyncio.sleep(0.03)
    finally:
        await http.close()
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--crawl", action="store_true")
    ap.add_argument("--per-path", type=int, default=3)
    ap.add_argument("--out", type=str, default=str(SAMPLES / "tip_slot_inventory_trusted.json"))
    ap.add_argument(
        "--schema-out",
        type=str,
        default=str(ROOT / "assets" / "tip_templates" / "family_slot_schema.json"),
    )
    args = ap.parse_args()

    items = load_all_local()
    crawl_info: dict[str, Any] = {}
    if args.crawl:
        crawl_info = asyncio.run(crawl_search_validated(per_path=args.per_path))
        by = {_item_id(x): x for x in items}
        for it in crawl_info.get("items") or []:
            iid = _item_id(it)
            if not iid:
                continue
            if iid not in by or len(it.keys()) > len(by[iid].keys()):
                by[iid] = it
        items = list(by.values())
        (SAMPLES / "tip_slot_crawl_search_raw.json").write_text(
            json.dumps(
                {
                    "by_path": crawl_info.get("by_path"),
                    "errors": crawl_info.get("errors"),
                    "skipped": crawl_info.get("skipped"),
                    "item_count": len(crawl_info.get("items") or []),
                    "items": crawl_info.get("items") or [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    menus = load_menus()
    by_genre: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for it in items:
        g = _genre_key(it)
        by_genre[g].append(it)
        by_family[family_of(it)].append(it)
        by_path[match_menu_path(it, menus)].append(it)

    per_genre = {
        GENRE_LABEL.get(g, g) + "[%s]" % g: scan_items(v)
        for g, v in sorted(by_genre.items(), key=lambda x: x[0])
    }
    per_family = {f: scan_items(v) for f, v in sorted(by_family.items())}
    per_path = {p: scan_items(v) for p, v in sorted(by_path.items()) if v}
    overall = scan_items(items)
    schema = build_schema_draft(per_family)

    slot_union = []
    for sid, when in LOGIC_SLOTS:
        cats = [f for f, sc in per_family.items() if (sc.get("slot_rates") or {}).get(sid, 0) > 0]
        if not cats:
            continue
        max_rate = max((sc.get("slot_rates") or {}).get(sid, 0) for sc in per_family.values())
        slot_union.append({"id": sid, "when": when, "families": cats, "max_rate": max_rate})

    out = {
        "overall": {
            "unique_items_scanned": overall["n"],
            "slot_rates": overall["slot_rates"],
            "proposed_slots": overall["proposed_slots"],
            "attr_types": overall["attr_types"],
            "icon_attr_types": overall["icon_attr_types"],
            "get_source_shapes": overall["get_source_shapes"],
            "strength_gt0": overall["strength_gt0"],
            "strength_zero": overall["strength_zero"],
            "horse_icon_items": overall["horse_icon_items"],
            "horse_samples": overall["horse_samples"],
        },
        "menus_top": [
            {
                "label": m.get("label"),
                "AucGenre": m.get("AucGenre"),
                "children": [c.get("label") for c in (m.get("children") or [])],
            }
            for m in menus
        ],
        "per_genre": per_genre,
        "per_family": per_family,
        "per_menu_path_nonzero": {k: {"n": v["n"], "slot_rates": v["slot_rates"]} for k, v in per_path.items()},
        "slot_union": slot_union,
        "crawl": {
            "enabled": bool(args.crawl),
            "fetched": len(crawl_info.get("items") or []) if crawl_info else 0,
            "paths": len((crawl_info.get("by_path") or {})) if crawl_info else 0,
            "skipped": (crawl_info.get("skipped") or [])[:40] if crawl_info else [],
            "errors_head": (crawl_info.get("errors") or [])[:20] if crawl_info else [],
        },
        "notes": [
            "Trusted inventory: local diverse samples + optional search-validated crawl",
            "Do NOT use tip_slot_crawl_raw.json (item/list filter broken)",
            "strength only when MaxStrengthLevel>0; zero must omit refine line",
            "horse_attr_icon = attributes with icon_id; render icon.jx3box.com/icon/{id}.png",
            "Empty fields omit_if_empty in family schema",
        ],
    }

    out_path = Path(args.out)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    schema_path = Path(args.schema_out)
    schema_path.write_text(
        json.dumps(
            {
                "version": 1,
                "render_order": [s[0] for s in LOGIC_SLOTS],
                "families": schema,
                "slot_defs": [{"id": a, "when": b} for a, b in LOGIC_SLOTS],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "TRUSTED_SCAN_OK items=%s genres=%s families=%s out=%s schema=%s"
        % (overall["n"], len(per_genre), len(per_family), out_path, schema_path)
    )
    print("SLOT_UNION:")
    for s in slot_union:
        print("  %-16s max=%.2f families=%s" % (s["id"], s["max_rate"], ",".join(s["families"][:8])))
    print("PER_FAMILY n / key slots:")
    for fam, sc in per_family.items():
        key = [sid for sid, r in (sc.get("slot_rates") or {}).items() if r >= 0.2]
        print("  %s n=%s horse_icon=%s slots>=0.2=%s" % (fam, sc["n"], sc.get("horse_icon_items"), key))
    if args.crawl:
        print(
            "CRAWL fetched=%s skipped=%s errors=%s"
            % (out["crawl"]["fetched"], len(crawl_info.get("skipped") or []), len(crawl_info.get("errors") or []))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
