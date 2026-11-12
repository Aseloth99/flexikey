@echo off
setlocal
cd /d "%~dp0"

rem Builds dist\FlexiKey.exe and dist\FlexiKey.zip (the exe at the archive root) with PyInstaller.
rem   build.bat                          picks the first Python with pip: py -3.12, py -3.13, py -3, py
rem   set PYTHON=py -3.12 & build.bat    uses the given Python command

if defined PYTHON (
    set "PY=%PYTHON%"
) else (
    set "PY="
    for %%P in ("py -3.12" "py -3.13" "py -3" "py") do (
        if not defined PY (
            call %%~P -m pip --version >nul 2>&1
            if not errorlevel 1 set "PY=%%~P"
        )
    )
)
if not defined PY (
    echo ERROR: no Python with pip was found. Install Python 3.12 or newer, or set PYTHON.
    exit /b 1
)

echo [1/3] Installing dependencies from requirements-dev.txt...
call %PY% -m pip install -r requirements-dev.txt
if errorlevel 1 (
    echo ERROR: could not install the dependencies.
    exit /b 1
)

echo [2/3] Removing previous build output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/3] Building dist\FlexiKey.exe...
call %PY% -m PyInstaller FlexiKey.spec --clean --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller failed.
    exit /b 1
)

echo Packing dist\FlexiKey.zip...
copy /y LICENSE dist\LICENSE >nul
> pack.py echo import zipfile
>> pack.py echo z_name = "dist/FlexiKey.zip"
>> pack.py echo z = zipfile.ZipFile(z_name, "w", zipfile.ZIP_DEFLATED)
>> pack.py echo z.write("dist/FlexiKey.exe", "FlexiKey.exe")
>> pack.py echo z.write("dist/LICENSE", "LICENSE")
>> pack.py echo z.close()
call %PY% pack.py
set "PACK_RESULT=%ERRORLEVEL%"
del pack.py
if not "%PACK_RESULT%"=="0" (
    echo ERROR: the zip file could not be created.
    exit /b 1
)

echo Done: dist\FlexiKey.exe and dist\FlexiKey.zip
