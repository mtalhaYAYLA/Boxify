@echo off
REM Boxify kurulumu (Windows).
REM
REM   kur.bat              - uygulamayi masaustune ve Baslat Menusune kaydet
REM   kur.bat ortam        - Python ortamini kur (conda varsa conda, yoksa venv)
REM   kur.bat ortam conda  - ortami zorla conda ile kur
REM   kur.bat ortam venv   - ortami zorla venv ile kur
REM   kur.bat tam          - once ortam, sonra uygulama kaydi
REM   kur.bat kaldir       - uygulama kaydini geri al
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kur.ps1" %1 %2
