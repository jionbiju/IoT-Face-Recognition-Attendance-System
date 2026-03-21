@echo off
echo ======================================================================
echo RETRAINING FACE RECOGNITION MODEL
echo ======================================================================
echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat
echo.
echo Running emergency fix...
python emergency_fix.py
echo.
echo Press any key to exit...
pause
