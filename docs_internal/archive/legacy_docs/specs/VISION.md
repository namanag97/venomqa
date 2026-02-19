# VenomQA Vision: State-Based Application Testing

## The Core Problem

Traditional API testing checks: "Did this endpoint return 200?"

But real applications are interconnected. **Every user action has cascading impacts across the entire app.** A file upload doesn't just create a file—it affects:
- File listing
- Storage usage display
- Quota remaining
- Billing calculations
- Search results
- Activity logs
- And more...

Human QA testers understand this intuitively. They don't just check "did the upload work?"—they verify the ENTIRE app state is consistent after every action.

**VenomQA should test like a human QA thinks.**

---

## The VenomQA Approach

### 1. State Model: Define Your App's Reality

Before testing, define what "state" exists in your application:

```yaml
state_model:
  files:
    - id
    - name
    - size
    - created_at
    - owner_id

  usage:
    - user_id
    - bytes_used
    - bytes_remaining
    - file_count

  user:
    - id
    - plan_type
    - quota_limit
```

This is the "shape" of your application's data.

### 2. Invariants: Rules That Must ALWAYS Be True

Define consistency rules that should hold after EVERY action:

```yaml
invariants:
  - name: "usage_matches_files"
    check: "usage.bytes_used == SUM(files.size WHERE files.owner_id == user.id)"
    severity: critical

  - name: "quota_calculation"
    check: "usage.bytes_remaining == user.quota_limit - usage.bytes_used"
    severity: critical

  - name: "file_count_accurate"
    check: "usage.file_count == COUNT(files WHERE files.owner_id == user.id)"
    severity: high
```

After EVERY step in EVERY journey, VenomQA verifies all invariants still hold.

### 3. Journeys With Branches: Test All Paths

A journey isn't linear. At each step, users can take different paths:

```
Upload File Journey:
    │
    ├─► Upload CSV file
    │   ├─► Valid CSV → success
    │   └─► Invalid CSV → error handling
    │
    ├─► Upload Excel file
    │   ├─► .xlsx → success
    │   └─► .xls (legacy) → conversion + success
    │
    ├─► Upload image
    │   ├─► Under size limit → success
    │   └─► Over size limit → rejection
    │
    └─► Upload duplicate file
        ├─► Dedup enabled → reference existing
        └─► Dedup disabled → create copy
```

VenomQA explores ALL branches, not just the happy path.

### 4. Cross-Journey State: Real User Behavior

Real users don't complete one journey then start another fresh. They:
- Start journey A
- Stop halfway
- Do something in journey B
- Come back to journey A
- Jump to journey C

VenomQA should test these combinations:

```yaml
test_scenarios:
  - name: "interrupted_upload"
    steps:
      - journey: "file_upload"
        stop_at: "file_selected"  # Stop before upload completes
      - journey: "check_usage"    # Does usage page handle partial state?
      - journey: "file_upload"
        resume: true              # Come back and complete
      - journey: "check_usage"    # Now verify final state
```

### 5. Node-Based Architecture

Think of your app as a graph of NODES (states) and EDGES (actions):

```
[Logged Out] ──login──► [Dashboard] ──upload──► [File Uploaded]
                │                                    │
                │                                    ▼
                │                            [Usage Updated]
                │                                    │
                └──────────check_usage───────────────┘
```

Each NODE is a state. Each EDGE is an action that transitions between states.

VenomQA:
1. Maps all your nodes and edges
2. Traverses every possible path
3. At each node, verifies invariants
4. Reports which nodes/edges are broken

---

## How It Works

### Developer Defines:

1. **State Model** - What data exists in the app
2. **Invariants** - Rules that must always be true
3. **Nodes** - Possible states the app can be in
4. **Edges/Actions** - How to transition between states
5. **Assertions** - What to check at each node

### VenomQA Executes:

1. Starts at initial node
2. Explores all possible paths (edges)
3. At each node:
   - Executes the action (HTTP call)
   - Captures the new state
   - Verifies ALL invariants
   - Records pass/fail
4. Branches into all possible next paths
5. Continues until all paths explored

### VenomQA Reports:

```
Journey Exploration Complete
============================

Nodes Tested: 47
Edges Tested: 156
Paths Explored: 23

BROKEN NODES:
  ✗ [Usage Page] - Invariant failed: usage_matches_files
    After: file_upload → delete_file
    Expected: bytes_used = 0
    Actual: bytes_used = 1048576 (stale data)

  ✗ [Search Results] - File still appears after deletion
    After: file_upload → delete_file → search

BROKEN EDGES:
  ✗ upload_duplicate_file → [Error State]
    Expected: Dedup to create reference
    Actual: Created duplicate (2x storage used)

COMPLETE JOURNEYS: 19/23
INVARIANT VIOLATIONS: 7
```

---

## The "Venom" Philosophy

The name **Venom** represents:
- **Penetrating** - Gets into every corner of your app
- **Spreading** - Tests cascading effects across features
- **Revealing** - Exposes hidden bugs in state consistency
- **Thorough** - Explores all paths, not just happy paths

Like venom spreading through a system, VenomQA touches every part of your application to find weaknesses.

---

## Example: File Storage App

```yaml
# venomqa.yaml

app:
  name: "CloudStorage"
  base_url: "http://localhost:8000"
  database: "postgresql://localhost/cloudstorage"

state_model:
  files:
    table: files
    fields: [id, name, size, owner_id, created_at, checksum]

  usage:
    table: user_usage
    fields: [user_id, bytes_used, file_count]

  users:
    table: users
    fields: [id, email, plan, quota_bytes]

invariants:
  - name: usage_accurate
    sql: |
      SELECT u.bytes_used = COALESCE(SUM(f.size), 0)
      FROM user_usage u
      LEFT JOIN files f ON f.owner_id = u.user_id
      GROUP BY u.user_id
    expect: true

  - name: quota_not_exceeded
    sql: |
      SELECT u.bytes_used <= us.quota_bytes
      FROM user_usage u
      JOIN users us ON us.id = u.user_id
    expect: true

  - name: file_count_matches
    sql: |
      SELECT u.file_count = COUNT(f.id)
      FROM user_usage u
      LEFT JOIN files f ON f.owner_id = u.user_id
      GROUP BY u.user_id
    expect: true

nodes:
  logged_out:
    description: "User not authenticated"

  dashboard:
    description: "Main dashboard after login"
    verify:
      - endpoint: GET /api/dashboard
      - status: 200

  file_list:
    description: "Viewing file list"
    verify:
      - endpoint: GET /api/files
      - check: response.count == state.usage.file_count

  usage_page:
    description: "Viewing storage usage"
    verify:
      - endpoint: GET /api/usage
      - check: response.bytes_used == state.usage.bytes_used

edges:
  login:
    from: logged_out
    to: dashboard
    action:
      endpoint: POST /api/auth/login
      body: { email: "{{user.email}}", password: "{{user.password}}" }

  upload_file:
    from: [dashboard, file_list]
    to: file_list
    variants:
      - name: small_csv
        action:
          endpoint: POST /api/files/upload
          file: "test_data/small.csv"
      - name: large_excel
        action:
          endpoint: POST /api/files/upload
          file: "test_data/large.xlsx"
      - name: duplicate
        action:
          endpoint: POST /api/files/upload
          file: "{{last_uploaded_file}}"

  delete_file:
    from: file_list
    to: file_list
    action:
      endpoint: DELETE /api/files/{{file.id}}

  view_usage:
    from: [dashboard, file_list]
    to: usage_page
    action:
      endpoint: GET /api/usage

exploration:
  strategy: exhaustive  # or: random_walk, priority_based
  max_depth: 10
  stop_on_invariant_failure: false  # Continue to find all bugs
```

---

## Summary

VenomQA is NOT just an API testing tool. It is a **state-based application testing framework** that:

1. **Models your app's state** - Understands what data exists
2. **Defines consistency rules** - Knows what "correct" looks like
3. **Explores all paths** - Tests every combination users might take
4. **Verifies after every action** - Checks invariants at each step
5. **Reports broken nodes** - Tells you exactly what's wrong and where

**The goal:** Test your app the way a thorough human QA would—checking everything, everywhere, after every action.
