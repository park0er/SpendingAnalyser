"""
Taxonomy — L1 + L2 Category System

Fixed category tree derived from real 2025 Alipay data analysis.
Used by both rule-based mapping and LLM tagging.
"""

import pandas as pd

# The canonical L1 -> L2 taxonomy tree
TAXONOMY = {
    "餐饮美食": ["外卖配送", "堂食正餐", "快餐简餐", "咖啡饮品", "自动售货/零食", "生鲜超市", "烘焙甜点"],
    "交通出行": ["高速/ETC", "网约车/打车", "公共交通", "租车", "机票火车票", "共享单车"],
    "爱车养车": ["停车费", "新能源充电", "加油", "购车/车辆订单", "车险", "维修保养", "洗车"],
    "住房物业": ["房租", "物业费", "水电燃气"],
    "日用百货": ["线上日杂", "线下超市/便利店", "日化清洁"],
    "服饰装扮": ["鞋靴", "服装", "箱包配饰"],
    "数码电器": ["手机/电子产品", "电脑办公", "智能家居"],
    "充值缴费": ["话费流量", "会员订阅", "水电燃气缴费"],
    "文化休闲": ["电影演出", "会员/知识付费", "书籍", "按摩/休闲", "文创/玩具"],
    "医疗健康": ["药品", "就医/体检"],
    "商业服务": ["ETC办理", "快递寄件", "以旧换新", "打印/办证"],
    "生活服务": ["快递", "打印", "家政"],
    "酒店旅游": ["酒店住宿", "景区门票", "签证"],
    "美容美发": ["美发", "美容护肤"],
    "母婴亲子": ["玩具", "母婴用品"],
    "家居家装": ["家具", "五金建材"],
    "保险": ["人寿保险", "财产保险"],
    "公共服务": ["政府缴费", "公共设施"],
    "其他": ["未分类"],
}

# Flat list of all L1 categories
ALL_L1 = list(TAXONOMY.keys())

# Flat list of all (L1, L2) tuples
ALL_L1_L2 = [(l1, l2) for l1, l2s in TAXONOMY.items() for l2 in l2s]


# ── Alipay direct mapping ──────────────────────────────────────────
# Map Alipay platform_category to a default L1 (L2 will be refined by LLM)
ALIPAY_L1_MAP = {
    "餐饮美食": "餐饮美食",
    "交通出行": "交通出行",
    "日用百货": "日用百货",
    "服饰装扮": "服饰装扮",
    "住房物业": "住房物业",
    "充值缴费": "充值缴费",
    "数码电器": "数码电器",
    "文化休闲": "文化休闲",
    "医疗健康": "医疗健康",
    "爱车养车": "爱车养车",
    "商业服务": "商业服务",
    "母婴亲子": "母婴亲子",
    "美容美发": "美容美发",
    "酒店旅游": "酒店旅游",
    "家居家装": "家居家装",
    "生活服务": "生活服务",
    "保险": "保险",
    "公共服务": "公共服务",
    "其他": "其他",
    # Cashflow categories (should not reach here, but just in case)
    "转账红包": "其他",
    "投资理财": "其他",
    "信用借还": "其他",
    "收入": "其他",
    "退款": "其他",
}


def apply_alipay_l1_mapping(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply L1 mapping for Alipay records based on platform_category.
    L2 is left empty — to be filled by LLM tagger.
    """
    df = df.copy()
    mask = (df["source_platform"] == "alipay") & (df["track"] == "consumption")

    for idx in df[mask].index:
        cat = df.at[idx, "platform_category"]
        l1 = ALIPAY_L1_MAP.get(cat, "其他")
        df.at[idx, "global_category_l1"] = l1

    return df


def get_taxonomy_prompt_block() -> str:
    """Generate the taxonomy section for LLM prompts."""
    lines = []
    for l1, l2s in TAXONOMY.items():
        l2_str = " / ".join(l2s)
        lines.append(f"[{l1}: {l2_str}]")
    return "\n".join(lines)
