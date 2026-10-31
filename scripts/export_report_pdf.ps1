# Export the technical report .docx to PDF with Microsoft Word (local only; CI reads the
# committed PDF) and print Word's own page count. Usage, from the repository root:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/export_report_pdf.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$docx = Join-Path $root "docs\report\cascadeguard-report.docx"
$pdf = Join-Path $root "docs\report\cascadeguard-report.pdf"
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0  # wdAlertsNone: never wait on a dialog
try {
    # ConfirmConversions false, ReadOnly true, AddToRecentFiles false
    $doc = $word.Documents.Open($docx, $false, $true, $false)
    try {
        $pages = $doc.ComputeStatistics(2)  # wdStatisticPages
        $doc.SaveAs2($pdf, 17)  # wdFormatPDF
        Write-Output "wrote docs/report/cascadeguard-report.pdf ($pages pages per Word)"
    } finally {
        $doc.Close($false)
    }
} finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
