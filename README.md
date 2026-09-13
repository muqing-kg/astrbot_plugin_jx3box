# 剑网3魔盒查询

面向普通用户的剑三查询插件：物品 tip 图、成就链接、任务信息卡。

## 命令

命令带不带 / 均可触发，默认不加 /。

- 物品查询 关键词：查物品，返回 tip 详情图
- 成就查询 关键词：查成就，返回链接
- 任务查询 关键词：查任务，返回信息卡图片
- 多个结果直接回复数字选择；超过 10 条出图，回复 换页 翻页
- jx3帮助：查看帮助图

## 使用示例

物品查询 玄晶
42

成就查询 武神重临

任务查询 茶馆问讯

## 安装

1. 把整个 astrbot_plugin_jx3box 文件夹放到 AstrBot 的 data/plugins/ 下
2. 安装依赖：pip install -r requirements.txt
3. 在 AstrBot 插件管理里启用本插件

## 配置说明

- enabled：总开关
- client：默认 std
- choice_ttl_seconds：候选列表有效时间

## 验证成功
- 2~10 条候选返回文字列表，可直接回复数字选择
- 超过 10 条返回候选图（每页最多 100 条），可回复 换页

- 发 jx3帮助 能收到帮助图
- 发 物品查询 龙木强弓 能收到 tip 图
- 发 成就查询 武神重临 能收到链接
- 发 任务查询 茶馆问讯 能收到任务卡

## 停止

在 AstrBot 插件管理中禁用/卸载本插件即可。

## 目录结构
- main.py：命令入口（AstrBot 要求固定在插件根目录）
- api/：http_client（HTTP 客户端）、jx3_api（魔盒接口封装）
- render/：choice_list（候选列表）、tip_html / item_tip（物品 tip）、quest_html（任务卡）、renderers（帮助图与文本标记）、html_util / font_util（渲染公共工具）
- assets/：模板 CSS、候选列表背景、任务图标等资源
- fonts/：本地字体（候选图 / 帮助图的 Pillow 渲染用）
- scripts/：smoke_test.py 离线冒烟与资源分析脚本


## 渲染说明

- 物品 tip / 任务卡：生产环境走 AstrBot html_render → 远端 astrbot-t2i
- scripts/smoke_test.py 只校验 HTML 模板与 API，不替代真机出图验收
- 帮助图仍为本地 Pillow 生成
