# SpendingAnalyser Desktop App

这是 SpendingAnalyser 的 **macOS 桌面 App 版**说明。

如果你要使用原来的网页版、一键启动脚本、或本地浏览器仪表盘，请继续看 [README.md](README.md)。那个文件对应网页版方向；本文件只讲桌面 App 方向。

## 项目介绍

SpendingAnalyser Desktop App 是一个本地运行的家庭账单分析工具。它把 Python 数据处理后端、Vite 前端仪表盘和 Electron 桌面壳打包在一起，让用户不用手动启动网页服务，也不用自己管理端口。

它适合这些场景：

- 个人或家庭整理支付宝、微信、京东、美团账单
- 按用户区分账单，例如“我”“老婆”“家庭共同账户”
- 汇总分析两个人的家庭消费，也可以单独筛选某一个人的支出
- 用 LLM 给消费流水做二级分类，减少手动整理成本
- 在本机离线保存账单、配置和处理结果

## 和网页版的区别

| 方向 | 桌面 App 版 | 网页版 |
|---|---|---|
| 入口 | 双击 `.app` 或安装 DMG | 运行 `./start.sh` 后打开浏览器 |
| 数据位置 | macOS App 数据目录 | 项目根目录的 `data/`、`output/` |
| 配置位置 | App 数据目录里的 `config.env` / `model_profiles.json` | 项目根目录 `config.env` |
| 使用方式 | 图形界面上传、处理、配置模型 | 脚本 + 浏览器页面 |
| 适合对象 | 不想接触命令行的普通用户 | 开发者或熟悉终端的用户 |

## 下载安装包

当前桌面版产物在 `release/` 目录：

```text
release/
├── SpendingAnalyser-1.0.0-arm64.dmg   # Apple Silicon：M1 / M2 / M3 / M4
├── SpendingAnalyser-1.0.0-x64.dmg     # Intel Mac
├── mac-arm64/SpendingAnalyser.app     # ARM App 解包目录
└── mac/SpendingAnalyser.app           # x86 App 解包目录
```

选哪个版本：

- 苹果自研芯片 Mac：用 `SpendingAnalyser-1.0.0-arm64.dmg`
- Intel Mac：用 `SpendingAnalyser-1.0.0-x64.dmg`

这个 App 目前是本地自用打包，没有做 Apple Developer ID 签名和公证。第一次打开时，如果 macOS 提示无法验证开发者，可以在 Finder 里右键 App，选择“打开”，再确认打开。

## 怎么打开

最简单的方式：

1. 打开对应架构的 DMG。
2. 把 `SpendingAnalyser.app` 拖到 `Applications`。
3. 双击 `SpendingAnalyser.app`。

开发或临时测试时，也可以直接打开构建目录里的 App：

```bash
open release/mac-arm64/SpendingAnalyser.app
```

Intel 版对应：

```bash
open release/mac/SpendingAnalyser.app
```

App 启动后会自动拉起内置后端，并打开桌面窗口。用户不需要手动启动 Flask、Vite 或浏览器。

## 基本使用流程

### 1. 导入账单

进入左侧菜单的 **导入账单**。

需要填写：

- 用户：例如 `我`、`老婆`、`家庭账户`
- 平台：支付宝、微信、京东、美团
- 文件：选择对应平台导出的账单文件

上传时必须先指定用户。桌面版会把这批账单归属到该用户名下，后续仪表盘可以按用户筛选，也可以查看全部用户汇总。

支持的文件类型：

- `.csv`
- `.xlsx`
- `.xls`

### 2. 数据处理

进入 **数据处理**，点击 **一键分析**。

App 会执行完整处理流程：

```text
上传账单 -> 解析平台格式 -> 合并去重 -> 退款对冲 -> 轨道识别 -> 标签继承 -> 生成仪表盘数据
```

处理完成后，回到 **仪表盘** 查看消费结果。

### 3. 配置模型

进入 **模型配置**。

模型配置用于 LLM 自动分类。你可以保存多套配置，例如：

- 公司网关模型
- 备用模型
- 更快但便宜的模型
- 更强但更慢的模型

每套配置包含：

- 配置名称
- Base URL
- 模型名称
- API Key

API Key 保存后不会在界面里回显。要切换模型时，先点击左侧已保存配置，再点 **设为当前**。

### 4. LLM 打标

进入 **数据处理**，点击 **开始 LLM 打标**。

适合在这些情况下使用：

- 一键分析后还有“消费待打标”
- 新上传了一批账单
- 想让模型补齐二级分类

打标完成后，点击 **应用已有结果**，或者等待任务状态更新后重新查看仪表盘。

### 5. 查看仪表盘

进入 **仪表盘**。

主要能力：

- 按用户、年份、平台、轨道、分类、日期筛选
- 查看净消费支出、退款金额、非消费转移、记录总数
- 查看分类分布、消费趋势、Top 分类、Top 商户
- 查看资金流动轨，例如转账、充值、理财等非消费项
- 搜索交易明细
- 编辑交易分类

多用户分析方式：

- 想看家庭整体：用户选择“全部用户”
- 想看某个人：用户选择对应名字
- 想比较两个人：分别切换用户筛选查看

## 数据保存在哪里

桌面版不使用项目根目录的 `data/` 和 `output/` 作为运行数据目录，而是使用 macOS 的 App 数据目录：

```text
~/Library/Application Support/spending-analyser-desktop/
```

常见文件：

```text
~/Library/Application Support/spending-analyser-desktop/
├── data/                 # 桌面版上传的原始账单
├── output/               # 桌面版处理结果
├── config.env            # 当前生效的 LLM 配置
├── model_profiles.json   # 多模型配置列表
└── backend.log           # 后端运行日志
```

注意：

- 桌面版和网页版的数据目录是分开的。
- 网页版仍然使用项目里的 `data/`、`output/`、`config.env`。
- 桌面版模型面板修改的是 App 数据目录里的配置文件，不会自动改项目根目录的 `config.env`。

## 当前项目目录结构

和桌面版相关的主要目录如下：

```text
SpendingAnalyser/
├── README.md                  # 网页版说明，不要和桌面版混用
├── README_DESKTOP_APP.md      # 桌面 App 版说明
├── assets/                    # 桌面 App 图标和 Logo 资源
│   ├── logo.png
│   └── icon.icns
├── electron/                  # Electron 主进程
│   └── main.cjs
├── frontend/                  # 桌面版和网页版共用的前端源码
│   ├── index.html
│   ├── public/
│   │   ├── logo.png
│   │   └── favicon.png
│   └── src/
│       ├── api.js
│       ├── main.js
│       └── style.css
├── src/                       # Python 后端与数据处理逻辑
│   ├── api.py
│   ├── main.py
│   ├── parsers/
│   ├── cleaners/
│   └── classifiers/
├── packaging/                 # PyInstaller 后端打包配置
│   ├── backend.spec
│   └── backend_entry.py
├── scripts/                   # macOS 桌面版打包脚本
│   ├── build_macos_dmg.sh
│   └── build_macos_all.sh
├── release/                   # 构建出的 macOS App 和 DMG
├── build/                     # 构建中间产物
├── package.json               # Electron Builder 配置和 npm 脚本
└── requirements.txt           # Python 后端依赖
```

## 开发运行

先安装 Node 依赖：

```bash
npm install
```

开发模式启动桌面壳：

```bash
npm run electron:dev
```

这个命令会先构建前端，再启动 Electron。开发模式下后端由 `python3 -m src.api` 启动。

## 构建桌面版

构建当前机器架构：

```bash
npm run dist:mac
```

同时构建 Apple Silicon 和 Intel 两套版本：

```bash
npm run dist:mac:all
```

构建完成后检查：

```bash
file release/mac-arm64/SpendingAnalyser.app/Contents/Resources/backend/spending-backend/spending-backend
file release/mac/SpendingAnalyser.app/Contents/Resources/backend/spending-backend/spending-backend
hdiutil verify release/SpendingAnalyser-1.0.0-arm64.dmg
hdiutil verify release/SpendingAnalyser-1.0.0-x64.dmg
```

预期：

- ARM 后端是 `Mach-O 64-bit executable arm64`
- x86 后端是 `Mach-O 64-bit executable x86_64`
- 两个 DMG 都校验有效

## 常见问题

### 为什么桌面版打开后没有浏览器地址？

桌面版会自动启动本机后端，并把前端加载到 Electron 窗口里。它底层仍然有本地端口，但用户不需要关心。

### 为什么我在项目根目录改了 `config.env`，桌面版没变化？

桌面版读取的是：

```text
~/Library/Application Support/spending-analyser-desktop/config.env
```

请在 App 的 **模型配置** 页面修改，或者直接改这个 App 数据目录里的文件。

### API Key 保存在哪里？

保存到：

```text
~/Library/Application Support/spending-analyser-desktop/config.env
~/Library/Application Support/spending-analyser-desktop/model_profiles.json
```

界面里不会回显已保存的 Key。更新某个模型配置时，如果 API Key 输入框留空，后端会保留原来的 Key。

### 上传给不同用户的账单会混在一起吗？

底层数据会统一处理，方便做家庭汇总；同时每条上传记录会带用户归属，仪表盘可以按用户筛选。

### 桌面版会影响网页版吗？

不会。桌面版和网页版共用源码，但运行数据目录不同。网页版 README、`start.sh`、项目根目录 `data/`、`output/` 仍然保留原有用途。

### 日志在哪里？

后端日志在：

```text
~/Library/Application Support/spending-analyser-desktop/backend.log
```

如果 App 启动失败或处理失败，优先看这个文件。
