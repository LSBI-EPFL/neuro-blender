@echo off
rem Neuro Blender for Windows: double-click this file to open the window of the tool.
rem It needs Miniconda or Anaconda and the conda environment "neuro-blender". README.md, section "Install", tells
rem how to make the environment one time.

cd /d "%~dp0"

rem Find conda: first in the usual install folders, then in the PATH.
set "ACTIVATE="
for %%B in ("%USERPROFILE%\miniconda3" "%USERPROFILE%\anaconda3" "%USERPROFILE%\miniforge3" "%LOCALAPPDATA%\miniconda3" "%LOCALAPPDATA%\anaconda3" "%ProgramData%\miniconda3" "%ProgramData%\anaconda3" "%ProgramData%\miniforge3") do if not defined ACTIVATE if exist "%%~B\Scripts\activate.bat" set "ACTIVATE=%%~B\Scripts\activate.bat"
if not defined ACTIVATE for /f "delims=" %%C in ('where conda.exe 2^>nul') do if not defined ACTIVATE if exist "%%~dpCactivate.bat" set "ACTIVATE=%%~dpCactivate.bat"
if not defined ACTIVATE echo Conda was not found. Install Miniconda or Anaconda: see README.md, section "Install".& pause & exit /b 1

rem Activate the environment, then open the window with no terminal window.
call "%ACTIVATE%" neuro-blender
if /i not "%CONDA_DEFAULT_ENV%"=="neuro-blender" echo The conda environment "neuro-blender" does not exist. Make it one time: see README.md, section "Install".& pause & exit /b 1
start "Neuro Blender" pythonw main.py
