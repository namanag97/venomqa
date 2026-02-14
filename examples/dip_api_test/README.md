# Data Integration Platform - Combinatorial API Test

Comprehensive combinatorial state test for a Data Integration Platform (DIP) API, built with VenomQA's combinatorial testing system.

## What it tests

Six dimensions of variation are combined to generate a minimal test suite
that covers all pairwise interactions:

| Dimension          | Values                              | Description                    |
|--------------------|-------------------------------------|--------------------------------|
| `auth_state`       | none, valid, expired, invalid       | Authentication token state     |
| `workspace_state`  | none, empty, has_files, has_tables  | Workspace data lifecycle       |
| `file_format`      | csv, json, parquet                  | Upload file format             |
| `data_size`        | empty, small, medium, large         | Dataset row count              |
| `user_role`        | owner, member, viewer               | User permission level          |
| `operation_type`   | read, write, delete                 | Category of API operation      |

**Full Cartesian product:** 4 x 4 x 3 x 4 x 3 x 3 = 1,728 combinations

After constraints and pairwise generation, this is reduced to approximately
30-40 test combinations while still covering every pair of dimension values.

## Constraints

The test defines realistic constraints that eliminate impossible or
meaningless combinations:

- Write/delete operations require valid authentication
- Viewers cannot write; only owners can delete
- Workspaces with files/tables require authentication to exist
- Tables imply at least some data

## Invariants

Four invariants are checked at every state during graph exploration:

1. **auth_consistency** - Unauthenticated requests to protected endpoints return 401
2. **data_integrity** - Row counts in the API match expected values
3. **permission_enforcement** - Role-based access control is enforced
4. **health_always_accessible** - `/health` and `/ready` never require auth

## Running

### Mock mode (no server required)

```bash
# From the repository root:
python examples/dip_api_test/test_dip_combinatorial.py
```

### Against a live server

```bash
DIP_BASE_URL=http://localhost:8000 python examples/dip_api_test/test_dip_combinatorial.py
```

### Configuration via environment variables

| Variable       | Default | Description                                   |
|----------------|---------|-----------------------------------------------|
| `DIP_BASE_URL` | (empty) | Base URL of the DIP API. Empty = mock mode.   |
| `DIP_STRENGTH` | `2`     | Covering array strength (2=pairwise, 3=3-wise)|
| `DIP_SEED`     | `42`    | Random seed for reproducible generation       |

### Three-wise coverage

```bash
DIP_STRENGTH=3 python examples/dip_api_test/test_dip_combinatorial.py
```

This generates more test combinations but covers every triple of dimension
values, catching interaction bugs that pairwise might miss.

## Output

The test prints:

1. **Dimension definitions** with value counts
2. **Constraint summary** showing how many impossible combinations are removed
3. **Coverage report** with 1-wise, 2-wise, and 3-wise tuple coverage
4. **All generated combinations** listed in full
5. **StateGraph statistics** (nodes, edges, invariants)
6. **Mermaid diagram** (first 30 lines) for visualization
7. **Exploration results** (mock mode only) with any invariant violations
8. **Final statistics** summarizing the test run

## Architecture

```
build_dimension_space()     - defines 6 Dimensions in a DimensionSpace
build_constraints()         - defines 13 Constraints in a ConstraintSet
build_graph()               - wires up:
  |-- 8 auth transitions        (login, logout, expire, invalidate, etc.)
  |-- 8 workspace transitions   (create, upload, import, delete, etc.)
  |-- 6 file format transitions (switch between csv/json/parquet)
  |-- 18 data size transitions  (grow, shrink, clear)
  |-- 6 operation transitions   (read, write, delete mode switches)
  |-- 6 role transitions        (owner, member, viewer switches)
  |-- 4 invariants              (auth, data, permissions, health)
```

The `CombinatorialGraphBuilder` takes these components and:

1. Generates a pairwise covering array (or n-wise per `DIP_STRENGTH`)
2. Creates a `StateNode` for each valid combination
3. Connects nodes that differ by exactly one dimension with the
   appropriate transition action
4. Attaches all invariants
5. Returns a standard `StateGraph` ready for exploration
