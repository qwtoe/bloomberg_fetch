# Bloomberg News Monitor

一个定时抓取彭博社（Bloomberg）实时新闻，并通过 Telegram Bot 推送中文翻译标题的小工具。

## 功能

- **定时轮询**：每 30 分钟查询一次 Google News RSS
- **时间过滤**：只推送过去 4 小时内发布的新闻，避免旧闻干扰
- **冷启动保护**：首次运行时仅推送最近 1 小时的新闻，防止首次启动时大量推送
- **中文翻译**：使用 DeepSeek LLM 将英文标题翻译为中文
- **Telegram 推送**：通过 Bot 将翻译后的标题、原文、发布时间、链接推送到你的 TG
- **缓存去重**：本地缓存已推送的新闻 ID，重启后不重复推送

## 安装

```bash
# 克隆仓库
git clone git@github.com:qwtoe/bloomberg_fetch.git
cd bloomberg_fetch

# 安装依赖
pip install feedparser requests
```

## 配置

1. 复制模板配置文件：
```bash
cp config.example.json config.json
```

2. 编辑 `config.json`，填入你的密钥：

```json
{
    "telegram": {
        "bot_token": "YOUR_TG_BOT_TOKEN",
        "chat_id": "YOUR_CHAT_ID"
    },
    "deepseek": {
        "api_key": "YOUR_DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com"
    },
    "monitor": {
        "poll_interval_seconds": 1800,
        "recent_hours": 4
    }
}
```

### 获取密钥

- **Telegram Bot Token**：在 [@BotFather](https://t.me/BotFather) 创建机器人获取
- **Telegram Chat ID**：发送消息给 [@userinfobot](https://t.me/userinfobot) 获取你的 ID
- **DeepSeek API Key**：在 [platform.deepseek.com](https://platform.deepseek.com) 注册获取

## 运行

```bash
python3 monitor_bloomberg.py
```

后台运行（推荐）：
```bash
nohup python3 -u monitor_bloomberg.py > monitor.log 2>&1 &
```

查看日志：
```bash
tail -f monitor.log
```

停止：
```bash
ps aux | grep monitor_bloomberg
kill <PID>
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `monitor_bloomberg.py` | 主脚本 |
| `config.json` | 配置文件（含密钥，**不要提交到 git**） |
| `config.example.json` | 配置模板 |
| `pushed_news_ids.txt` | 已推送新闻 ID 缓存（自动生成） |
| `monitor.log` | 运行日志 |

## License

[MIT](LICENSE)
