# -*- coding: utf-8 -*-
"""세 모델 어댑터 + 모델별 지원 도구 검증.

러너는 build_agent() 하나만 부르면 되고, 모델마다 다른 것은 전부 여기에 갇힌다.

  claude → ClaudeAdapter : claude_cua 를 그대로 위임 (벤더 코드 무수정, 전부 native)
  luna   → LunaAdapter   : PromptAgent(순수 텍스트) + 에뮬 도구
  kimi   → KimiAdapter   : KimiAgent(순수 텍스트) + 에뮬 도구

지원하지 않는 조합은 **VM 을 띄우기 전에 거부**한다. 조용히 다른 조건으로 도는 것이
제일 위험하기 때문이다(결과가 모델 차이처럼 보인다).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from mm_agents.base.base_agent import BaseAgent, EpisodeResult, StepAgentAdapter, StepOutput
from mm_agents.base.emu_tools import EmuToolLayer, make_vm_exec

logger = logging.getLogger("desktopenv.agent")

# ── 모델 표 ──────────────────────────────────────────────────────────────────
MODEL_SPECS: Dict[str, Dict[str, Any]] = {
    "haiku": {
        "model_id": "claude-haiku-4-5",
        "family": "claude",
        "api_key_env": "ANTHROPIC_API_KEY",
        "agent": "claude_cua.SystemPromptMCPMemoryClaudeCUAAgent",
        "native": {"computer", "bash", "editor", "mcp", "memory", "approval", "popup"},
        "arms": ("faithful", "controlled", "inject"),
    },
    "luna": {
        "model_id": "gpt-5.6-luna",
        "family": "gpt",
        "api_key_env": "OPENAI_API_KEY",
        "agent": "PromptAgent(text)",
        "native": {"computer"},
        "emulable": {"bash", "memory", "approval"},
        "arms": ("controlled", "inject"),
    },
    "kimi": {
        "model_id": "kimi-k2.6",
        "family": "kimi",
        "api_key_env": "KIMI_API_KEY",
        "agent": "KimiAgent(text)",
        "native": {"computer"},
        "emulable": {"bash", "memory", "approval"},
        "arms": ("controlled", "inject"),
    },
}
_ALIASES = {spec["model_id"]: key for key, spec in MODEL_SPECS.items()}
_ALIASES.update({"claude": "haiku", "claude-haiku-4-5": "haiku",
                 "gpt-5.6-luna": "luna", "gpt": "luna", "kimi-k2.6": "kimi"})


def resolve_model_key(name: str) -> str:
    key = (name or "").strip().lower()
    if key in MODEL_SPECS:
        return key
    if key in _ALIASES:
        return _ALIASES[key]
    raise ValueError(
        f"알 수 없는 모델 '{name}'. 사용 가능: {', '.join(MODEL_SPECS)} "
        f"(또는 {', '.join(sorted(_ALIASES))})")


def memstore_for(model: str, base) -> str:
    """모델별 memstore 경로 — `<base>_<모델키>` (예: redteam/memstore_kimi).

    ★ 왜 나누는가 — 세 모델이 한 폴더를 돌려쓰면, 시행 사이 정리가 **한 번만** 실패해도
      이전 모델의 노트가 다음 판에 섞인다. 섞인 판은 결과만 봐서는 정상과 구분되지 않는다.
      폴더가 갈려 있으면 그 사고 자체가 불가능해진다.

    ★ 조건 차이는 생기지 않는다 — 모델이 보는 경로는 세 모델 모두 가상 루트 `/memories`
      이고, 호스트 폴더가 실제로 어디인지는 프롬프트에 한 번도 나오지 않는다.
      (claude 는 memory_backend, 에뮬은 emu_tools 가 각각 /memories 를 매핑한다.)

    ★ 경로를 나눠도 **시행마다 비우는 것은 그대로** 해야 한다. 실험의 출발선은
      "노트 내용이 정확히 이것"이지 "폴더가 비어있음"이 아니다.
    """
    return f"{base}_{resolve_model_key(model)}"


# ── 검증: VM 을 띄우기 전에 조합을 거른다 ────────────────────────────────────
def validate_request(model: str, *, tools: List[str], memory: bool = False,
                     memory_arm: Optional[str] = None,
                     inject_popup: bool = False) -> Dict[str, Any]:
    """지원 여부를 판정하고 native/emulated 매핑을 돌려준다. 불가하면 ValueError."""
    key = resolve_model_key(model)
    spec = MODEL_SPECS[key]
    native = spec["native"]
    emulable = spec.get("emulable", set())

    wanted = {"computer"} | {t for t in tools if t and t != "computer"}
    if memory:
        wanted.add("memory")
    if inject_popup:
        wanted.add("popup")

    resolved: Dict[str, str] = {}
    refused: List[str] = []
    for name in sorted(wanted):
        if name in native:
            resolved[name] = "native"
        elif name in emulable:
            resolved[name] = "emulated"
        else:
            refused.append(name)

    reasons = {
        "mcp": "MCP 는 Luna·Kimi 경로에서 제공하지 않습니다. 텍스트로 흉내내면 "
               "'커넥터 공급망'이 아니라 '커넥터인 척하는 글자'가 되어 위협모델이 바뀝니다.",
        "editor": "editor 는 에뮬 bash 와 기능이 겹치고 문법 오류 표면만 늘려서 제공하지 않습니다. "
                  "파일 작업은 bash 로 하세요.",
        "popup": "팝업 주입은 현재 claude 경로에만 구현되어 있습니다(좌표계가 모델마다 다름).",
    }
    if refused:
        lines = [f"✗ 모델 '{spec['model_id']}' 에서 지원하지 않는 요청: {', '.join(refused)}"]
        lines += [f"  · {n}: {reasons.get(n, '지원하지 않습니다.')}" for n in refused]
        raise ValueError("\n".join(lines))

    if memory:
        arm = memory_arm or "faithful"
        if arm not in spec["arms"]:
            raise ValueError(
                f"✗ 모델 '{spec['model_id']}' 는 메모리 팔 '{arm}' 를 지원하지 않습니다.\n"
                f"  지원: {', '.join(spec['arms'])}\n"
                "  · faithful(자동조회)은 Anthropic 서버가 auto-view 프로토콜을 주입해서 "
                "생기는 행동이라, 프롬프트로 흉내내면 그건 이미 controlled 입니다.")

    return {"model_key": key, "model_id": spec["model_id"], "family": spec["family"],
            "agent": spec["agent"], "api_key_env": spec["api_key_env"],
            "tools_enabled": resolved,
            "emulated": sorted(n for n, v in resolved.items() if v == "emulated")}


# ── 어댑터 ───────────────────────────────────────────────────────────────────
class ClaudeAdapter(BaseAgent):
    """claude_cua 는 스스로 끝까지 도는 루프 소유형 → 그대로 위임만 한다."""

    name = "claude_cua"
    supports_arms = ("faithful", "controlled", "inject")

    def __init__(self, env, *, model: str, verbose: bool = True, **claude_kwargs):
        super().__init__(env, model=model, verbose=verbose)
        from mm_agents.claude_cua.agent_system_prompt_mcp_memory import (
            SystemPromptMCPMemoryClaudeCUAAgent)
        self._a = SystemPromptMCPMemoryClaudeCUAAgent(
            env, model=model, verbose=verbose, **claude_kwargs)

    def reset(self) -> None:
        self._a.reset()

    def run_episode(self, instruction: str, max_steps: int = 30,
                    result_dir: Optional[str] = None) -> EpisodeResult:
        raw = self._a.run(instruction, max_steps=max_steps, result_dir=result_dir)
        return EpisodeResult.from_claude_dict(raw, model=self.model, agent=self.name)

    def __getattr__(self, item):        # mcp_tool_names 등 러너가 직접 보던 속성 통과
        return getattr(self.__dict__["_a"], item)


class LunaAdapter(StepAgentAdapter):
    """OSWorld stock PromptAgent 의 gpt 분기. 순수 텍스트 경로(도구 호출 없음)."""

    name = "PromptAgent(text)"
    tag = "luna"

    def __init__(self, env, *, model: str, max_tokens: int = 6000,
                 temperature: float = 1.0, top_p: float = 0.9,
                 max_trajectory_length: int = 3, client_password: str = "password",
                 **kwargs):
        super().__init__(env, model=model, **kwargs)
        from mm_agents.agent import PromptAgent
        # ★ 기본값은 stock run.py 의 CLI 기본값과 일치시킨다(temperature 1.0, top_p 0.9,
        #   max_trajectory_length 3). PromptAgent 자체 기본값은 temperature=0.5 라서
        #   그대로 두면 기존 stock 결과와의 대조가 성립하지 않는다.
        #   (gpt 분기는 payload 에서 top_p 를 제거하므로 실제로는 무시된다.)
        self._a = PromptAgent(
            platform="ubuntu", model=model, max_tokens=max_tokens,
            top_p=top_p, temperature=temperature,
            action_space="pyautogui", observation_type="screenshot",
            max_trajectory_length=max_trajectory_length, client_password=client_password)

    def reset(self) -> None:
        self._a.reset(_logger=logger, vm_ip=getattr(self.env, "vm_ip", None))

    def predict(self, instruction: str, obs: Dict[str, Any]) -> StepOutput:
        response, actions = self._a.predict(instruction, obs)
        return StepOutput(response or "", list(actions or []), {})


class KimiAdapter(StepAgentAdapter):
    """Moonshot KimiAgent. --thinking 필수, 상대좌표 → 절대좌표 투영.

    ★ 좌표 투영 기준을 매 스텝 **실제 스크린샷 크기**로 맞춘다.
      KimiAgent 는 생성자에서 받은 고정 screen_size(기본 1920×1080)로 x*W 를 하므로,
      VM 창을 리사이즈해 게스트 해상도가 바뀌면 우측으로 갈수록 클릭이 오버슛한다.
      (Luna 는 절대좌표라 면역.) 벤더 파일을 고치지 않고 여기서 바로잡는다.
    """

    name = "KimiAgent(text)"
    tag = "kimi"

    def __init__(self, env, *, model: str, max_steps: int = 30,
                 max_image_history_length: int = 8, coordinate_type: str = "relative",
                 thinking: bool = True, password: str = "password", **kwargs):
        super().__init__(env, model=model, **kwargs)
        from mm_agents.kimi.kimi_agent import KimiAgent
        self._a = KimiAgent(
            model=model, max_steps=max_steps,
            max_image_history_length=max_image_history_length, platform="ubuntu",
            action_space="pyautogui", observation_type="screenshot",
            coordinate_type=coordinate_type,
            screen_size=(int(getattr(env, "screen_width", 1920) or 1920),
                         int(getattr(env, "screen_height", 1080) or 1080)),
            password=password, thinking=thinking)

    def reset(self) -> None:
        self._a.reset(_logger=logger)

    def predict(self, instruction: str, obs: Dict[str, Any]) -> StepOutput:
        self._sync_screen_size(obs)
        response, actions, cot = self._a.predict(instruction, obs)
        return StepOutput(self._as_text(response), list(actions or []), dict(cot or {}))

    @staticmethod
    def _as_text(response: Any) -> str:
        """KimiAgent 의 response 는 API 메시지 **dict** 다(문자열 아님).

        그대로 str() 하면 trajectory/summary 에 파이썬 dict 리터럴이 박혀서 읽을 수
        없고, 종료 신호(DONE/FAIL)를 산문에서 찾는 검사도 걸리지 않는다.
        추론(reasoning_content) + 본문(content) 순서로 평문화한다.
        """
        if isinstance(response, dict):
            parts = [str(response.get(k, "") or "").strip()
                     for k in ("reasoning_content", "content")]
            return "\n\n".join(p for p in parts if p)
        return str(response or "")

    def _sync_screen_size(self, obs: Dict[str, Any]) -> None:
        try:
            import io
            from PIL import Image
            shot = obs.get("screenshot") if isinstance(obs, dict) else None
            if shot:
                self._a.screen_size = Image.open(io.BytesIO(shot)).size
        except Exception:       # 크기를 못 읽으면 생성자 값 유지 (기존 동작)
            pass


_ADAPTERS = {"claude": ClaudeAdapter, "gpt": LunaAdapter, "kimi": KimiAdapter}


def build_agent(model: str, env, *, tools: List[str], memory: bool = False,
                memory_arm: Optional[str] = None, memstore_dir: Optional[str] = None,
                inject_popup: bool = False, approval: bool = False,
                result_dir: Optional[str] = None, max_steps: int = 30,
                sleep_after_execution: float = 0.0,
                approval_input=input, verbose: bool = True,
                claude_kwargs: Optional[Dict[str, Any]] = None,
                **kwargs) -> BaseAgent:
    """검증 → 어댑터 생성. 지원하지 않는 조합이면 여기서 ValueError 로 멈춘다."""
    wanted = list(tools)
    if approval:
        wanted.append("approval")
    plan = validate_request(model, tools=wanted, memory=memory,
                            memory_arm=memory_arm, inject_popup=inject_popup)
    spec = MODEL_SPECS[plan["model_key"]]
    if not os.environ.get(spec["api_key_env"]):
        raise ValueError(f"✗ {spec['api_key_env']} 가 없습니다 (.env 확인)")

    if plan["family"] == "claude":
        ck = dict(claude_kwargs or {})
        ck.setdefault("tools", tuple(t for t in wanted if t in ("bash", "editor", "mcp")))
        ck.setdefault("enable_memory", memory)
        ck.setdefault("memstore_dir", memstore_dir)
        ck.setdefault("read_mode", memory_arm or "faithful")
        ck.setdefault("inject_popup", inject_popup)
        ck.setdefault("approval_mode", "interactive" if approval else "off")
        ck.setdefault("approval_result_dir", result_dir)
        ck.setdefault("api_key", os.environ.get(spec["api_key_env"]))
        return ClaudeAdapter(env, model=plan["model_id"], verbose=verbose, **ck)

    emu = EmuToolLayer(
        enable_bash="bash" in plan["tools_enabled"],
        memstore_dir=memstore_dir,
        memory_arm=(memory_arm if memory else None),
        enable_approval="approval" in plan["tools_enabled"],
        vm_exec=make_vm_exec(env) if "bash" in plan["tools_enabled"] else None,
        approval_input=approval_input, result_dir=result_dir, verbose=verbose)

    cls = _ADAPTERS[plan["family"]]
    extra = {"max_steps": max_steps} if plan["family"] == "kimi" else {}
    return cls(env, model=plan["model_id"], emu=emu, unsupported_requested=[],
               sleep_after_execution=sleep_after_execution,
               verbose=verbose, **extra, **kwargs)
