---
hide:
  - navigation
  - toc
  - footer
---

<style>
/* ══════════════════════════════════════════════════════════════
   VENOMQA LANDING PAGE - Engineering Blueprint Aesthetic
   Auto-scales between light and dark modes
   ══════════════════════════════════════════════════════════════ */

/* CSS Variables - Auto-scaling colors */
:root {
  --venom-bg: #f8fafc;
  --venom-bg-alt: #f1f5f9;
  --venom-surface: #ffffff;
  --venom-text: #0f172a;
  --venom-text-muted: #64748b;
  --venom-border: #e2e8f0;
  --venom-primary: #0ea5e9;
  --venom-primary-dim: #0284c7;
  --venom-success: #10b981;
  --venom-danger: #f43f5e;
  --venom-warning: #f59e0b;
  --venom-glow: rgba(14, 165, 233, 0.15);
  --venom-node-bg: #f0f9ff;
  --venom-path: #cbd5e1;
  --venom-font-display: 'DM Sans', system-ui, sans-serif;
  --venom-font-mono: 'IBM Plex Mono', monospace;
}

[data-md-color-scheme="slate"] {
  --venom-bg: #0f172a;
  --venom-bg-alt: #1e293b;
  --venom-surface: #1e293b;
  --venom-text: #f1f5f9;
  --venom-text-muted: #94a3b8;
  --venom-border: #334155;
  --venom-glow: rgba(14, 165, 233, 0.25);
  --venom-node-bg: #0c4a6e;
  --venom-path: #475569;
}

/* Reset for landing page */
.md-content {
  max-width: 100% !important;
}

.md-content__inner {
  margin: 0 !important;
  padding: 0 !important;
  max-width: 100% !important;
}

/* Google Fonts */
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

/* ══════════════════════════════════════════════════════════════
   LAYOUT
   ══════════════════════════════════════════════════════════════ */

.venom-landing {
  font-family: var(--venom-font-display);
  color: var(--venom-text);
  line-height: 1.6;
}

.venom-section {
  padding: 5rem 2rem;
}

.venom-container {
  max-width: 1100px;
  margin: 0 auto;
}

/* ══════════════════════════════════════════════════════════════
   HERO SECTION
   ══════════════════════════════════════════════════════════════ */

.venom-hero {
  text-align: center;
  padding: 4rem 2rem 3rem;
  background: var(--venom-bg);
}

.venom-hero h1 {
  font-size: clamp(2.5rem, 6vw, 4rem);
  font-weight: 700;
  margin: 0 0 1rem;
  letter-spacing: -0.03em;
  line-height: 1.1;
}

.venom-hero h1 span {
  color: var(--venom-primary);
}

.venom-hero-subtitle {
  font-size: 1.25rem;
  color: var(--venom-text-muted);
  max-width: 600px;
  margin: 0 auto 2rem;
}

.venom-hero-cta {
  display: flex;
  gap: 1rem;
  justify-content: center;
  flex-wrap: wrap;
}

.venom-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.875rem 1.75rem;
  border-radius: 8px;
  font-weight: 600;
  font-size: 1rem;
  text-decoration: none;
  transition: all 0.2s;
  font-family: var(--venom-font-display);
}

.venom-btn-primary {
  background: var(--venom-primary);
  color: white;
}

.venom-btn-primary:hover {
  background: var(--venom-primary-dim);
  transform: translateY(-2px);
  color: white;
}

.venom-btn-secondary {
  background: var(--venom-surface);
  color: var(--venom-text);
  border: 2px solid var(--venom-border);
}

.venom-btn-secondary:hover {
  border-color: var(--venom-primary);
  color: var(--venom-primary);
}

/* ══════════════════════════════════════════════════════════════
   ANIMATED STATE DIAGRAM - The Star of the Show
   ══════════════════════════════════════════════════════════════ */

.venom-diagram-section {
  background: var(--venom-bg-alt);
  padding: 4rem 2rem;
}

.venom-diagram-header {
  text-align: center;
  margin-bottom: 2rem;
}

.venom-diagram-header h2 {
  font-size: 1rem;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--venom-primary);
  margin: 0 0 0.5rem;
  font-weight: 600;
}

.venom-diagram-header p {
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0;
  color: var(--venom-text);
}

.venom-diagram-container {
  background: var(--venom-surface);
  border: 1px solid var(--venom-border);
  border-radius: 16px;
  padding: 3rem;
  max-width: 900px;
  margin: 0 auto;
  position: relative;
  overflow: hidden;
}

/* Blueprint grid background */
.venom-diagram-container::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(var(--venom-border) 1px, transparent 1px),
    linear-gradient(90deg, var(--venom-border) 1px, transparent 1px);
  background-size: 40px 40px;
  opacity: 0.5;
  pointer-events: none;
}

/* State Graph SVG */
.venom-state-graph {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: center;
  padding: 2rem 0;
}

.venom-state-graph svg {
  max-width: 100%;
  height: auto;
}

/* State nodes */
.state-node {
  transition: all 0.4s ease;
}

.state-node rect {
  fill: var(--venom-node-bg);
  stroke: var(--venom-border);
  stroke-width: 2;
  transition: all 0.4s ease;
}

.state-node.active rect {
  fill: var(--venom-primary);
  stroke: var(--venom-primary);
  filter: drop-shadow(0 0 20px var(--venom-glow));
}

.state-node.visited rect {
  stroke: var(--venom-success);
  stroke-width: 3;
}

.state-node text {
  fill: var(--venom-text);
  font-family: var(--venom-font-mono);
  font-size: 14px;
  font-weight: 500;
  transition: all 0.4s ease;
}

.state-node.active text {
  fill: white;
}

/* Edges/paths */
.state-edge {
  stroke: var(--venom-path);
  stroke-width: 2;
  fill: none;
  transition: all 0.4s ease;
}

.state-edge.active {
  stroke: var(--venom-primary);
  stroke-width: 3;
  filter: drop-shadow(0 0 8px var(--venom-glow));
}

.state-edge.traversed {
  stroke: var(--venom-success);
  stroke-width: 3;
}

/* Edge arrow markers */
.edge-arrow {
  fill: var(--venom-path);
  transition: all 0.4s ease;
}

.edge-arrow.active {
  fill: var(--venom-primary);
}

.edge-arrow.traversed {
  fill: var(--venom-success);
}

/* Edge labels */
.edge-label {
  font-family: var(--venom-font-mono);
  font-size: 11px;
  fill: var(--venom-text-muted);
}

/* Live stats */
.venom-live-stats {
  display: flex;
  justify-content: center;
  gap: 3rem;
  margin-top: 2rem;
  padding-top: 2rem;
  border-top: 1px solid var(--venom-border);
}

.venom-stat {
  text-align: center;
}

.venom-stat-value {
  font-family: var(--venom-font-mono);
  font-size: 2rem;
  font-weight: 600;
  color: var(--venom-primary);
  line-height: 1;
}

.venom-stat-label {
  font-size: 0.85rem;
  color: var(--venom-text-muted);
  margin-top: 0.25rem;
}

/* Status indicator */
.venom-status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  margin-top: 1.5rem;
  font-family: var(--venom-font-mono);
  font-size: 0.9rem;
  color: var(--venom-text-muted);
}

.venom-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--venom-success);
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ══════════════════════════════════════════════════════════════
   PROBLEM / SOLUTION - Visual Comparison
   ══════════════════════════════════════════════════════════════ */

.venom-comparison {
  background: var(--venom-bg);
  padding: 5rem 2rem;
}

.venom-comparison h2 {
  text-align: center;
  font-size: 2rem;
  margin: 0 0 3rem;
}

.venom-comparison-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2rem;
  max-width: 900px;
  margin: 0 auto;
}

@media (max-width: 768px) {
  .venom-comparison-grid {
    grid-template-columns: 1fr;
  }
}

.venom-comparison-card {
  padding: 2rem;
  border-radius: 12px;
  border: 2px solid;
}

.venom-comparison-card.problem {
  border-color: var(--venom-danger);
  background: color-mix(in srgb, var(--venom-danger) 5%, var(--venom-surface));
}

.venom-comparison-card.solution {
  border-color: var(--venom-success);
  background: color-mix(in srgb, var(--venom-success) 5%, var(--venom-surface));
}

.venom-comparison-card h3 {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 1.25rem;
  margin: 0 0 1.5rem;
}

.venom-comparison-icon {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
}

.problem .venom-comparison-icon {
  background: var(--venom-danger);
  color: white;
}

.solution .venom-comparison-icon {
  background: var(--venom-success);
  color: white;
}

/* Visual diagram inside cards */
.venom-mini-diagram {
  background: var(--venom-bg-alt);
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.venom-mini-diagram svg {
  width: 100%;
  height: auto;
}

.venom-comparison-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.venom-comparison-list li {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.5rem 0;
  color: var(--venom-text-muted);
}

.venom-comparison-list li::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-top: 0.5rem;
  flex-shrink: 0;
}

.problem .venom-comparison-list li::before {
  background: var(--venom-danger);
}

.solution .venom-comparison-list li::before {
  background: var(--venom-success);
}

/* ══════════════════════════════════════════════════════════════
   HOW IT WORKS - 3 Steps
   ══════════════════════════════════════════════════════════════ */

.venom-steps {
  background: var(--venom-bg-alt);
  padding: 5rem 2rem;
}

.venom-steps h2 {
  text-align: center;
  font-size: 2rem;
  margin: 0 0 3rem;
}

.venom-steps-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 2rem;
  max-width: 1000px;
  margin: 0 auto;
}

@media (max-width: 900px) {
  .venom-steps-grid {
    grid-template-columns: 1fr;
    max-width: 400px;
  }
}

.venom-step {
  text-align: center;
  padding: 2rem;
  background: var(--venom-surface);
  border-radius: 12px;
  border: 1px solid var(--venom-border);
}

.venom-step-icon {
  width: 80px;
  height: 80px;
  margin: 0 auto 1.5rem;
  background: var(--venom-bg-alt);
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid var(--venom-border);
}

.venom-step-icon svg {
  width: 40px;
  height: 40px;
  color: var(--venom-primary);
}

.venom-step-number {
  font-family: var(--venom-font-mono);
  font-size: 0.75rem;
  color: var(--venom-primary);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 0.5rem;
}

.venom-step h3 {
  font-size: 1.25rem;
  margin: 0 0 0.75rem;
}

.venom-step p {
  color: var(--venom-text-muted);
  margin: 0;
  font-size: 0.95rem;
}

/* ══════════════════════════════════════════════════════════════
   FEATURES
   ══════════════════════════════════════════════════════════════ */

.venom-features {
  background: var(--venom-bg);
  padding: 5rem 2rem;
}

.venom-features h2 {
  text-align: center;
  font-size: 2rem;
  margin: 0 0 3rem;
}

.venom-features-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.5rem;
  max-width: 1000px;
  margin: 0 auto;
}

.venom-feature {
  padding: 1.5rem;
  background: var(--venom-surface);
  border: 1px solid var(--venom-border);
  border-radius: 12px;
  transition: all 0.2s;
}

.venom-feature:hover {
  border-color: var(--venom-primary);
  transform: translateY(-2px);
}

.venom-feature-icon {
  font-size: 1.75rem;
  margin-bottom: 1rem;
}

.venom-feature h3 {
  font-size: 1.1rem;
  margin: 0 0 0.5rem;
}

.venom-feature p {
  color: var(--venom-text-muted);
  margin: 0;
  font-size: 0.9rem;
}

/* ══════════════════════════════════════════════════════════════
   CTA
   ══════════════════════════════════════════════════════════════ */

.venom-cta {
  background: var(--venom-bg-alt);
  padding: 5rem 2rem;
  text-align: center;
}

.venom-cta h2 {
  font-size: 2rem;
  margin: 0 0 1rem;
}

.venom-cta p {
  color: var(--venom-text-muted);
  font-size: 1.1rem;
  margin: 0 0 2rem;
}

.venom-install-box {
  display: inline-flex;
  align-items: center;
  gap: 1rem;
  background: var(--venom-surface);
  border: 2px solid var(--venom-border);
  border-radius: 8px;
  padding: 1rem 1.5rem;
  font-family: var(--venom-font-mono);
  margin-bottom: 2rem;
}

.venom-install-box code {
  font-size: 1rem;
  color: var(--venom-text);
  background: none;
  padding: 0;
}

/* ══════════════════════════════════════════════════════════════
   RESPONSIVE
   ══════════════════════════════════════════════════════════════ */

@media (max-width: 600px) {
  .venom-hero h1 {
    font-size: 2rem;
  }

  .venom-live-stats {
    gap: 1.5rem;
  }

  .venom-stat-value {
    font-size: 1.5rem;
  }

  .venom-diagram-container {
    padding: 1.5rem;
  }
}
</style>

<div class="venom-landing">

<!-- HERO -->
<section class="venom-hero">
  <div class="venom-container">
    <h1>Find <span>sequence bugs</span><br>your tests will never catch</h1>
    <p class="venom-hero-subtitle">
      VenomQA autonomously explores every API call sequence — the stateful bugs that pytest, Schemathesis, and Postman all miss.
    </p>
    <div class="venom-hero-cta">
      <a href="getting-started/quickstart/" class="venom-btn venom-btn-primary">Get Started</a>
      <a href="https://github.com/namanag97/venomqa" class="venom-btn venom-btn-secondary">View on GitHub</a>
    </div>
  </div>
</section>

<!-- ANIMATED STATE DIAGRAM -->
<section class="venom-diagram-section">
  <div class="venom-container">
    <div class="venom-diagram-header">
      <h2>Watch it work</h2>
      <p>VenomQA explores every state transition</p>
    </div>

    <div class="venom-diagram-container">
      <div class="venom-state-graph">
        <svg viewBox="0 0 700 200" id="stateGraphSvg">
          <!-- Arrows/markers definition -->
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M 0 0 L 10 5 L 0 10 z" class="edge-arrow" id="arrow1"/>
            </marker>
            <marker id="arrow-active" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M 0 0 L 10 5 L 0 10 z" class="edge-arrow active"/>
            </marker>
            <marker id="arrow-traversed" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M 0 0 L 10 5 L 0 10 z" class="edge-arrow traversed"/>
            </marker>
          </defs>

          <!-- Edge 1: Empty → Has Data -->
          <path id="edge1" class="state-edge" d="M 170 100 L 280 100" marker-end="url(#arrow)"/>
          <text class="edge-label" x="225" y="85">create()</text>

          <!-- Edge 2: Has Data → Modified -->
          <path id="edge2" class="state-edge" d="M 420 100 L 530 100" marker-end="url(#arrow)"/>
          <text class="edge-label" x="475" y="85">update()</text>

          <!-- Edge 3: Modified → Empty (curved, below) -->
          <path id="edge3" class="state-edge" d="M 570 130 Q 350 220 130 130" marker-end="url(#arrow)"/>
          <text class="edge-label" x="350" y="195">delete()</text>

          <!-- Node 1: Empty -->
          <g class="state-node" id="node1">
            <rect x="50" y="60" width="120" height="80" rx="12"/>
            <text x="110" y="95" text-anchor="middle">Empty</text>
            <text x="110" y="115" text-anchor="middle" style="font-size: 10px; fill: var(--venom-text-muted)">initial</text>
          </g>

          <!-- Node 2: Has Data -->
          <g class="state-node" id="node2">
            <rect x="290" y="60" width="120" height="80" rx="12"/>
            <text x="350" y="95" text-anchor="middle">Has Data</text>
            <text x="350" y="115" text-anchor="middle" style="font-size: 10px; fill: var(--venom-text-muted)">1+ items</text>
          </g>

          <!-- Node 3: Modified -->
          <g class="state-node" id="node3">
            <rect x="540" y="60" width="120" height="80" rx="12"/>
            <text x="600" y="95" text-anchor="middle">Modified</text>
            <text x="600" y="115" text-anchor="middle" style="font-size: 10px; fill: var(--venom-text-muted)">changed</text>
          </g>
        </svg>
      </div>

      <div class="venom-live-stats">
        <div class="venom-stat">
          <div class="venom-stat-value" id="pathsExplored">0</div>
          <div class="venom-stat-label">Paths Explored</div>
        </div>
        <div class="venom-stat">
          <div class="venom-stat-value" id="statesVisited">0</div>
          <div class="venom-stat-label">States Visited</div>
        </div>
        <div class="venom-stat">
          <div class="venom-stat-value" id="checksRun">0</div>
          <div class="venom-stat-label">Checks Run</div>
        </div>
      </div>

      <div class="venom-status">
        <span class="venom-status-dot"></span>
        <span id="statusText">Exploring paths...</span>
      </div>
    </div>
  </div>
</section>

<!-- PROBLEM vs SOLUTION -->
<section class="venom-comparison">
  <div class="venom-container">
    <h2>Traditional testing has blind spots</h2>

    <div class="venom-comparison-grid">
      <div class="venom-comparison-card problem">
        <h3>
          <span class="venom-comparison-icon">✗</span>
          Traditional Testing
        </h3>

        <!-- Visual: Isolated dots -->
        <div class="venom-mini-diagram">
          <svg viewBox="0 0 200 80">
            <circle cx="40" cy="40" r="20" fill="var(--venom-border)" stroke="var(--venom-danger)" stroke-width="2"/>
            <circle cx="100" cy="40" r="20" fill="var(--venom-border)" stroke="var(--venom-danger)" stroke-width="2"/>
            <circle cx="160" cy="40" r="20" fill="var(--venom-border)" stroke="var(--venom-danger)" stroke-width="2"/>
            <text x="40" y="44" text-anchor="middle" font-size="10" fill="var(--venom-text-muted)">Test 1</text>
            <text x="100" y="44" text-anchor="middle" font-size="10" fill="var(--venom-text-muted)">Test 2</text>
            <text x="160" y="44" text-anchor="middle" font-size="10" fill="var(--venom-text-muted)">Test 3</text>
          </svg>
        </div>

        <ul class="venom-comparison-list">
          <li>Each test runs in isolation</li>
          <li>State combinations untested</li>
          <li>Flaky from test order</li>
          <li>Manual scenario setup</li>
        </ul>
      </div>

      <div class="venom-comparison-card solution">
        <h3>
          <span class="venom-comparison-icon">✓</span>
          VenomQA
        </h3>

        <!-- Visual: Connected graph -->
        <div class="venom-mini-diagram">
          <svg viewBox="0 0 200 80">
            <line x1="60" y1="40" x2="100" y2="40" stroke="var(--venom-success)" stroke-width="2"/>
            <line x1="100" y1="40" x2="140" y2="40" stroke="var(--venom-success)" stroke-width="2"/>
            <path d="M 140 40 Q 100 80 60 40" fill="none" stroke="var(--venom-success)" stroke-width="2"/>
            <circle cx="40" cy="40" r="20" fill="var(--venom-success)" stroke="var(--venom-success)" stroke-width="2"/>
            <circle cx="100" cy="40" r="20" fill="var(--venom-node-bg)" stroke="var(--venom-success)" stroke-width="2"/>
            <circle cx="160" cy="40" r="20" fill="var(--venom-node-bg)" stroke="var(--venom-success)" stroke-width="2"/>
            <text x="40" y="44" text-anchor="middle" font-size="10" fill="white">A</text>
            <text x="100" y="44" text-anchor="middle" font-size="10" fill="var(--venom-text)">B</text>
            <text x="160" y="44" text-anchor="middle" font-size="10" fill="var(--venom-text)">C</text>
          </svg>
        </div>

        <ul class="venom-comparison-list">
          <li>Explores ALL paths automatically</li>
          <li>Finds state transition bugs</li>
          <li>Database checkpoints for branching</li>
          <li>Invariants checked everywhere</li>
        </ul>
      </div>
    </div>
  </div>
</section>

<!-- HOW IT WORKS -->
<section class="venom-steps">
  <div class="venom-container">
    <h2>How it works</h2>

    <div class="venom-steps-grid">
      <div class="venom-step">
        <div class="venom-step-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3"/>
            <circle cx="12" cy="4" r="2"/>
            <circle cx="12" cy="20" r="2"/>
            <circle cx="4" cy="12" r="2"/>
            <circle cx="20" cy="12" r="2"/>
            <line x1="12" y1="6" x2="12" y2="9"/>
            <line x1="12" y1="15" x2="12" y2="18"/>
            <line x1="6" y1="12" x2="9" y2="12"/>
            <line x1="15" y1="12" x2="18" y2="12"/>
          </svg>
        </div>
        <div class="venom-step-number">Step 1</div>
        <h3>Define States</h3>
        <p>Model your app as states and transitions. Empty cart, has items, checked out.</p>
      </div>

      <div class="venom-step">
        <div class="venom-step-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 11l3 3L22 4"/>
            <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>
          </svg>
        </div>
        <div class="venom-step-number">Step 2</div>
        <h3>Add Invariants</h3>
        <p>Define rules that must always hold. "Cart total = sum of items" checked everywhere.</p>
      </div>

      <div class="venom-step">
        <div class="venom-step-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
          </svg>
        </div>
        <div class="venom-step-number">Step 3</div>
        <h3>Explore</h3>
        <p>VenomQA traverses every path, checks invariants, reports violations.</p>
      </div>
    </div>
  </div>
</section>

<!-- COMPARISON TABLE -->
<section class="venom-matrix">
  <div class="venom-container">

    <div class="venom-matrix-header">
      <p class="venom-matrix-label">TOOL COMPARISON</p>
      <h2 class="venom-matrix-title">The only tool that tests sequences</h2>
      <p class="venom-matrix-subtitle">Other tools test endpoints in isolation. VenomQA tests what happens <em>between</em> them.</p>
    </div>

    <div class="venom-table-wrap">
      <table class="venom-compare-table">
        <thead>
          <tr>
            <th>Capability</th>
            <th class="venom-col-highlight">VenomQA</th>
            <th>Schemathesis</th>
            <th>pytest</th>
            <th>Postman</th>
            <th>Hypothesis</th>
            <th>Dredd</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Sequence / ordering bugs</td>
            <td class="venom-col-highlight venom-yes">✓ Only tool</td>
            <td class="venom-no">✗</td>
            <td class="venom-no">✗</td>
            <td class="venom-no">✗</td>
            <td class="venom-no">✗</td>
            <td class="venom-no">✗</td>
          </tr>
          <tr>
            <td>DB rollback &amp; branching</td>
            <td class="venom-col-highlight venom-yes">✓ Only tool</td>
            <td class="venom-no">✗</td>
            <td class="venom-no">✗</td>
            <td class="venom-no">✗</td>
            <td class="venom-no">✗</td>
            <td class="venom-no">✗</td>
          </tr>
          <tr>
            <td>Autonomous exploration</td>
            <td class="venom-col-highlight venom-yes">✓ Sequences</td>
            <td class="venom-partial">~ Per endpoint</td>
            <td class="venom-no">✗ Manual</td>
            <td class="venom-no">✗ Manual</td>
            <td class="venom-partial">~ Per function</td>
            <td class="venom-no">✗</td>
          </tr>
          <tr>
            <td>OpenAPI / Swagger</td>
            <td class="venom-col-highlight venom-yes">✓</td>
            <td class="venom-yes">✓</td>
            <td class="venom-no">✗</td>
            <td class="venom-yes">✓</td>
            <td class="venom-no">✗</td>
            <td class="venom-yes">✓</td>
          </tr>
          <tr>
            <td>Fuzz / random inputs</td>
            <td class="venom-col-highlight venom-no">✗</td>
            <td class="venom-yes">✓ Best-in-class</td>
            <td class="venom-no">✗</td>
            <td class="venom-no">✗</td>
            <td class="venom-yes">✓ Best-in-class</td>
            <td class="venom-no">✗</td>
          </tr>
          <tr>
            <td>Contract compliance</td>
            <td class="venom-col-highlight venom-no">✗</td>
            <td class="venom-yes">✓</td>
            <td class="venom-no">✗</td>
            <td class="venom-partial">~</td>
            <td class="venom-no">✗</td>
            <td class="venom-yes">✓ Best-in-class</td>
          </tr>
          <tr>
            <td>Zero test writing</td>
            <td class="venom-col-highlight venom-yes">✓</td>
            <td class="venom-yes">✓</td>
            <td class="venom-no">✗</td>
            <td class="venom-no">✗</td>
            <td class="venom-no">✗</td>
            <td class="venom-yes">✓</td>
          </tr>
          <tr>
            <td>Python native</td>
            <td class="venom-col-highlight venom-yes">✓</td>
            <td class="venom-yes">✓</td>
            <td class="venom-yes">✓</td>
            <td class="venom-no">✗ JS/GUI</td>
            <td class="venom-yes">✓</td>
            <td class="venom-no">✗ JS</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="venom-matrix-note">
      <strong>Recommended stack:</strong> Use <strong>Schemathesis</strong> to fuzz individual endpoints + <strong>VenomQA</strong> to find sequence bugs. They catch completely different bugs.
    </div>

  </div>
</section>

<!-- FEATURES -->
<section class="venom-features">
  <div class="venom-container">
    <h2>Features</h2>

    <div class="venom-features-grid">
      <div class="venom-feature">
        <div class="venom-feature-icon">🔀</div>
        <h3>State Graph Exploration</h3>
        <p>Model as nodes & edges. Auto-explore all reachable paths.</p>
      </div>

      <div class="venom-feature">
        <div class="venom-feature-icon">✅</div>
        <h3>Invariant Checking</h3>
        <p>Rules checked after every action. Catch consistency bugs.</p>
      </div>

      <div class="venom-feature">
        <div class="venom-feature-icon">💾</div>
        <h3>DB Checkpoint & Rollback</h3>
        <p>Save database state. Branch to test multiple paths.</p>
      </div>

      <div class="venom-feature">
        <div class="venom-feature-icon">🛡️</div>
        <h3>Resilience</h3>
        <p>Circuit breakers, retries, rate limiting built-in.</p>
      </div>

      <div class="venom-feature">
        <div class="venom-feature-icon">📊</div>
        <h3>Reports</h3>
        <p>HTML, JSON, JUnit. Slack & Discord notifications.</p>
      </div>

      <div class="venom-feature">
        <div class="venom-feature-icon">🔌</div>
        <h3>Adapters</h3>
        <p>Postgres, MySQL, Redis. Mock external services.</p>
      </div>
    </div>
  </div>
</section>

<!-- CTA -->
<section class="venom-cta">
  <div class="venom-container">
    <h2>Ready to find sequence bugs automatically?</h2>
    <p>pip install venomqa — finds bugs in 30 seconds, no configuration needed</p>

    <div class="venom-install-box">
      <code>pip install venomqa && venomqa demo</code>
    </div>

    <div>
      <a href="getting-started/quickstart/" class="venom-btn venom-btn-primary">Read the Docs</a>
    </div>
  </div>
</section>

<!-- SEO: crawlable text for search engines and LLMs -->
<section style="position:absolute;left:-9999px;top:auto;width:1px;height:1px;overflow:hidden;" aria-hidden="true">
<h2>Stateful API Testing Tool for Python</h2>
<p>VenomQA is a Python library for autonomous stateful API testing. Unlike pytest which tests functions in isolation, or Schemathesis which fuzzes individual endpoints, VenomQA tests sequences of API calls: create then refund then refund, finding the double-refund bug that your unit tests miss.</p>
<p>Use VenomQA to find sequence bugs, state machine bugs, and ordering bugs in REST APIs. Works with PostgreSQL, SQLite, Redis. Generates test actions from OpenAPI specs. Alternatives: Schemathesis, Dredd, Newman, Postman, pytest-httpx.</p>
<p>Install with pip install venomqa. Python 3.10+. MIT license. Open source.</p>
</section>

</div>

<script>
// State graph animation
(function() {
  const nodes = ['node1', 'node2', 'node3'];
  const edges = ['edge1', 'edge2', 'edge3'];

  let pathsExplored = 0;
  let statesVisited = 0;
  let checksRun = 0;
  let step = 0;

  const sequence = [
    { type: 'node', id: 'node1', status: 'Visiting: Empty' },
    { type: 'edge', id: 'edge1', status: 'Action: create()' },
    { type: 'node', id: 'node2', status: 'Visiting: Has Data' },
    { type: 'check', status: 'Checking invariants...' },
    { type: 'edge', id: 'edge2', status: 'Action: update()' },
    { type: 'node', id: 'node3', status: 'Visiting: Modified' },
    { type: 'check', status: 'Checking invariants...' },
    { type: 'path', status: 'Path complete ✓' },
    { type: 'edge', id: 'edge3', status: 'Action: delete()' },
    { type: 'node', id: 'node1', status: 'Visiting: Empty' },
    { type: 'check', status: 'Checking invariants...' },
    { type: 'path', status: 'Path complete ✓' },
    { type: 'reset', status: 'Exploring paths...' }
  ];

  function updateStats() {
    document.getElementById('pathsExplored').textContent = pathsExplored;
    document.getElementById('statesVisited').textContent = statesVisited;
    document.getElementById('checksRun').textContent = checksRun;
  }

  function clearActive() {
    nodes.forEach(id => {
      document.getElementById(id)?.classList.remove('active');
    });
    edges.forEach(id => {
      document.getElementById(id)?.classList.remove('active');
    });
  }

  function resetAll() {
    nodes.forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.classList.remove('active', 'visited');
      }
    });
    edges.forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.classList.remove('active', 'traversed');
      }
    });
  }

  function animate() {
    const action = sequence[step];
    document.getElementById('statusText').textContent = action.status;

    if (action.type === 'node') {
      clearActive();
      const node = document.getElementById(action.id);
      if (node) {
        node.classList.add('active', 'visited');
      }
      statesVisited++;
    } else if (action.type === 'edge') {
      clearActive();
      const edge = document.getElementById(action.id);
      if (edge) {
        edge.classList.add('active', 'traversed');
      }
    } else if (action.type === 'check') {
      checksRun++;
    } else if (action.type === 'path') {
      pathsExplored++;
    } else if (action.type === 'reset') {
      resetAll();
    }

    updateStats();
    step = (step + 1) % sequence.length;
  }

  // Start animation
  setTimeout(() => {
    setInterval(animate, 1200);
  }, 500);
})();
</script>
