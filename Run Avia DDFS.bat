@echo off
title Avia Cortex - DDFS live service (port 8030)
cd /d "C:\Users\Carte\OneDrive\Avia\Model_refs"
echo Starting the DDFS live service on http://localhost:8030/
echo Cockpit: http://localhost:8030/cockpit   (live: ddfs.aviacortex.com/cockpit)
echo Close this window or press Ctrl+C to stop.
python ddfs_service.py
echo.
echo Service stopped. If it failed to start, check port 8030 is free
echo (an earlier instance may still be running) and that Python is on PATH.
pause
