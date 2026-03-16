param(
    [string]$Url = "https://jsonplaceholder.typicode.com/posts",
    [string]$Source = "jsonplaceholder"
)

$body = @{
    url = $Url
    source = $Source
    metadata = @{
        requested_by = "powershell"
    }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri "http://localhost:8080/task" -ContentType "application/json" -Body $body