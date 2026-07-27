## 1. Load the environment

```powershell
. .\scripts\live_env.ps1
```

## 2. Get access tokens for the three profiles

```powershell
python scripts\live_tokens.py
```

Load them into the session

```powershell
. .\.live-tokens.ps1
```


## 3. Retrieve an object — `GET /resource/{id}`
```powershell
aws s3 cp demo.txt "s3://$env:LIVE_BUCKET/resources/demo1"
```

All users should be allowed to read the object

```powershell
foreach ($t in @($env:LIVE_TOKEN_EMPLEADO, $env:LIVE_TOKEN_SUPERVISOR, $env:LIVE_TOKEN_ADMIN)) {
    curl.exe -s -w "`nHTTP %{http_code}`n" -H "Authorization: Bearer $t" "$env:LIVE_API_URL/resource/demo1"
}
```

Expect `200` and `{"id": "demo-1", "content": "hello from the runbook"}` three times.

## 4. Upload an object — `POST /upload` (supervisor + admin)

Upload an object from Supervisor profile

```powershell
curl.exe -s -w "`nHTTP %{http_code}`n" -X POST `
  -H "Authorization: Bearer $env:LIVE_TOKEN_SUPERVISOR" `
  -H "Content-Type: text/plain" `
  --data "uploaded by the supervisor" `
  "$env:LIVE_API_URL/upload?key=runbook.txt"
```

Expect `201` and `{"key": "uploads/runbook.txt", "bytes": 26}`

Upload an object from Empleado profile

```powershell
curl.exe -s -w "`nHTTP %{http_code}`n" -X POST `
  -H "Authorization: Bearer $env:LIVE_TOKEN_EMPLEADO" `
  -H "Content-Type: text/plain" `
  --data "uploaded by the empleado" `
  "$env:LIVE_API_URL/upload?key=runbookEmpleado.txt"
```

Expect `403` and `User is not authorized to access this resource with an explicit deny in an identity-based policy`

Upload an object with not accepted content type

```powershell
curl.exe -s -w "`nHTTP %{http_code}`n" -X POST `
  -H "Authorization: Bearer $env:LIVE_TOKEN_SUPERVISOR" `
  -H "Content-Type: text/html" `
  --data "<script>alert(1)</script>" `
  "$env:LIVE_API_URL/upload?key=evil.html"
```

Expect `415` and `Unsupported content type`

## 5. Create a user — `POST /createUser` (admin only)

Create an user from Admin profile

```powershell
curl.exe -s -w "`nHTTP %{http_code}`n" -X POST `
  -H "Authorization: Bearer $env:LIVE_TOKEN_ADMIN" `
  -H "Content-Type: application/json" `
  --data '{\"email\":\"alice@example.com\",\"group\":\"empleado\"}' `
  "$env:LIVE_API_URL/createUser"
```

Expect `201` and `{"username": "alice@example.com", "group": "empleado"}`

```powershell
aws cognito-idp admin-list-groups-for-user --user-pool-id $env:LIVE_USER_POOL_ID --username alice@example.com
```

Try to create an user from Empleado profile

```powershell
curl.exe -s -w "`nHTTP %{http_code}`n" -X POST `
  -H "Authorization: Bearer $env:LIVE_TOKEN_EMPLEADO" `
  -H "Content-Type: application/json" `
  --data '{\"email\":\"jorge@example.com\",\"group\":\"empleado\"}' `
  "$env:LIVE_API_URL/createUser"
```

Expect `403` and `User is not authorized to access this resource with an explicit deny in an identity-based policy`

## 6. Log in as the user you just created

```powershell
$env:LIVE_TOKEN_ADHOC = python scripts\live_tokens.py --user alice@example.com --group empleado --token-only
```

Log in as Alice to get a resource and to upload an object

```powershell
curl.exe -s -w "`nHTTP %{http_code}`n" -H "Authorization: Bearer $env:LIVE_TOKEN_ADHOC" "$env:LIVE_API_URL/resource/demo-1"

curl.exe -s -w "`nHTTP %{http_code}`n" -X POST -H "Authorization: Bearer $env:LIVE_TOKEN_ADHOC" `
  -H "Content-Type: text/plain" --data "should be refused" "$env:LIVE_API_URL/upload?key=alice.txt"
```

Promote Alice to supervisor and retry. It should work now

```powershell
aws cognito-idp admin-add-user-to-group --user-pool-id $env:LIVE_USER_POOL_ID --username alice@example.com --group-name supervisor
$env:LIVE_TOKEN_ADHOC = python scripts\live_tokens.py --user alice@example.com --group supervisor --token-only
```