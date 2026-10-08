#!/usr/bin/env python3
"""删除在中国服务器环境下用不到的 OpenClaw skills"""

import os
import shutil

SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openclaw", "skills")

# 因网络封锁(GFW)、macOS桌面依赖、硬件/局域网限制、地区服务不可用
SKILLS_TO_DELETE = [
    # === 已删除的（首批）===
    # GFW 封锁 (14)
    "xurl",
    "spotify-player",
    "goplaces",
    "nano-banana-pro",
    "openai-image-gen",
    "openai-whisper-api",
    "notion",
    "blogwatcher",
    "bluebubbles",
    "clawhub",
    # macOS 桌面环境依赖 (8)
    "apple-notes",
    "apple-reminders",
    "bear-notes",
    "things-mac",
    "imsg",
    "peekaboo",
    "voice-call",
    "model-usage",
    # 硬件/局域网限制 (5)
    "camsnap",
    "openhue",
    "eightctl",
    "sonoscli",
    "blucli",
    # 地区服务不可用 (1)
    "ordercli",

    # === 第二批清理：医学AI平台无关或中国环境不可用 ===
    # GFW 封锁的服务
    "gemini",           # Google Gemini API，GFW封锁
    "gog",              # Google Workspace (Gmail/Calendar/Drive)，GFW封锁
    "discord",          # Discord 部分被封锁，且与医学无关
    # 与医学AI平台无关
    "gifgrep",          # GIF搜索，与医学无关
    "weather",          # 天气预报，与医学无关
    "songsee",          # 音频频谱可视化，与医学无关
    "trello",           # 项目管理工具，非医学用途
    "wacli",            # WhatsApp，在中国不常用
    "sag",              # ElevenLabs付费云TTS，国内不稳定
    # 桌面/移动端依赖，Docker中不可用
    "1password",        # 需要桌面端1Password
    "canvas",           # 需要OpenClaw移动端companion app
    "node-connect",     # 需要移动端/桌面端节点配对
    "obsidian",         # 需要Obsidian桌面端
    # 仅开发工具，运行时不需要
    "tmux",             # 终端复用，Docker中不需要
    "himalaya",         # CLI邮件客户端，非核心功能
    "summarize",        # 依赖被封锁的外部API (Google等)
    "video-frames",     # 视频帧提取，非核心医学功能
]


def main():
    # 统计当前 skills
    all_skills = [
        d for d in os.listdir(SKILLS_DIR)
        if os.path.isdir(os.path.join(SKILLS_DIR, d)) and not d.startswith(".")
    ]
    print(f"当前共有 {len(all_skills)} 个 skills")

    # 确认要删除的
    existing = [s for s in SKILLS_TO_DELETE if s in all_skills]
    missing = [s for s in SKILLS_TO_DELETE if s not in all_skills]
    if missing:
        print(f"以下 {len(missing)} 个 skill 未找到，跳过: {', '.join(missing)}")

    print(f"即将删除 {len(existing)} 个 skills: {', '.join(existing)}")
    print()

    # 执行删除
    deleted = 0
    for skill in existing:
        path = os.path.join(SKILLS_DIR, skill)
        try:
            shutil.rmtree(path)
            print(f"  ✓ 已删除 {skill}")
            deleted += 1
        except Exception as e:
            print(f"  ✗ 删除 {skill} 失败: {e}")

    # 统计剩余
    remaining = [
        d for d in os.listdir(SKILLS_DIR)
        if os.path.isdir(os.path.join(SKILLS_DIR, d)) and not d.startswith(".")
    ]
    print()
    print(f"删除完成: 成功删除 {deleted} 个, 剩余 {len(remaining)} 个 skills")


if __name__ == "__main__":
    main()
