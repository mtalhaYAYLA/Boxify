@echo off
REM Boxify'i uygulama menusune (Windows) kaydeder.
REM Kullanim:  kur.bat          - kur
REM            kur.bat kaldir   - kaldir
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kur.ps1" %1
