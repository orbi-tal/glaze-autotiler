# Create hooks directory if it doesn't exist
$hooksDir = ".git/hooks"
New-Item -ItemType Directory -Force -Path $hooksDir

# Copy the pre-push hook
Copy-Item "scripts/hooks/pre-push.ps1" ".git/hooks/pre-push.ps1" -Force

# Set file permissions (Windows alternative to make executable)
$acl = Get-Acl ".git/hooks/pre-push"
$accessRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    [System.Security.Principal.WindowsIdentity]::GetCurrent().Name,
    "FullControl",
    "Allow"
)
$acl.SetAccessRule($accessRule)
Set-Acl ".git/hooks/pre-push" $acl

Write-Host "Git hooks installed successfully"
