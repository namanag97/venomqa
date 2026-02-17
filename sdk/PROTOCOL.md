# VenomQA Control Protocol v1

This document specifies the HTTP control protocol that allows VenomQA to manage database transactions in APIs written in **any language**.

## Overview

VenomQA explores APIs by testing every possible sequence of actions. To do this efficiently, it needs to **rollback** the database between branches so each path starts from the same state.

When your API is written in a different language than VenomQA (Python), they can't share a database connection directly. Instead, your API implements a simple HTTP control interface that VenomQA calls to manage transactions.

```
┌─────────────┐     HTTP API calls      ┌─────────────┐
│   VenomQA   │ ───────────────────────▶│  Your API   │
│  (Python)   │                         │ (Node/Go/…) │
└──────┬──────┘                         └──────┬──────┘
       │                                       │
       │  POST /venomqa/checkpoint             │
       │  POST /venomqa/rollback               │
       │◀──────────────────────────────────────│
       │                                       │
       │                                       ▼
       │                               ┌─────────────┐
       └──────────────────────────────▶│ PostgreSQL  │
           (VenomQA does NOT connect   └─────────────┘
            to DB directly)
```

## Endpoints

### `GET /venomqa/health`

Health check endpoint. VenomQA calls this to verify the control interface is available.

**Response:**
```json
{
  "status": "ok",
  "venomqa_protocol": "1.0",
  "database": "postgresql"
}
```

### `POST /venomqa/begin`

Begin a new exploration session. Your API should:
1. Start a database transaction (but don't commit it)
2. Store the connection for reuse during this session

**Request:**
```json
{
  "session_id": "venomqa_abc123"
}
```

**Response:**
```json
{
  "session_id": "venomqa_abc123",
  "status": "active"
}
```

### `POST /venomqa/checkpoint`

Create a savepoint. Your API should:
1. Execute `SAVEPOINT <checkpoint_id>` on the active connection
2. Return the checkpoint ID

**Request:**
```json
{
  "session_id": "venomqa_abc123"
}
```

**Response:**
```json
{
  "checkpoint_id": "sp_1",
  "session_id": "venomqa_abc123"
}
```

### `POST /venomqa/rollback`

Rollback to a savepoint. Your API should:
1. Execute `ROLLBACK TO SAVEPOINT <checkpoint_id>`
2. The database state is now back to when the checkpoint was created

**Request:**
```json
{
  "session_id": "venomqa_abc123",
  "checkpoint_id": "sp_1"
}
```

**Response:**
```json
{
  "status": "rolled_back",
  "checkpoint_id": "sp_1"
}
```

### `POST /venomqa/end`

End the exploration session. Your API should:
1. Rollback the entire transaction (don't commit!)
2. Close the connection

**Request:**
```json
{
  "session_id": "venomqa_abc123"
}
```

**Response:**
```json
{
  "status": "ended",
  "session_id": "venomqa_abc123"
}
```

## Implementation Requirements

### 1. Single Connection Per Session

During a VenomQA session, ALL database operations must use the SAME connection. This is critical - if your API creates new connections for each request, ROLLBACK won't work.

**Pattern:**
```
Session starts → Open connection, BEGIN transaction
All API requests → Use this same connection (don't commit!)
Checkpoint → SAVEPOINT on this connection
Rollback → ROLLBACK TO SAVEPOINT
Session ends → ROLLBACK entire transaction, close connection
```

### 2. Connection Injection

Your API needs a way to inject the VenomQA-controlled connection into your request handlers. Common patterns:

**Middleware approach:**
```javascript
// Node.js/Express example
app.use((req, res, next) => {
  const sessionId = req.headers['x-venomqa-session'];
  if (sessionId && venomqaSessions[sessionId]) {
    req.db = venomqaSessions[sessionId].connection;
  } else {
    req.db = defaultPool.getConnection();
  }
  next();
});
```

**Dependency injection:**
```go
// Go example
func GetDB(r *http.Request) *sql.Tx {
    sessionID := r.Header.Get("X-VenomQA-Session")
    if tx, ok := venomqaSessions[sessionID]; ok {
        return tx
    }
    return defaultDB
}
```

### 3. No Auto-Commit

During VenomQA sessions, your ORM/database layer must NOT auto-commit. Changes should only be visible within the transaction.

## Headers

VenomQA includes these headers with every request during a session:

| Header | Value | Description |
|--------|-------|-------------|
| `X-VenomQA-Session` | `venomqa_abc123` | Active session ID |
| `X-VenomQA-Mode` | `exploration` | Indicates VenomQA is active |

Your API should check for `X-VenomQA-Session` and use the corresponding connection.

## Example Flow

```
1. VenomQA: POST /venomqa/begin {session_id: "s1"}
   API: Opens connection, BEGIN, stores in sessions["s1"]

2. VenomQA: POST /users {name: "Alice"}  [X-VenomQA-Session: s1]
   API: INSERT INTO users... (using sessions["s1"].connection)

3. VenomQA: POST /venomqa/checkpoint {session_id: "s1"}
   API: SAVEPOINT sp_1, returns {checkpoint_id: "sp_1"}

4. VenomQA: DELETE /users/1  [X-VenomQA-Session: s1]
   API: DELETE FROM users WHERE id=1 (same connection)

5. VenomQA: POST /venomqa/rollback {session_id: "s1", checkpoint_id: "sp_1"}
   API: ROLLBACK TO SAVEPOINT sp_1
   (User Alice is back!)

6. VenomQA: PUT /users/1 {name: "Bob"}  [X-VenomQA-Session: s1]
   API: UPDATE users SET name='Bob' (testing different branch)

7. VenomQA: POST /venomqa/end {session_id: "s1"}
   API: ROLLBACK, close connection
   (All changes discarded, DB unchanged)
```

## Error Handling

### Session Not Found
```json
{
  "error": "session_not_found",
  "message": "No active session with ID: venomqa_xyz"
}
```
HTTP Status: 404

### Checkpoint Not Found
```json
{
  "error": "checkpoint_not_found",
  "message": "No checkpoint with ID: sp_99"
}
```
HTTP Status: 404

### Database Error
```json
{
  "error": "database_error",
  "message": "SAVEPOINT failed: connection lost"
}
```
HTTP Status: 500

## Security Considerations

The VenomQA control endpoints should **ONLY** be available in test/development environments. Recommended approaches:

1. **Environment variable:** Only register routes if `VENOMQA_ENABLED=true`
2. **Separate port:** Run control endpoints on a different port
3. **Authentication:** Require a secret token in headers

```javascript
// Only enable in test mode
if (process.env.VENOMQA_ENABLED === 'true') {
  app.use('/venomqa', venomqaRouter);
}
```

## SDK Availability

We provide SDKs that implement this protocol for:

- **Node.js/Express:** `npm install @venomqa/express`
- **Node.js/Fastify:** `npm install @venomqa/fastify`
- **Go:** `go get github.com/venomqa/venomqa-go`
- **Python/FastAPI:** Built into VenomQA
- **Java/Spring:** `com.venomqa:venomqa-spring`
- **Ruby/Rails:** `gem install venomqa-rails`

See the `/sdk` directory for implementation examples.
