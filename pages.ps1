$headers = @{
    "Authorization" = "token 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"
    "Accept" = "application/vnd.github.v3+json"
    "Content-Type" = "application/json"
}
$body = '{"source":{"branch":"main","path":"/"}}'
try {
    $r = Invoke-RestMethod -Uri "https://api.github.com/repos/Yossi20000/pubg-tournament/pages" -Method POST -Headers $headers -Body $body
    Write-Host "Pages enabled! URL: $($r.html_url)"
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    Write-Host "Status: $code"
    if ($code -eq 409) { Write-Host "Pages already enabled - OK!" -ForegroundColor Green }
    else { Write-Host $_.Exception.Message }
}
