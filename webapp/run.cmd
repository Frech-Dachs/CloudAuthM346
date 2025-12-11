@echo off
setlocal

REM Move to the directory where this script lives
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%"

REM Ensure a local venv exists inside webapp
if not exist ".venv" (
    python -m venv .venv
)

REM Activate venv
call ".venv\\Scripts\\activate"

REM Install dependencies
pip install -r requirements.txt

REM Launch FastAPI app with uvicorn (app lives in this directory)
python -m uvicorn main:app --reload

popd
endlocal
