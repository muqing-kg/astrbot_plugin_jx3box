# 剑三魔盒查询插件

面向普通用户的剑三查询插件：物品 tip 图、成就链接、任务信息卡，以及后台赤兔提醒。

## 命令

- /物品 关键词：查物品，返回 tip 详情图
- /成就 关键词：查成就，返回链接
- /任务 关键词：查任务，返回信息卡图片
- /1 到 /10：多个结果时选择
- /jx3帮助：查看帮助图

刷马（赤兔）在后台自动运行，不写进帮助图。

## 使用示例

/物品 玄晶
/1

/成就 武神重临

/任务 茶馆问讯

## 安装

1. 把整个 astrbot_plugin_jx3box 文件夹放到 AstrBot 的 data/plugins/ 下
2. 安装依赖：pip install -r requirements.txt
3. 在 AstrBot 插件管理里启用本插件
4. 如需赤兔提醒，在插件配置里填写区服和推送目标群号

## 配置说明

- enabled：总开关
- client：默认 std
- choice_ttl_seconds：候选列表有效时间
- horse.enabled：是否启用赤兔提醒
- horse.server：区服
- horse.target_groups：推送群号列表
- horse.pre_alert_minutes：刷新前提醒（默认 10 分钟）

## 验证成功

- 发 /jx3帮助 能收到帮助图
- 发 /物品 龙木强弓 能收到 tip 图
- 发 /成就 武神重临 能收到链接
- 发 /任务 茶馆问讯 能收到任务卡

## 停止

在 AstrBot 插件管理中禁用/卸载本插件即可。

## 主要文件

- main.py：命令入口与推送
- jx3_api.py：魔盒接口
- renderers.py：物品 tip / 任务卡 / 帮助图
- horse_watcher.py：赤兔提醒状态机
