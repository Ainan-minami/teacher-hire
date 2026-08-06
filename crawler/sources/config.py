"""数据源配置。

集中管理各源开关、分页深度、关键词等，方便 fork 后按需调整。
"""

SOURCES = {
    # 万行教师人才网：民办学校职位为主，列表页字段完整
    "job910": {
        "enabled": True,
        "pages": 30,             # 每类抓取页数，每页约 10 条（实测 30 页×6 类 ≈ 1800 条）
        "job_types": [30, 10, 20, 40, 60, 70],  # 教师/中小学/培训/国际学校/兼职/其他（分类间零重叠）
        "delay": 1.5,
    },
    # 教育部人才服务网：直属事业单位 + 高校公告，权威
    "jybzp": {
        "enabled": True,
        "pages": 6,              # POST 分页，每页 10 条
        "categories": ["drus", "school"],
        "delay": 1.2,
    },
    # 应届生招聘网：每日公告流，含大量高校/事业单位教师岗
    "yjszp": {
        "enabled": True,
        "pages": 8,              # 每页 30 条
        "delay": 1.2,
    },
    # 省教育厅/人事考试网公告（通用解析器，覆盖面广但每日增量少）
    "prov_bureau": {
        "enabled": True,
        "delay": 1.0,
        "max_pages": 3,
    },
    # 中国教师招聘网（GBK 编码，国际学校/民办为主，质量一般，默认关闭）
    "chinajob": {
        "enabled": False,
        "pages": 2,
        "delay": 1.0,
    },
}

# 每个源最多保留的条数（防止单源刷屏）
MAX_PER_SOURCE = 1500

# 来源标签（前端展示用）
SOURCE_LABELS = {
    "job910": "万行教师人才网",
    "jybzp": "教育部人才服务网",
    "yjszp": "应届生招聘网",
    "prov_bureau": "省厅公告",
    "chinajob": "中国教师招聘网",
}
