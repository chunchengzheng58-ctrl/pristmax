# Pristmax Storage API Documentation

## Base URL

```
http://localhost:5001/api
```

---

## Authentication

Pristmax supports two authentication methods:

### 1. JWT Token

Login to get a JWT token:

```bash
POST /api/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "password123"
}
```

Response:
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_at": "2024-01-01T12:00:00",
  "user": {
    "user_id": "xxx",
    "username": "admin",
    "role": "admin"
  }
}
```

Use the token:
```bash
Authorization: Bearer <token>
```

### 2. API Key

Login with API key:

```bash
POST /api/auth/apikey/login
Content-Type: application/json

{
  "api_key": "pk_xxxxx..."
}
```

---

## Roles & Permissions

| Role | Permissions |
|------|-------------|
| `admin` | Full access |
| `operator` | Create tasks, view data |
| `viewer` | View only |

---

## Endpoints

### Auth

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/auth/register` | Register user | No |
| POST | `/api/auth/login` | Login | No |
| POST | `/api/auth/apikey/login` | API Key login | No |
| GET | `/api/auth/me` | Current user | Yes |

### Stats

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/stats` | Get statistics | No |

### Tasks

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/tasks` | List tasks | Yes |
| POST | `/api/tasks` | Create task | Yes (operator+) |
| GET | `/api/tasks/:id` | Get task | Yes |
| DELETE | `/api/tasks/:id` | Cancel task | Yes |

### Storage

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/storages` | List storages | Yes |
| POST | `/api/storages` | Add storage | Yes (admin) |
| DELETE | `/api/storages/:id` | Remove storage | Yes (admin) |

### Strategies

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/strategies` | List strategies | Yes |
| PUT | `/api/strategies/:id` | Update strategy | Yes (admin) |

### Alerts

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/alerts` | List alerts | Yes |

---

## Examples

### Register & Login

```bash
# Register
curl -X POST http://localhost:5001/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","email":"admin@example.com","password":"password123"}'

# Login
curl -X POST http://localhost:5001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"password123"}'
```

### Create Task

```bash
curl -X POST http://localhost:5001/api/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "task_type": "encode",
    "input_path": "/videos/test.mp4",
    "output_path": "/videos/test_encoded.mp4",
    "params": {"crf": 28, "preset": "medium"}
  }'
```

### Get Stats

```bash
curl http://localhost:5001/api/stats
```

---

## Error Responses

```json
{
  "error": "Error message",
  "code": "ERROR_CODE"
}
```

| HTTP Code | Meaning |
|----------|---------|
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 409 | Conflict |
| 500 | Server Error |

---

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `/api/auth/*` | 10/min |
| `/api/tasks` | 100/min |
| Other | 1000/min |
