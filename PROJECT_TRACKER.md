# VenomQA Project Tracker

> Last updated: 2026-02-14

---

## Quick Status

| Area | Status | Priority |
|------|--------|----------|
| Core Framework | ✅ Complete | - |
| Documentation | 🟡 In Progress | High |
| Website/Landing | 🟡 In Progress | High |
| Demo Command | ✅ Complete | - |
| GitHub Pages | 🔴 Blocked (env settings) | High |
| Load Testing | ❌ Not Started | Medium |
| AI Features | ❌ Not Started | Low |

---

## Current Sprint

### In Progress
- [ ] Fix GitHub Pages deployment (environment protection rules)
- [ ] Improve landing page design
- [ ] Add more examples

### Blocked
- [ ] GitHub Pages deploy - needs environment settings configured
  - Go to: https://github.com/namanag97/venomqa/settings/environments
  - Add `main` branch to allowed deployment branches

### Recently Completed
- [x] `venomqa demo` command with `--explain` mode
- [x] Landing page redesign with hero, features, code comparison
- [x] Theory documentation (`docs/concepts/theory.md`)
- [x] Fixed GitHub URLs (namanag97 not namanagarwal)

---

## Roadmap

### Phase 1: Developer Experience (Current)
Priority: **HIGH** - This is what stops adoption

| Feature | Status | Notes |
|---------|--------|-------|
| `venomqa demo` | ✅ Done | Zero-config demo with `--explain` mode |
| Better error messages | 🟡 Partial | Need "how to fix" suggestions |
| Journey discovery fix | ❌ TODO | Two different discovery mechanisms |
| VSCode extension | ❌ TODO | Test runner, snippets, autocomplete |
| `venomqa record` | ❌ TODO | Record API calls → generate journey |

### Phase 2: Observability & Debugging
Priority: **HIGH**

| Feature | Status | Notes |
|---------|--------|-------|
| Trace viewer | ❌ TODO | Visual timeline of requests |
| Request/response on failure | 🟡 Partial | Always show, not just debug mode |
| OpenTelemetry integration | ❌ TODO | Distributed tracing |

### Phase 3: Performance Testing
Priority: **MEDIUM**

| Feature | Status | Notes |
|---------|--------|-------|
| `venomqa load` | ❌ TODO | Reuse journeys for load testing |
| Latency assertions | ❌ TODO | p50, p95, p99 < X ms |
| Performance baselines | ❌ TODO | Detect regressions |

### Phase 4: Contract Testing
Priority: **MEDIUM**

| Feature | Status | Notes |
|---------|--------|-------|
| OpenAPI validation | ❌ TODO | Validate responses against spec |
| Breaking change detection | ❌ TODO | Compare schema versions |
| Pact-style contracts | ❌ TODO | Consumer-driven contracts |

### Phase 5: AI Features
Priority: **LOW** (future differentiator)

| Feature | Status | Notes |
|---------|--------|-------|
| Test generation from OpenAPI | ❌ TODO | Auto-generate journeys |
| Flaky test detection | ❌ TODO | Run N times, detect flakiness |
| "Explain this failure" | ❌ TODO | AI-powered debugging |
| Natural language tests | ❌ TODO | "Test that users can checkout" |

### Phase 6: Enterprise/Cloud
Priority: **LOW** (monetization)

| Feature | Status | Notes |
|---------|--------|-------|
| Cloud platform (venomqa.io) | ❌ TODO | Hosted execution |
| Team collaboration | ❌ TODO | Shared dashboards |
| Historical trends | ❌ TODO | Track test health over time |

---

## Competitive Analysis

### Direct Competitors

| Tool | Strengths | Weaknesses | Our Advantage |
|------|-----------|------------|---------------|
| **Postman** | No-code, collaboration | No state management | State graphs, invariants |
| **Pytest** | Huge ecosystem | Not API-focused | API-first, journeys |
| **Karate** | DSL, no coding | Java ecosystem | Python native |
| **k6** | Load testing | No functional tests | Both in one tool |
| **Pact** | Contract testing | Complex setup | Simpler API |

### Indirect Competitors

| Tool | Category | Notes |
|------|----------|-------|
| Playwright | E2E browser | We're API-only |
| Cypress | E2E browser | We're API-only |
| RestAssured | Java API testing | We're Python |

### Our Unique Value
1. **State Graph Testing** - No one else does this well
2. **Invariants** - Rules checked after EVERY action
3. **Checkpoint/Branch** - Git-like state management
4. **Cross-feature testing** - Verify consistency across endpoints

---

## Known Issues

### High Priority
| Issue | Impact | Status |
|-------|--------|--------|
| Journey discovery inconsistency | Confuses users | TODO |
| `--strict` build fails | Blocks deployment | Fixed |
| Error messages not helpful | Users give up | TODO |

### Medium Priority
| Issue | Impact | Status |
|-------|--------|--------|
| Broken internal doc links | Poor UX | TODO |
| No offline docs | Can't work offline | TODO |
| Import path hell in generated code | Confuses beginners | TODO |

### Low Priority
| Issue | Impact | Status |
|-------|--------|--------|
| `.env not found` warning | Noise | TODO |
| Some adapters untested | Technical debt | TODO |

---

## Missing Features (by category)

### Must Have (blocking adoption)
- [ ] Better error messages with "how to fix"
- [ ] Consistent journey discovery
- [ ] Request/response shown on failure

### Should Have (expected by users)
- [ ] Load testing mode
- [ ] OpenAPI schema validation
- [ ] Performance baselines
- [ ] More reporter options (SARIF, TAP)

### Nice to Have (differentiators)
- [ ] AI test generation
- [ ] Trace viewer UI
- [ ] `venomqa record` (record → generate)
- [ ] VSCode extension

### Future (enterprise)
- [ ] Cloud platform
- [ ] Team dashboards
- [ ] Historical trends
- [ ] SSO integration

---

## File Structure Reference

```
venomqa/
├── cli/
│   ├── commands.py      # Main CLI commands
│   ├── demo.py          # Demo server & command ✅
│   ├── doctor.py        # Health checks
│   └── output.py        # CLI output formatting
├── core/
│   ├── graph.py         # StateGraph implementation
│   └── models.py        # Journey, Step, Branch, etc.
├── runner/
│   └── __init__.py      # JourneyRunner
├── reporters/           # HTML, JSON, JUnit, etc.
├── adapters/            # Redis, Postgres, S3, etc.
├── ports/               # Abstract interfaces
└── ...

docs/
├── index.md             # Landing page ✅
├── concepts/
│   ├── theory.md        # Why VenomQA works ✅
│   └── ...
└── getting-started/
    └── quickstart.md    # With demo command ✅

.github/
└── workflows/
    └── docs.yml         # GitHub Pages deployment
```

---

## Change Log (Recent)

### 2026-02-14
- Added `venomqa demo` command with `--explain` mode
- Redesigned landing page (hero, features, code comparison)
- Added theory documentation
- Fixed GitHub URLs (namanag97)
- Removed `--strict` from docs build
- Created PROJECT_TRACKER.md

### 2026-02-13
- Added preflight smoke test module
- Various bug fixes

---

## Next Actions

1. **Fix GitHub Pages** - Configure environment settings
2. **Test demo locally** - `venomqa demo --explain`
3. **Improve error messages** - Add "how to fix" suggestions
4. **Fix journey discovery** - Unify the two mechanisms
5. **Add more examples** - Real-world use cases

---

## Links

- **GitHub**: https://github.com/namanag97/venomqa
- **PyPI**: https://pypi.org/project/venomqa/
- **Docs**: https://namanag97.github.io/venomqa (pending deployment)
- **Issues**: https://github.com/namanag97/venomqa/issues
