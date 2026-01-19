@echo off
echo Installing Python packages from requirements.txt...
echo.

pip install -r requirements.txt

if %errorlevel% equ 0 (
    echo.
    echo Installation completed successfully!
) else (
    echo.
    echo Installation failed. Please check the error messages above.
)

echo.
pause