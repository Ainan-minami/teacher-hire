# 🧑‍🏫 教师招聘聚合站

一个**零服务器成本、每日自动更新**的教师招聘信息聚合网站，聚合全国中小学、高校、教育局的公开招聘信息，支持按地区、学科、学历、学段、来源、时间筛选，并配有岗位分布热度地图。

> 本项目定位：低成本快速验证的初产品，同时把地基打好——数据源模块化、字段标准化、一键部署，方便后续加数据源、加功能。

---

## ✨ 功能特性

| 能力 | 说明 |
|------|------|
| 每日自动更新 | GitHub Actions 定时（每天 07:00 UTC = 北京时间 15:00），无需人工干预 |
| 多数据源聚合 | 万行教师人才网（中小学/国际学校/培训机构，4 类 600+ 条）+ 教育部人才服务网 + 应届生招聘网 |
| 结构化字段 | 职位名称、学校、省份、城市、学历、经验、薪资、截止日期、来源、链接、发布时间 |
| 多维筛选 | 关键词搜索 + 省份/学科/学历/学段/来源/时间范围筛选 + 按时间/薪资排序 |
| 今日新增 | 一键只看当天新抓取的岗位（🆕 标记） |
| 关注组合 | 把筛选条件存成"关注"，每天有新增自动显示 +N 角标 |
| 岗位热度地图 | Leaflet 免费地图，按省份展示岗位数量分布，点击省份即可筛选 |
| 移动端友好 | 响应式布局，无框架、无构建步骤，首屏加载快 |
| 完全零成本 | GitHub Pages 托管 + GitHub Actions 定时任务，全部免费额度 |

## 📡 数据源与覆盖率

| 数据源 | 类型 | 覆盖内容 | 状态 |
|--------|------|----------|------|
| [万行教师人才网](https://www.job910.com) | 垂直招聘站 | 4 类岗位（教师/中小学/培训/国际学校）× 15 页，约 600 条，含薪资/学历/经验 | ✅ 已接入 |
| [教育部人才服务网](https://jybzp.chsi.com.cn) | 官方平台 | 教育部直属事业单位、高校公开招聘公告 | ✅ 已接入 |
| [应届生招聘网](https://www.yjszp.com) | 公告聚合 | 高校、事业单位、中小学教师岗公告 | ✅ 已接入 |

> ⚠️ **诚实声明**：当前版本是「可信稳定的来源优先」策略。以下渠道经实测后**主动放弃**：
> - **高校人才网 gaoxiaojob.com**：返回 403 反爬，且对 GitHub Actions（美国 IP）访问更严。
> - **全国事业单位招聘网 qgsydw.com**：页面为 JS 动态渲染、导航结构混乱，抓取成本高、产出偏事业单位而非教师岗。
> - **百度/必应搜索聚合**：必应 RSS 对中文招聘查询返回大量百科/门户噪音，实测相关率极低，已替换为结构化来源。
> - **智联/BOSS/前程无忧**：反爬严格，违背"零成本"原则，直接跳过。
>
> 后续可按 `DECISIONS.md` 中的扩展路线，继续接入各省人事考试网、教育局官网等静态 HTML 来源，逐步提升到 60%+ 渠道覆盖。

## 🏗️ 技术架构

```
GitHub Actions（定时 07:00 UTC）
        │
        ▼
   crawler/runner.py ──► job910 / jybzp / yjszp 各源模块
        │
        ▼
   清洗 + 结构化 + 去重（按 URL，120 天保留）
        │
        ▼
   web/data/jobs.json（前端数据）  +  crawler/data/snapshot-日期.json（历史快照）
        │
        ▼
   git commit & push  ──►  GitHub Pages 自动部署
```

**技术选型（详见 [DECISIONS.md](DECISIONS.md)）**

- 爬虫：Python + urllib（标准库）+ BeautifulSoup，无 requests/Playwright 依赖，单源失败不影响整体。
- 存储：仓库内静态 JSON。日增约 200-300 条（约 100KB），GitHub Pages 直接托管，无数据库、无配额风险。
- 前端：原生 HTML/CSS/JS，无构建步骤；Leaflet 免费地图（国内 CDN 加载）。
- 部署：GitHub Actions + Pages artifact 方式，仓库在根目录或子路径下都能正常访问。

## 🚀 快速开始（本地）

### 1. 运行爬虫

需要 Python 3.10+：

```bash
pip install -r requirements.txt
python -m crawler.runner --shallow   # 浅抓取，快速验证
python -m crawler.runner             # 完整抓取
```

成功后会在 `web/data/` 生成 `jobs.json`、`meta.json`、`province-counts.json`。

### 2. 预览前端

```bash
python scripts/serve.py 8000
# 浏览器打开 http://localhost:8000
```

### 3. 跑测试

```bash
node scripts/smoke-test.js   # 前端冒烟测试（无需浏览器）
```

## 🌐 一键部署到 GitHub Pages

1. **Fork 本仓库**（或 push 到自己仓库）。
2. 仓库 Settings → Pages → Build and deployment → Source 选 **GitHub Actions**。
3. 无需配置任何 Secret（爬虫只抓公开页面）。
4. 首次部署可手动触发：
   - 仓库 Actions → **每日爬取并部署** → **Run workflow**。
5. 之后每天 07:00 UTC 自动爬取并更新。

站点地址：`https://<你的用户名>.github.io/<仓库名>/`

> **推荐部署：国内服务器（主站）**
> GitHub Pages 在部分大陆网络环境下访问不稳定，建议把主站部署到国内云服务器
> （阿里云/腾讯云轻量服务器，Ubuntu 22.04，约几十元/年）。
> 一键部署脚本见 `scripts/deploy_server.py`：
> ```bash
> python scripts/deploy_server.py <服务器IP> root <密码>
> ```
> 脚本会自动：安装 Nginx → 上传网站 → 安装爬虫环境 → 配置每日 15:30 本地爬取 → 首次运行生成数据。
> GitHub Pages 保留作为开源镜像/备用入口。

## 🧩 如何加一个新数据源

1. 在 `crawler/sources/` 新建 `my_source.py`：

```python
def run(ctx) -> list[dict]:
    # 返回统一 schema 的记录列表，字段见 crawler/runner.py 或已有源
    return []
```

2. 在 `crawler/sources/config.py` 的 `SOURCES` 中注册并设置 `enabled`。
3. 本地跑 `python -m crawler.runner --only my_source` 验证。

**统一字段**：`title / school / url / source / source_label / province / city / education / experience / salary / salary_text / subject / school_level / deadline / publish_date / crawl_date / summary`

## 📁 项目结构

```
teacher-hire-aggregator/
├── .github/workflows/
│   └── daily-crawl-and-deploy.yml   # 每日爬取 + Pages 部署
├── crawler/
│   ├── runner.py                    # 调度、合并、去重、写数据
│   ├── fetch.py                     # HTTP 公共层（重试/UA/节流）
│   ├── clean.py                     # 字段提取（省份/城市/学历/学科/薪资/截止）
│   ├── storage.py                   # JSON 持久化 + 快照管理
│   ├── sources/
│   │   ├── config.py                # 数据源配置
│   │   ├── job910.py                # 万行教师人才网
│   │   ├── jybzp.py                 # 教育部人才服务网
│   │   └── yjszp.py                 # 应届生招聘网
│   └── data/                        # 每日快照（保留 14 天）
├── web/
│   ├── index.html                   # 前端页面
│   ├── css/style.css
│   ├── js/app.js                    # 前端逻辑（原生 JS）
│   └── data/                        # 前端数据（爬虫生成）
├── scripts/
│   ├── serve.py                     # 本地预览
│   └── smoke-test.js                # 前端冒烟测试
├── requirements.txt
└── DECISIONS.md                     # 开发决策日志
```

## ⚠️ 使用须知

- 本站仅做**信息聚合与筛选**，投递前请务必点击"查看原文"到官方页面核实。
- 数据来自公开网页，爬取频率已做礼貌节流；若某个来源方明确禁止抓取，请在该源配置中关闭。
- 只聚合公开招聘信息（标题/摘要/链接），不采集任何个人隐私信息（简历、联系方式等）。
- 每条记录保留 160 字摘要并附原文链接，不复制完整职位描述。
- GitHub Actions 运行在海外节点，部分国内网站可能限流；各源独立容错，失败不影响其他源。

## 🗺️ 后续路线

- [ ] 接入更多稳定来源（各省人事考试网、教育局官网 RSS）
- [ ] 详情页正文抓取（用链接去重后的正文做更准的字段提取）
- [ ] 站内收藏/订阅（本地存储）
- [ ] 按城市自动推送（Telegram/微信机器人）
- [ ] 数据量超过 2MB 后引入 Supabase/索引分片
