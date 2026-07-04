"""Director CLI — 独立启动"""
import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from src.agents.director_agent.agent import DirectorAgent

p = argparse.ArgumentParser(description="🎬 Director — 小说→剧本改编")
p.add_argument("--project", "-p", required=True, help="项目ID")
p.add_argument("--sections", "-s", nargs="*", type=int, help="指定章节ID（默认全部未改编）")
args = p.parse_args()

agent = DirectorAgent(args.project)
count = agent.adapt(args.sections)
print(f"\n✅ 完成: {count} 个场景")
agent.close()
