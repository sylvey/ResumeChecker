# Server

Backend server for ResumeChecker (Go + Gin).

## Requirements

Go 1.26.4. Check whether it's installed:

```bash
go version
```

If not, download it from https://go.dev/dl/.

## Run

```bash
cd server
go mod download
go run .
```

The server runs on :8080. Verify it's working with:

```bash
curl http://localhost:8080/sample/hello

curl -X POST http://localhost:8080/sample/echo \
  -H "Content-Type: application/json" \
  -d '{"name": "Alex", "age": 25}'
```
