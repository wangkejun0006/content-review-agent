"""Deterministic fictional outputs; no claim of model extraction accuracy."""


def product_import_fixture(text, names):
    conflict = "CONFLICT" in text
    second = "CLIP_V1" in text
    version2 = "SPEC_V2" in text
    pages = 120 if version2 else 96
    features = (
        ["固定纸张", "岩灰色"]
        if second
        else [
            "采用 A5 尺寸",
            f"内页 {pages} 页",
            "内页为点阵布局",
            "封面有雾蓝与砂白两种颜色",
        ]
    )
    return {
        "stable_key": "orbit-clip-02" if second else "orbit-note-01",
        "payload": {
            "name": "云角桌面收纳夹" if second else "轨迹点阵笔记本",
            "sku": "CLIP02" if second else "NOTE01",
            "product_type": "desk_accessory" if second else "stationery",
            "description": "虚构桌面配件，用于固定纸张。"
            if second
            else "虚构的纸质笔记本，用于记录灵感与待办。",
            "features": features,
            "materials": ["金属"] if second else ["纸质内页"],
            "non_medical_disclaimer": "虚构资料，仅用于软件演示。",
        },
        "search_text": "虚构资料冲突，等待人工确认" if conflict else "虚构确认规格",
        "field_confidence": {"sku": 1.0, "features": 0.2 if conflict else 0.8},
        "missing_fields": ["防水和效率效果证据"],
        "warnings": [
            "确定性离线 fixture 输出，不代表真实模型抽取或核验。",
            *(["尺寸 A5/A6、页数 96/160、颜色存在冲突；不得自动合并或激活。"] if conflict else []),
            "防水、保证提高效率 80% 未证实，不得作为效果 Claim。",
        ],
        "source_summaries": [
            {"source_name": name, "summary": "虚构演示资料，需人工复核。"} for name in names
        ],
    }
