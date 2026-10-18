"""Pure aliases shared by schema validation without importing Django models."""
ALIASES = {
    "电子与智能化": "electronic", "电子智能化": "electronic", "电子与智能化工程专业承包": "electronic",
    "施工劳务": "labor", "施工劳务资质": "labor", "劳务资质": "labor",
    "CS": "cs", "信息系统建设和服务能力": "cs", "CMMI": "cmmi", "软件能力成熟度": "cmmi",
    "CCRC": "ccrc", "信息安全服务资质": "ccrc", "ITSS": "itss", "信息技术服务运行维护": "itss",
    "安防": "security", "安防工程企业设计施工维护能力": "security",
}


def canonical_category(value):
    return ALIASES.get(value, value)
