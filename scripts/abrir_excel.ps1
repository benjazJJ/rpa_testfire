# Evaluacion 3 - Subproceso 3 (escritorio): abre el reporte final en la aplicacion Excel.
#
# 1. Abre Excel (visible) por automatizacion COM, sin librerias extra.
# 2. Ajusta el ancho de columnas y muestra la hoja "Referencia externa".
# 3. Saca una captura de pantalla como evidencia (excel_abierto_<fecha>.png).
# 4. Guarda y CIERRA el libro y Excel (si quedara abierto, el performer no
#    podria escribir la hoja de seguimiento).
#
# Uso: powershell -ExecutionPolicy Bypass -File abrir_excel.ps1 -Salida <carpeta> [-Archivo <xlsx>] [-Segundos 4]
param(
    [Parameter(Mandatory = $true)][string]$Salida,
    [string]$Archivo = "",
    [int]$Segundos = 4
)
$ErrorActionPreference = "Stop"
$excel = $null
$libro = $null
try {
    if (-not $Archivo) {
        $ultimo = Get-ChildItem -Path $Salida -Filter "reporte_final_*.xlsx" |
            Where-Object { $_.Name -notlike "~$*" -and $_.Name -ne "reporte_final_ultimo.xlsx" } |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $ultimo) { throw "No hay reporte_final_*.xlsx en $Salida" }
        $Archivo = $ultimo.FullName
    }
    if (-not (Test-Path $Archivo)) { throw "No existe $Archivo" }

    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $true
    $excel.DisplayAlerts = $false
    $libro = $excel.Workbooks.Open($Archivo)
    $hojas = @()
    foreach ($hoja in $libro.Worksheets) {
        $null = $hoja.UsedRange.Columns.AutoFit()
        $hojas += $hoja.Name
    }
    $libro.Worksheets.Item("Referencia externa").Activate()
    $excel.WindowState = -4137   # maximizada
    Start-Sleep -Seconds $Segundos

    Add-Type -AssemblyName System.Windows.Forms, System.Drawing
    $pantalla = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $imagen = New-Object System.Drawing.Bitmap $pantalla.Width, $pantalla.Height
    $grafico = [System.Drawing.Graphics]::FromImage($imagen)
    $grafico.CopyFromScreen($pantalla.Location, [System.Drawing.Point]::Empty, $pantalla.Size)
    $captura = Join-Path $Salida ("excel_abierto_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".png")
    $imagen.Save($captura, [System.Drawing.Imaging.ImageFormat]::Png)
    $grafico.Dispose(); $imagen.Dispose()

    $libro.Save()
    $libro.Close($true)
    $libro = $null
    $excel.Quit()
    @{ ok = $true; archivo = $Archivo; hojas = $hojas; captura = $captura } | ConvertTo-Json -Compress
    exit 0
}
catch {
    @{ ok = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress
    exit 2
}
finally {
    if ($libro) { try { $libro.Close($false) } catch {} }
    if ($excel) {
        try { $excel.Quit() } catch {}
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
    }
}
