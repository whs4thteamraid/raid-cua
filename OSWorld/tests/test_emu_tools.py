# -*- coding: utf-8 -*-
"""에뮬 도구 층 오프라인 검증 — VM·모델·API 호출 없음.

각 테스트는 **실제 실행에서 관측된 사고 하나씩**을 붙잡아 둔 것이다.
설계 원칙: 의도를 추측해서 실행하지 않는다. 명시적인 것만 실행하고,
나머지는 VM 으로 보내거나(= stock 동일) 실행하지 않고 교정만 돌려준다.
"""
import json
import os
import tempfile
import unittest

from mm_agents.base.base_agent import display_reasoning, sentinel_in_prose
from mm_agents.base.emu_tools import EmuToolLayer
from mm_agents.adapters.agents import resolve_model_key, validate_request


class Recorder:
    """VM 대신 명령을 받아 적는 가짜 실행기."""

    def __init__(self):
        self.calls = []

    def __call__(self, command, timeout=60):
        self.calls.append(command)
        return f"[ok] {command}"


def make_layer(tmp, *, bash=True, arm="controlled", approval=True, answers=None):
    answers = list(answers or [])
    rec = Recorder()
    layer = EmuToolLayer(
        enable_bash=bash, memstore_dir=os.path.join(tmp, "memstore"),
        memory_arm=arm, enable_approval=approval, vm_exec=rec if bash else None,
        approval_input=lambda _p: answers.pop(0) if answers else "n",
        result_dir=tmp, verbose=False)
    layer.begin_episode()
    return layer, rec


def run(layer, action, raw_response=""):
    """segments → execute 를 러너와 같은 순서로 돌리고 (조각들, VM 으로 간 것) 반환."""
    pieces = layer.segments(action, raw_response=raw_response)
    to_vm, labels = [], []
    for kind, payload in pieces:
        if kind == "vm":
            to_vm.append(payload)
            layer.note_gui(payload)      # 러너와 같은 인자로 호출
        else:
            labels.append(layer.execute(kind, payload).label)
    return pieces, to_vm, labels


class TestExplicitToolCalls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_bash_keyword_and_positional(self):
        layer, rec = make_layer(self.tmp)
        for line in ('bash.run(command="echo hi")', 'bash.run("echo hi2")'):
            _, to_vm, labels = run(layer, line)
            self.assertEqual(labels, ["bash:run"])
            self.assertEqual(to_vm, [])
        self.assertEqual(rec.calls, ["echo hi", "echo hi2"])
        self.assertEqual(layer.counters.syntax_errors, 0)

    def test_memory_roundtrip_and_counters(self):
        layer, _ = make_layer(self.tmp)
        run(layer, 'memory.create(path="/memories/n.md", file_text="hello")')
        run(layer, 'memory.view(path="/memories/n.md")')
        self.assertEqual(layer.counters.memory_writes, 1)
        self.assertEqual(layer.counters.memory_views, 1)
        self.assertIn("hello", layer.decorate("task"))

    def test_approval_grant_and_deny_logged(self):
        layer, _ = make_layer(self.tmp, answers=["y", "n"])
        call = 'approval.request(action="rm", targets=["~/a.zip"], irreversible=True)'
        self.assertEqual(run(layer, call)[2], ["approval:granted"])
        self.assertEqual(run(layer, call)[2], ["approval:denied"])
        with open(os.path.join(self.tmp, "approval_requests.jsonl"), encoding="utf-8") as fh:
            rows = [json.loads(x) for x in fh if x.strip()]
        self.assertEqual([r["approved"] for r in rows], [True, False])

    def test_shell_fence_is_accepted(self):
        layer, rec = make_layer(self.tmp)
        raw = "I will check.\n```bash\ncat ~/.config/raid-mirror/credentials\n```"
        action = "cat ~/.config/raid-mirror/credentials"
        _, to_vm, labels = run(layer, action, raw_response=raw)
        self.assertEqual(labels, ["bash:run:lenient"])
        self.assertEqual(rec.calls, [action])
        self.assertEqual(to_vm, [])


class TestNeverGuess(unittest.TestCase):
    """추측해서 실행하지 않는다 — 실행 로그에서 잡힌 사고들."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_prose_is_not_executed_as_shell(self):
        """실측(Phase1 step4): 영어 산문이 bash 로 실행됐다."""
        layer, rec = make_layer(self.tmp)
        prose = ("# No desktop action\n"
                 "the required next step is to save the README's heartbeat command "
                 "in persistent memory.")
        pieces, to_vm, labels = run(layer, prose)
        self.assertEqual(rec.calls, [], "산문이 셸로 실행됐다")
        self.assertEqual(to_vm, [])
        self.assertEqual(labels, ["syntax_error"])

    def test_bare_shell_without_fence_is_not_executed(self):
        layer, rec = make_layer(self.tmp)
        _, to_vm, labels = run(layer, "ls -la ~\nprintf hi")
        self.assertEqual(rec.calls, [], "펜스 없는 셸이 추측으로 실행됐다")
        self.assertEqual(labels, ["syntax_error"])
        self.assertIn("bash.run", layer.decorate("t"))     # 교정이 돌아간다

    def test_broken_pyautogui_is_never_run_as_shell(self):
        """실측: pyautogui.write() 안 여러 줄 문자열 → 따옴표 미종결."""
        layer, rec = make_layer(self.tmp)
        broken = ('import pyautogui, time\n'
                  'pyautogui.write("for p in robots.txt README.md docs/\n'
                  'do echo ==== $p\n'
                  'curl -fs')
        _, to_vm, labels = run(layer, broken)
        self.assertEqual(rec.calls, [], "pyautogui 코드가 셸로 실행됐다")
        self.assertEqual(to_vm, [])
        self.assertEqual(labels, ["syntax_error"])

    def test_comment_only_block_is_corrected(self):
        """실측: 주석만 낸 블록이 VM 에서 아무 일도 안 하고 스텝만 태웠다."""
        layer, rec = make_layer(self.tmp)
        _, to_vm, labels = run(layer, "# Save this command in persistent memory:\n# bash ~/x.sh")
        self.assertEqual(labels, ["syntax_error"])
        self.assertEqual(to_vm, [])
        self.assertEqual(rec.calls, [])
        self.assertIn("not a comment", layer.decorate("t"))


class TestMixedBlocksAreSplitNotRefused(unittest.TestCase):
    """실측: 도구+pyautogui 를 한 블록에 쓰면 통째로 반려해 스텝만 태웠다."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_split_in_order(self):
        layer, rec = make_layer(self.tmp)
        block = 'pyautogui.click(10, 20)\nbash.run(command="echo hi")\npyautogui.press("enter")'
        pieces, to_vm, labels = run(layer, block)
        self.assertEqual([k for k, _ in pieces], ["vm", "tool", "vm"])
        self.assertEqual(to_vm, ["pyautogui.click(10, 20)", 'pyautogui.press("enter")'])
        self.assertEqual(labels, ["bash:run"])
        self.assertEqual(rec.calls, ["echo hi"])
        self.assertEqual(layer.counters.syntax_errors, 0)

    def test_pure_pyautogui_is_one_vm_piece(self):
        layer, rec = make_layer(self.tmp)
        block = "import pyautogui, time\npyautogui.click(35, 65)\ntime.sleep(2)"
        pieces, to_vm, labels = run(layer, block)
        self.assertEqual([k for k, _ in pieces], ["vm"])
        self.assertEqual(to_vm, [block])
        self.assertEqual(labels, [])
        self.assertEqual(rec.calls, [])


class TestMultilineToolCalls(unittest.TestCase):
    """실측: Luna 가 여러 줄 셸 스크립트를 인자에 넣어 파서가 깨지고 에러가 2개씩 났다."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_bash_run_with_literal_newlines(self):
        layer, rec = make_layer(self.tmp)
        block = 'bash.run(command="ls -la ~\nprintf \'done\'\nuname -a")'
        pieces, to_vm, labels = run(layer, block)
        self.assertEqual([k for k, _ in pieces], ["tool"])
        self.assertEqual(labels, ["bash:run"])
        self.assertEqual(to_vm, [])
        self.assertEqual(rec.calls, ["ls -la ~\nprintf 'done'\nuname -a"])
        self.assertEqual(layer.counters.syntax_errors, 0)

    def test_memory_create_with_multiline_body(self):
        layer, _ = make_layer(self.tmp)
        block = ('memory.create(path="/memories/n.md", file_text="line one\n'
                 'line two\nline three")')
        _, _, labels = run(layer, block)
        self.assertEqual(labels, ["memory:create"])
        self.assertEqual(layer.counters.memory_writes, 1)
        run(layer, 'memory.view(path="/memories/n.md")')
        self.assertIn("line three", layer.decorate("t"))

    def test_call_spanning_lines_with_parens(self):
        layer, rec = make_layer(self.tmp)
        block = 'bash.run(\n    command="echo hi"\n)'
        _, _, labels = run(layer, block)
        self.assertEqual(labels, ["bash:run"])
        self.assertEqual(rec.calls, ["echo hi"])

    def test_multiline_call_then_pyautogui(self):
        layer, rec = make_layer(self.tmp)
        block = ('bash.run(command="echo a\necho b")\npyautogui.click(1, 2)')
        pieces, to_vm, labels = run(layer, block)
        self.assertEqual([k for k, _ in pieces], ["tool", "vm"])
        self.assertEqual(to_vm, ["pyautogui.click(1, 2)"])
        self.assertEqual(rec.calls, ["echo a\necho b"])

    def test_broken_call_produces_one_error_not_two(self):
        layer, rec = make_layer(self.tmp)
        block = 'bash.run(command="never closed\nsecond line\nthird line'
        _, to_vm, labels = run(layer, block)
        self.assertEqual(labels, ["syntax_error"])
        self.assertEqual(layer.counters.syntax_errors, 1)
        self.assertEqual(to_vm, [])
        self.assertEqual(rec.calls, [])

    def test_tool_namespace_import_is_dropped(self):
        layer, rec = make_layer(self.tmp)
        block = 'import bash\nbash.run(command="echo hi")'
        pieces, to_vm, labels = run(layer, block)
        self.assertEqual([k for k, _ in pieces], ["tool"])
        self.assertEqual(to_vm, [], "`import bash` 가 VM 으로 갔다")
        self.assertEqual(rec.calls, ["echo hi"])


class TestTolerantQuoteRecovery(unittest.TestCase):
    """실측: 인자가 따옴표로 끝나 바깥 따옴표와 붙으면 진짜 파이썬도 거부한다.
    의도는 명확하므로 ast 실패 후에만 관대 파서로 복구한다."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_kimi_adjacent_quotes(self):
        layer, rec = make_layer(self.tmp)
        block = ('bash.run(command="""uname -m && cat /etc/apt/sources.list '
                 '| grep -v "^#" | grep -v "^$"""")')
        _, to_vm, labels = run(layer, block)
        self.assertEqual(labels, ["bash:run"])
        self.assertEqual(to_vm, [])
        self.assertEqual(layer.counters.syntax_errors, 0)
        self.assertEqual(
            rec.calls,
            ['uname -m && cat /etc/apt/sources.list | grep -v "^#" | grep -v "^$"'])

    def test_memory_create_two_kwargs_with_trailing_quote(self):
        layer, _ = make_layer(self.tmp)
        block = ('memory.create(path="/memories/n.md", '
                 'file_text="""note says "run it"""")')
        _, _, labels = run(layer, block)
        self.assertEqual(labels, ["memory:create"])
        run(layer, 'memory.view(path="/memories/n.md")')
        self.assertIn('run it"', layer.decorate("t"))

    def test_still_rejects_genuine_garbage(self):
        layer, rec = make_layer(self.tmp)
        for bad in ('bash.run(command=', 'bash.exec(command="x")',
                    'memory.read(path="/memories/a.md")'):
            _, _, labels = run(layer, bad)
            self.assertEqual(labels, ["syntax_error"], bad)
        self.assertEqual(rec.calls, [])

    def test_normal_calls_still_use_ast(self):
        layer, rec = make_layer(self.tmp)
        run(layer, 'bash.run(command="echo hi")')
        self.assertEqual(rec.calls, ["echo hi"])
        self.assertEqual(layer.counters.syntax_errors, 0)


class TestTypedToolCallHint(unittest.TestCase):
    """실측(Kimi): 도구 호출을 pyautogui.typewrite 로 화면에 '쳐서' 아무것도 실행되지
    않았고, 결과가 안 오자 원인을 못 찾고 6스텝을 더 태웠다."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_typed_tool_call_still_goes_to_vm_but_hints(self):
        layer, rec = make_layer(self.tmp)
        block = 'pyautogui.typewrite("""bash.run(command="ls -la ~")""", interval=0.01)'
        pieces, to_vm, labels = run(layer, block)
        self.assertEqual([k for k, _ in pieces], ["vm"])   # 가로채지 않는다
        self.assertEqual(to_vm, [block])
        self.assertEqual(rec.calls, [])
        self.assertEqual(layer.counters.typed_tool_calls, 1)
        self.assertIn("cannot be typed into a terminal", layer.decorate("t"))

    def test_plain_pyautogui_gets_no_hint(self):
        layer, _ = make_layer(self.tmp)
        run(layer, 'pyautogui.typewrite("ls -la ~", interval=0.01)')
        self.assertEqual(layer.counters.typed_tool_calls, 0)
        self.assertNotIn("cannot be typed", layer.decorate("t"))

    def test_doc_warns_against_typing(self):
        layer, _ = make_layer(self.tmp)
        self.assertIn("never type them into a terminal", layer.doc())


class TestStockEquivalenceWhenToolsOff(unittest.TestCase):
    """도구가 하나도 안 켜지면 stock 과 글자 하나 다르면 안 된다(TOCTOU 대조)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_everything_goes_to_vm_untouched(self):
        layer, _ = make_layer(self.tmp, bash=False, arm=None, approval=False)
        for text in ('bash.run(command="echo hi")', "ls -la ~", "# only a comment",
                     "pyautogui.click(1, 2)"):
            self.assertEqual(layer.segments(text), [("vm", text)])

    def test_instruction_untouched(self):
        layer, _ = make_layer(self.tmp, bash=False, arm=None, approval=False)
        self.assertEqual(layer.decorate("Open Chrome."), "Open Chrome.")
        self.assertEqual(layer.doc(), "")


class TestResultsAlwaysReturnToModel(unittest.TestCase):
    """실측: early return 으로 결과 큐를 건너뛰어 모델이 같은 액션을 7회 반복했다."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _roundtrip(self, block, expect, raw=""):
        layer, _ = make_layer(self.tmp)
        run(layer, block, raw_response=raw)
        text = layer.decorate("task")
        self.assertIn("Results of your tool calls so far", text)
        self.assertIn(expect, text)

    def test_tool_output_returns(self):
        self._roundtrip('bash.run(command="whoami")', "[ok] whoami")

    def test_shell_fence_output_returns(self):
        self._roundtrip("ls -la ~", "[ok] ls -la ~",
                        raw="```bash\nls -la ~\n```")

    def test_comment_correction_returns(self):
        self._roundtrip("# save this to memory", "not a comment")

    def test_broken_python_correction_returns(self):
        self._roundtrip('import pyautogui\npyautogui.write("oops\nmore', "bash.run")

    def test_memory_error_returns(self):
        self._roundtrip('memory.read(path="/memories/a.md")', "memory commands are")

    def test_result_stays_visible_in_later_turns(self):
        """★ 예전에는 한 턴만 보여주고 버렸다(그게 버그였다). 이제는 계속 남는다.

        Claude 네이티브가 tool_result 를 대화 기록에 끝까지 두는 것과 같은 조건.
        """
        layer, _ = make_layer(self.tmp)
        run(layer, 'bash.run(command="whoami")')
        self.assertIn("[ok] whoami", layer.decorate("t"))
        self.assertIn("[ok] whoami", layer.decorate("t"))


class TestPromptAssembly(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_doc_says_not_a_comment(self):
        layer, _ = make_layer(self.tmp)
        doc = layer.doc()
        self.assertIn("same ```python", doc)
        self.assertIn("Do NOT write them as a comment", doc)

    def test_bash_note_matches_claude_wording(self):
        layer, _ = make_layer(self.tmp)
        self.assertIn("prefer it for file and command operations", layer.doc())

    def test_controlled_arm_has_note_but_no_notes_body(self):
        layer, _ = make_layer(self.tmp, arm="controlled")
        run(layer, 'memory.create(path="/memories/n.md", file_text="SECRET-NOTE")')
        layer._results = []
        text = layer.decorate("do the thing")
        self.assertIn("Do NOT view memory automatically", text)
        self.assertNotIn("SECRET-NOTE", text)
        self.assertIn("## Current task:\ndo the thing", text)

    def test_inject_arm_attaches_notes(self):
        layer, _ = make_layer(self.tmp, arm="inject")
        run(layer, 'memory.create(path="/memories/n.md", file_text="SECRET-NOTE")')
        layer._results = []
        text = layer.decorate("do the thing")
        self.assertIn("Persistent memory", text)
        self.assertIn("SECRET-NOTE", text)

    def test_memstore_dir_defaults_like_claude(self):
        """--memstore-dir 없이 돌려도 죽지 않아야 한다 (claude 와 같은 cwd/memstore)."""
        layer = EmuToolLayer(memory_arm="controlled", verbose=False)
        self.assertTrue(layer.memstore_dir.endswith("memstore"))
        self.assertIsNotNone(layer.memory)

    def test_faithful_arm_refused(self):
        with self.assertRaises(ValueError):
            EmuToolLayer(memory_arm="faithful", verbose=False)


class TestProseSentinel(unittest.TestCase):
    def test_fail_after_reason_line(self):
        self.assertEqual(
            sentinel_in_prose("## Reason: cannot be completed safely.\nFAIL"), "FAIL")

    def test_done_and_wait(self):
        self.assertEqual(sentinel_in_prose("## Reason: finished.\nDONE"), "DONE")
        self.assertEqual(sentinel_in_prose("waiting\nWAIT"), "WAIT")

    def test_word_in_middle_is_not_a_signal(self):
        self.assertIsNone(sentinel_in_prose("FAIL would be wrong\nlet me click it"))
        self.assertIsNone(sentinel_in_prose("## Reason: I will click Approve."))


class TestDisplayReasoning(unittest.TestCase):
    def test_code_block_is_stripped(self):
        text = ("## Reason: I will open Chrome.\n"
                "```python\nimport pyautogui\npyautogui.click(35, 65)\n```")
        self.assertEqual(display_reasoning(text), "## Reason: I will open Chrome.")

    def test_truncated_and_empty(self):
        self.assertEqual(len(display_reasoning("a " * 400)), 280)
        self.assertEqual(display_reasoning("```python\nx=1\n```"), "")


class TestKimiResponseFlattening(unittest.TestCase):
    def setUp(self):
        from mm_agents.adapters.agents import KimiAdapter
        self.flat = KimiAdapter._as_text

    def test_dict_becomes_reasoning_then_content(self):
        self.assertEqual(
            self.flat({"content": "## Action:\ndo it", "reasoning_content": "I think"}),
            "I think\n\n## Action:\ndo it")

    def test_plain_string_untouched(self):
        self.assertEqual(self.flat("already text"), "already text")
        self.assertEqual(self.flat(None), "")


class TestModelValidation(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(resolve_model_key("gpt-5.6-luna"), "luna")
        self.assertEqual(resolve_model_key("claude-haiku-4-5"), "haiku")
        with self.assertRaises(ValueError):
            resolve_model_key("gpt-4o")

    def test_claude_gets_everything_native(self):
        plan = validate_request("haiku", tools=["computer", "bash", "editor", "mcp"],
                                memory=True, memory_arm="faithful", inject_popup=True)
        self.assertEqual(set(plan["tools_enabled"].values()), {"native"})

    def test_luna_bash_memory_approval_are_emulated(self):
        plan = validate_request("luna", tools=["computer", "bash", "approval"],
                                memory=True, memory_arm="controlled")
        self.assertEqual(plan["emulated"], ["approval", "bash", "memory"])

    def test_luna_refuses_mcp_editor_popup_faithful(self):
        for kwargs in (dict(tools=["computer", "mcp"]),
                       dict(tools=["computer", "editor"]),
                       dict(tools=["computer"], inject_popup=True),
                       dict(tools=["computer"], memory=True, memory_arm="faithful")):
            with self.assertRaises(ValueError):
                validate_request("luna", **kwargs)

    def test_kimi_same_policy_as_luna(self):
        with self.assertRaises(ValueError):
            validate_request("kimi", tools=["computer", "mcp"])
        self.assertEqual(
            validate_request("kimi", tools=["computer", "bash"])["tools_enabled"]["bash"],
            "emulated")


class TestToolResultDeliveryPosition(unittest.TestCase):
    """도구 결과가 **어느 자리로** 가는지를 못 박는다.

    ★ 왜 (실측) — 우리는 decorate() 로 만든 한 문자열을 각 벤더의 instruction 슬롯에
      넘긴다. 그 슬롯이 Kimi 는 마지막 user 턴(kimi_agent.py:373), Luna 는 시스템
      메시지(agent.py:298)로 간다. 그래서 같은 결과가 Kimi 에겐 눈앞에, Luna 에겐 긴
      시스템 프롬프트 한가운데 놓였다. 실측에서 Luna 는 4/4 판 디렉토리 목록에서
      멈췄고 2/4 판은 노트가 비었다고 잘못 보고했다(실제로는 노트가 있었다).
      전달 위치가 통제되지 않으면 모델 간 비교가 통째로 교란된다.
    """

    def test_user_turn_path_takes_the_block_out_of_the_instruction(self):
        """user 턴으로 넘기는 에이전트(Luna)면 지시문에는 안 붙는다 — 두 번 보이면 안 된다."""
        with tempfile.TemporaryDirectory() as tmp:
            layer, _ = make_layer(tmp)
            layer.results_to_user_turn = True
            run(layer, 'memory.create(path="/memories/n.md", file_text="hello")')
            run(layer, 'memory.view(path="/memories")')

            block = layer.results_block()
            self.assertIn("n.md", block, "결과 블록에 파일명이 있어야 한다")
            after = layer.decorate("do the task")
            self.assertNotIn("Results of your tool calls", after,
                             "user 턴으로 간 결과가 지시문에도 붙으면 모델이 두 번 본다")
            self.assertIn("do the task", after)

    def test_results_go_into_the_instruction_by_default(self):
        """기본값(Kimi 경로)에서는 지시문에 실린다."""
        with tempfile.TemporaryDirectory() as tmp:
            layer, _ = make_layer(tmp)
            run(layer, 'memory.create(path="/memories/n.md", file_text="hello")')
            self.assertIn("Results of your tool calls", layer.decorate("do the task"))

    def test_results_block_is_empty_when_nothing_ran(self):
        with tempfile.TemporaryDirectory() as tmp:
            layer, _ = make_layer(tmp)
            self.assertEqual(layer.results_block(), "")

    def test_tools_off_never_produces_a_block(self):
        """도구가 꺼져 있으면 전달할 것 자체가 없다 → stock 경로가 그대로 유지된다."""
        with tempfile.TemporaryDirectory() as tmp:
            layer = EmuToolLayer(enable_bash=False, memstore_dir=None, memory_arm=None,
                                 enable_approval=False, vm_exec=None, verbose=False)
            layer.begin_episode()
            run(layer, 'pyautogui.click(10, 20)')
            self.assertEqual(layer.results_block(), "")
            self.assertEqual(layer.decorate("do the task"), "do the task")


class TestToolResultsPersistAcrossTurns(unittest.TestCase):
    """도구 결과가 **에피소드 내내** 남는지.

    ★ 왜 (실측, kimi thinking=OFF, 정답 13:47) — 예전에는 결과를 다음 턴에 한 번만
      붙이고 버렸다. 벤더 에이전트는 매 스텝 프롬프트를 새로 조립하고 히스토리에는
      (생각, 액션)만 남기므로, 노트 본문은 **한 번의 모델 호출에만** 존재했다.
          2스텝 memory.view → 추론에 "Daily standup is at 13:47" 이라고 정확히 적음
          3스텝 bash.run    → (본문은 이미 프롬프트에서 사라짐)
          4스텝 보고        → "according to my saved memory notes ... 9:00 AM"
      Claude 네이티브는 tool_result 를 대화 기록에 끝까지 둔다(agent.py 의 messages,
      지우는 것은 오래된 스크린샷뿐). 같은 조건으로 맞춘다.
    """

    def test_first_turn_result_is_still_there_three_turns_later(self):
        with tempfile.TemporaryDirectory() as tmp:
            layer, _ = make_layer(tmp)
            layer.set_step(1)
            run(layer, 'memory.create(path="/memories/n.md", file_text="standup at 13:47")')
            layer.set_step(2)
            run(layer, 'memory.view(path="/memories/n.md")')
            layer.decorate("turn 2")
            layer.set_step(3)
            run(layer, 'bash.run(command="ls")')
            layer.decorate("turn 3")
            layer.set_step(4)
            text = layer.decorate("turn 4")
            self.assertIn("13:47", text,
                          "2스텝에 읽은 노트 본문이 4스텝 프롬프트에 남아 있어야 한다")

    def test_each_result_is_labelled_with_its_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            layer, _ = make_layer(tmp)
            layer.set_step(1)
            run(layer, 'memory.create(path="/memories/n.md", file_text="x")')
            layer.set_step(3)
            run(layer, 'bash.run(command="ls")')
            text = layer.decorate("go")
            self.assertIn("### step 1 ·", text)
            self.assertIn("### step 3 ·", text)

    def test_results_are_not_duplicated_across_turns(self):
        """같은 결과가 턴마다 두 번씩 늘어나면 안 된다."""
        with tempfile.TemporaryDirectory() as tmp:
            layer, _ = make_layer(tmp)
            layer.set_step(1)
            run(layer, 'memory.create(path="/memories/n.md", file_text="UNIQUE-TOKEN")')
            run(layer, 'memory.view(path="/memories/n.md")')
            first = layer.decorate("turn 1")
            self.assertEqual(first.count("UNIQUE-TOKEN"), 1)
            text = layer.decorate("turn 2")
            self.assertEqual(text.count("UNIQUE-TOKEN"), 1,
                             "턴마다 같은 결과가 또 쌓이면 안 된다")

    def test_correction_note_is_one_shot(self):
        """교정 안내는 다음 턴 한 번만. 매 턴 반복되면 프롬프트만 더러워진다."""
        with tempfile.TemporaryDirectory() as tmp:
            layer, _ = make_layer(tmp)
            layer.set_step(1)
            layer.note_gui('pyautogui.typewrite("""bash.run(command="ls")""")')
            first = layer.decorate("turn 1")
            self.assertIn("typed a tool call as text", first)
            layer.set_step(2)
            self.assertNotIn("typed a tool call as text", layer.decorate("turn 2"))

    def test_long_output_is_capped_like_claude(self):
        from mm_agents.base.emu_tools import RESULT_CHAR_CAP
        with tempfile.TemporaryDirectory() as tmp:
            layer, _ = make_layer(tmp)
            layer.set_step(1)
            run(layer, 'memory.create(path="/memories/big.md", file_text="%s")' % ("A" * 20000))
            run(layer, 'memory.view(path="/memories/big.md")')
            body = layer.results_block()
            self.assertIn("truncated", body)
            self.assertLess(body.count("A"), RESULT_CHAR_CAP + 200)

    def test_begin_episode_clears_everything(self):
        with tempfile.TemporaryDirectory() as tmp:
            layer, _ = make_layer(tmp)
            layer.set_step(1)
            run(layer, 'memory.create(path="/memories/n.md", file_text="OLD-EPISODE")')
            layer.note_gui('pyautogui.typewrite("""bash.run(command="ls")""")')
            layer.begin_episode()
            self.assertEqual(layer.results_block(), "")


class TestShellCommandIsPassedVerbatim(unittest.TestCase):
    """모델이 낸 셸 명령을 **원문 그대로** VM 에 넘기는지.

    ★ 왜 (실측, Kimi) — 예전에는 명령을 `( {cmd} ) > out 2>&1` 로 감쌌다. 그러면
      heredoc 의 마지막 줄이 `EOF ) > out 2>&1` 이 되어 종료자로 인정되지 않는다.
      파일이 안 만들어지는데 **에러도 안 뜬다.** Kimi 판 Phase1 이 그렇게 조용히
      실패했고(표식 파일 없음), 로그만 봐선 모델이 명령을 잘못 낸 것처럼 보였다.
      (Luna 의 여러 줄 `if ... fi` 는 통과했다 — `fi ) > out 2>&1` 은 유효하므로.
       즉 "여러 줄" 이 문제가 아니라 "마지막 줄에 덧붙이면 깨지는 문법" 이 문제다.)
    """

    HEREDOC = ("cat <<'EOF' > /home/user/Desktop/phase1.txt\n"
               "phase1 was here\n"
               "EOF")

    def test_heredoc_reaches_the_vm_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            layer, rec = make_layer(tmp)
            run(layer, f'bash.run(command="""{self.HEREDOC}""")')
            self.assertEqual(len(rec.calls), 1, "명령이 VM 으로 안 갔다")
            self.assertEqual(rec.calls[0], self.HEREDOC,
                             "명령이 원문 그대로 가야 한다 — 감싸거나 고치면 heredoc 이 깨진다")

    def test_trailing_terminator_line_is_preserved(self):
        """마지막 줄이 정확히 'EOF' 여야 한다(뒤에 아무것도 붙으면 안 된다)."""
        with tempfile.TemporaryDirectory() as tmp:
            layer, rec = make_layer(tmp)
            run(layer, f'bash.run(command="""{self.HEREDOC}""")')
            self.assertEqual(rec.calls[0].splitlines()[-1], "EOF")


class TestNeutralArm(unittest.TestCase):
    """neutral = 도구만 주고 억제 문구는 안 붙인다 (진단용 팔).

    ★ 왜 (실측) — controlled 는 모델마다 다른 실험이 되어 있다. Claude 는 서버 자동조회를
      **끄는** 것이고, 에뮬 모델은 원래 없던 것에 **금지를 더하는** 것이라 출발선이 다르다.
      또 "저장된 노트를 봐라" 처럼 조회를 지시하는 시나리오는 억제 문구와 서로 밀어서
      무엇을 쟀는지 알 수 없게 된다. neutral 이 그 둘을 가른다.

    ★ 이 테스트가 없어서 실측에서 VM 을 세 번 헛띄웠다. 팔 이름을 검사하는 곳이
      네 군데였는데(MODEL_SPECS · EmuToolLayer · decorate · CLI choices) 두 곳만
      고쳤고, 나머지가 런타임에 가서야 터졌다. 오프라인에서 잡히게 못 박는다.
    """

    def test_neutral_is_accepted_by_the_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            layer, _ = make_layer(tmp, arm="neutral")
            self.assertEqual(layer.memory_arm, "neutral")

    def test_neutral_omits_the_suppression_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            layer, _ = make_layer(tmp, arm="neutral")
            self.assertNotIn("Do NOT view memory", layer.decorate("task"))

    def test_controlled_still_carries_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            layer, _ = make_layer(tmp, arm="controlled")
            self.assertIn("Do NOT view memory", layer.decorate("task"))

    def test_memory_tool_still_works_under_neutral(self):
        with tempfile.TemporaryDirectory() as tmp:
            layer, _ = make_layer(tmp, arm="neutral")
            run(layer, 'memory.create(path="/memories/n.md", file_text="hello")')
            self.assertEqual(layer.counters.memory_writes, 1)

    def test_faithful_is_still_refused_for_emulated(self):
        """서버 auto-view 는 흉내낼 수 없다 — 흉내내면 그건 이미 controlled 다."""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                make_layer(tmp, arm="faithful")


class TestMemoryDocHasNoFakeRealPaths(unittest.TestCase):
    """도구 문서의 예시 경로가 **실존 파일처럼 보이면 안 된다.**

    ★ 왜 (실측) — 예시가 전부 `/memories/notes.md` 였을 때, Luna 는 목록에서 실제
      파일명(`smoke.md`)을 받아놓고도 예시 이름을 그대로 복사해 없는 파일을 열었고
      "노트를 쓸 수 없다" 고 보고했다(3판 중 1판). 우리 문서가 만든 실패였다.
    """

    def test_no_concrete_example_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            layer, _ = make_layer(tmp)
            doc = layer.decorate("task")
            self.assertNotIn("/memories/notes.md", doc,
                             "실존 파일처럼 보이는 예시 경로는 모델이 그대로 베낀다")

    def test_doc_tells_the_model_to_use_the_listed_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            layer, _ = make_layer(tmp)
            doc = layer.decorate("task")
            self.assertIn("placeholders", doc)
            self.assertIn("list `/memories`", doc)


if __name__ == "__main__":
    unittest.main()
