@echo off
setlocal
cd /d "%~dp0"

rem =====================================================================
rem  Sudoku launcher (Windows)
rem  1) locate a Python interpreter  2) make sure pygame is there
rem  3) run the game, passing through any extra arguments
rem =====================================================================

set "PYEXE="

rem --- 1) Windows official launcher "py" is the most reliable, try it first ---
where py >nul 2>nul
if not errorlevel 1 set "PYEXE=py -3"
if defined PYEXE goto check_deps

where python >nul 2>nul
if not errorlevel 1 set "PYEXE=python"
if defined PYEXE goto check_deps

goto no_python

:check_deps
%PYEXE% -c "import pygame" >nul 2>nul
if errorlevel 1 goto install_deps
goto run

:install_deps
echo pygame is not installed, installing it now...
rem Try the Tencent Cloud mirror first, then fall back to the official PyPI.
rem (pypi.tuna.tsinghua.edu.cn now answers 403 to recent pip versions.)
%PYEXE% -m pip install --disable-pip-version-check -i https://mirrors.cloud.tencent.com/pypi/simple -r requirements.txt
if not errorlevel 1 goto run
%PYEXE% -m pip install --disable-pip-version-check -r requirements.txt
if not errorlevel 1 goto run

echo No official pygame wheel for this Python, trying pygame-ce...
%PYEXE% -m pip install --disable-pip-version-check -i https://mirrors.cloud.tencent.com/pypi/simple pygame-ce
if not errorlevel 1 goto run
%PYEXE% -m pip install --disable-pip-version-check pygame-ce
if not errorlevel 1 goto run

goto install_failed

:run
echo Launching Sudoku...
%PYEXE% "%~dp0sudoku.py" %*
if errorlevel 1 pause
exit /b 0

:no_python
echo.
echo [ERROR] Python was not found.
echo.
echo   Install Python 3.10 or newer from https://www.python.org/downloads/
echo   and tick "Add python.exe to PATH" during setup.
echo.
pause
exit /b 1

:install_failed
echo.
echo [ERROR] Could not install a pygame package.
echo.
echo   Try it manually:
echo     %PYEXE% -m pip install pygame
echo     %PYEXE% -m pip install pygame-ce
echo.
pause
exit /b 1
