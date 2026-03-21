@echo off
echo Activating virtual environment...
call venv\Scripts\activate

echo.
echo Retraining with FaceNet...
python retrain_with_facenet.py

echo.
pause
