#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""§7 영향 범위 분류 재현 스크립트.

OSWorld 저장소 루트에서 실행:
    python3 classify_tasks.py [--root .]

369개 태스크를 다음으로 분류한다.
  - evaluator 의 result.type 에 vm_file 이 있는가 (게스트 파일을 평가 환경으로 회수)
  - 그 태스크가 어떤 채점 함수를 쓰는가
정적 분석이며 실행을 수반하지 않는다.
"""
import argparse, collections, glob, json, os, sys


def as_list(x):
    return x if isinstance(x, list) else [x]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="OSWorld 저장소 루트")
    args = ap.parse_args()

    pat = os.path.join(args.root, "evaluation_examples", "examples", "**", "*.json")
    files = sorted(glob.glob(pat, recursive=True))
    if not files:
        sys.exit(f"태스크 JSON 없음: {pat}")

    total = 0
    vm_pull = 0
    func_of_vmpull = collections.Counter()
    target_tasks = []
    TARGET = "check_python_file_by_test_suite"

    for f in files:
        try:
            t = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        ev = t.get("evaluator")
        if not isinstance(ev, dict):
            continue
        total += 1
        funcs = [x for x in as_list(ev.get("func")) if isinstance(x, str)]
        res_types = [r.get("type") for r in as_list(ev.get("result") or {}) if isinstance(r, dict)]

        if TARGET in funcs:
            target_tasks.append(os.path.relpath(f, args.root))
        if "vm_file" in res_types:
            vm_pull += 1
            for fn in funcs:
                func_of_vmpull[fn] += 1

    print(f"evaluator 를 가진 태스크                     : {total}")
    print(f"vm_file 로 게스트 파일을 평가 환경으로 회수  : {vm_pull}")
    print(f"회수하지 않음                                : {total - vm_pull}")
    print()
    print(f"'{TARGET}' 를 선언한 태스크 : {len(target_tasks)}")
    for p in target_tasks:
        print(f"    {p}")
    print()
    print("vm_file 을 받아 처리하는 채점 함수 (상위 25)")
    for fn, c in func_of_vmpull.most_common(25):
        mark = "  ← 본 건" if fn == TARGET else ""
        print(f"  {c:4d}  {fn}{mark}")
    print()
    print("정적 위험 싱크 스캔은 아래 명령으로:")
    print('  grep -rn "exec_module\\|\\beval(\\|pickle\\.load\\|yaml\\.load(\\|extractall\\|'
          'unpack_archive\\|os\\.system\\|shell=True" desktop_env/evaluators/metrics/ | grep -v "\\.pyc"')


if __name__ == "__main__":
    main()
