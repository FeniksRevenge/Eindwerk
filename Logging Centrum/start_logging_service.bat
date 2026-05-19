@echo off
REM Stop alle containers en verwijder ze
cd /d %~dp0
cd "School\Eindwerk\Logging Centrum"
docker compose down
REM Bouw alles opnieuw en start
docker compose up --build
pause
