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
    "日用百货": ["线上日杂", "线下超市/便利店", "日化清洁", "鲜花绿植"],
    "服饰装扮": ["鞋靴", "服装", "箱包配饰"],
    "数码电器": ["手机/电子产品", "电脑办公", "智能家居"],
    "充值缴费": ["话费流量", "会员订阅", "水电燃气缴费"],
    "文化休闲": ["电影演出", "会员/知识付费", "书籍", "按摩/休闲", "文创/玩具", "运动健身"],
    "医疗健康": ["药品", "就医/体检", "保健品/器械"],
    "商业服务": ["ETC办理", "快递寄件", "以旧换新", "打印/办证"],
    "生活服务": ["快递", "打印", "家政"],
    "酒店旅游": ["酒店住宿", "景区门票", "护照签证", "旅行保险", "旅行团费/套餐", "导游/游玩项目", "旅游杂费", "机票火车票", "租车"],
    "美容美发": ["美发", "美容护肤", "美妆个护"],
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



def get_taxonomy_prompt_block() -> str:
    """Generate the taxonomy section for LLM prompts."""
    lines = []
    for l1, l2s in TAXONOMY.items():
        l2_str = " / ".join(l2s)
        lines.append(f"[{l1}: {l2_str}]")
    return "\n".join(lines)
