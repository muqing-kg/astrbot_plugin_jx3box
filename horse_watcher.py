"""赤兔抓马提醒状态机。"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Awaitable

from .jx3_api import Jx3Api

TZ = timezone(timedelta(hours=8))
CHITU_RE = re.compile(r"距离下一匹赤兔出世还有(\d+)分钟")
CHITU_SOON_RE = re.compile(r"下一匹赤兔即将出世")


def now_cn() -> datetime:
    return datetime.now(TZ)


def parse_created_at(value: str | None) -> datetime | None:
    if not value:
        return None
    s = value.strip()
    try:
        # 2026-07-25T22:10:59+08:00
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt.astimezone(TZ)
    except Exception:
        return None


@dataclass
class HorseState:
    server: str = ""
    map_name: str = ""
    eta: str = ""  # iso
    source_created_at: str = ""
    source_minutes: int | None = None
    last_calibrated_at: str = ""
    pushed_found: bool = False
    pushed_pre: bool = False
    pushed_refresh: bool = False
    cycle_id: str = ""
    locked: bool = False

    def eta_dt(self) -> datetime | None:
        if not self.eta:
            return None
        try:
            dt = datetime.fromisoformat(self.eta)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
            return dt.astimezone(TZ)
        except Exception:
            return None


class HorseWatcher:
    def __init__(
        self,
        api: Jx3Api,
        state_path: str,
        server: str,
        pre_alert_minutes: int = 10,
        calibrate_before_seconds: int = 30,
        send_fn: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.api = api
        self.state_path = state_path
        self.server = server
        self.pre_alert_minutes = pre_alert_minutes
        self.calibrate_before_seconds = calibrate_before_seconds
        self.send_fn = send_fn
        self.state = self._load()

    def _load(self) -> HorseState:
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return HorseState(**{k: data.get(k) for k in HorseState.__dataclass_fields__.keys()})
            except Exception:
                pass
        return HorseState(server=self.server)

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self.state), f, ensure_ascii=False, indent=2)

    def _cycle_id(self, dt: datetime | None = None) -> str:
        # 周二 07:00 到下周一 07:00
        dt = dt or now_cn()
        # Python: Monday=0 ... Sunday=6; Tuesday=1
        days_since_tue = (dt.weekday() - 1) % 7
        tue = (dt - timedelta(days=days_since_tue)).replace(hour=7, minute=0, second=0, microsecond=0)
        if dt < tue:
            tue -= timedelta(days=7)
        return tue.strftime("%Y%m%d")

    def _extract_chitu(self, reports: list[dict[str, Any]]) -> tuple[str, datetime, int | None] | None:
        best = None
        for row in reports:
            content = str(row.get("content") or "")
            if "赤兔" not in content:
                continue
            created = parse_created_at(row.get("created_at"))
            if not created:
                continue
            m = CHITU_RE.search(content)
            soon = bool(CHITU_SOON_RE.search(content))
            minutes = int(m.group(1)) if m else (1 if soon else None)
            if minutes is None:
                continue
            map_name = str(row.get("map_name") or "")
            eta = created + timedelta(minutes=minutes)
            # 取最近未来/最近过去的有效预告
            cand = (map_name, created, minutes, eta)
            if best is None or abs((eta - now_cn()).total_seconds()) < abs((best[3] - now_cn()).total_seconds()):
                best = cand
        if not best:
            return None
        return best[0], best[3], best[2]

    def _format_found(self, eta: datetime, map_name: str) -> str:
        remain = eta - now_cn()
        mins = max(0, int(remain.total_seconds() // 60))
        if mins >= 60:
            hours = mins / 60
            remain_s = f"{hours:.1f} 小时".replace(".0", "")
        else:
            remain_s = f"{mins} 分钟"
        return (
            f"[赤兔速报] 预计 {remain_s}后刷新\n"
            f"区服：{self.server}\n"
            f"地点：{map_name or '未知'}\n"
            f"预计时间：{eta.strftime('%H:%M')}\n"
            f"必备：卦文龟甲（刷新后再到信使处领取，有效期 8 天）"
        )

    def _format_pre(self, eta: datetime, map_name: str) -> str:
        return (
            f"[赤兔速报] 还有 {self.pre_alert_minutes} 分钟刷新\n"
            f"区服：{self.server}\n"
            f"地点：{map_name or '未知'}\n"
            f"预计时间：{eta.strftime('%H:%M')}\n"
            f"必备：卦文龟甲（刷新后再到信使处领取，有效期 8 天）"
        )

    def _format_refresh(self, map_name: str) -> str:
        return (
            f"[赤兔速报] 赤兔已刷新在 {map_name or '未知'} ！\n"
            f"必备：卦文龟甲\n"
            f"赤兔刷新后再到信使处领取，有效期 8 天。"
        )

    async def _send(self, text: str) -> None:
        if self.send_fn:
            await self.send_fn(text)

    async def tick(self) -> None:
        st = self.state
        st.server = self.server
        cycle = self._cycle_id()
        if st.cycle_id and st.cycle_id != cycle and st.pushed_refresh:
            # 新周期重置
            st = HorseState(server=self.server, cycle_id=cycle)
            self.state = st
            self._save()

        if not st.cycle_id:
            st.cycle_id = cycle

        # 已完成则冷却
        if st.pushed_refresh:
            self._save()
            return

        now = now_cn()
        eta = st.eta_dt()

        # 未锁定：轮询发现
        if not st.locked:
            reports = await self.api.fetch_horse_reports(self.server)
            hit = self._extract_chitu(reports)
            if not hit:
                self._save()
                return
            map_name, eta_dt, minutes = hit
            # 过旧预告忽略
            if eta_dt < now - timedelta(minutes=20):
                self._save()
                return
            st.locked = True
            st.map_name = map_name
            st.eta = eta_dt.isoformat()
            st.source_minutes = minutes
            st.source_created_at = now.isoformat()
            if not st.pushed_found:
                await self._send(self._format_found(eta_dt, map_name))
                st.pushed_found = True
            self._save()
            return

        # 已锁定：本地计时 + 临近校准
        if not eta:
            st.locked = False
            self._save()
            return

        # 校准窗口
        if (
            not st.last_calibrated_at
            and now >= eta - timedelta(seconds=self.calibrate_before_seconds)
            and now < eta + timedelta(minutes=2)
        ):
            try:
                reports = await self.api.fetch_horse_reports(self.server)
                hit = self._extract_chitu(reports)
                if hit:
                    map_name, eta_dt, minutes = hit
                    st.map_name = map_name or st.map_name
                    st.eta = eta_dt.isoformat()
                    st.source_minutes = minutes
                    eta = eta_dt
                st.last_calibrated_at = now.isoformat()
                self._save()
            except Exception:
                st.last_calibrated_at = now.isoformat()
                self._save()

        # 提前提醒
        pre_point = eta - timedelta(minutes=self.pre_alert_minutes)
        if not st.pushed_pre and now >= pre_point and now < eta:
            await self._send(self._format_pre(eta, st.map_name))
            st.pushed_pre = True
            self._save()

        # 到点
        if not st.pushed_refresh and now >= eta:
            await self._send(self._format_refresh(st.map_name))
            st.pushed_refresh = True
            self._save()
