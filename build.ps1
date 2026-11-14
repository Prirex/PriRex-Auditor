"""Скрипт сборки Windows-дистрибутива.

1. (по желанию) создаёт виртуальное окружение и ставит зависимости;
2. прогоняет тесты;
3. собирает onefile-exe через PyInstaller;
4. кладёт готовый файл в корень проекта (рядом с main.py), чтобы не искать его
   в dist/, и печатает путь и размер.

Запуск:  powershell -ExecutionPolicy Bypass -File build.ps1
"""

param(
    [switch]$SkipTests,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$exeName = "PriRex Auditor.exe"
$specName = "PriRex Auditor.spec"

Write-Host "== PriRex Auditor: сборка ==" -ForegroundColor Green
Write-Host "Каталог: $root"

# 0. Активы (логотип -> png/ico), если их нет
if (-not (Test-Path "assets/logo.ico")) {
    Write-Host "-- Генерирую логотип и иконку" -ForegroundColor Yellow
    python tools/make_assets.py
}

# 1. Тесты
if (-not $SkipTests) {
    Write-Host "-- Тесты" -ForegroundColor Yellow
    python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Тесты не прошли — сборка остановлена" }
}

# 2. Чистка
if ($Clean) {
    Write-Host "-- Удаляю build/ dist/" -ForegroundColor Yellow
    Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
}

# 3. Сборка
Write-Host "-- PyInstaller" -ForegroundColor Yellow
python -m PyInstaller $specName --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller завершился с ошибкой" }

# 4. Переносим в корень проекта (в dist копию не оставляем — не дублируем 117 МБ)
$distExe = Join-Path $root "dist/$exeName"
if (-not (Test-Path $distExe)) { throw "Не найден $distExe" }

$rootExe = Join-Path $root $exeName
Move-Item -LiteralPath $distExe -Destination $rootExe -Force
Remove-Item -Recurse -Force (Join-Path $root "dist") -ErrorAction SilentlyContinue

$size = [math]::Round((Get-Item $rootExe).Length / 1MB, 1)
Write-Host ""
Write-Host "Готово: $rootExe ($size МБ)" -ForegroundColor Green
Write-Host "Запуск: просто откройте «$exeName» в папке проекта." -ForegroundColor Green
