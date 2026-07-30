# AllergenGrid

**宾客 CSV + 菜单 JSON 输入，输出候选/暂停/禁止矩阵、交叉接触原因链、打印标签和可校验活动包。完全离线，不用 AI 猜。**

[English](README.md) ·
[输入格式](docs/input-format.md) ·
[安全模型](docs/safety-model.md) ·
[故障修复](docs/troubleshooting.md)

社区聚餐、学校活动、志愿者厨房或小型餐饮通常把信息分散在三处：宾客 RSVP、配方/包装标签，以及某个人对砧板、锅具和公勺复用情况的记忆。AllergenGrid 只连接明确声明，不自行补全事实。

> [!CAUTION]
> AllergenGrid 是记录和复核工具，不是医疗建议、人员培训、清洁规程或食品安全认证。`CANDIDATE` 仅表示本次输入中没有发现冲突，不等于“安全”。上桌前仍须重新核对当前标签和配方、解决所有暂停项、确认备餐与服务控制，并与宾客本人沟通。

## v0.1.0 的真实功能

- 严格读取 UTF-8 `event.json` 与 `guests.csv`，未知过敏原、缺列或歧义别名会直接失败；
- 内置美国九大过敏原、欧盟十四项过敏原及合并声明集；
- 为每个“宾客 × 菜品”输出 `BLOCK`、`HOLD` 或 `CANDIDATE` 及原因；
- 按备餐顺序追踪砧板、锅具、油、器械等资源上的已知/可能/未知残留；
- 把共用自助餐夹、勺或容器视为双向交叉接触路径；
- 检查 `free_from` 声明是否与配料或资源路径冲突；
- 生成独立 HTML 报告、打印菜品牌、CSV 矩阵、JSON 分析、Markdown 厨房交接单、回执和 SHA-256 清单；
- 生成确定性 ZIP，并可在不解压的情况下逐文件校验；
- 零运行时依赖、固定退出码、JSON 输出和严格 CI 模式。

它不会从配料名字推断过敏原，不抓取菜谱，不诊断过敏，也不会给菜品贴“安全”标签。

## 五分钟验收

```bash
git clone https://github.com/KanadeK/allergengrid.git
cd allergengrid
python -m venv .venv
```

激活环境：

```bash
# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

安装并运行严格通过样例：

```bash
python -m pip install -e .
allergengrid audit examples/community-supper-safe --strict
```

生成完整交付物：

```bash
allergengrid build examples/community-supper-safe --out build/community-supper --strict
allergengrid pack examples/community-supper-safe --out build/community-supper.zip --strict
allergengrid verify-pack build/community-supper.zip
```

本地打开 `build/community-supper/report.html`，打印
`build/community-supper/labels.html`。

GitHub Release 也提供无需安装的单文件版本：

```bash
python allergengrid-0.1.0.pyz audit community-supper-safe --strict
```

## 三种状态

| 状态 | 含义 | 动作 |
| --- | --- | --- |
| `BLOCK` | 菜品明确含有宾客声明回避的过敏原 | 不提供该菜品 |
| `HOLD` | 存在 `may_contain`、交叉接触、缺少饮食标签、未核实配料或未知残留 | 解决原因并与宾客确认；否则不提供 |
| `CANDIDATE` | 当前明确输入中未发现冲突 | 上桌前仍须复核标签、配方、备餐、服务布置和宾客需求 |

查看单个格子的原因：

```bash
allergengrid explain examples/community-supper-safe \
  --guest leo \
  --dish yogurt-dip
```

## 建立自己的活动

```bash
allergengrid init my-event --profile us
```

目录结构只有两个源文件：

```text
my-event/
├── event.json
└── guests.csv
```

CSV 中多值字段使用 `|` 分隔。`notes` 只供人阅读，程序不会把自由文本解析成安全结论。完整字段见[输入格式](docs/input-format.md)。

## 命令和退出码

```text
allergengrid init DIRECTORY [--profile us|eu|global]
allergengrid validate CASE [--json]
allergengrid audit CASE [--json] [--strict]
allergengrid explain CASE --guest ID --dish ID [--json]
allergengrid build CASE --out DIRECTORY [--strict]
allergengrid pack CASE --out FILE.zip [--strict]
allergengrid verify-pack FILE.zip [--json]
```

| 退出码 | 含义 |
| ---: | --- |
| `0` | 命令完成，所选门禁通过 |
| `1` | 输入、文件系统或压缩包无法安全读取 |
| `2` | 发现项未通过门禁，或压缩包完整性失败 |

不加 `--strict` 时警告仍会显示，但只有错误导致失败；加上后，警告或错误都会返回 `2`。

## 必须失败的样例

`examples/community-supper-risky` 故意包含：

- 芝麻面和水果共用砧板，且中间没有清洁边界；
- 水果配料未核实；
- 两个菜共用自助餐夹；
- 水果却声明 `sesame` free-from。

```bash
allergengrid audit examples/community-supper-risky --strict
```

命令必须返回 `2` 并出现 `AG203`。这证明失败路径不是文档里的假描述。

## 一键验证与发布门禁

```bash
python -m pip install -e ".[dev]"
python scripts/verify.py
python scripts/verify.py --release
```

发布门禁包含 Ruff、严格 mypy、分支覆盖率不低于 90%、功能/负向/篡改测试、通过与失败样例、秘密与贡献者尾注扫描、wheel/sdist/单文件 zipapp/样例包/校验和、间隔构建字节一致性，以及干净虚拟环境安装验收。

失败时按照[故障修复手册](docs/troubleshooting.md)处理，不要跳过或把警告隐藏掉。

## 调研和差异化

项目在 2026-07-30 先完成了本地历史项目盘点、GitHub 精确查询和官方资料核对。针对活动过敏原矩阵、宾客/菜品匹配和交叉接触图的查询没有找到直接同类开源工具；相邻结果主要是 RSVP、菜谱或 AI 膳食规划，未把宾客限制、明确配料声明、资源复用、未知状态和可校验离线活动包组合起来。

检索无法证明绝对不存在，因此[调研记录](docs/research.md)公开了日期、查询和边界。Star 和浏览量无法保证，但项目针对反复出现的真实问题，提供零账号、零服务器、零 API key、可立即运行的样例和可分享成果。

## 隐私与安全

- 全部处理在本地进行，核心不会联网；
- HTML 全部转义，CSV 会中和公式形态的单元格；
- ZIP 校验检查路径、重复条目、大小和 SHA-256，且不解压；
- 不要在公开 Issue 或样例中放入真实宾客姓名或健康信息；
- `CANDIDATE` 永远不等于“安全”。

详见 [SECURITY.md](SECURITY.md) 和[安全模型](docs/safety-model.md)。

MIT 许可证。AllergenGrid 与 FDA、CDC、欧盟委员会或任何医疗/监管机构没有隶属或背书关系。
