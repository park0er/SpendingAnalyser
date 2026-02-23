# 跨平台支付数据记账分析工具实施方案 (V1)

基于两份参考文档（02-22版 / 02-23版）的系统性分析，提出分两步走的务实方案：先做出能用的一次性分析脚本，再包装成可复用的 Agent Skill。

---

## 核心思路

两份参考文档信息量很大，但真正落地时，核心问题可以归结为 4 件事：

1. 解析：每个平台的 CSV 格式不同（编码、表头、字段名），需要各写一个 parser
2. 清洗：退款对冲（别算重）+ 非消费项过滤（红包/转账/充值别算进去）
3. 分类：利用平台预设标签做一级归一化，模糊的再用关键词匹配兜底
4. 输出：生成一份 Markdown 分析报告（按分类汇总、月度趋势、Top 商户等）

数据隐私：所有处理 100% 本地完成，不调用任何云端 API。分类逻辑全部基于规则和关键词匹配，不依赖 LLM。这既保护隐私，又避免了部署大模型的复杂度。未来如果想引入 LLM 做更智能的分类，可以作为增强层加上去。

---

## 第一步：一次性分析脚本（MVP）

目标：一个 Python 脚本，扔进去 CSV 文件，输出一份干净的消费分析报告。

### 项目结构

```
SpendingAnalyser/
├── 参考材料/                    # 已保存的两份参考文档
├── data/                       # 用户放置原始 CSV 的目录
├── output/                     # 生成的分析报告
├── src/
│   ├── main.py                 # 入口：读取 data/ → 输出 output/
│   ├── parsers/                # 各平台 CSV 解析器
│   │   ├── base.py             # 基类：定义 UUL 标准字段
│   │   ├── alipay.py           # 支付宝解析器
│   │   ├── wechat.py           # 微信支付解析器
│   │   ├── meituan.py          # 美团支付解析器
│   │   ├── jd.py               # 京东支付解析器
│   │   └── douyin.py           # 抖音支付解析器
│   ├── cleaners/
│   │   ├── refund_netting.py   # 退款对冲算法
│   │   └── non_consumption.py  # 非消费项过滤
│   ├── classifiers/
│   │   └── taxonomy.py         # 分类归一化映射
│   └── reporters/
│       └── markdown_report.py  # Markdown 报告生成
├── tests/
└── requirements.txt
```

### 数据模型 (UUL Schema)

统一标准账单模型（UUL），所有平台的 parser 都输出同一个 DataFrame schema：
source_platform, transaction_id, timestamp, direction, amount, counterparty, description, payment_method, status, platform_category, original_transaction_id, is_consumption, effective_amount, global_category_l1, global_category_l2

### 退款对冲算法

分两级：
1. 确定性匹配：支付宝有 originalTransactionId，美团有相同订单号 + 状态码 3，直接精确关联
2. 启发式匹配：微信等缺乏关联 ID 的平台，用 30 天时间窗 + 对手方字符串相似度（≥0.85）+ 金额匹配

### 非消费项过滤

两层过滤：
硬过滤：正则匹配关键词黑名单，命中即 is_consumption = False
软过滤：对手方特征分析

### 分类归一化

静态映射表 + 关键词兜底。如果平台预设分类命中映射表，直接用；否则对 description 做关键词匹配兜底。

### 报告输出

生成 Markdown 报告，包含总览卡片、按分类汇总表、月度趋势表、Top 15 商户、退款明细、未分类/待确认记录。

---

## 第二步：固化为 Agent Skill

MVP 验证通过后，将核心逻辑封装为 Agent 可调用的 Skill。

SKILL.md 定义 Agent 调用接口，内部调用 Python CLI：
```bash
python -m src.main --input data/ --output output/report.md
```
