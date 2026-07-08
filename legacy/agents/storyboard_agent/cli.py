"""Storyboard CLI""" 
import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from src.agents.storyboard_agent.agent import StoryboardAgent

p = argparse.ArgumentParser(description="🎨 Storyboard — 场景→分镜图")
p.add_argument("--project", "-p", required=True)
p.add_argument("--real", action="store_true", help="使用真实API(默认Mock)")
args = p.parse_args()

agent = StoryboardAgent(args.project)
count = agent.generate(use_mock=not args.real)
print(f"\n✅ 完成: {count} 个分镜")
agent.close()
