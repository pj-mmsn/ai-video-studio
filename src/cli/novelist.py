"""
小说家独立 CLI — 交互式写作工具
============================================================
启动: python -m src.cli.novelist

交互式协作写作:
  你: 写一个都市修仙小说，主角是996程序员
  AI: [构思框架、大纲、角色]
  你: 第一章写得不错，但主角性格再痞一点
  AI: [重写第一章]
  你: /continue
  AI: [写第二章]
  ...
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from src.agents.novelist import NovelistAgent, Novel

# 简洁的 Rich 风格命令行
try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.prompt import Prompt
    console = Console()
    USE_RICH = True
except ImportError:
    USE_RICH = False
    console = None


class NovelistCLI:
    """小说家命令行界面"""

    def __init__(self):
        self.agent = NovelistAgent()
        self.running = True

    def run(self):
        self._print_banner()

        # 第一步：初始化
        idea = self._input("💡 想写什么故事？")
        genre = self._input("📚 什么类型？(玄幻/科幻/都市/悬疑/言情/历史)", default="玄幻")

        self.agent.init_novel(idea, genre)

        # 第二步：交互循环
        print("\n📝 输入 /write 开始写第一章，/help 查看所有命令\n")

        while self.running:
            user_input = self._input("✏️").strip()
            if not user_input:
                continue
            self._dispatch(user_input)

    def _dispatch(self, cmd: str):
        """命令分发"""
        if cmd == "/quit" or cmd == "/q":
            self.agent.save()
            self._print("👋 已保存，再见！")
            self.running = False

        elif cmd == "/help":
            self._print("""
可用命令:
  /write            - 开始/继续写当前章节
  /rewrite          - 重写当前章节
  /continue         - 继续下一章
  /revise <意见>    - 根据意见修改当前章节
  /outline          - 查看/修改大纲
  /characters       - 查看角色设定
  /summary          - 查看故事概要
  /status           - 查看进度
  /save             - 保存到文件
  /quit             - 保存并退出
直接输入文字  - 给 AI 提供反馈或指令""")

        elif cmd == "/write":
            ch = self.agent.write_chapter()
            self._print_chapter(ch)

        elif cmd == "/rewrite":
            feedback = self._input("💬 重写意见（直接回车=换一种写法）")
            ch = self.agent.rewrite_chapter(feedback or "换一种写法")
            self._print_chapter(ch)

        elif cmd == "/continue":
            ch = self.agent.write_chapter()
            self._print_chapter(ch)

        elif cmd.startswith("/revise"):
            instruction = cmd[len("/revise "):].strip()
            if not instruction:
                instruction = self._input("💬 修改意见")
            result = self.agent.revise_content(instruction)
            self._print(result)

        elif cmd == "/outline":
            self._print_outline()

        elif cmd == "/characters":
            self._print_characters()

        elif cmd == "/summary":
            self._print(self.agent.get_status())

        elif cmd == "/save":
            self.agent.save()

        elif cmd == "/status":
            self._print(self.agent.get_status())

        else:
            # 当作反馈意见：修改当前章节
            if self.agent.novel and self.agent.novel.chapters:
                self._print(f"🔧 按你的意见修改...")
                result = self.agent.revise_content(cmd)
                self._print(result[:500] + "...")
            else:
                self._print("还没有内容可修改，先 /write 写第一章吧")

    # ---------------------------------------------------------------
    # UI helpers
    # ---------------------------------------------------------------

    def _print_banner(self):
        print("=" * 50)
        print("  📖 AI 小说家 — 交互式协作写作")
        print("  输入 /help 查看命令")
        print("=" * 50)

    def _print_chapter(self, ch):
        print(f"\n{'─'*50}")
        print(f"📖 第{ch.number}章 {ch.title}")
        print(f"{'─'*50}")
        print(ch.content)
        if ch.summary:
            print(f"\n📝 {ch.summary}")
        if ch.next_hint:
            print(f"🔮 {ch.next_hint}")
        print(f"{'─'*50}")
        print("输入 /continue 继续 | /rewrite 重写 | 或直接输入反馈意见\n")

    def _print_outline(self):
        if not self.agent.novel:
            return
        print(f"\n📋 《{self.agent.novel.title}》大纲")
        for i, o in enumerate(self.agent.novel.outline, 1):
            done = "✅" if i <= len(self.agent.novel.chapters) else "⬜"
            print(f"  {done} 第{i}章: {o}")
        print()

    def _print_characters(self):
        if not self.agent.novel:
            return
        print(f"\n👥 《{self.agent.novel.title}》角色")
        for c in self.agent.novel.characters:
            print(f"  {c.name}({c.role}): {c.description}")
        print()

    def _input(self, prompt_text, default=""):
        if USE_RICH:
            return Prompt.ask(prompt_text, default=default)
        val = input(f"{prompt_text} ").strip()
        return val if val else default

    def _print(self, text):
        if USE_RICH:
            console.print(text)
        else:
            print(text)


def main():
    cli = NovelistCLI()
    try:
        cli.run()
    except KeyboardInterrupt:
        if cli.agent.novel:
            cli.agent.save()
        print("\n👋 已保存，再见！")


if __name__ == "__main__":
    main()
