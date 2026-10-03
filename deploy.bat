@echo off
setlocal
cd /d "%~dp0"

git add -A -- . ":(exclude)AGENTS.md"
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "chore: deploy dashboard updates"
  if errorlevel 1 goto :error
)

git pull --rebase origin master
if errorlevel 1 goto :error

git push origin master
if errorlevel 1 goto :error

echo.
echo Deployment request completed. Check GitHub Actions for completion.
pause
exit /b 0

:error
echo.
echo Deployment stopped. Read the message above before trying again.
pause
exit /b 1
