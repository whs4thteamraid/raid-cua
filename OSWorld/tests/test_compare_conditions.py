# -*- coding: utf-8 -*-
"""조건 비교기 회귀 테스트 — VM·과금 없이 돈다.

★ 왜 이 테스트가 필요한가 (실측 사고)
  처음 구현한 same() 은 None 을 '비교 대상 아님'으로 걸러냈다. 그러면 top_p 가
  (None, None, 0.95) 일 때 비교할 값이 하나만 남아 **'같다'로 통과**해버린다.
  실제로 Kimi 만 top_p 가 걸려 있는데 시연에서 ✓ 가 찍혔다.
  여기서 None 은 '값 없음'이 아니라 **'안 보냄'이라는 조건**이다.
"""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    p = ROOT / "redteam" / "compare_conditions.py"
    spec = importlib.util.spec_from_file_location("compare_conditions", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cc = _load()


class TestSame(unittest.TestCase):
    def test_none_is_a_condition_not_a_gap(self):
        # 'Kimi 만 top_p 가 걸린다' 를 놓치면 안 된다
        self.assertFalse(cc.same([None, None, 0.95], "top_p"))
        self.assertTrue(cc.same([None, None, None], "top_p"))

    def test_int_float_equal(self):
        self.assertTrue(cc.same([1, 1.0, 1], "temperature"))

    def test_not_sent_differs_from_sent(self):
        # Haiku 는 temperature 를 안 보내고 나머지는 보낸다 → 다른 조건
        self.assertFalse(cc.same([None, 1.0, 1], "temperature"))

    def test_bool_not_collapsed_into_int(self):
        # isinstance(True, int) 가 True 라서 순서를 잘못 두면 False 와 0 이 뭉개진다
        self.assertFalse(cc.same([False, False, 0], "thinking"))
        self.assertFalse(cc.same([False, None, True], "thinking"))

    def test_lists_compared_elementwise(self):
        self.assertFalse(cc.same([[1280, 720], [1920, 1080], [1920, 1080]], "image_sent_wh"))
        self.assertTrue(cc.same([[1920, 1080]] * 3, "image_sent_wh"))

    def test_measured_tolerance(self):
        self.assertTrue(cc.same([1.0, 1.05, 1.1], "measured.calls_per_step"))
        self.assertFalse(cc.same([1.0, 1.68, 1.3], "measured.calls_per_step"))

    def test_aligned_axis_passes(self):
        self.assertTrue(cc.same([6, 6, 6], "history_steps"))


class TestAxisLists(unittest.TestCase):
    def test_axis_lists_disjoint(self):
        """같아야 할 축과 못 맞추는 축이 겹치면 판정이 모순된다."""
        self.assertFalse(set(cc.MUST_MATCH) & set(cc.STRUCTURAL_RESIDUE))

    def test_no_axis_appears_twice(self):
        """세 목록은 **분할**이어야 한다 — 중복도 교집합도 없어야 한다.

        ★ 실측: INFO 에 measured.gui_calls_per_step 이 두 번 들어 있어 참고 표에
          같은 줄이 두 번 찍혔다. known_axes() 는 set 이라 조용히 넘어갔고, 표를
          읽는 사람에게는 서로 다른 축 둘로 보였다. 목록이 '닫힌 분할' 이라는 것이
          비교기 주장('이것 말고는 같다')의 근거이므로 여기서 못 박는다.
        """
        for name in ("MUST_MATCH", "STRUCTURAL_RESIDUE", "INFO"):
            axes = getattr(cc, name)
            dups = sorted({a for a in axes if axes.count(a) > 1})
            self.assertEqual(dups, [], f"{name} 에 중복된 축: {dups}")
        pairs = (("MUST_MATCH", "STRUCTURAL_RESIDUE"), ("MUST_MATCH", "INFO"),
                 ("STRUCTURAL_RESIDUE", "INFO"))
        for a, b in pairs:
            overlap = sorted(set(getattr(cc, a)) & set(getattr(cc, b)))
            self.assertEqual(overlap, [], f"{a} 와 {b} 가 겹친다: {overlap}")

    def test_known_axes_cover_adapter_output(self):
        """어댑터가 내놓는 조건 키가 두 목록 중 하나에 들어 있어야 한다.

        ★ 목록이 닫혀 있어야 '이것 말고는 같다' 가 성립한다. 새 조건을 어댑터에
          추가하고 목록에 안 넣으면 비교기가 그 축을 통째로 못 보고 지나간다.
        """
        import sys
        sys.path.insert(0, str(ROOT))
        try:
            from mm_agents.adapters.agents import claude_conditions
        except ImportError as exc:
            # 어댑터 임포트는 anthropic 등 벤더 SDK 를 끌고 온다. 의존성이 없는
            # 환경(예: 맨 파이썬)에서는 이 검사만 건너뛰고 나머지는 그대로 돈다.
            self.skipTest(f"어댑터 임포트 불가: {exc}")

        class _Fake:                      # 속성 없는 객체 → getattr 기본값 경로
            pass

        produced = set(claude_conditions(_Fake()))
        known = cc.known_axes()   # ★ 비교기와 **같은** 정의 (두 벌로 갈리면 어긋난다)
        missing = produced - known
        self.assertFalse(missing, f"비교기 목록에 없는 조건 축: {sorted(missing)}")


if __name__ == "__main__":
    unittest.main()
