import json
import feedparser
import requests
import time
import os
import datetime
import email.utils

# ==================== 加载配置 ====================

def load_config(path="config.json"):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"配置文件不存在: {path}\n"
            f"请复制 config.example.json 为 config.json 并填入你的密钥。"
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

CONFIG = load_config()

# ==================== 配置区域 ====================

# RSS 配置（when:12h 从源头过滤过去 12 小时的新闻，减少旧闻混入）
RSS_URL = "https://news.google.com/rss/search?q=site:bloomberg.com+when:12h&hl=en-US&gl=US&ceid=US:en"
RSS_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# 时间阈值：只推送过去 N 小时内发布的新闻（单位：小时）
RECENT_HOURS = CONFIG["monitor"]["recent_hours"]

# Telegram 配置
TG_BOT_TOKEN = CONFIG["telegram"]["bot_token"]
TG_CHAT_ID = CONFIG["telegram"]["chat_id"]

# DeepSeek 配置
DEEPSEEK_API_KEY = CONFIG["deepseek"]["api_key"]
DEEPSEEK_MODEL = CONFIG["deepseek"]["model"]
DEEPSEEK_BASE_URL = CONFIG["deepseek"]["base_url"]

# 本地缓存（每行一个已推送的新闻 ID）
CACHE_FILE = "pushed_news_ids.txt"

# 轮询间隔（秒）
POLL_INTERVAL = CONFIG["monitor"]["poll_interval_seconds"]

# ==================== 功能函数 ====================

def load_pushed_ids():
    """加载已推送的新闻 ID 集合"""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_pushed_ids(pushed_ids):
    """保存已推送的新闻 ID 集合到文件"""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        for news_id in sorted(pushed_ids):
            f.write(news_id + "\n")

def fetch_feed():
    """使用 requests 获取 RSS 内容，再交给 feedparser 解析（避免默认 urllib 被拦截）"""
    resp = requests.get(RSS_URL, headers=RSS_HEADERS, timeout=15)
    resp.raise_for_status()
    return feedparser.parse(resp.text)

def send_telegram(text):
    """发送消息到 Telegram"""
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        print("  → Telegram 消息发送成功")
    except Exception as e:
        print(f"  → Telegram 发送失败: {e}")

def verify_deepseek():
    """每次调用前验证 DeepSeek 模型连通性"""
    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            err_msg = data["error"].get("message", str(data["error"]))
            print(f"DeepSeek 验证失败: {err_msg}")
            return False
        print("DeepSeek 连通性验证通过")
        return True
    except Exception as e:
        print(f"DeepSeek 验证异常: {e}")
        return False

def translate_title(title):
    """使用 DeepSeek LLM 翻译标题为中文"""
    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a professional news translator. Translate the following English news headline into concise, natural Chinese. Only return the translated text without any explanations, quotes, or markdown."
            },
            {
                "role": "user",
                "content": title
            }
        ],
        "max_tokens": 1024,
        "temperature": 0.3
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            err_msg = data["error"].get("message", str(data["error"]))
            print(f"DeepSeek 翻译失败: {err_msg}")
            return f"{title} (翻译失败)"

        translated = data["choices"][0]["message"]["content"].strip()
        translated = translated.strip('"').strip("'")
        return translated
    except Exception as e:
        print(f"DeepSeek 翻译异常: {e}")
        return f"{title} (翻译失败)"

def is_recent(entry, hours=RECENT_HOURS):
    """判断新闻发布时间是否在指定小时数内"""
    try:
        dt_utc = email.utils.parsedate_to_datetime(entry.published)
        age = datetime.datetime.now(datetime.timezone.utc) - dt_utc
        return age <= datetime.timedelta(hours=hours)
    except Exception:
        # 解析失败时，保守处理：视为旧闻
        return False

def push_entry(entry, translate=True):
    """处理并推送单条新闻"""
    title_en = entry.title.replace(" - Bloomberg.com", "")
    link = entry.link
    pub_date = entry.published

    # 转换为北京时间
    try:
        dt_utc = email.utils.parsedate_to_datetime(pub_date)
        dt_bj = dt_utc + datetime.timedelta(hours=8)
        pub_date_bj = dt_bj.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pub_date_bj = pub_date

    print(f"\n检测到新新闻: {title_en}")

    # 翻译标题（如果 DeepSeek 可用）
    if translate:
        title_zh = translate_title(title_en)
    else:
        title_zh = f"{title_en} (翻译服务不可用)"

    message = (
        f"<b>中文标题:</b> {title_zh}\n"
        f"<b>英文原文:</b> {title_en}\n"
        f"<b>发布时间:</b> {pub_date} (北京时间: {pub_date_bj})\n"
        f"<b>链接:</b> {link}"
    )

    send_telegram(message)
    print(f"  已推送: {title_zh}")

# ==================== 主程序 ====================

def cleanup_old_files():
    """清理旧的/无用的文件"""
    # 删除旧的单条缓存（已废弃，现在使用 pushed_news_ids.txt）
    old_cache = "last_news_id.txt"
    if os.path.exists(old_cache):
        os.remove(old_cache)
        print(f"已清理旧缓存: {old_cache}")

    # 删除旧的日志文件（彻底清理，避免二进制残留或空字节污染）
    log_file = "monitor.log"
    if os.path.exists(log_file):
        os.remove(log_file)
        print(f"已删除旧日志: {log_file}")

def monitor_bloomberg():
    cleanup_old_files()
    print("开始监控彭博社实时新闻（每 30 分钟轮询一次）...")
    pushed_ids = load_pushed_ids()

    while True:
        try:
            feed = fetch_feed()

            if not feed.entries:
                print("暂未抓取到内容，等待重试...")
                time.sleep(POLL_INTERVAL)
                continue

            # 收集本轮未推送过的新闻（按 RSS 顺序，从旧到新）
            new_entries = []
            for entry in feed.entries:
                if entry.id not in pushed_ids:
                    new_entries.append(entry)

            if not new_entries:
                print(f"[{time.strftime('%H:%M:%S')}] 暂无更新...")
            else:
                print(f"\n本轮发现 {len(new_entries)} 条缓存中未记录的新闻")

                # 每轮只验证一次 DeepSeek 连通性，避免多条新闻时重复请求
                ds_available = verify_deepseek()

                pushed_count = 0
                skipped_count = 0
                for entry in reversed(new_entries):  # 从旧到新处理，保证顺序
                    pushed_ids.add(entry.id)
                    if is_recent(entry):
                        push_entry(entry, translate=ds_available)
                        pushed_count += 1
                        # 避免 Telegram 频率限制，每条消息间隔 1 秒
                        time.sleep(1)
                    else:
                        print(f"  跳过旧闻（>{RECENT_HOURS}h）: {entry.title.replace(' - Bloomberg.com', '')}")
                        skipped_count += 1
                    # 每次处理后保存，防止中断导致重复推送/处理
                    save_pushed_ids(pushed_ids)
                print(f"\n本轮处理完成: 推送 {pushed_count} 条, 跳过旧闻 {skipped_count} 条")

        except Exception as e:
            print(f"主循环发生错误: {e}")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    monitor_bloomberg()
