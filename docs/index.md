---
hide:
  - navigation
  - toc
  - footer
---

<style>
:root {
  --venom-purple: #7c3aed;
  --venom-purple-dark: #5b21b6;
  --venom-purple-light: #a78bfa;
  --venom-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #7c3aed 100%);
}

/* Reset and base */
.md-content {
  max-width: 100% !important;
}

.md-content__inner {
  margin: 0 !important;
  padding: 0 !important;
  max-width: 100% !important;
}

/* Hero Section */
.hero {
  background: var(--venom-gradient);
  padding: 6rem 2rem 5rem 2rem;
  text-align: center;
  position: relative;
  overflow: hidden;
}

.hero::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.05'%3E%3Ccircle cx='30' cy='30' r='2'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
  pointer-events: none;
}

.hero-content {
  max-width: 900px;
  margin: 0 auto;
  position: relative;
  z-index: 1;
}

.hero h1 {
  font-size: 4rem;
  font-weight: 800;
  color: white;
  margin: 0 0 1rem 0;
  letter-spacing: -0.02em;
  text-shadow: 0 2px 20px rgba(0,0,0,0.2);
}

.hero-tagline {
  font-size: 1.5rem;
  color: rgba(255,255,255,0.9);
  margin-bottom: 0.5rem;
  font-weight: 500;
}

.hero-subtitle {
  font-size: 1.1rem;
  color: rgba(255,255,255,0.7);
  margin-bottom: 2.5rem;
  max-width: 600px;
  margin-left: auto;
  margin-right: auto;
}

/* Terminal Box */
.terminal-box {
  background: #1a1a2e;
  border-radius: 12px;
  padding: 0;
  max-width: 580px;
  margin: 2rem auto;
  text-align: left;
  box-shadow: 0 25px 50px -12px rgba(0,0,0,0.4);
  overflow: hidden;
}

.terminal-header {
  background: #252540;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.terminal-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.terminal-dot.red { background: #ff5f56; }
.terminal-dot.yellow { background: #ffbd2e; }
.terminal-dot.green { background: #27ca40; }

.terminal-title {
  color: #888;
  font-size: 0.8rem;
  margin-left: auto;
  font-family: var(--md-code-font-family);
}

.terminal-body {
  padding: 1.5rem;
  font-family: var(--md-code-font-family);
  font-size: 0.95rem;
  line-height: 1.6;
}

.terminal-line {
  margin: 0.3rem 0;
}

.terminal-prompt {
  color: #27ca40;
}

.terminal-command {
  color: #f0f0f0;
}

.terminal-comment {
  color: #666;
}

/* Buttons */
.hero-buttons {
  display: flex;
  gap: 1rem;
  justify-content: center;
  flex-wrap: wrap;
  margin-top: 2rem;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.875rem 2rem;
  border-radius: 8px;
  font-weight: 600;
  font-size: 1rem;
  text-decoration: none;
  transition: all 0.2s ease;
}

.btn-primary {
  background: white;
  color: var(--venom-purple);
  box-shadow: 0 4px 14px rgba(0,0,0,0.15);
}

.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0,0,0,0.2);
  color: var(--venom-purple-dark);
}

.btn-secondary {
  background: rgba(255,255,255,0.1);
  color: white;
  border: 2px solid rgba(255,255,255,0.3);
}

.btn-secondary:hover {
  background: rgba(255,255,255,0.2);
  border-color: rgba(255,255,255,0.5);
}

/* Sections */
.section {
  padding: 5rem 2rem;
  max-width: 1200px;
  margin: 0 auto;
}

.section-dark {
  background: var(--md-code-bg-color);
}

.section-title {
  font-size: 2.5rem;
  font-weight: 700;
  text-align: center;
  margin-bottom: 1rem;
  color: var(--md-default-fg-color);
}

.section-subtitle {
  text-align: center;
  color: var(--md-default-fg-color--light);
  font-size: 1.2rem;
  max-width: 600px;
  margin: 0 auto 3rem auto;
}

/* Problem/Solution */
.problem-solution {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 3rem;
  margin-bottom: 3rem;
}

@media (max-width: 768px) {
  .problem-solution {
    grid-template-columns: 1fr;
  }
}

.problem-card, .solution-card {
  padding: 2rem;
  border-radius: 12px;
}

.problem-card {
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  border: 1px solid #fecaca;
}

.solution-card {
  background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
  border: 1px solid #bbf7d0;
}

[data-md-color-scheme="slate"] .problem-card {
  background: linear-gradient(135deg, #2d1f1f 0%, #3d2020 100%);
  border-color: #5c2d2d;
}

[data-md-color-scheme="slate"] .solution-card {
  background: linear-gradient(135deg, #1f2d1f 0%, #203d20 100%);
  border-color: #2d5c2d;
}

.card-label {
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 0.75rem;
}

.problem-card .card-label { color: #dc2626; }
.solution-card .card-label { color: #16a34a; }

.card-title {
  font-size: 1.5rem;
  font-weight: 700;
  margin-bottom: 1rem;
}

.card-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.card-list li {
  padding: 0.5rem 0;
  padding-left: 1.75rem;
  position: relative;
}

.card-list li::before {
  position: absolute;
  left: 0;
  font-weight: bold;
}

.problem-card .card-list li::before {
  content: "✗";
  color: #dc2626;
}

.solution-card .card-list li::before {
  content: "✓";
  color: #16a34a;
}

/* Features Grid */
.features-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 1.5rem;
}

.feature-card {
  background: var(--md-code-bg-color);
  border: 1px solid var(--md-default-fg-color--lightest);
  border-radius: 12px;
  padding: 2rem;
  transition: all 0.2s ease;
}

.feature-card:hover {
  border-color: var(--venom-purple-light);
  box-shadow: 0 4px 20px rgba(124, 58, 237, 0.1);
}

.feature-icon {
  font-size: 2rem;
  margin-bottom: 1rem;
}

.feature-title {
  font-size: 1.25rem;
  font-weight: 700;
  margin-bottom: 0.75rem;
}

.feature-desc {
  color: var(--md-default-fg-color--light);
  line-height: 1.6;
}

/* Code Comparison */
.code-comparison {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2rem;
  margin: 3rem 0;
}

@media (max-width: 900px) {
  .code-comparison {
    grid-template-columns: 1fr;
  }
}

.code-block {
  background: #1a1a2e;
  border-radius: 12px;
  overflow: hidden;
}

.code-header {
  background: #252540;
  padding: 0.75rem 1rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.code-label {
  color: #888;
  font-size: 0.85rem;
  font-weight: 600;
}

.code-badge {
  font-size: 0.7rem;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-weight: 600;
}

.code-badge.old {
  background: #dc2626;
  color: white;
}

.code-badge.new {
  background: #16a34a;
  color: white;
}

.code-content {
  padding: 1.25rem;
  font-family: var(--md-code-font-family);
  font-size: 0.85rem;
  line-height: 1.6;
  color: #e0e0e0;
  overflow-x: auto;
}

.code-content .keyword { color: #c678dd; }
.code-content .string { color: #98c379; }
.code-content .function { color: #61afef; }
.code-content .comment { color: #5c6370; }

/* Steps */
.steps {
  max-width: 800px;
  margin: 0 auto;
}

.step {
  display: flex;
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.step-number {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  background: var(--venom-gradient);
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 1.25rem;
}

.step-content {
  flex: 1;
}

.step-title {
  font-size: 1.25rem;
  font-weight: 700;
  margin-bottom: 0.5rem;
}

.step-code {
  background: var(--md-code-bg-color);
  padding: 1rem;
  border-radius: 8px;
  font-family: var(--md-code-font-family);
  font-size: 0.9rem;
  margin-top: 0.75rem;
}

/* CTA */
.cta {
  background: var(--venom-gradient);
  padding: 5rem 2rem;
  text-align: center;
}

.cta-title {
  font-size: 2.5rem;
  font-weight: 700;
  color: white;
  margin-bottom: 1rem;
}

.cta-subtitle {
  color: rgba(255,255,255,0.8);
  font-size: 1.2rem;
  margin-bottom: 2rem;
}

/* Footer links */
.footer-links {
  display: flex;
  justify-content: center;
  gap: 2rem;
  padding: 3rem 2rem;
  background: var(--md-code-bg-color);
}

.footer-link {
  color: var(--md-default-fg-color--light);
  text-decoration: none;
  font-weight: 500;
}

.footer-link:hover {
  color: var(--venom-purple);
}

/* Responsive */
@media (max-width: 768px) {
  .hero h1 {
    font-size: 2.5rem;
  }

  .hero-tagline {
    font-size: 1.2rem;
  }

  .section-title {
    font-size: 2rem;
  }

  .hero-buttons {
    flex-direction: column;
    align-items: center;
  }
}
</style>

<!-- Hero -->
<div class="hero">
  <div class="hero-content">
    <h1>VenomQA</h1>
    <p class="hero-tagline">State-Based API Testing Framework</p>
    <p class="hero-subtitle">Test your entire app, not just endpoints. Find bugs that traditional testing misses.</p>

    <div class="terminal-box">
      <div class="terminal-header">
        <span class="terminal-dot red"></span>
        <span class="terminal-dot yellow"></span>
        <span class="terminal-dot green"></span>
        <span class="terminal-title">Terminal</span>
      </div>
      <div class="terminal-body">
        <div class="terminal-line">
          <span class="terminal-comment"># Try it now - no setup needed</span>
        </div>
        <div class="terminal-line">
          <span class="terminal-prompt">$</span>
          <span class="terminal-command"> pip install venomqa</span>
        </div>
        <div class="terminal-line">
          <span class="terminal-prompt">$</span>
          <span class="terminal-command"> venomqa demo</span>
        </div>
      </div>
    </div>

    <div class="hero-buttons">
      <a href="getting-started/quickstart/" class="btn btn-primary">Get Started</a>
      <a href="https://github.com/namanag97/venomqa" class="btn btn-secondary">GitHub</a>
    </div>
  </div>
</div>

<!-- Problem/Solution -->
<div class="section">
  <h2 class="section-title">Why VenomQA?</h2>
  <p class="section-subtitle">Traditional API testing checks endpoints in isolation. Real bugs hide in state combinations.</p>

  <div class="problem-solution">
    <div class="problem-card">
      <div class="card-label">The Problem</div>
      <div class="card-title">Traditional API Testing</div>
      <ul class="card-list">
        <li>Tests endpoints in isolation</li>
        <li>Each test starts from unknown state</li>
        <li>Misses bugs from state combinations</li>
        <li>Flaky tests from test interdependence</li>
        <li>Manual setup for each scenario</li>
      </ul>
    </div>
    <div class="solution-card">
      <div class="card-label">The Solution</div>
      <div class="card-title">VenomQA</div>
      <ul class="card-list">
        <li>Tests complete user journeys</li>
        <li>Checkpoints save exact database state</li>
        <li>Explores all state transitions automatically</li>
        <li>Branch from checkpoints - no flakiness</li>
        <li>Invariants catch consistency bugs</li>
      </ul>
    </div>
  </div>
</div>

<!-- Code Comparison -->
<div class="section section-dark">
  <h2 class="section-title">Two Ways to Test</h2>
  <p class="section-subtitle">Choose the approach that fits your needs.</p>

  <div class="code-comparison">
    <div class="code-block">
      <div class="code-header">
        <span class="code-label">Journey Testing</span>
        <span class="code-badge new">User Flows</span>
      </div>
      <div class="code-content">
<span class="keyword">from</span> venomqa <span class="keyword">import</span> Journey, Step

journey = Journey(
    name=<span class="string">"checkout"</span>,
    steps=[
        Step(<span class="string">"login"</span>, action=login),
        Step(<span class="string">"add_cart"</span>, action=add_to_cart),
        Checkpoint(<span class="string">"cart_ready"</span>),
        Branch(paths=[
            Path(<span class="string">"card"</span>, [pay_card]),
            Path(<span class="string">"wallet"</span>, [pay_wallet]),
        ])
    ]
)
      </div>
    </div>
    <div class="code-block">
      <div class="code-header">
        <span class="code-label">State Graph Testing</span>
        <span class="code-badge new">Auto-Explore</span>
      </div>
      <div class="code-content">
<span class="keyword">from</span> venomqa <span class="keyword">import</span> StateGraph

graph = StateGraph(<span class="string">"cart"</span>)
graph.add_node(<span class="string">"empty"</span>, initial=<span class="keyword">True</span>)
graph.add_node(<span class="string">"has_items"</span>)

graph.add_edge(<span class="string">"empty"</span>, <span class="string">"has_items"</span>,
    action=add_item)
graph.add_edge(<span class="string">"has_items"</span>, <span class="string">"empty"</span>,
    action=clear)

<span class="comment"># Explores ALL paths automatically</span>
result = graph.explore(client)
      </div>
    </div>
  </div>
</div>

<!-- Features -->
<div class="section">
  <h2 class="section-title">Key Features</h2>
  <p class="section-subtitle">Everything you need to test complex APIs.</p>

  <div class="features-grid">
    <div class="feature-card">
      <div class="feature-icon">🔀</div>
      <div class="feature-title">State Branching</div>
      <div class="feature-desc">Save database checkpoints, fork to test multiple paths from the same state. No more flaky tests.</div>
    </div>
    <div class="feature-card">
      <div class="feature-icon">🔍</div>
      <div class="feature-title">Auto Path Exploration</div>
      <div class="feature-desc">State graphs automatically discover and test all reachable paths. Find bugs humans miss.</div>
    </div>
    <div class="feature-card">
      <div class="feature-icon">✅</div>
      <div class="feature-title">Invariants</div>
      <div class="feature-desc">Rules that must always be true. "API count = DB count" checked after every action.</div>
    </div>
    <div class="feature-card">
      <div class="feature-icon">🐛</div>
      <div class="feature-title">Rich Debugging</div>
      <div class="feature-desc">Full request/response logs, timing breakdowns, and actionable suggestions on failure.</div>
    </div>
    <div class="feature-card">
      <div class="feature-icon">📊</div>
      <div class="feature-title">Multiple Reporters</div>
      <div class="feature-desc">HTML, JSON, JUnit XML, Markdown. Slack and Discord notifications built-in.</div>
    </div>
    <div class="feature-card">
      <div class="feature-icon">🔌</div>
      <div class="feature-title">Ports & Adapters</div>
      <div class="feature-desc">Swap backends (Postgres, Redis, S3) without changing tests. Mock external services.</div>
    </div>
  </div>
</div>

<!-- Quick Start -->
<div class="section section-dark">
  <h2 class="section-title">Get Started in 2 Minutes</h2>
  <p class="section-subtitle">From zero to running tests.</p>

  <div class="steps">
    <div class="step">
      <div class="step-number">1</div>
      <div class="step-content">
        <div class="step-title">Install VenomQA</div>
        <div class="step-code">pip install venomqa</div>
      </div>
    </div>
    <div class="step">
      <div class="step-number">2</div>
      <div class="step-content">
        <div class="step-title">See it work</div>
        <div class="step-code">venomqa demo</div>
      </div>
    </div>
    <div class="step">
      <div class="step-number">3</div>
      <div class="step-content">
        <div class="step-title">Create your project</div>
        <div class="step-code">venomqa init</div>
      </div>
    </div>
    <div class="step">
      <div class="step-number">4</div>
      <div class="step-content">
        <div class="step-title">Run your tests</div>
        <div class="step-code">venomqa run</div>
      </div>
    </div>
  </div>
</div>

<!-- CTA -->
<div class="cta">
  <div class="cta-title">Ready to find bugs others miss?</div>
  <div class="cta-subtitle">Start testing your API in minutes.</div>
  <div class="hero-buttons">
    <a href="getting-started/quickstart/" class="btn btn-primary">Read the Docs</a>
    <a href="https://github.com/namanag97/venomqa" class="btn btn-secondary">Star on GitHub</a>
  </div>
</div>

<!-- Footer -->
<div class="footer-links">
  <a href="getting-started/quickstart/" class="footer-link">Documentation</a>
  <a href="https://github.com/namanag97/venomqa" class="footer-link">GitHub</a>
  <a href="https://pypi.org/project/venomqa/" class="footer-link">PyPI</a>
  <a href="https://github.com/namanag97/venomqa/issues" class="footer-link">Issues</a>
</div>
