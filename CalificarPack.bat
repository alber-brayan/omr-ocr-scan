@echo off
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" (
  echo Selecciona el ZIP o la carpeta exportada por la app...
  for /f "delims=" %%I in ('powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; $f=New-Object System.Windows.Forms.OpenFileDialog; $f.Filter='Pack OMR|*.zip|Todos|*.*'; $f.Title='ZIP de la app Lectora OMR'; if($f.ShowDialog() -eq 'OK'){$f.FileName}"') do set "SRC=%%I"
  if not defined SRC (
    for /f "delims=" %%I in ('powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description='Carpeta general exportada por la app'; if($d.ShowDialog() -eq 'OK'){$d.SelectedPath}"') do set "SRC=%%I"
  )
) else (
  set "SRC=%~1"
)
if not defined SRC (
  echo Cancelado.
  pause
  exit /b 1
)
python calificar_pack.py "%SRC%"
echo.
pause
