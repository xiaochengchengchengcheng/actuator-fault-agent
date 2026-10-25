import argparse
import json
from uuid import uuid4

from langgraph.types import Command

from actuator_fault_agent.graph.builder import graph


def run_demo() -> None:
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    request = {
        "thread_id": thread_id,
        "question": "EOL 测试时输出扭矩偏低、振动升高，请给出排查顺序",
        "actuator_id": "RA-2407-018",
        "station": "EOL-02",
        "product_model": "RA-60",
        "fault_code": "EOL-TQ-LOW",
        "require_human_review": False,
    }
    result = graph.invoke(request, config=config)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    if result.get("__interrupt__"):
        print("\n演示自动提交人工复核批准。\n")
        result = graph.invoke(
            Command(
                resume={
                    "approved": True,
                    "reviewer": "demo-quality-engineer",
                    "note": "仅用于软件演示",
                }
            ),
            config=config,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Actuator production fault diagnosis agent")
    parser.add_argument("command", choices=["demo"], nargs="?", default="demo")
    parser.parse_args()
    run_demo()


if __name__ == "__main__":
    main()
