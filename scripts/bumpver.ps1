# Define the paths to the files that need version updates
$mainPyPath = "src\main.py"
$manifestXmlPath = "manifest.xml"
$fileVersionInfoPath = "file_version_info.txt"

# Fetch the latest tags from the remote repository
git fetch --tags

# Get the latest tag
$latestTag = git describe --tags --abbrev=0

# Extract the version number from the latest tag
$newVersion = $latestTag -replace "v", ""

Write-Host "Latest tag: $latestTag"
Write-Host "New version: $newVersion"

# Function to update version in a file
function Update-VersionInFile {
    param (
        [string]$filePath,
        [string]$pattern,
        [string]$replacement
    )
    (Get-Content $filePath) -replace $pattern, $replacement | Set-Content $filePath
}

# Update version in main.py
Update-VersionInFile -filePath $mainPyPath -pattern 'APP_VERSION = ".*"' -replacement "APP_VERSION = `"$newVersion`""

# Update version in manifest.xml
Update-VersionInFile -filePath $manifestXmlPath -pattern 'version="[0-9.]*"' -replacement "version=`"$newVersion.0`""

# Update version in file_version_info.txt
Update-VersionInFile -filePath $fileVersionInfoPath -pattern 'filevers=\(.*\)' -replacement "filevers=($($newVersion -replace '\.', ','),0)"
Update-VersionInFile -filePath $fileVersionInfoPath -pattern 'prodvers=\(.*\)' -replacement "prodvers=($($newVersion -replace '\.', ','),0)"
Update-VersionInFile -filePath $fileVersionInfoPath -pattern "StringStruct\(u'FileVersion', u'.*'\)" -replacement "StringStruct(u'FileVersion', u'$newVersion')"
Update-VersionInFile -filePath $fileVersionInfoPath -pattern "StringStruct\(u'ProductVersion', u'.*'\)" -replacement "StringStruct(u'ProductVersion', u'$newVersion')"

# Commit the changes
git config --global user.name "orbi-tal"
git config --global user.email "stalkmode01@gmail.com"
git add $mainPyPath $manifestXmlPath $fileVersionInfoPath
git commit -m "Bump version to $latestTag"

# Push the changes to the correct branch
$branchName = git branch --show-current
git push origin $branchName

Write-Host "Version bump completed and changes pushed to branch: $branchName"
