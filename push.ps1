Set-Location "C:\PUBG_Tournament"
$USER = "yossi20000"
$REPO = "pubg-tournament"
$TOKEN = "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"

# Remove token from deploy.ps1 so GitHub doesnt block it
Set-Content -Path "deploy.ps1" -Value "# deploy placeholder"

# Amend commit to overwrite the one with the token
git add deploy.ps1
git commit --amend --no-edit

# Push
$url = "https://" + $USER + ":" + $TOKEN + "@github.com/" + $USER + "/" + $REPO + ".git"
git remote set-url origin $url
git push -u origin main --force
Write-Host "PUSH_DONE"
