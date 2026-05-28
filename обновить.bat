@echo off
cd /d "%~dp0"
echo.
echo  Отправка обновлений в репозиторий...
echo.

:: Настраиваем remote если ещё не задан
git remote get-url origin >nul 2>&1
if errorlevel 1 (
    git remote add origin https://fimbetth:d17m10y02172H@proxyapn.umxx.ru/git/fimbetth/uspd-export.git
)

git add .
git status --short
echo.
set /p MSG="Комментарий (Enter = update): "
if "%MSG%"=="" set MSG=update
git -c http.sslVerify=false commit -m "%MSG%"
git -c http.sslVerify=false push origin main
echo.
echo  Готово.
pause
