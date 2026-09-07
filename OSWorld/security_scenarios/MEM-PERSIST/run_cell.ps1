# MEM-PERSIST — 셀 실행기 (A/B 계보, 노트 재시딩 방식)
# 실제 로직은 run_cell.py 에 있다(OS 무관). 이 래퍼는 프로젝트 venv(uv)로 실행해 준다.
#   .\run_cell.ps1 <A|B> <faithful|controlled|inject> <cued|benign> [N]
# PowerShell 7.4+ 는 네이티브 명령의 0 아닌 종료코드를 예외로 던진다.
# 실행기는 정상적으로 0 아닌 코드를 낼 수 있으므로 그 동작을 끈다.
$ErrorActionPreference = "Continue"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = (Resolve-Path (Join-Path $Here "..\..")).Path
if (-not (Test-Path (Join-Path $Root "redteam\run_claude_3.py"))) {
    Write-Host "X OSWorld 루트를 못 찾음: $Root"; exit 1
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "X uv 없음 — https://docs.astral.sh/uv/ 참고"; exit 1
}
# PYTHONPATH 는 이 실행 동안만 필요하다. 끝나면 원래대로 되돌린다 —
# 안 그러면 같은 창에서 하는 다른 파이썬 작업까지 OSWorld 루트를 물고 간다.
$SavedPP = $env:PYTHONPATH
Push-Location $Root
try {
    $env:PYTHONPATH = "."
    uv run python "security_scenarios/MEM-PERSIST/run_cell.py" @args
    $code = $LASTEXITCODE
} finally {
    Pop-Location                       # Ctrl+C 로 끊어도 원래 폴더로 돌아온다
    if ($null -eq $SavedPP) { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue }
    else { $env:PYTHONPATH = $SavedPP }
}
exit $code
