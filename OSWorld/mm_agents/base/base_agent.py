# -*- coding: utf-8 -*-
"""통합 실행기용 공통 에이전트 계약 + Luna/Kimi 껍데기 루프.

러너(run_claude_3 / run_chain)는 `run_episode()` 하나만 안다.

  BaseAgent         — 계약. run_episode(instruction, max_steps, result_dir) -> EpisodeResult
  StepAgentAdapter  — predict 형 에이전트(Luna/Kimi)를 에피소드 계약으로 승격.
                      스텝 루프를 여기 한 번만 구현하고 둘이 공유한다.
  (claude 어댑터)    — 자체 루프를 가진 claude_cua 를 그대로 위임. adapters/ 참조.

왜 predict 가 아니라 run_episode 가 계약인가
  claude_cua 는 env.controller 를 직접 잡고 messages/tool_result 짝을 맞추며 스스로
  도는 루프 소유형이다. predict 단위로 쪼개면 prompt-cache breakpoint·이미지 트리밍이
  깨지고, 그 파일이 만들어낸 기존 실험 결과를 전부 재검증해야 한다. 반대로 predict 형을
  에피소드로 감싸는 것은 얇은 루프 하나면 된다. 그래서 낮은 쪽을 올린다.
"""
from __future__ import annotations

import json
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

DONE_TOKENS = ("DONE",)
FAIL_TOKENS = ("FAIL",)
WAIT_TOKENS = ("WAIT",)
TERMINATE_PAT = re.compile(r"computer\.terminate\s*\(", re.I)   # Kimi 방언


_FENCE = re.compile(r"```.*?```", re.S)


def display_reasoning(text: str, limit: int = 280) -> str:
    """터미널에 찍을 한 줄. 코드블록은 빼고 모델이 '말한 것'만 남긴다.

    claude_cua 는 text 블록과 tool_use 가 나뉘어 있어 추론만 뽑기 쉽지만,
    스텝 에이전트는 응답 한 덩어리에 설명과 코드가 섞여 있다.
    """
    plain = " ".join(_FENCE.sub(" ", text or "").split())
    return plain[:limit]


def sentinel_in_prose(response: str) -> Optional[str]:
    """코드블록 없이 산문 끝에 DONE/FAIL/WAIT 만 쓴 경우를 잡는다.

    ★ PromptAgent 의 파서는 ```펜스``` 안의 내용, 또는 응답 **전체**가 정확히
      'DONE'/'FAIL'/'WAIT' 일 때만 신호로 인정한다. 그래서 모델이
      "## Reason: ...\nFAIL" 처럼 이유를 쓰고 마지막 줄에 FAIL 만 두면
      액션이 **빈 리스트**로 나온다. 그걸 그냥 '에러'로 기록하면 정상 종료가
      오류로 집계되어 termination 열이 오염된다(실측으로 잡힌 사례).
    """
    for line in reversed([ln.strip() for ln in (response or "").splitlines() if ln.strip()]):
        if line in DONE_TOKENS + FAIL_TOKENS + WAIT_TOKENS:
            return line
        break        # 마지막 비어있지 않은 줄만 본다 (본문 중간의 단어는 무시)
    return None


@dataclass
class StepOutput:
    """predict 한 번의 결과. 세 에이전트의 서로 다른 반환형을 여기로 모은다.

    PromptAgent : (response, actions|None)   → actions=None 은 [] 로 정규화
    KimiAgent   : (response, actions, cot)   → cot 는 info 로
    """
    response: str
    actions: List[str]
    info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EpisodeResult:
    """에피소드 한 판의 측정값.

    ★ tools_enabled 는 이름 목록이 아니라 **{도구: "native"|"emulated"} 매핑**이다.
      summary.json 이 이 실험의 유일한 영구 기록이므로, 여기에 native/emulated 가
      없으면 반년 뒤 Claude 결과와 나란히 놓았을 때 조건이 달랐다는 걸 알 방법이 없다.
    """
    final_text: str = ""
    termination: str = "max_steps"      # stop | max_steps | done | fail | error
    steps: int = 0
    usage: Dict[str, int] = field(default_factory=dict)
    model: Optional[str] = None
    agent: Optional[str] = None
    tools_enabled: Dict[str, str] = field(default_factory=dict)
    unsupported_requested: List[str] = field(default_factory=list)
    memory_arm: Optional[str] = None
    memstore_dir: Optional[str] = None
    memory_files_at_start: int = 0
    memory_views: int = 0
    memory_writes: int = 0
    memory_recalled_via_tool: bool = False
    approval_requests: int = 0
    approval_grants: int = 0
    approval_denials: int = 0
    tool_syntax_errors: int = 0
    tool_lenient_accepts: int = 0
    tool_choice_counts: Dict[str, int] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    # 기존 코드가 r.get("memory_writes") 처럼 dict 로 읽던 것을 그대로 살린다.
    def get(self, key: str, default: Any = None) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        return self.extra.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.update(d.pop("extra") or {})
        return d

    @classmethod
    def from_claude_dict(cls, d: Dict[str, Any], **over) -> "EpisodeResult":
        """claude_cua.run() 이 내놓는 dict 를 계약 모양으로 옮긴다."""
        known = {f for f in cls.__dataclass_fields__ if f != "extra"}
        base = {k: v for k, v in d.items() if k in known and k != "tools_enabled"}
        extra = {k: v for k, v in d.items()
                 if k not in known and k not in ("tools_enabled",)}
        # claude 는 전부 네이티브.
        base["tools_enabled"] = {name: "native" for name in d.get("tools_enabled", [])}
        base["memory_arm"] = d.get("read_mode")
        base.setdefault("usage", {})
        base.update({k: v for k, v in over.items() if v is not None})
        return cls(extra=extra, **base)


class BaseAgent(ABC):
    name: str = "base"
    tag: str = "agent"          # 터미널 로그 앞에 붙는 짧은 이름
    supports_arms: Tuple[str, ...] = ("controlled", "inject")

    def __init__(self, env, *, model: str, verbose: bool = True, **kwargs):
        self.env = env
        self.model = model
        self.verbose = verbose

    @abstractmethod
    def reset(self) -> None: ...

    @abstractmethod
    def run_episode(self, instruction: str, max_steps: int = 30,
                    result_dir: Optional[str] = None) -> EpisodeResult: ...


class StepAgentAdapter(BaseAgent):
    """predict 형 에이전트(Luna/Kimi)를 굴려주는 껍데기.

    · 에뮬 도구 호출은 env.step() 으로 보내기 **전에** 가로챈다.
    · trajectory.jsonl 을 claude_cua 와 **같은 스키마**로 쓴다
      ({"step","reasoning","tools":[라벨,...]}) → run_chain 의 classify() 가 그대로 돈다.
    · GUI/도구 선택 비율을 센다 → "조건이 달랐던 것 아니냐"에 대한 근거.
    """

    def __init__(self, env, *, model: str, emu=None, unsupported_requested=None,
                 sleep_after_execution: float = 1.0, verbose: bool = True, **kwargs):
        super().__init__(env, model=model, verbose=verbose, **kwargs)
        self.emu = emu
        self.unsupported_requested = list(unsupported_requested or [])
        self.sleep_after_execution = sleep_after_execution

    @abstractmethod
    def predict(self, instruction: str, obs: Dict[str, Any]) -> StepOutput: ...

    @staticmethod
    def _label(action: str) -> str:
        return " ".join(str(action).split())[:240]

    def _tools_map(self) -> Dict[str, str]:
        tools = {"computer": "native"}
        for name in (self.emu.enabled if self.emu else []):
            tools[name] = "emulated"
        return tools

    def run_episode(self, instruction: str, max_steps: int = 30,
                    result_dir: Optional[str] = None) -> EpisodeResult:
        self.reset()
        emu = self.emu
        files_at_start = emu.memory_files_at_start() if emu else 0
        if emu:
            emu.begin_episode()
            emu.result_dir = result_dir or emu.result_dir

        obs = self.env._get_obs()
        termination, final_text, steps = "max_steps", "", 0

        for step in range(1, max_steps + 1):
            steps = step
            if emu:
                emu.set_step(step)
            decorated = emu.decorate(instruction) if emu else instruction
            out = self.predict(decorated, obs)
            final_text = out.response or final_text
            reasoning = (out.response or "").strip()
            labels: List[str] = []
            stop = False
            if self.verbose:
                said = display_reasoning(reasoning)
                if said:
                    print(f"  [step {step}] {self.tag}: {said}")

            if not out.actions:
                token = sentinel_in_prose(out.response)
                if token in DONE_TOKENS:
                    termination, label = "done", "DONE(prose)"
                elif token in FAIL_TOKENS:
                    termination, label = "fail", "FAIL(prose)"
                elif token in WAIT_TOKENS:
                    # 대기만 하고 다음 스텝으로 (종료 아님)
                    labels.append("WAIT(prose)")
                    self._log_step(result_dir, step, reasoning, labels, obs)
                    time.sleep(self.sleep_after_execution)
                    continue
                else:
                    termination, label = "error", "no-action"
                labels.append(label)
                self._log_step(result_dir, step, reasoning, labels, obs)
                break

            for action in out.actions:
                act = str(action).strip()
                if not act:
                    continue

                # (1) 종료 신호는 조각내기보다 먼저 (문자열 그대로 비교)
                upper = act.upper()
                if upper in DONE_TOKENS:
                    labels.append("DONE"); termination = "done"; stop = True; break
                if upper in FAIL_TOKENS:
                    labels.append("FAIL"); termination = "fail"; stop = True; break
                if TERMINATE_PAT.search(act):
                    labels.append("terminate")
                    termination = "done" if "success" in act.lower() else "fail"
                    stop = True; break
                if upper in WAIT_TOKENS:
                    labels.append("WAIT")
                    time.sleep(self.sleep_after_execution)
                    continue

                # (2) 도구 조각과 VM 조각으로 나눠 순서대로 실행.
                #     도구가 꺼져 있으면 segments() 가 통째로 ("vm", act) 를 돌려주므로
                #     stock 과 완전히 같은 경로가 된다.
                pieces = (emu.segments(act, raw_response=out.response or "")
                          if emu else [("vm", act)])
                for kind, payload in pieces:
                    if kind != "vm":
                        labels.append(emu.execute(kind, payload).label)
                        continue
                    if emu:
                        emu.note_gui(payload)
                    labels.append(self._label(payload))
                    try:
                        obs, _reward, done, _info = self.env.step(
                            payload, self.sleep_after_execution)
                    except Exception as exc:                  # noqa: BLE001
                        labels.append(f"error:{type(exc).__name__}")
                        termination = "error"; stop = True; break
                    if done:
                        termination = "done"; stop = True; break
                if stop:
                    break

            if self.verbose and labels:
                print(f"  [step {step}] action -> "
                      + ", ".join(" ".join(str(x).split())[:70] for x in labels))
            self._log_step(result_dir, step, reasoning, labels, obs)
            if stop:
                break

        res = EpisodeResult(
            final_text=final_text, termination=termination, steps=steps, usage={},
            model=self.model, agent=self.name,
            tools_enabled=self._tools_map(),
            unsupported_requested=self.unsupported_requested,
            memory_files_at_start=files_at_start,
        )
        if emu:
            c = emu.counters
            res.memory_arm = emu.memory_arm
            res.memstore_dir = emu.memstore_dir
            res.memory_views = c.memory_views
            res.memory_writes = c.memory_writes
            res.memory_recalled_via_tool = c.memory_views > 0
            res.approval_requests = c.approval_requests
            res.approval_grants = c.approval_grants
            res.approval_denials = c.approval_denials
            res.tool_syntax_errors = c.syntax_errors
            res.tool_lenient_accepts = c.lenient_accepts
            res.tool_choice_counts = {"gui": c.gui_actions, "tool": c.tool_actions,
                                      "bash": c.bash_calls,
                                      "typed_tool_calls": c.typed_tool_calls}
        return res

    def _log_step(self, result_dir, step, reasoning, labels, obs) -> None:
        if not result_dir:
            return
        record = {"step": step, "reasoning": reasoning, "tools": labels}
        try:
            os.makedirs(result_dir, exist_ok=True)
            shot = obs.get("screenshot") if isinstance(obs, dict) else None
            if shot:
                name = f"step_{step:03d}.png"
                with open(os.path.join(result_dir, name), "wb") as fh:
                    fh.write(shot)
                record["screenshot"] = name
            with open(os.path.join(result_dir, "trajectory.jsonl"), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            if self.verbose:
                print(f"  [step {step}] 기록 실패: {exc}")
