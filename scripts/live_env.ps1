# Sets the LIVE_* variables the live smoke tests need, straight from the
# deployed stack. Dot-source it so the variables land in your session:
#
#     . .\scripts\live_env.ps1
#     python -m pytest tests/live -m live
#
# Requires AWS credentials and a terraform state that has been applied.

$json = terraform -chdir=terraform output -json
if ($LASTEXITCODE -ne 0) {
    Write-Error "terraform output failed - is the stack applied and are your AWS credentials set?"
    return
}

$outputs = $json | ConvertFrom-Json

$env:LIVE_API_URL           = $outputs.api_invoke_url.value
$env:LIVE_USER_POOL_ID      = $outputs.user_pool_id.value
$env:LIVE_APP_CLIENT_ID     = $outputs.app_client_id.value
$env:LIVE_BUCKET            = $outputs.resource_bucket_name.value
$env:LIVE_CLOUDFRONT_DOMAIN = $outputs.cloudfront_domain_name.value

Write-Host "LIVE_* environment set for $($env:LIVE_USER_POOL_ID):"
Write-Host "  API        $env:LIVE_API_URL"
Write-Host "  bucket     $env:LIVE_BUCKET"
Write-Host "  CloudFront $env:LIVE_CLOUDFRONT_DOMAIN"
$tokenFile = Join-Path $PSScriptRoot "..\.live-tokens.ps1"
if (Test-Path $tokenFile) {
    . $tokenFile
    Write-Host "  tokens    loaded from .live-tokens.ps1 (valid 60 min from minting)"
} else {
    Write-Host ""
    Write-Host "No tokens yet - run: python scripts\live_tokens.py"
}
