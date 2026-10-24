$ErrorActionPreference='Stop'
$env:WRANGLER_SEND_METRICS='false'
$env:WRANGLER_LOG='none'
$account='e5a0857508f37d031d9137c3ecec80e3'
$repository='renatirudy246-maker/gate-test'
$statusPath=Join-Path $PSScriptRoot 'local-status.json'
if(Test-Path -LiteralPath $statusPath){throw 'Bootstrap status exists; refusing to recreate or rotate resources'}
$output=(& node "$PSScriptRoot/node_modules/wrangler/bin/wrangler.js" auth token --json 2>$null)-join "`n"
try {
    $auth=$output.Substring($output.IndexOf('{'),$output.LastIndexOf('}')-$output.IndexOf('{')+1)|ConvertFrom-Json
    if(!$auth.token){throw 'missing'}
} catch { throw 'Unable to load authorized CLI credentials safely' }
$headers=@{Authorization=('Bearer '+$auth.token)}
$output=$null
function Invoke-TestAPI($method,$path,$body=$null) {
    $allowed=$path -match '^/workers/scripts/gate-checker-test/(secrets|subdomain)$' -or $path -eq '/storage/kv/namespaces' -or $path -eq '/pages/projects' -or $path -eq '/pages/projects/edgetunnel-test'
    if(!$allowed){throw 'Resource is outside test allowlist'}
    if($method -ne 'Get' -and $path -eq '/storage/kv/namespaces' -and $body.title -ne 'EDGETUNNEL_TEST_KV'){throw 'Invalid KV target'}
    if($method -ne 'Get' -and $path -eq '/pages/projects' -and $body.name -ne 'edgetunnel-test'){throw 'Invalid Pages target'}
    $args=@{Method=$method;Uri=('https://api.cloudflare.com/client/v4/accounts/'+$account+$path);Headers=$headers;TimeoutSec=30}
    if($null -ne $body){$args.ContentType='application/json';$args.Body=($body|ConvertTo-Json -Depth 12 -Compress)}
    try{$response=Invoke-RestMethod @args}catch{throw ('Cloudflare test API failed: '+$method+' '+$path+' HTTP '+[int]$_.Exception.Response.StatusCode)}
    if(!$response.success){throw ('Cloudflare test API unsuccessful: '+$method+' '+$path)}
    return $response.result
}
function New-TestSecret { return [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLowerInvariant() }
function Set-GitHubSecret($name,$value) {
    $value | gh secret set $name --repo $repository
    if($LASTEXITCODE -ne 0){throw ('GitHub Secret write failed: '+$name)}
}
$namespaces=@(Invoke-TestAPI Get '/storage/kv/namespaces')
if($namespaces.title -contains 'EDGETUNNEL_TEST_KV'){throw 'Test KV name exists without local ownership record; stop'}
$projects=@(Invoke-TestAPI Get '/pages/projects')
if($projects.name -contains 'edgetunnel-test'){throw 'Test Pages name exists without local ownership record; stop'}
$checkToken=New-TestSecret
$null=Invoke-TestAPI Put '/workers/scripts/gate-checker-test/secrets' @{name='CHECK_TOKEN';text=$checkToken;type='secret_text'}
Set-GitHubSecret 'CHECK_TOKEN' $checkToken
$checkToken=$null
$kv=Invoke-TestAPI Post '/storage/kv/namespaces' @{title='EDGETUNNEL_TEST_KV'}
$status=@{checker='gate-checker-test';checker_url='https://gate-checker-test.renatirudy246.workers.dev';kv_id=$kv.id;kv_title=$kv.title;created_at=(Get-Date -Format o)}
$status|ConvertTo-Json|Set-Content -LiteralPath $statusPath -Encoding utf8
if($kv.id -eq '3b6aee361811487a832e59e0ed1db112'){throw 'Production KV guard triggered'}
$admin=New-TestSecret
$key=New-TestSecret
$uuid=[Guid]::NewGuid().ToString()
$subToken=New-TestSecret
$variables=@{
    ADMIN=@{type='secret_text';value=$admin}
    KEY=@{type='secret_text';value=$key}
    UUID=@{type='secret_text';value=$uuid}
    SUB_TOKEN=@{type='secret_text';value=$subToken}
    NODES_URL=@{type='plain_text';value='https://renatirudy246-maker.github.io/gate-test/nodes.txt'}
    OFF_LOG=@{type='plain_text';value='1'}
    DEBUG=@{type='plain_text';value='false'}
}
$config=@{compatibility_date='2026-10-24';kv_namespaces=@{KV=@{namespace_id=$kv.id}};env_vars=$variables}
$project=Invoke-TestAPI Post '/pages/projects' @{name='edgetunnel-test';production_branch='main';deployment_configs=@{production=$config;preview=$config}}
$status.pages=$project.name
$status.pages_url=('https://'+$project.subdomain)
$status|ConvertTo-Json|Set-Content -LiteralPath $statusPath -Encoding utf8
Set-GitHubSecret 'TEST_ADMIN' $admin
Set-GitHubSecret 'TEST_SUB_TOKEN' $subToken
$admin=$null;$key=$null;$uuid=$null;$subToken=$null;$variables=$null;$config=$null;$auth=$null;$headers=$null
$pagesConfig=@{name='edgetunnel-test';compatibility_date='2026-10-24';pages_build_output_dir='dist/pages';kv_namespaces=@(@{binding='KV';id=$kv.id});vars=@{NODES_URL='https://renatirudy246-maker.github.io/gate-test/nodes.txt';OFF_LOG='1';DEBUG='false'}}
$pagesConfig|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $PSScriptRoot 'wrangler.json') -Encoding utf8
$status|ConvertTo-Json
