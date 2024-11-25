   #!/usr/bin/env pwsh

   Write-Host "Pre-push hook running..."

   # Read standard input for ref information
   $stdin = [Console]::In.ReadLine()
   if ($stdin) {
       $localRef, $localSha, $remoteRef, $remoteSha = $stdin.Split()

       # Check if this is a tag push
       if ($localRef -match "^refs/tags/") {
           $tagName = $localRef -replace "^refs/tags/", ""
           Write-Host "Pushing tag: $tagName"

           # Run the version bump script
           $scriptPath = Join-Path $PSScriptRoot "../../scripts/bumpver.ps1"
           Write-Host "Running version bump script: $scriptPath"

           & $scriptPath

           if ($LASTEXITCODE -ne 0) {
               Write-Error "Version bump script failed"
               exit 1
           }
       } else {
           Write-Host "Not a tag push, skipping version bump"
       }
   }

   exit 0
