#!/usr/bin/env python3
"""
AI & Semiconductor Daily News Crawler
每日抓取 AI 和半导体领域新闻，生成结构化报告（含中文翻译）
"""

import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timezone, timedelta
import time
import re
import os
import sys
import base64
import urllib.request
import urllib.parse

# 修复 Windows 终端 GBK 编码问题
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# ============================================================
# 配置
# ============================================================
SOURCES = [
    {
        "name": "MIT Technology Review AI",
        "url": "https://www.technologyreview.com/topic/artificial-intelligence/",
        "type": "mittr",
        "max_articles": 4,
    },
    {
        "name": "MIT Technology Review Semiconductor",
        "url": "https://www.technologyreview.com/topic/semiconductors/",
        "type": "mittr",
        "max_articles": 3,
    },
    {
        "name": "Ars Technica AI",
        "url": "https://arstechnica.com/ai/",
        "type": "ars",
        "max_articles": 3,
    },
    {
        "name": "IEEE Spectrum AI",
        "url": "https://spectrum.ieee.org/artificial-intelligence",
        "type": "ieee",
        "max_articles": 3,
    },
]

# 龙头企业关键词映射
COMPANY_KEYWORDS = {
    "NVIDIA": ["nvidia", "nvidia"],
    "AMD": ["amd", "advanced micro devices"],
    "Intel": ["intel"],
    "TSMC": ["tsmc", "taiwan semiconductor"],
    "Samsung Electronics": ["samsung electronics", "samsung"],
    "ASML": ["asml"],
    "Applied Materials": ["applied materials"],
    "Lam Research": ["lam research"],
    "KLA Corporation": ["kla", "kla corporation"],
    "Google": ["google", "alphabet"],
    "Microsoft": ["microsoft"],
    "Apple": ["apple"],
    "Meta": ["meta", "facebook"],
    "Amazon": ["amazon"],
    "Tesla": ["tesla"],
    "Boston Dynamics": ["boston dynamics"],
    "Figure AI": ["figure ai"],
    "UBTech": ["ubtech"],
    "ABB": ["abb"],
    "Fanuc": ["fanuc"],
    "Yaskawa": ["yaskawa"],
    "SMIC": ["smic", "semiconductor manufacturing international", "中芯国际"],
    "Huawei": ["huawei", "华为"],
    "NAURA": ["naURA", "naura technology", "北方华创"],
    "AMEC": ["amec", "advanced micro-fabrication equipment", "中微公司"],
}

SEMICONDUCTOR_KEYWORDS = [
    "semiconductor", "chip", "wafer", "foundry", "fabrication", "lithography",
    "photoresist", "etching", "deposition", "CVD", "PVD", "EUV", "DUV",
    "integrated circuit", "IC design", "SoC", "GPU", "NPU", "TPU",
]

ROBOT_KEYWORDS = [
    "robot", "robotics", "humanoid", "automation", "actuator", "manipulator",
    "autonomous", "cobots", "industrial robot",
]


# ============================================================
# 翻译函数（使用免费 API）
# ============================================================

def translate_to_zh(text, max_len=4000):
    """
    将英文翻译为中文，使用 Google Translate 免费接口
    如果翻译失败，返回原文
    """
    if not text or len(text.strip()) < 5:
        return text

    # 分段翻译，避免超长
    if len(text) > max_len:
        chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]
        translated_chunks = [translate_to_zh(chunk, max_len) for chunk in chunks]
        return "\n".join(translated_chunks)

    try:
        # 使用 Google Translate 非官方 API（免费）
        encoded = urllib.parse.quote(text)
        url = (
            f"https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=en&tl=zh-CN&dt=t&q={encoded}"
        )
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            # result[0] 是翻译结果数组，每个元素格式： [翻译文本, 原文, ...]
            translated = "".join([item[0] for item in result[0] if item[0]])
            return translated.strip()
    except Exception as e:
        print(f"  [翻译] 失败：{e}")
        return text  # 翻译失败返回原文


def translate_title(title):
    """翻译标题（较短，直接翻译）"""
    return translate_to_zh(title, max_len=200)


def translate_summary(summary):
    """翻译摘要"""
    if not summary or len(summary) < 10:
        return summary
    return translate_to_zh(summary, max_len=2000)


# ============================================================
# 爬虫函数
# ============================================================

def fetch_url(url, headers=None):
    """通用 URL 抓取，带重试"""
    default_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if headers:
        default_headers.update(headers)

    for attempt in range(3):
        try:
            resp = requests.get(url, headers=default_headers, timeout=15)
            if resp.status_code == 200:
                return resp.text
        except Exception as e:
            print(f"  [尝试 {attempt+1}] 抓取失败 {url}: {e}")
            time.sleep(2)
    return None


def parse_mittr(html, source_cfg):
    """解析 MIT Technology Review"""
    soup = BeautifulSoup(html, "html.parser")
    articles = []

    for a in soup.select("a[href*='/202']")[:source_cfg["max_articles"] * 3]:
        title = a.get_text(strip=True)
        href = a.get("href", "")
        if title and len(title) > 20 and "/topic/" not in href:
            if not href.startswith("http"):
                href = "https://www.technologyreview.com" + href
            articles.append({"title": title, "url": href, "source": source_cfg["name"]})
            if len(articles) >= source_cfg["max_articles"]:
                break

    if not articles:
        for article in soup.select("article")[:source_cfg["max_articles"]]:
            a = article.select_one("a")
            if a:
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if title and len(title) > 20:
                    if not href.startswith("http"):
                        href = "https://www.technologyreview.com" + href
                    articles.append({"title": title, "url": href, "source": source_cfg["name"]})

    return articles


def parse_ars(html, source_cfg):
    """解析 Ars Technica"""
    soup = BeautifulSoup(html, "html.parser")
    articles = []

    for a in soup.select("a[href*='/202']")[:source_cfg["max_articles"] * 3]:
        title = a.get_text(strip=True)
        href = a.get("href", "")
        if title and len(title) > 20:
            if not href.startswith("http"):
                href = "https://arstechnica.com" + href
            articles.append({"title": title, "url": href, "source": source_cfg["name"]})
            if len(articles) >= source_cfg["max_articles"]:
                break

    return articles


def parse_ieee(html, source_cfg):
    """解析 IEEE Spectrum"""
    soup = BeautifulSoup(html, "html.parser")
    articles = []

    for a in soup.select("a[href]")[:source_cfg["max_articles"] * 4]:
        title = a.get_text(strip=True)
        href = a.get("href", "")
        if title and len(title) > 25 and "/article/" in href:
            if not href.startswith("http"):
                href = "https://spectrum.ieee.org" + href
            articles.append({"title": title, "url": href, "source": source_cfg["name"]})
            if len(articles) >= source_cfg["max_articles"]:
                break

    return articles


def fetch_article_content(url, source_name):
    """抓取单篇文章的正文内容"""
    html = fetch_url(url)
    if not html:
        return {"content": "", "pub_time": ""}

    soup = BeautifulSoup(html, "html.parser")
    content = ""
    pub_time = ""

    # IEEE Spectrum
    if "ieee.org" in url:
        article = soup.select_one("div.article-content, div.post-content, main")
        if article:
            paragraphs = article.select("p")
            content = "\n".join(p.get_text(strip=True) for p in paragraphs[:15])
        time_tag = soup.select_one("time")
        if time_tag:
            pub_time = time_tag.get("datetime", "")

    # MIT Technology Review
    elif "technologyreview.com" in url:
        article = soup.select_one("div.article-content, main")
        if article:
            paragraphs = article.select("p")
            content = "\n".join(p.get_text(strip=True) for p in paragraphs[:15])
        time_tag = soup.select_one("time")
        if time_tag:
            pub_time = time_tag.get("datetime", "")

    # Ars Technica
    elif "arstechnica.com" in url:
        article = soup.select_one("div.article-content, section.post")
        if article:
            paragraphs = article.select("p")
            content = "\n".join(p.get_text(strip=True) for p in paragraphs[:15])

    # 通用备选
    if not content:
        paragraphs = soup.select("article p, .post-content p, main p")
        if paragraphs:
            content = "\n".join(p.get_text(strip=True) for p in list(paragraphs)[:12])

    summary = content[:800].strip() if content else ""

    return {"content": summary, "pub_time": pub_time}


def identify_companies(text):
    """从文本中识别涉及的龙头企业"""
    text_lower = text.lower()
    found = []
    for company, keywords in COMPANY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                found.append(company)
                break
    return list(dict.fromkeys(found))


def classify_news(text):
    """判断新闻所属板块"""
    text_lower = text.lower()
    tags = []
    for kw in SEMICONDUCTOR_KEYWORDS:
        if kw.lower() in text_lower:
            tags.append("半导体")
            break
    for kw in ROBOT_KEYWORDS:
        if kw.lower() in text_lower:
            tags.append("机器人")
            break
    if any(k in text_lower for k in ["ai", "artificial intelligence", "machine learning", "llm", "gpt", "model"]):
        tags.append("人工智能")
    return list(dict.fromkeys(tags))


# ============================================================
# AI 解读
# ============================================================

def generate_analysis(title, content, companies, tags):
    """生成新闻解读（中文输出）"""
    analysis = []

    if "人工智能" in tags:
        analysis.append("**AI 算力板块**：")
        if any(c in companies for c in ["NVIDIA", "AMD", "Intel"]):
            ai_companies = [c for c in companies if c in ["NVIDIA", "AMD", "Intel"]]
            analysis.append(f"  涉及核心算力厂商 {', '.join(ai_companies)}，关注 GPU/加速芯片供需及定价动态。")
        else:
            analysis.append("  关注大模型训练/推理需求变化，以及算力基础设施投资动向。")

    if "半导体" in tags:
        analysis.append("**半导体设备/制造板块**：")
        equipment = [c for c in companies if c in ["ASML", "Applied Materials", "Lam Research", "KLA Corporation", "NAURA", "AMEC"]]
        foundry = [c for c in companies if c in ["TSMC", "Samsung Electronics", "SMIC"]]
        if equipment:
            analysis.append(f"  涉及设备龙头 {', '.join(equipment)}，关注设备订单及出口管制政策。")
        if foundry:
            analysis.append(f"  涉及晶圆制造 {', '.join(foundry)}，关注产能利用率及资本开支指引。")
        if not equipment and not foundry:
            analysis.append("  关注半导体产业链整体景气度及库存周期变化。")

    if "机器人" in tags:
        analysis.append("**机器人板块**：")
        robot_companies = [c for c in companies if c in ["Tesla", "Boston Dynamics", "Figure AI", "UBTech", "ABB", "Fanuc", "Yaskawa"]]
        if robot_companies:
            analysis.append(f"  涉及人形/工业机器人厂商 {', '.join(robot_companies)}，关注量产进展及供应链机会。")
        else:
            analysis.append("  关注机器人产业链（减速器、伺服电机、传感器、AI 芯片）相关机会。")

    analysis.append("**投资参考**：")
    if companies:
        analysis.append(f"  直接关注标的：{', '.join(companies)}")
    analysis.append("  ⚠️ 以上为信息整理，不构成投资建议，请结合自身风险偏好谨慎决策。")

    return "\n".join(analysis)


# ============================================================
# 推送相关
# ============================================================

def send_pushplus(title, content, token):
    """通过 PushPlus 发送微信通知"""
    if not token:
        print("[PushPlus] Token 未配置，跳过推送")
        return False

    url = "http://www.pushplus.plus/send"
    data = {
        "token": token,
        "title": title,
        "content": content,
        "template": "markdown",
    }
    try:
        resp = requests.post(url, json=data, timeout=10)
        result = resp.json()
        if result.get("code") == 200:
            print("[PushPlus] 推送成功")
            return True
        else:
            print(f"[PushPlus] 推送失败：{result.get('msg')}")
            return False
    except Exception as e:
        print(f"[PushPlus] 推送异常：{e}")
        return False


# ============================================================
# 主流程
# ============================================================

def crawl_all_sources():
    """抓取所有数据源"""
    all_articles = []

    for source in SOURCES:
        print(f"[抓取] {source['name']} ...")
        html = fetch_url(source["url"])
        if not html:
            print(f"  [失败] {source['name']}")
            continue

        parser_map = {
            "mittr": parse_mittr,
            "ars": parse_ars,
            "ieee": parse_ieee,
        }
        parser = parser_map.get(source["type"], parse_mittr)
        articles = parser(html, source)

        print(f"  [成功] 找到 {len(articles)} 篇")
        all_articles.extend(articles)
        time.sleep(1)

    return all_articles


def process_articles(articles):
    """处理文章列表：抓取正文 + 翻译 + 提取信息"""
    results = []

    for i, article in enumerate(articles[:12]):
        print(f"\n[处理 {i+1}/{min(len(articles), 12)}] {article['title'][:60]}...")

        # 翻译标题
        print("  [翻译] 标题...")
        title_zh = translate_title(article["title"])
        print(f"  [中文] {title_zh}")

        # 抓取正文
        detail = fetch_article_content(article["url"], article["source"])

        # 翻译摘要
        summary_en = detail["content"]
        summary_zh = ""
        if summary_en:
            print("  [翻译] 摘要...")
            summary_zh = translate_summary(summary_en)

        combined_text = (article["title"] + " " + (summary_en or "")).lower()

        companies = identify_companies(combined_text)
        tags = classify_news(combined_text)
        analysis = generate_analysis(article["title"], combined_text, companies, tags)

        results.append({
            "title_en": article["title"],
            "title_zh": title_zh,
            "source": article["source"],
            "url": article["url"],
            "pub_time": detail["pub_time"],
            "summary_en": summary_en,
            "summary_zh": summary_zh,
            "companies": companies,
            "tags": tags,
            "analysis": analysis,
        })

        time.sleep(0.5)

    return results


def generate_markdown(results, date_str):
    """生成 Markdown 汇总报告（中文）"""
    lines = []
    lines.append(f"# AI & 半导体每日资讯汇总 · {date_str}")
    lines.append("")
    lines.append(f"> 自动生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"> 数据来源：MIT Technology Review、Ars Technica、IEEE Spectrum")
    lines.append(f"> 由 **龙猫** 自动抓取并解读（英文标题/内容已自动翻译为中文）")
    lines.append("")
    lines.append("---")
    lines.append("")

    for i, item in enumerate(results, 1):
        # 优先显示中文标题，附英文原标题
        lines.append(f"## {i}. {item['title_zh']}")
        lines.append("")
        if item["title_en"] != item["title_zh"]:
            lines.append(f"*（原标题：{item['title_en']}）*")
            lines.append("")
        lines.append(f"**来源**：{item['source']}  ")
        if item["pub_time"]:
            lines.append(f"**发布时间**：{item['pub_time']}  ")
        lines.append(f"**原文链接**：[{item['url']}]({item['url']})")
        lines.append("")

        if item["companies"]:
            lines.append(f"**涉及企业**：{'、'.join(item['companies'])}")
            lines.append("")

        if item["tags"]:
            lines.append(f"**所属板块**：{' / '.join(item['tags'])}")
            lines.append("")

        if item["summary_zh"]:
            lines.append("### 摘要（中文）")
            lines.append("")
            lines.append(item["summary_zh"])
            lines.append("")

        if item["summary_en"] and item["summary_en"] != item["summary_zh"]:
            lines.append("### 原文摘要（英文）")
            lines.append("")
            lines.append(item["summary_en"])
            lines.append("")

        lines.append("### 龙猫解读")
        lines.append("")
        lines.append(item["analysis"])
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(f"> 📌 本日报由龙猫自动生成，数据来源于公开新闻渠道，仅供参考。")
    return "\n".join(lines)


def generate_push_content(results, date_str):
    """生成推送到微信的精简内容（Markdown 格式，中文）"""
    lines = []
    lines.append(f"## 📰 AI & 半导体日报 · {date_str}")
    lines.append("")
    lines.append(f"今日共抓取 **{len(results)}** 条资讯，以下为摘要：")
    lines.append("")

    for i, item in enumerate(results[:8], 1):
        lines.append(f"**{i}. {item['title_zh']}**")
        if item["companies"]:
            lines.append(f"> 🏢 涉及：{'、'.join(item['companies'])}")
        if item["tags"]:
            lines.append(f"> 📊 板块：{' / '.join(item['tags'])}")
        if item["summary_zh"]:
            summary = item["summary_zh"][:150]
            lines.append(f"> {summary}...")
        lines.append(f"[查看原文]({item['url']})")
        lines.append("")

    lines.append("---")
    lines.append(f"[📄 查看完整报告](https://github.com/chengzheng123456/ai-semiconductor/blob/main/news/{date_str}.md)")
    lines.append(f"\n> 由 **龙猫** 自动推送")

    return "\n".join(lines)


def push_to_github(content, date_str, github_token):
    """将报告推送到 GitHub 仓库"""
    if not github_token:
        print("  [GitHub] Token 未配置，跳过推送")
        return False

    try:
        api_url = f"https://api.github.com/repos/chengzheng123456/ai-semiconductor/contents/news/{date_str}.md"
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        # 检查文件是否已存在
        req = urllib.request.Request(api_url, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            existing = json.loads(resp.read())
            sha = existing.get("sha")
        except:
            sha = None

        data = {
            "message": f"Auto: add news report {date_str}",
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": "main",
        }
        if sha:
            data["sha"] = sha

        req = urllib.request.Request(
            api_url,
            data=json.dumps(data).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="PUT",
        )

        resp = urllib.request.urlopen(req, timeout=15)
        if resp.status in (200, 201):
            print(f"  [GitHub] 推送成功：news/{date_str}.md")
            return True
        else:
            print(f"  [GitHub] 推送失败：HTTP {resp.status}")
            return False

    except Exception as e:
        print(f"  [GitHub] 推送异常：{e}")
        return False


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    pushplus_token = os.environ.get("PUSHPLUS_TOKEN", "")
    github_token = os.environ.get("GITHUB_TOKEN", "")

    import sys
    if len(sys.argv) > 1:
        pushplus_token = sys.argv[1]
    if len(sys.argv) > 2:
        github_token = sys.argv[2]

    print(f"=== AI & 半导体新闻爬虫 [{today}] ===\n")
    print(f"[配置] PushPlus: {'已配置' if pushplus_token else '未配置'}")
    print(f"[配置] GitHub Token: {'已配置' if github_token else '未配置'}")
    print()

    # Step 1: 抓取链接
    articles = crawl_all_sources()
    print(f"\n总计找到 {len(articles)} 篇文章\n")

    if not articles:
        print("[警告] 未抓取到任何文章，请检查网络连接或数据源配置")
        return None, []

    # Step 2: 处理文章（翻译 + 提取信息）
    print("=" * 60)
    print("开始处理文章（含翻译）...")
    print("=" * 60)
    results = process_articles(articles)

    # Step 3: 生成 Markdown
    md_content = generate_markdown(results, today)

    # 保存本地
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{today}.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"\n[完成] 报告已生成：{output_path}")
    print(f"[完成] 共处理 {len(results)} 篇文章")

    # Step 4: 推送到 GitHub
    if github_token:
        print("\n[GitHub] 正在推送到仓库...")
        push_to_github(md_content, today, github_token)
    else:
        print("\n[GitHub] Token 未配置，跳过推送（可手动上传）")

    # Step 5: 推送到微信
    if pushplus_token:
        print("\n[PushPlus] 正在推送到微信...")
        push_content = generate_push_content(results, today)
        send_pushplus(
            title=f"AI & 半导体日报 · {today}",
            content=push_content,
            token=pushplus_token,
        )
    else:
        print("\n[PushPlus] Token 未配置，跳过微信推送")

    return output_path, results


if __name__ == "__main__":
    main()
