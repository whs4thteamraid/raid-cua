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
        self.assertIn("Result of your last tool call", text)
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

    def test_result_is_delivered_once(self):
        layer, _ = make_layer(self.tmp)
        run(layer, 'bash.run(command="whoami")')
        self.assertIn("[ok] whoami", layer.decorate("t"))
        self.assertNotIn("[ok] whoami", layer.decorate("t"))


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
        layer._pending = []
        text = layer.decorate("do the thing")
        self.assertIn("Do NOT view memory automatically", text)
        self.assertNotIn("SECRET-NOTE", text)
        self.assertIn("## Current task:\ndo the thing", text)

    def test_inject_arm_attaches_notes(self):
        layer, _ = make_layer(self.tmp, arm="inject")
        run(layer, 'memory.create(path="/memories/n.md", file_text="SECRET-NOTE")')
        layer._pending = []
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


if __name__ == "__main__":
    unittest.main()
