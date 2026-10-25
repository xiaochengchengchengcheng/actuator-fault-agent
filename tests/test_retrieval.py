import tempfile
import unittest
from pathlib import Path

from actuator_fault_agent.retrieval.knowledge_base import LocalKnowledgeBase


class RetrievalTest(unittest.TestCase):
    def test_returns_relevant_section_with_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual.md"
            path.write_text(
                "# 测试手册\n\n## 扭矩异常\n输出扭矩不足时检查传感器标定和减速机构。\n\n"
                "## 温升异常\n温升异常时检查电流和摩擦。\n",
                encoding="utf-8",
            )
            kb = LocalKnowledgeBase(Path(directory))
            results = kb.search("输出扭矩低 标定", top_k=1)
            self.assertEqual(len(results), 1)
            self.assertIn("扭矩", results[0].title)
            self.assertEqual(results[0].source, "manual.md")
            self.assertGreater(results[0].score, 0)


if __name__ == "__main__":
    unittest.main()
