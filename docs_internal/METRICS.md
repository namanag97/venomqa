# Success Metrics & KPIs

> What we measure and why.

---

## North Star Metric

**Active Weekly Users (AWU)**
- Definition: Unique users who run `venomqa run` or `venomqa demo` in a week
- Target: 1,000 AWU by end of Q2

---

## Metric Categories

### 1. Adoption Metrics

| Metric | Current | Target | How to Measure |
|--------|---------|--------|----------------|
| PyPI downloads/month | ? | 10,000 | pypistats |
| GitHub stars | ? | 500 | GitHub API |
| GitHub forks | ? | 50 | GitHub API |
| `venomqa demo` runs | ? | 1,000/mo | Analytics in demo |
| `venomqa init` runs | ? | 500/mo | Analytics |

### 2. Engagement Metrics

| Metric | Current | Target | How to Measure |
|--------|---------|--------|----------------|
| Journeys run/user/week | ? | 20 | Telemetry (opt-in) |
| State graphs created | ? | 100/mo | Telemetry |
| Return rate (7-day) | ? | 40% | Telemetry |
| Avg session length | ? | 15 min | Telemetry |

### 3. Quality Metrics

| Metric | Current | Target | How to Measure |
|--------|---------|--------|----------------|
| Bug reports/month | ? | <10 | GitHub issues |
| Time to first response | ? | <24h | Issue timestamps |
| Test coverage | ? | >80% | pytest-cov |
| Doc coverage | ? | 100% core | Manual audit |

### 4. Community Metrics

| Metric | Current | Target | How to Measure |
|--------|---------|--------|----------------|
| Contributors | ? | 20 | GitHub |
| Discord members | 0 | 200 | Discord |
| Stack Overflow questions | ? | 50 | SO API |
| Blog mentions | ? | 10 | Google Alerts |

---

## Funnel Metrics

```
Awareness    →  Install    →  Demo    →  Init    →  Regular Use
   ?             ?             ?          ?           ?
```

| Stage | Metric | Target Conversion |
|-------|--------|-------------------|
| Awareness → Install | Install rate | 10% of visitors |
| Install → Demo | Demo run rate | 50% of installs |
| Demo → Init | Init rate | 30% of demo runners |
| Init → Regular | Retention | 20% after 30 days |

---

## Product Metrics

### Feature Usage

| Feature | Usage | Notes |
|---------|-------|-------|
| Journey testing | ? | Core feature |
| State graphs | ? | Differentiator |
| Checkpoints | ? | Power feature |
| Branching | ? | Power feature |
| Invariants | ? | Differentiator |
| Reporters (HTML) | ? | |
| Reporters (JUnit) | ? | CI/CD indicator |
| `--debug` mode | ? | |
| `--explain` mode | ? | Learning indicator |

### Error Rates

| Error Type | Rate | Action if High |
|------------|------|----------------|
| Connection errors | ? | Improve error messages |
| Journey not found | ? | Fix discovery |
| Config errors | ? | Better validation |
| Assertion failures | ? | Expected (tests failing) |

---

## Business Metrics (Future)

### If/When Monetized

| Metric | Definition |
|--------|------------|
| MRR | Monthly Recurring Revenue |
| CAC | Customer Acquisition Cost |
| LTV | Lifetime Value |
| Churn | Monthly churn rate |
| NPS | Net Promoter Score |

---

## Dashboards

### Developer Dashboard (Weekly)
- GitHub stars trend
- PyPI downloads
- Open issues / PRs
- Test coverage
- Build status

### Growth Dashboard (Monthly)
- AWU trend
- Funnel conversion
- Feature usage
- Error rates

### Community Dashboard (Monthly)
- New contributors
- Discord activity
- Social mentions
- Blog posts

---

## Alerting

| Alert | Threshold | Action |
|-------|-----------|--------|
| CI failing | Any | Fix immediately |
| PyPI download drop | >50% week-over-week | Investigate |
| Bug report spike | >5/day | Emergency triage |
| Negative review | Any | Respond within 24h |

---

## Data Collection Plan

### Phase 1: Manual (Current)
- GitHub Insights
- PyPI Stats
- Manual user feedback

### Phase 2: Basic Analytics
- Anonymous telemetry (opt-in)
- Error tracking (Sentry?)
- Feature flags

### Phase 3: Full Analytics
- User journey tracking
- A/B testing
- Cohort analysis

---

## Reporting Cadence

| Report | Frequency | Audience |
|--------|-----------|----------|
| Daily standup | Daily | Dev team |
| Weekly metrics | Weekly | All |
| Monthly review | Monthly | Leadership |
| Quarterly OKRs | Quarterly | All |

---

## OKRs (Example)

### Q1 Objective: Establish Developer Adoption

**KR1:** Reach 5,000 PyPI downloads/month
- Current: ?
- Target: 5,000

**KR2:** 200 GitHub stars
- Current: ?
- Target: 200

**KR3:** 10 external contributors
- Current: ?
- Target: 10

**KR4:** <24h average first response on issues
- Current: ?
- Target: <24h
