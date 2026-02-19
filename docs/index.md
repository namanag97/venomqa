---
hide:
  - navigation
  - toc
  - footer
---

<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600&family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet">

<style>
/* ═══════════════════════════════════════════════════════════════
   VENOMQA — MERIDIAN DESIGN SYSTEM
   Swiss / Bauhaus / Precision Instrument
   ═══════════════════════════════════════════════════════════════ */

:root {
  --stone-50:  #F8F5F2;
  --stone-100: #F0ECE8;
  --stone-200: #E2DDD8;
  --stone-300: #CCC6BF;
  --stone-400: #A89E94;
  --stone-500: #7A6E66;
  --stone-600: #5A5049;
  --stone-700: #3E3530;
  --stone-800: #292118;
  --stone-900: #18120C;

  --orange:    #D05A08;
  --orange-lt: #FDF0E8;
  --orange-bdr:#F0A070;

  --green:     #176B3A;
  --green-lt:  #EBF5EF;
  --amber:     #8A5A00;
  --amber-lt:  #FBF3E0;
  --red:       #AA2020;
  --red-lt:    #FBEDED;

  --sans: 'Geist', system-ui, sans-serif;
  --mono: 'Geist Mono', 'Courier New', monospace;
}

[data-md-color-scheme="slate"] {
  --stone-50:  #1C1714;
  --stone-100: #221E1A;
  --stone-200: #2E2924;
  --stone-300: #3E3835;
  --stone-400: #6B6460;
  --stone-500: #9A918B;
  --stone-600: #B8B0A9;
  --stone-700: #D0C9C3;
  --stone-800: #E8E3DE;
  --stone-900: #F5F2EF;
}

/* Reset MkDocs Material layout for this page */
.md-content {
  max-width: 100% !important;
}
.md-content__inner {
  margin: 0 !important;
  padding: 0 !important;
  max-width: 100% !important;
}
.md-content__inner > h1:first-child {
  display: none;
}

/* ── BASE ────────────────────────────────────────────────────── */

.vp {
  font-family: var(--sans);
  color: var(--stone-900);
  background: var(--stone-50);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}

/* ── TOP BAR ─────────────────────────────────────────────────── */

.vp-topbar {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--stone-400);
  letter-spacing: 0.08em;
  padding: 0 2rem;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--stone-200);
  background: var(--stone-50);
}

.vp-topbar-left {
  font-weight: 500;
  color: var(--stone-600);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.vp-topbar-line {
  flex: 1;
  height: 1px;
  background: var(--stone-200);
  margin: 0 1.5rem;
}

.vp-topbar-right {
  color: var(--stone-400);
  white-space: nowrap;
}

/* ── SECTION LABEL ───────────────────────────────────────────── */

.vp-label {
  font-family: var(--mono);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--orange);
  margin-bottom: 2rem;
}

/* ── HERO ────────────────────────────────────────────────────── */

.vp-hero {
  padding: 6rem 2rem 5rem;
  background: var(--stone-50);
  border-bottom: 1px solid var(--stone-200);
}

.vp-hero-inner {
  max-width: 880px;
  margin: 0 auto;
}

.vp-hero h1 {
  font-family: var(--sans);
  font-size: clamp(2.8rem, 5.5vw, 4.8rem);
  font-weight: 300;
  letter-spacing: -0.03em;
  line-height: 1.08;
  color: var(--stone-900);
  margin: 0 0 1.5rem;
}

.vp-hero-sub {
  font-size: 1.1rem;
  font-weight: 300;
  color: var(--stone-500);
  max-width: 600px;
  margin: 0 0 2.5rem;
  line-height: 1.65;
}

.vp-hero-cta {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 3.5rem;
}

.vp-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  border-radius: 0;
  font-family: var(--mono);
  font-size: 0.85rem;
  font-weight: 500;
  text-decoration: none;
  letter-spacing: 0.02em;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
  border: 1px solid transparent;
}

.vp-btn-primary {
  background: var(--stone-900);
  color: var(--stone-50);
  border-color: var(--stone-900);
}

.vp-btn-primary:hover {
  background: var(--stone-800);
  border-color: var(--stone-800);
  color: var(--stone-50);
}

.vp-btn-secondary {
  background: transparent;
  color: var(--stone-700);
  border-color: var(--stone-300);
}

.vp-btn-secondary:hover {
  border-color: var(--stone-500);
  color: var(--stone-900);
}

.vp-hero-rule {
  border: none;
  border-top: 1px solid var(--stone-200);
  margin: 0 0 2.5rem;
}

.vp-hero-stats {
  display: flex;
  gap: 3rem;
  flex-wrap: wrap;
}

.vp-hero-stat {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.vp-hero-stat-num {
  font-family: var(--sans);
  font-size: 2rem;
  font-weight: 300;
  letter-spacing: -0.02em;
  color: var(--stone-900);
  line-height: 1;
}

.vp-hero-stat-lbl {
  font-family: var(--mono);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--stone-400);
}

/* ── TERMINAL ────────────────────────────────────────────────── */

.vp-terminal-section {
  padding: 5rem 2rem;
  background: var(--stone-100);
  border-bottom: 1px solid var(--stone-200);
}

.vp-terminal-inner {
  max-width: 760px;
  margin: 0 auto;
}

.vp-terminal {
  background: #100E0B;
  border: 1px solid var(--stone-200);
  border-radius: 0;
  overflow: hidden;
}

.vp-terminal-titlebar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #2A2320;
}

.vp-terminal-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #3E3530;
}

.vp-terminal-title {
  font-family: var(--mono);
  font-size: 11px;
  color: #4A4240;
  letter-spacing: 0.08em;
  margin-left: auto;
}

.vp-terminal-body {
  padding: 1.75rem 2rem;
  font-family: var(--mono);
  font-size: 0.82rem;
  line-height: 1.8;
  color: #C8BEB6;
}

.vp-t-prompt {
  color: var(--orange);
}

.vp-t-cmd {
  color: #D0C8C0;
}

.vp-t-dim {
  color: #4A4240;
}

.vp-t-pass {
  color: #176B3A;
}

.vp-t-rule {
  color: #3E3530;
}

.vp-t-key {
  color: #A89E94;
}

.vp-t-val {
  color: #D0C8C0;
}

.vp-t-critical {
  color: #AA2020;
  font-weight: 600;
}

.vp-t-warn {
  color: var(--orange);
}

.vp-t-em {
  color: #F0ECE8;
}

.vp-t-footer {
  display: block;
  margin-top: 0.5rem;
  padding-top: 0.75rem;
  border-top: 1px solid #2A2320;
  font-family: var(--mono);
  font-size: 10px;
  color: #3E3530;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

/* ── PROBLEM ─────────────────────────────────────────────────── */

.vp-problem {
  padding: 5.5rem 2rem;
  border-bottom: 1px solid var(--stone-200);
  background: var(--stone-50);
}

.vp-problem-inner {
  max-width: 1080px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 5rem;
}

@media (max-width: 860px) {
  .vp-problem-inner {
    grid-template-columns: 1fr;
    gap: 3rem;
  }
}

.vp-problem-col h2 {
  font-family: var(--sans);
  font-size: 1.6rem;
  font-weight: 300;
  letter-spacing: -0.02em;
  color: var(--stone-900);
  margin: 0 0 2rem;
  line-height: 1.25;
}

.vp-bug-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.vp-bug-item {
  padding: 1rem 0;
  border-bottom: 1px solid var(--stone-200);
}

.vp-bug-item:last-child {
  border-bottom: none;
}

.vp-bug-seq {
  font-family: var(--mono);
  font-size: 0.8rem;
  color: var(--stone-600);
  margin-bottom: 0.3rem;
  display: block;
}

.vp-bug-desc {
  font-family: var(--mono);
  font-size: 0.75rem;
  color: var(--red);
  letter-spacing: 0.02em;
}

.vp-problem-text {
  font-size: 0.95rem;
  font-weight: 300;
  color: var(--stone-500);
  line-height: 1.75;
  margin: 0 0 1.25rem;
}

.vp-problem-text:last-child {
  margin-bottom: 0;
}

/* ── HOW IT WORKS ────────────────────────────────────────────── */

.vp-how {
  padding: 5.5rem 2rem;
  background: var(--stone-100);
  border-bottom: 1px solid var(--stone-200);
}

.vp-how-inner {
  max-width: 1080px;
  margin: 0 auto;
}

.vp-how-header {
  margin-bottom: 4rem;
}

.vp-how-header h2 {
  font-family: var(--sans);
  font-size: clamp(1.6rem, 3vw, 2.2rem);
  font-weight: 300;
  letter-spacing: -0.02em;
  color: var(--stone-900);
  margin: 0;
}

.vp-steps-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0;
  border: 1px solid var(--stone-200);
  background: var(--stone-50);
}

@media (max-width: 860px) {
  .vp-steps-grid {
    grid-template-columns: 1fr;
  }
  .vp-step + .vp-step {
    border-left: none !important;
    border-top: 1px solid var(--stone-200);
  }
}

.vp-step {
  padding: 2.5rem 2rem;
}

.vp-step + .vp-step {
  border-left: 1px solid var(--stone-200);
}

.vp-step-num {
  font-family: var(--mono);
  font-size: 2rem;
  font-weight: 400;
  color: var(--stone-300);
  line-height: 1;
  margin-bottom: 1.5rem;
  display: block;
}

.vp-step h3 {
  font-family: var(--sans);
  font-size: 1rem;
  font-weight: 500;
  color: var(--stone-900);
  margin: 0 0 0.75rem;
}

.vp-step p {
  font-size: 0.9rem;
  font-weight: 300;
  color: var(--stone-500);
  margin: 0;
  line-height: 1.65;
}

/* ── CODE BLOCK ──────────────────────────────────────────────── */

.vp-code-section {
  padding: 5.5rem 2rem;
  background: var(--stone-50);
  border-bottom: 1px solid var(--stone-200);
}

.vp-code-inner {
  max-width: 820px;
  margin: 0 auto;
}

.vp-code-header {
  margin-bottom: 2rem;
}

.vp-code-header h2 {
  font-family: var(--sans);
  font-size: clamp(1.4rem, 2.5vw, 1.9rem);
  font-weight: 300;
  letter-spacing: -0.02em;
  color: var(--stone-900);
  margin: 0;
}

.vp-code-block {
  background: #100E0B;
  border: 1px solid var(--stone-200);
  border-radius: 0;
  overflow: auto;
}

.vp-code-block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1.25rem;
  border-bottom: 1px solid #2A2320;
}

.vp-code-filename {
  font-family: var(--mono);
  font-size: 11px;
  color: #6A6260;
  letter-spacing: 0.06em;
}

.vp-code-lang {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--orange);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.vp-code-block pre {
  margin: 0;
  padding: 1.75rem 1.5rem;
  font-family: var(--mono);
  font-size: 0.8rem;
  line-height: 1.75;
  color: #C8BEB6;
  white-space: pre;
  overflow-x: auto;
}

.vp-c-kw  { color: #A89E94; }
.vp-c-fn  { color: #D0C8C0; }
.vp-c-str { color: #8A7A6E; }
.vp-c-cmt { color: #3E3530; font-style: italic; }
.vp-c-cls { color: var(--orange); }
.vp-c-num { color: #9E8E85; }
.vp-c-arg { color: #B0A899; }

/* ── TABLE ───────────────────────────────────────────────────── */

.vp-table-section {
  padding: 5.5rem 2rem;
  background: var(--stone-100);
  border-bottom: 1px solid var(--stone-200);
}

.vp-table-inner {
  max-width: 1100px;
  margin: 0 auto;
}

.vp-table-header {
  margin-bottom: 3rem;
  max-width: 600px;
}

.vp-table-header h2 {
  font-family: var(--sans);
  font-size: clamp(1.6rem, 3vw, 2.2rem);
  font-weight: 300;
  letter-spacing: -0.02em;
  color: var(--stone-900);
  margin: 0 0 0.75rem;
}

.vp-table-sub {
  font-size: 0.95rem;
  font-weight: 300;
  color: var(--stone-500);
  margin: 0;
}

.vp-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--stone-200);
  background: var(--stone-50);
}

.vp-compare-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
  background: var(--stone-50);
}

.vp-compare-table th {
  padding: 0.875rem 1rem;
  font-family: var(--mono);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--stone-400);
  font-weight: 400;
  text-align: center;
  border-bottom: 1px solid var(--stone-200);
  white-space: nowrap;
  background: var(--stone-100);
}

.vp-compare-table th:first-child {
  text-align: left;
}

.vp-compare-table td {
  padding: 0.8rem 1rem;
  text-align: center;
  border-bottom: 1px solid var(--stone-200);
  color: var(--stone-400);
  font-family: var(--mono);
  font-size: 0.8rem;
  white-space: nowrap;
}

.vp-compare-table td:first-child {
  text-align: left;
  font-family: var(--sans);
  font-size: 0.875rem;
  font-weight: 400;
  color: var(--stone-700);
  white-space: normal;
}

.vp-compare-table tr:last-child td {
  border-bottom: none;
}

.vp-col-venom {
  background: var(--orange-lt) !important;
  border-left: 2px solid var(--orange) !important;
}

.vp-compare-table th.vp-col-venom {
  color: var(--orange) !important;
  font-weight: 600;
}

.vp-compare-table td.vp-col-venom {
  font-weight: 500;
  color: var(--stone-700);
}

.vp-yes { color: var(--green) !important; font-weight: 500; }
.vp-no  { color: var(--stone-300) !important; }
.vp-partial { color: var(--amber) !important; font-weight: 500; }

.vp-table-note {
  margin-top: 1.5rem;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--stone-400);
  letter-spacing: 0.04em;
  padding-left: 0.25rem;
}

/* ── FEATURES ────────────────────────────────────────────────── */

.vp-features {
  padding: 5.5rem 2rem;
  background: var(--stone-50);
  border-bottom: 1px solid var(--stone-200);
}

.vp-features-inner {
  max-width: 1080px;
  margin: 0 auto;
}

.vp-features-header {
  margin-bottom: 3rem;
}

.vp-features-header h2 {
  font-family: var(--sans);
  font-size: clamp(1.6rem, 3vw, 2.2rem);
  font-weight: 300;
  letter-spacing: -0.02em;
  color: var(--stone-900);
  margin: 0;
}

.vp-feat-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0;
  border: 1px solid var(--stone-200);
}

@media (max-width: 900px) {
  .vp-feat-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 560px) {
  .vp-feat-grid {
    grid-template-columns: 1fr;
  }
}

.vp-feat-card {
  padding: 2rem;
  border-right: 1px solid var(--stone-200);
  border-bottom: 1px solid var(--stone-200);
  background: var(--stone-50);
  transition: border-left 0.15s;
  position: relative;
}

.vp-feat-card:nth-child(3n) {
  border-right: none;
}

.vp-feat-card:nth-last-child(-n+3) {
  border-bottom: none;
}

.vp-feat-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 2px;
  background: transparent;
  transition: background 0.15s;
}

.vp-feat-card:hover::before {
  background: var(--orange);
}

.vp-feat-name {
  font-family: var(--sans);
  font-size: 0.95rem;
  font-weight: 500;
  color: var(--stone-900);
  margin: 0 0 0.5rem;
}

.vp-feat-desc {
  font-size: 0.875rem;
  font-weight: 300;
  color: var(--stone-500);
  margin: 0;
  line-height: 1.6;
}

/* ── CTA ─────────────────────────────────────────────────────── */

.vp-cta {
  padding: 6rem 2rem;
  background: var(--stone-100);
  border-bottom: 1px solid var(--stone-200);
}

.vp-cta-inner {
  max-width: 680px;
  margin: 0 auto;
}

.vp-cta h2 {
  font-family: var(--sans);
  font-size: clamp(2rem, 4vw, 3rem);
  font-weight: 300;
  letter-spacing: -0.02em;
  color: var(--stone-900);
  margin: 0 0 2.5rem;
  line-height: 1.15;
}

.vp-cta-cmds {
  display: flex;
  flex-direction: column;
  gap: 0;
  border: 1px solid var(--stone-200);
  background: #100E0B;
  margin-bottom: 2.5rem;
}

.vp-cta-cmd {
  display: flex;
  align-items: center;
  padding: 0.9rem 1.25rem;
  font-family: var(--mono);
  font-size: 0.875rem;
  color: #C8BEB6;
  border-bottom: 1px solid #2A2320;
}

.vp-cta-cmd:last-child {
  border-bottom: none;
}

.vp-cta-cmd-prompt {
  color: var(--orange);
  margin-right: 0.75rem;
  flex-shrink: 0;
}

.vp-cta-links {
  display: flex;
  gap: 2rem;
  align-items: center;
  margin-bottom: 3rem;
}

.vp-cta-link {
  font-family: var(--mono);
  font-size: 0.85rem;
  color: var(--stone-600);
  text-decoration: none;
  letter-spacing: 0.04em;
  border-bottom: 1px solid var(--stone-300);
  padding-bottom: 1px;
  transition: color 0.15s, border-color 0.15s;
}

.vp-cta-link:hover {
  color: var(--orange);
  border-color: var(--orange);
}

.vp-cta-footer {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--stone-400);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

/* ── SCROLL ANIMATIONS ───────────────────────────────────────── */

.vp-fade {
  opacity: 0;
  transform: translateY(16px);
  transition: opacity 0.4s ease-out, transform 0.4s ease-out;
}

.vp-fade.vp-visible {
  opacity: 1;
  transform: translateY(0);
}

.vp-fade-d1 { transition-delay: 0.05s; }
.vp-fade-d2 { transition-delay: 0.12s; }
.vp-fade-d3 { transition-delay: 0.19s; }
.vp-fade-d4 { transition-delay: 0.26s; }
.vp-fade-d5 { transition-delay: 0.33s; }
.vp-fade-d6 { transition-delay: 0.40s; }

/* ── DARK MODE OVERRIDES ─────────────────────────────────────── */

[data-md-color-scheme="slate"] .vp-topbar,
[data-md-color-scheme="slate"] .vp-hero,
[data-md-color-scheme="slate"] .vp-problem,
[data-md-color-scheme="slate"] .vp-code-section,
[data-md-color-scheme="slate"] .vp-features,
[data-md-color-scheme="slate"] .vp-feat-card {
  background: var(--stone-50);
}

[data-md-color-scheme="slate"] .vp-terminal-section,
[data-md-color-scheme="slate"] .vp-how,
[data-md-color-scheme="slate"] .vp-table-section,
[data-md-color-scheme="slate"] .vp-cta {
  background: var(--stone-100);
}

[data-md-color-scheme="slate"] .vp-steps-grid,
[data-md-color-scheme="slate"] .vp-step,
[data-md-color-scheme="slate"] .vp-table-wrap,
[data-md-color-scheme="slate"] .vp-compare-table {
  background: var(--stone-50);
}

[data-md-color-scheme="slate"] .vp-compare-table th {
  background: var(--stone-100);
}

[data-md-color-scheme="slate"] .vp-col-venom {
  background: rgba(208, 90, 8, 0.08) !important;
}
</style>

<div class="vp">

<!-- ── TOP BAR ──────────────────────────────────────────────────── -->
<div class="vp-topbar">
  <span class="vp-topbar-left">VENOMQA</span>
  <span class="vp-topbar-line"></span>
  <span class="vp-topbar-right">v0.6.4 · MIT · Python 3.10+</span>
</div>

<!-- ── HERO ─────────────────────────────────────────────────────── -->
<section class="vp-hero">
  <div class="vp-hero-inner">
    <div class="vp-label vp-fade">// AUTONOMOUS API TESTING</div>
    <h1 class="vp-fade vp-fade-d1">Find the bugs hiding<br>between your API calls.</h1>
    <p class="vp-hero-sub vp-fade vp-fade-d2">VenomQA explores every sequence of API calls automatically — the stateful bugs that pytest, Schemathesis, and Postman never see.</p>
    <div class="vp-hero-cta vp-fade vp-fade-d3">
      <a href="https://pypi.org/project/venomqa/" class="vp-btn vp-btn-primary">pip install venomqa</a>
      <a href="https://github.com/namanag97/venomqa" class="vp-btn vp-btn-secondary">View on GitHub</a>
    </div>
    <hr class="vp-hero-rule vp-fade vp-fade-d4">
    <div class="vp-hero-stats vp-fade vp-fade-d5">
      <div class="vp-hero-stat">
        <span class="vp-hero-stat-num">20+</span>
        <span class="vp-hero-stat-lbl">STATES EXPLORED</span>
      </div>
      <div class="vp-hero-stat">
        <span class="vp-hero-stat-num">∞</span>
        <span class="vp-hero-stat-lbl">SEQUENCES TESTED</span>
      </div>
      <div class="vp-hero-stat">
        <span class="vp-hero-stat-num">0</span>
        <span class="vp-hero-stat-lbl">TEST SCRIPTS WRITTEN</span>
      </div>
    </div>
  </div>
</section>

<!-- ── TERMINAL ──────────────────────────────────────────────────── -->
<section class="vp-terminal-section">
  <div class="vp-terminal-inner">
    <div class="vp-label vp-fade">// LIVE DEMO OUTPUT</div>
    <div class="vp-terminal vp-fade vp-fade-d1">
      <div class="vp-terminal-titlebar">
        <span class="vp-terminal-dot"></span>
        <span class="vp-terminal-dot"></span>
        <span class="vp-terminal-dot"></span>
        <span class="vp-terminal-title">bash</span>
      </div>
      <div class="vp-terminal-body">
<span class="vp-t-prompt">$</span> <span class="vp-t-cmd">venomqa demo</span>
<span class="vp-t-dim"></span>
  <span class="vp-t-key">Unit Tests:  </span><span class="vp-t-pass">3/3 PASS ✓</span>
<span class="vp-t-dim"></span>
  <span class="vp-t-em">VenomQA Exploration </span><span class="vp-t-rule">────────────────────────</span>
  <span class="vp-t-key">States visited:     </span><span class="vp-t-val">8</span>
  <span class="vp-t-key">Transitions:        </span><span class="vp-t-val">20</span>
  <span class="vp-t-key">Invariants checked: </span><span class="vp-t-val">40</span>
<span class="vp-t-dim"></span>
  <span class="vp-t-critical">╭─ CRITICAL VIOLATION ──────────────────────────╮</span>
  <span class="vp-t-critical">│</span> <span class="vp-t-key">Sequence: </span><span class="vp-t-warn">create_order → refund → refund</span>       <span class="vp-t-critical">│</span>
  <span class="vp-t-critical">│</span> <span class="vp-t-key">Bug:      </span><span class="vp-t-warn">refunded $200 on a $100 order</span>         <span class="vp-t-critical">│</span>
  <span class="vp-t-critical">╰───────────────────────────────────────────────╯</span>
<span class="vp-t-dim"></span>
  <span class="vp-t-key">Summary: </span><span class="vp-t-pass">3 tests passed.</span> <span class="vp-t-critical">1 sequence bug found.</span>
  <span class="vp-t-dim">Your tests passed. VenomQA found the bug.</span>
<span class="vp-t-footer">// 0.6.4 · namanag97.github.io/venomqa</span>
      </div>
    </div>
  </div>
</section>

<!-- ── THE PROBLEM ───────────────────────────────────────────────── -->
<section class="vp-problem">
  <div class="vp-problem-inner">
    <div class="vp-problem-col vp-fade">
      <div class="vp-label">// 01 THE PROBLEM</div>
      <h2>Your tests pass.<br>The bug ships.</h2>
      <ul class="vp-bug-list">
        <li class="vp-bug-item">
          <span class="vp-bug-seq">POST /refund → 200 · POST /refund → 200</span>
          <span class="vp-bug-desc">→ over-refund: refunded more than original amount</span>
        </li>
        <li class="vp-bug-item">
          <span class="vp-bug-seq">DELETE /user → 204 · GET /user → 200</span>
          <span class="vp-bug-desc">→ stale state: deleted user still accessible</span>
        </li>
        <li class="vp-bug-item">
          <span class="vp-bug-seq">POST /order → 201 · POST /order → 201</span>
          <span class="vp-bug-desc">→ duplicate creation: idempotency not enforced</span>
        </li>
      </ul>
    </div>
    <div class="vp-problem-col vp-fade vp-fade-d2">
      <div class="vp-label">// WHY SEQUENCES MATTER</div>
      <h2>Why sequences<br>matter.</h2>
      <p class="vp-problem-text">Unit tests are stateless. Each request runs in isolation, against a clean fixture, with a predetermined response. That's not how production works.</p>
      <p class="vp-problem-text">In production, your API has state. When a user creates an order, then requests a refund, then requests another refund — each individual HTTP call looks valid. The bug only appears in the sequence.</p>
      <p class="vp-problem-text">VenomQA explores the state graph your application creates. It tries every combination: create→refund→refund, create→cancel→refund. With DB rollback between branches, it covers paths no human would think to write.</p>
    </div>
  </div>
</section>

<!-- ── HOW IT WORKS ──────────────────────────────────────────────── -->
<section class="vp-how">
  <div class="vp-how-inner">
    <div class="vp-how-header vp-fade">
      <div class="vp-label">// 02 HOW IT WORKS</div>
      <h2>Three concepts.<br>No test scripts.</h2>
    </div>
    <div class="vp-steps-grid">
      <div class="vp-step vp-fade vp-fade-d1">
        <span class="vp-step-num">01</span>
        <h3>Define Actions</h3>
        <p>Write the API calls your users actually make. <code>create_order</code>, <code>refund</code>, <code>cancel</code>. That's it. Each action is a Python function: <code>(api, context) → response</code>.</p>
      </div>
      <div class="vp-step vp-fade vp-fade-d2">
        <span class="vp-step-num">02</span>
        <h3>Define Invariants</h3>
        <p>Rules that must always hold. <code>refunded ≤ original_amount</code>. VenomQA checks them after every single step — not just at test boundaries.</p>
      </div>
      <div class="vp-step vp-fade vp-fade-d3">
        <span class="vp-step-num">03</span>
        <h3>Explore</h3>
        <p>VenomQA tries every sequence: create→refund→refund, create→cancel→refund. The DB rolls back between branches. Violations surface automatically.</p>
      </div>
    </div>
  </div>
</section>

<!-- ── CODE EXAMPLE ──────────────────────────────────────────────── -->
<section class="vp-code-section">
  <div class="vp-code-inner">
    <div class="vp-code-header vp-fade">
      <div class="vp-label">// 03 MINIMAL EXAMPLE</div>
      <h2>Twenty lines.<br>One bug found.</h2>
    </div>
    <div class="vp-code-block vp-fade vp-fade-d1">
      <div class="vp-code-block-header">
        <span class="vp-code-filename">qa/test_orders.py</span>
        <span class="vp-code-lang">PYTHON</span>
      </div>
      <pre><span class="vp-c-kw">from</span> venomqa <span class="vp-c-kw">import</span> <span class="vp-c-cls">Action</span>, <span class="vp-c-cls">Agent</span>, <span class="vp-c-cls">BFS</span>, <span class="vp-c-cls">Invariant</span>, <span class="vp-c-cls">Severity</span>, <span class="vp-c-cls">World</span>
<span class="vp-c-kw">from</span> venomqa.adapters.http <span class="vp-c-kw">import</span> <span class="vp-c-cls">HttpClient</span>

api   = <span class="vp-c-cls">HttpClient</span>(<span class="vp-c-str">"http://localhost:8000"</span>)
world = <span class="vp-c-cls">World</span>(api=api, state_from_context=[<span class="vp-c-str">"order_id"</span>])

<span class="vp-c-kw">def</span> <span class="vp-c-fn">create_order</span>(api, context):
    resp = api.post(<span class="vp-c-str">"/orders"</span>, json={<span class="vp-c-str">"amount"</span>: <span class="vp-c-num">100</span>})
    context.set(<span class="vp-c-str">"order_id"</span>, resp.json()[<span class="vp-c-str">"id"</span>])
    <span class="vp-c-kw">return</span> resp

<span class="vp-c-kw">def</span> <span class="vp-c-fn">refund_order</span>(api, context):
    order_id = context.get(<span class="vp-c-str">"order_id"</span>)
    <span class="vp-c-kw">return</span> api.post(<span class="vp-c-str">f"/orders/{order_id}/refund"</span>)

no_over_refund = <span class="vp-c-cls">Invariant</span>(
    <span class="vp-c-str">"no_over_refund"</span>,
    <span class="vp-c-kw">lambda</span> world: world.api.get(<span class="vp-c-str">"/orders"</span>).json()[<span class="vp-c-num">0</span>][<span class="vp-c-str">"refunded"</span>] &lt;= <span class="vp-c-num">100</span>,
    <span class="vp-c-cls">Severity</span>.CRITICAL,
)

result = <span class="vp-c-cls">Agent</span>(
    world=world,
    actions=[<span class="vp-c-cls">Action</span>(<span class="vp-c-str">"create_order"</span>, create_order), <span class="vp-c-cls">Action</span>(<span class="vp-c-str">"refund_order"</span>, refund_order)],
    invariants=[no_over_refund],
    strategy=<span class="vp-c-cls">BFS</span>(), max_steps=<span class="vp-c-num">50</span>,
).explore()

<span class="vp-c-fn">print</span>(<span class="vp-c-str">f"States: {result.states_visited}, Violations: {result.violations}"</span>)</pre>
    </div>
  </div>
</section>

<!-- ── COMPARISON TABLE ──────────────────────────────────────────── -->
<section class="vp-table-section">
  <div class="vp-table-inner">
    <div class="vp-table-header vp-fade">
      <div class="vp-label">// 04 WHERE IT FITS</div>
      <h2>The only tool that<br>tests sequences.</h2>
      <p class="vp-table-sub">Others test endpoints in isolation. VenomQA tests what happens between them.</p>
    </div>
    <div class="vp-table-wrap vp-fade vp-fade-d1">
      <table class="vp-compare-table">
        <thead>
          <tr>
            <th>Capability</th>
            <th class="vp-col-venom">VenomQA</th>
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
            <td class="vp-col-venom vp-yes">✓ Only tool</td>
            <td class="vp-no">✗</td>
            <td class="vp-no">✗</td>
            <td class="vp-no">✗</td>
            <td class="vp-no">✗</td>
            <td class="vp-no">✗</td>
          </tr>
          <tr>
            <td>DB rollback &amp; branching</td>
            <td class="vp-col-venom vp-yes">✓ Only tool</td>
            <td class="vp-no">✗</td>
            <td class="vp-no">✗</td>
            <td class="vp-no">✗</td>
            <td class="vp-no">✗</td>
            <td class="vp-no">✗</td>
          </tr>
          <tr>
            <td>Autonomous exploration</td>
            <td class="vp-col-venom vp-yes">✓ Sequences</td>
            <td class="vp-partial">~ Per endpoint</td>
            <td class="vp-no">✗ Manual</td>
            <td class="vp-no">✗ Manual</td>
            <td class="vp-partial">~ Per function</td>
            <td class="vp-no">✗</td>
          </tr>
          <tr>
            <td>OpenAPI integration</td>
            <td class="vp-col-venom vp-yes">✓</td>
            <td class="vp-yes">✓</td>
            <td class="vp-no">✗</td>
            <td class="vp-yes">✓</td>
            <td class="vp-no">✗</td>
            <td class="vp-yes">✓</td>
          </tr>
          <tr>
            <td>Fuzz / random inputs</td>
            <td class="vp-col-venom vp-no">✗</td>
            <td class="vp-yes">✓ Best</td>
            <td class="vp-no">✗</td>
            <td class="vp-no">✗</td>
            <td class="vp-yes">✓ Best</td>
            <td class="vp-no">✗</td>
          </tr>
          <tr>
            <td>Python native</td>
            <td class="vp-col-venom vp-yes">✓</td>
            <td class="vp-yes">✓</td>
            <td class="vp-yes">✓</td>
            <td class="vp-no">✗ JS</td>
            <td class="vp-yes">✓</td>
            <td class="vp-no">✗ JS</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="vp-table-note vp-fade vp-fade-d2">// Recommended: run Schemathesis + VenomQA together. They catch entirely different bugs.</p>
  </div>
</section>

<!-- ── FEATURES ──────────────────────────────────────────────────── -->
<section class="vp-features">
  <div class="vp-features-inner">
    <div class="vp-features-header vp-fade">
      <div class="vp-label">// 05 CAPABILITIES</div>
      <h2>Everything you need<br>to test sequences.</h2>
    </div>
    <div class="vp-feat-grid">
      <div class="vp-feat-card vp-fade vp-fade-d1">
        <p class="vp-feat-name">State Graph Exploration</p>
        <p class="vp-feat-desc">BFS, DFS, and Coverage-Guided strategies across all reachable sequences. Configurable depth and step budget.</p>
      </div>
      <div class="vp-feat-card vp-fade vp-fade-d2">
        <p class="vp-feat-name">Invariant Checking</p>
        <p class="vp-feat-desc">Rules checked after every single action — not just at test boundaries. CRITICAL, HIGH, MEDIUM severity levels.</p>
      </div>
      <div class="vp-feat-card vp-fade vp-fade-d3">
        <p class="vp-feat-name">DB Checkpoint &amp; Rollback</p>
        <p class="vp-feat-desc">PostgreSQL SAVEPOINTs, SQLite file copy, Redis DUMP/RESTORE, and in-memory mocks. True branching exploration.</p>
      </div>
      <div class="vp-feat-card vp-fade vp-fade-d4">
        <p class="vp-feat-name">OpenAPI Generation</p>
        <p class="vp-feat-desc"><code>venomqa scaffold openapi spec.json</code> generates all action stubs automatically from your API spec.</p>
      </div>
      <div class="vp-feat-card vp-fade vp-fade-d5">
        <p class="vp-feat-name">HTML Trace Reporter</p>
        <p class="vp-feat-desc">D3 force graph of the full state space explored. See every path taken, every invariant checked, every violation found.</p>
      </div>
      <div class="vp-feat-card vp-fade vp-fade-d6">
        <p class="vp-feat-name">CLI Zero-Config</p>
        <p class="vp-feat-desc"><code>venomqa demo</code> finds a bug in 30 seconds, no setup needed. <code>venomqa doctor</code> diagnoses your environment.</p>
      </div>
    </div>
  </div>
</section>

<!-- ── CTA ───────────────────────────────────────────────────────── -->
<section class="vp-cta">
  <div class="vp-cta-inner">
    <div class="vp-label vp-fade">// 06 GET STARTED</div>
    <h2 class="vp-fade vp-fade-d1">Start in<br>30 seconds.</h2>
    <div class="vp-cta-cmds vp-fade vp-fade-d2">
      <div class="vp-cta-cmd">
        <span class="vp-cta-cmd-prompt">$</span>
        <span>pip install venomqa</span>
      </div>
      <div class="vp-cta-cmd">
        <span class="vp-cta-cmd-prompt">$</span>
        <span>venomqa demo</span>
      </div>
    </div>
    <div class="vp-cta-links vp-fade vp-fade-d3">
      <a href="https://namanag97.github.io/venomqa/" class="vp-cta-link">Documentation</a>
      <a href="https://github.com/namanag97/venomqa" class="vp-cta-link">GitHub</a>
    </div>
    <p class="vp-cta-footer vp-fade vp-fade-d4">VenomQA · MIT License · Built by Naman Agarwal · v0.6.4</p>
  </div>
</section>

<!-- SEO: crawlable content for search engines -->
<div style="position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden;" aria-hidden="true">
<h2>Stateful API Testing Tool for Python</h2>
<p>VenomQA is a Python library for autonomous stateful API testing. Unlike pytest which tests functions in isolation, or Schemathesis which fuzzes individual endpoints, VenomQA tests sequences of API calls: create then refund then refund again — finding the double-refund bug that your unit tests miss. Install with pip install venomqa. Python 3.10+. MIT license. Open source.</p>
</div>

</div>

<script>
(function() {
  'use strict';

  // Intersection Observer for scroll-triggered fade-in
  var observer = new IntersectionObserver(function(entries) {
    entries.forEach(function(entry) {
      if (entry.isIntersecting) {
        entry.target.classList.add('vp-visible');
        observer.unobserve(entry.target);
      }
    });
  }, {
    threshold: 0.12,
    rootMargin: '0px 0px -40px 0px'
  });

  document.querySelectorAll('.vp-fade').forEach(function(el) {
    observer.observe(el);
  });

  // Hero elements are visible immediately (above fold)
  var heroFades = document.querySelectorAll('.vp-hero .vp-fade');
  heroFades.forEach(function(el) {
    setTimeout(function() {
      el.classList.add('vp-visible');
    }, 50);
  });
})();
</script>
