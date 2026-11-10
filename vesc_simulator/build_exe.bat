@echo off
REM Génère dist\VESC_SIMULATOR_PRO\VESC_SIMULATOR_PRO.exe (Windows 10/11, Python 3.12 recommandé)
python -m pip install -r requirements.txt -r requirements-dev.txt || goto :err
python -m pytest -q tests || goto :err
python -m PyInstaller --noconfirm --clean --windowed --name VESC_SIMULATOR_PRO ^
  --add-data "profiles;profiles" ^
  --hidden-import can.interfaces.virtual --hidden-import can.interfaces.slcan ^
  --collect-submodules winrt ^
  main.py || goto :err
echo.
echo OK : dist\VESC_SIMULATOR_PRO\VESC_SIMULATOR_PRO.exe
exit /b 0
:err
echo ECHEC
exit /b 1
