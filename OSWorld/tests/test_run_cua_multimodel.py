# -*- coding: utf-8 -*-
"""run_cua 다모델 확장 오프라인 검증 — VM·모델·API 호출 없음.

확인하는 것
  1. Luna/Kimi 에서 bash·memory·approval 이 **emulated 로 표시**되는가
     (summary/출력에 이게 없으면 나중에 Claude 결과와 조건을 못 가른다)
  2. 지원하지 않는 조합(mcp / editor / popup / faithful)이 **VM 을 띄우기 전에** 거부되는가
     (조용히 다른 조건으로 도는 것이 제일 위험하다)
  3. claude 경로는 예전 그대로 전부 native 인가
"""
import io
import unittest
from unittest import mock

from redteam import run_cua as runner


def config_check(argv):
    """VM·에이전트가 절대 생성되지 않는 상태로 --config-check-only 를 돌린다."""
    out = io.StringIO()
    with (
        mock.patch.object(runner, "DesktopEnv",
                          side_effect=AssertionError("VM must not start")),
        mock.patch.object(runner, "SystemPromptMCPMemoryClaudeCUAAgent",
                          side_effect=AssertionError("agent must not start")),
        mock.patch.object(runner, "build_agent",
                          side_effect=AssertionError("adapter must not start")),
        mock.patch("sys.stdout", out),
    ):
        runner.main(argv + ["--config-check-only"])
    return out.getvalue()


BASE = ["--instruction", "offline"]


class TestEmulatedToolsAreVisible(unittest.TestCase):
    def test_luna_marks_bash_and_memory_emulated(self):
        text = config_check(BASE + ["--model", "luna", "--tools", "computer,bash",
                                    "--memory", "--read-mode", "controlled"])
        self.assertIn("Model: gpt-5.6-luna", text)
        self.assertIn("Agent: PromptAgent(text)", text)
        self.assertIn("computer(native)", text)
        self.assertIn("bash(emulated)", text)
        self.assertIn("memory(emulated)", text)
        self.assertIn("Emulated", text)
        self.assertIn("CONFIG_CHECK_READY", text)

    def test_kimi_approval_is_emulated(self):
        text = config_check(BASE + ["--model", "kimi", "--tools", "computer,bash",
                                    "--approval-mode", "interactive"])
        self.assertIn("Model: kimi-k2.6", text)
        self.assertIn("Agent: KimiAgent(text)", text)
        self.assertIn("bash(emulated)", text)

    def test_claude_stays_all_native(self):
        text = config_check(BASE + ["--model", "haiku",
                                    "--tools", "computer,bash,editor",
                                    "--memory", "--read-mode", "faithful"])
        self.assertIn("Model: claude-haiku-4-5", text)
        self.assertIn("bash(native)", text)
        self.assertIn("editor(native)", text)
        self.assertIn("memory(native)", text)
        self.assertNotIn("Emulated", text)

    def test_model_alias_works(self):
        self.assertIn("Model: claude-haiku-4-5",
                      config_check(BASE + ["--model", "claude-haiku-4-5"]))
        self.assertIn("Model: gpt-5.6-luna",
                      config_check(BASE + ["--model", "gpt-5.6-luna"]))


class TestUnsupportedCombosRefusedBeforeVM(unittest.TestCase):
    def _refused(self, argv, must_mention):
        with self.assertRaises(SystemExit) as ctx:
            config_check(argv)
        message = str(ctx.exception)
        self.assertIn(must_mention, message)
        return message

    def test_luna_refuses_mcp(self):
        self._refused(BASE + ["--model", "luna", "--tools", "computer,mcp"], "mcp")

    def test_luna_refuses_editor(self):
        self._refused(BASE + ["--model", "luna", "--tools", "computer,editor"], "editor")

    def test_luna_refuses_popup(self):
        self._refused(BASE + ["--model", "luna", "--inject-popup"], "popup")

    def test_luna_refuses_faithful_arm(self):
        self._refused(BASE + ["--model", "luna", "--memory", "--read-mode", "faithful"],
                      "faithful")

    def test_kimi_refuses_mcp(self):
        self._refused(BASE + ["--model", "kimi", "--tools", "computer,mcp"], "mcp")

    def test_unknown_model_is_refused(self):
        self._refused(BASE + ["--model", "gpt-4o"], "gpt-4o")

    def test_luna_without_memory_flag_ignores_read_mode_default(self):
        # --memory 없이 --read-mode 기본값(faithful)이 남아 있어도 거부되면 안 된다.
        text = config_check(BASE + ["--model", "luna", "--tools", "computer,bash"])
        self.assertIn("CONFIG_CHECK_READY", text)


class _FakeEnv:
    """DesktopEnv 의 되돌림 규칙만 흉내낸 가짜 — 플래그가 켜져 있을 때만 되돌린다."""

    def __init__(self, **kw):
        self.snapshot_name = kw.get("snapshot_name")
        self.is_environment_used = False
        self.reverted = []
        self.configs = []

    def reset(self, task_config=None):
        if self.is_environment_used:
            self.reverted.append(self.snapshot_name)
            self.is_environment_used = False
        self.configs.append(task_config)

    def _get_obs(self):
        return {"screenshot": b""}

    def close(self):
        pass


def _session(**kw):
    with mock.patch.object(runner, "DesktopEnv", _FakeEnv):
        return runner.Session(model="kimi", vmx="x", check_api_key=False,
                              tools=("computer", "bash"), memory=True,
                              memory_arm="controlled", initial_wait=0,
                              verbose=False, **kw)


class TestRestoreIsUnconditional(unittest.TestCase):
    """restore 를 명시하면 **반드시** 되돌아가야 한다.

    ★ 왜 테스트로 못박는가 — DesktopEnv.reset() 은 is_environment_used 가 True 일 때만
      스냅샷을 되돌린다. 그 플래그는 env.step() 과 config 셋업에서만 켜지므로, 에뮬
      bash·memory 만 쓴 페이즈(= GUI 조작 0회)는 VM 을 실제로 바꿔놓고도 플래그가
      False 로 남는다. 그대로 두면 다음 페이즈가 "초기화된 VM" 이라고 믿고 시작하는데
      실은 이전 페이즈의 파일이 살아있다. 로그가 정상처럼 보여서 조용히 실험을
      무효화한다(실측: 스모크 모드 3 에서 표식 파일이 살아남음).
    """

    TASK = {"id": "t", "instruction": "x", "config": [], "evaluator": {"func": "infeasible"}}

    def test_restore_reverts_even_when_env_looks_unused(self):
        import tempfile
        sess = _session()
        self.assertFalse(sess.env.is_environment_used)      # GUI 를 한 번도 안 쓴 상태
        with tempfile.TemporaryDirectory() as td:
            sess.prepare(self.TASK, result_dir=td, restore="init_state")
        self.assertEqual(sess.env.reverted, ["init_state"],
                         "restore 를 줬는데 되돌아가지 않았다 — 다음 페이즈가 오염된 VM 에서 시작한다")

    def test_restore_none_does_not_touch_the_vm(self):
        import tempfile
        sess = _session()
        with tempfile.TemporaryDirectory() as td:
            sess.prepare(self.TASK, result_dir=td, restore=None)
        self.assertEqual(sess.env.reverted, [], "restore=None 인데 VM 을 되돌렸다")
        self.assertEqual(sess.env.configs, [], "restore=None 인데 reset 을 불렀다")


class TestNeutralArmIsWiredEndToEnd(unittest.TestCase):
    """팔 이름을 검사하는 **모든 관문**이 neutral 을 통과시키는지.

    실측 사고: MODEL_SPECS 와 decorate 만 고치고 EmuToolLayer 와 CLI choices 를
    빠뜨려서, VM 을 띄운 뒤에야 ValueError 가 났다(3판 낭비). 여기서 잡는다.
    """

    def test_luna_accepts_neutral(self):
        text = config_check(BASE + ["--model", "luna", "--tools", "computer,bash",
                                    "--memory", "--read-mode", "neutral"])
        self.assertIn("CONFIG_CHECK_READY", text)

    def test_kimi_accepts_neutral(self):
        text = config_check(BASE + ["--model", "kimi", "--tools", "computer,bash",
                                    "--memory", "--read-mode", "neutral"])
        self.assertIn("CONFIG_CHECK_READY", text)

    def test_luna_still_refuses_faithful(self):
        with self.assertRaises(SystemExit):
            config_check(BASE + ["--model", "luna", "--tools", "computer,bash",
                                 "--memory", "--read-mode", "faithful"])


class TestContextLengthIsAligned(unittest.TestCase):
    """세 모델의 문맥 길이가 같은 값에 묶여 있는지.

    ★ 왜 (실측) — 예전에는 Luna 3 / Haiku 6 / Kimi 8 로 제각각이었고, Kimi 의 8 만
      우리가 벤더 기본값 3 에서 올려둔 값이었다. "1번 턴에 본 목록을 3번 턴에 쓰는"
      판단이 여기 직접 걸리므로, 값이 다르면 모델 차이인지 문맥 길이 차이인지
      가를 수 없다. Haiku 기준(6)으로 맞췄고, 누가 한쪽만 바꾸면 여기서 걸린다.
    """

    # 벤더가 이미지를 몇 장 붙이는지, **각자의 코드에 있는 식을 그대로** 옮긴다.
    #   선언값 비교는 약하다 — 예전 이 테스트가 선언값만 봐서, Kimi 가 6 을 선언하고
    #   5 장만 받는 off-by-one 을 놓쳤다(지문에는 6 이라고 적히고 있었다).
    #   식을 옮겨두면 다음에 벤더가 조건을 바꿔도 여기서 걸린다.
    @staticmethod
    def _images_seen(kind: str, declared: int, steps: int) -> int:
        if kind == "kimi":      # kimi_agent.py:341  if i > len(actions) - m
            return len([i for i in range(steps) if i > steps - declared])
        if kind == "luna":      # agent.py:324  observations[-m:]
            return min(steps, declared)
        if kind == "claude":    # agent_mcp.py:496  excess = len(images) - m
            return min(steps, declared)
        raise ValueError(kind)

    def test_all_three_see_the_same_number_of_screenshots(self):
        """선언값이 아니라 **실제로 붙는 장수**가 같아야 한다."""
        from mm_agents.adapters import agents as A
        import inspect
        self.assertEqual(A.HISTORY_STEPS, 6)
        luna = inspect.signature(
            A.LunaAdapter.__init__).parameters["max_trajectory_length"].default
        kimi = inspect.signature(
            A.KimiAdapter.__init__).parameters["max_image_history_length"].default
        claude = inspect.signature(runner.Session.__init__).parameters["only_n"].default

        for steps in (1, 2, 5, 6, 7, 13, 21, 40, 60):
            c = self._images_seen("claude", claude, steps)
            l = self._images_seen("luna", luna, steps)
            k = self._images_seen("kimi", kimi, steps)
            self.assertEqual((c, l, k), (c, c, c),
                             f"{steps}스텝에서 붙는 스크린샷 수가 다르다 "
                             f"(claude={c} luna={l} kimi={k})")
            self.assertEqual(c, min(steps, A.HISTORY_STEPS),
                             f"{steps}스텝에서 기준선(HISTORY_STEPS)과도 다르다")

    def test_kimi_declares_one_more_than_it_gets(self):
        """+1 보정과 지문의 실효값 환산이 같은 출처를 쓰는지."""
        from mm_agents.adapters import agents as A
        import inspect
        declared = inspect.signature(
            A.KimiAdapter.__init__).parameters["max_image_history_length"].default
        self.assertEqual(declared, A.HISTORY_STEPS + 1,
                         "Kimi 는 벤더 off-by-one 때문에 +1 을 선언해야 한다")
        self.assertEqual(A.kimi_effective_history(declared), A.HISTORY_STEPS,
                         "지문에 적히는 실효값이 기준선과 다르다")
        # 긴 에피소드에서 실효값이 정말 그 수인지 식으로도 확인
        self.assertEqual(self._images_seen("kimi", declared, 40),
                         A.kimi_effective_history(declared))

    def test_luna_context_is_tied_to_the_constant(self):
        from mm_agents.adapters import agents as A
        import inspect
        luna = inspect.signature(
            A.LunaAdapter.__init__).parameters["max_trajectory_length"].default
        self.assertEqual(luna, A.HISTORY_STEPS, "Luna 문맥 길이가 상수에서 떨어졌다")

    def test_claude_runner_default_matches(self):
        """실행기의 only_n(= Haiku 유지 스크린샷 수) 도 같은 값이어야 한다."""
        from mm_agents.adapters import agents as A
        import inspect
        only_n = inspect.signature(runner.Session.__init__).parameters["only_n"]
        self.assertEqual(only_n.default, A.HISTORY_STEPS,
                         "Haiku 쪽 기본값이 달라지면 기준 자체가 흔들린다")


if __name__ == "__main__":
    unittest.main()
