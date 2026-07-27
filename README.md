# 剑三魔盒查询插件

面向普通用户的剑三查询插件：物品 tip 图、成就链接、任务信息卡，以及后台赤兔提醒。

## 命令

- /物品 关键词：查物品，返回 tip 详情图
- /成就 关键词：查成就，返回链接
- /任务 关键词：查任务，返回信息卡图片
- /1 到 /10：多个结果时选择
- /jx3帮助：查看帮助图
- /赤兔订阅 区服：当前群订阅该区服赤兔提醒
- /赤兔查询：管理员查看全部群订阅（带序号）
- /赤兔删除 序号：管理员删除指定订阅

## 使用示例

/物品 玄晶
/1

/成就 武神重临

/任务 茶馆问讯

/赤兔订阅 梦江南
/赤兔查询
/赤兔删除 1

## 安装

1. 把整个 astrbot_plugin_jx3box 文件夹放到 AstrBot 的 data/plugins/ 下
2. 安装依赖：pip install -r requirements.txt
3. 在 AstrBot 插件管理里启用本插件
4. 在群里用 /赤兔订阅 区服 开通提醒；管理员可用 /赤兔查询 与 /赤兔删除 管理

## 配置说明

- enabled：总开关
- client：默认 std
- choice_ttl_seconds：候选列表有效时间
- horse.enabled：是否启用赤兔后台
- horse.pre_alert_minutes：刷新前提醒（默认 10 分钟）
- horse.poll_idle_seconds：空闲轮询间隔
- horse.calibrate_before_seconds：到点前校准秒数

说明：区服与推送群不再走配置页，全部由命令订阅保存。

## 赤兔订阅规则

- 仅群聊可订阅
- 区服名按官方名单校验，错误会提示：请输入正确区服！
- 一条订阅 = 一个群 + 一个区服；同群可订多个区服
- 推送只发给订阅了该区服的群，不串群、不串区服
- 文案始终带「区服：xxx」
- 订阅数据保存在插件数据目录 horse_subscriptions.json

## 验证成功

- 发 /jx3帮助 能收到帮助图
- 发 /物品 龙木强弓 能收到 tip 图
- 发 /成就 武神重临 能收到链接
- 发 /任务 茶馆问讯 能收到任务卡
- 群内 /赤兔订阅 梦江南 提示成功；错区服提示请输入正确区服！
- 管理员 /赤兔查询 能看到序号列表，/赤兔删除 序号 可删除

## 停止

在 AstrBot 插件管理中禁用/卸载本插件即可。

## 主要文件

- main.py：命令入口与推送
- jx3_api.py：魔盒接口
- tip_html.py / quest_html.py：物品 tip / 任务卡 HTML 渲染
- horse_watcher.py：赤兔提醒状态机
- horse_subscribe.py：群订阅与区服匹配
- assets/server_list.json：内置区服名单\n- 数据目录 server_list.json：运行时刷新缓存（优先）\n- tip_html.py / quest_html.py：生产 HTML 模板（AstrBot html_render / t2i）\n- smoke_test.py：离线 HTML/API 冒烟（非 t2i 真机出图）


## 渲染说明

- 物品 tip / 任务卡：生产环境走 AstrBot html_render → 远端 astrbot-t2i
- 本地 smoke_test.py 只校验 HTML 模板与 API，不替代真机出图验收
- 帮助图仍为本地 Pillow 生成
