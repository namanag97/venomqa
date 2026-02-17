"""HTML trace reporter — renders exploration as an interactive D3 force graph."""

from __future__ import annotations

import json
from typing import Any

from venomqa.v1.core.result import ExplorationResult
from venomqa.v1.core.invariant import Severity


class HTMLTraceReporter:
    """Generates a self-contained HTML file visualising the exploration.

    Each node is a state, edges are actions, and violations are highlighted
    in red.  Uses D3.js (loaded from CDN) — no server required.

    Usage::

        reporter = HTMLTraceReporter()
        html = reporter.report(result)
        Path("trace.html").write_text(html)
    """

    def report(self, result: ExplorationResult) -> str:
        """Render exploration result as a self-contained HTML string."""
        graph_data = self._build_graph_data(result)
        return self._render_html(graph_data, result)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_graph_data(self, result: ExplorationResult) -> dict[str, Any]:
        """Convert ExplorationResult into a D3-compatible graph dict."""
        violated_state_ids: set[str] = {
            v.state.id for v in result.violations
        }
        violation_by_state: dict[str, list[str]] = {}
        for v in result.violations:
            violation_by_state.setdefault(v.state.id, []).append(
                f"[{v.severity.value.upper()}] {v.invariant_name}: {v.message}"
            )

        nodes: list[dict[str, Any]] = []
        graph = result.graph
        initial_id = graph.initial_state_id

        for state_id, state in graph.states.items():
            is_initial = state_id == initial_id
            has_violation = state_id in violated_state_ids
            nodes.append({
                "id": state_id,
                "label": state_id[:10],
                "is_initial": is_initial,
                "has_violation": has_violation,
                "violations": violation_by_state.get(state_id, []),
                "observation_systems": list(state.observations.keys()),
            })

        links: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for t in graph.transitions:
            key = (t.from_state_id, t.action_name, t.to_state_id)
            if key in seen:
                continue
            seen.add(key)
            status = None
            if t.result and t.result.response:
                status = t.result.response.status_code
            links.append({
                "source": t.from_state_id,
                "target": t.to_state_id,
                "label": t.action_name,
                "status": status,
                "ok": t.result.success if t.result else True,
            })

        return {
            "nodes": nodes,
            "links": links,
            "summary": result.summary(),
        }

    def _render_html(self, graph_data: dict[str, Any], result: ExplorationResult) -> str:
        data_json = json.dumps(graph_data, indent=2, default=str)
        summary = result.summary()
        status_badge = (
            '<span class="badge pass">PASSED</span>'
            if result.success
            else '<span class="badge fail">FAILED</span>'
        )
        violations_html = self._render_violations_list(result)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VenomQA Exploration Trace</title>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #e2e8f0; }}
  header {{ padding: 1rem 2rem; background: #1e293b; border-bottom: 1px solid #334155; display: flex; align-items: center; gap: 1rem; }}
  header h1 {{ font-size: 1.25rem; font-weight: 700; color: #f8fafc; }}
  .badge {{ padding: .25rem .75rem; border-radius: 9999px; font-size: .75rem; font-weight: 700; }}
  .badge.pass {{ background: #166534; color: #bbf7d0; }}
  .badge.fail {{ background: #7f1d1d; color: #fecaca; }}
  .layout {{ display: flex; height: calc(100vh - 56px); }}
  #graph-container {{ flex: 1; position: relative; overflow: hidden; }}
  svg {{ width: 100%; height: 100%; }}
  #sidebar {{ width: 340px; background: #1e293b; border-left: 1px solid #334155; overflow-y: auto; padding: 1rem; }}
  #sidebar h2 {{ font-size: .9rem; font-weight: 600; color: #94a3b8; margin-bottom: .75rem; text-transform: uppercase; letter-spacing: .05em; }}
  .stat-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; margin-bottom: 1rem; }}
  .stat {{ background: #0f172a; border-radius: .5rem; padding: .5rem .75rem; }}
  .stat .val {{ font-size: 1.25rem; font-weight: 700; color: #38bdf8; }}
  .stat .lbl {{ font-size: .7rem; color: #64748b; }}
  .violation-card {{ background: #450a0a; border: 1px solid #991b1b; border-radius: .5rem; padding: .75rem; margin-bottom: .5rem; }}
  .violation-card .v-name {{ font-weight: 600; color: #fca5a5; font-size: .85rem; }}
  .violation-card .v-msg {{ color: #fecaca; font-size: .75rem; margin-top: .25rem; }}
  .violation-card .v-path {{ color: #94a3b8; font-size: .7rem; margin-top: .25rem; font-family: monospace; }}
  #tooltip {{ position: absolute; background: #1e293b; border: 1px solid #475569; border-radius: .5rem;
              padding: .5rem .75rem; font-size: .75rem; pointer-events: none; opacity: 0;
              transition: opacity .15s; max-width: 260px; z-index: 10; }}
  .node circle {{ stroke-width: 2; cursor: pointer; transition: r .2s; }}
  .node circle:hover {{ stroke-width: 3; }}
  .node text {{ font-size: 10px; fill: #cbd5e1; pointer-events: none; text-anchor: middle; dy: 4; }}
  .link {{ fill: none; stroke-opacity: .6; }}
  .link-label {{ font-size: 9px; fill: #94a3b8; pointer-events: none; }}
  marker path {{ fill: #475569; }}
  .no-violations {{ color: #86efac; font-size: .8rem; text-align: center; padding: 1rem; }}
</style>
</head>
<body>
<header>
  <h1>VenomQA Exploration Trace</h1>
  {status_badge}
  <span style="margin-left:auto;color:#64748b;font-size:.8rem;">
    {summary['states_visited']} states &middot; {summary['transitions_taken']} transitions &middot;
    {summary['coverage_percent']:.1f}% coverage &middot; {summary['duration_ms']:.0f}ms
  </span>
</header>
<div class="layout">
  <div id="graph-container">
    <svg id="graph"></svg>
    <div id="tooltip"></div>
  </div>
  <div id="sidebar">
    <h2>Summary</h2>
    <div class="stat-grid">
      <div class="stat"><div class="val">{summary['states_visited']}</div><div class="lbl">States</div></div>
      <div class="stat"><div class="val">{summary['transitions_taken']}</div><div class="lbl">Transitions</div></div>
      <div class="stat"><div class="val">{summary['coverage_percent']:.1f}%</div><div class="lbl">Coverage</div></div>
      <div class="stat"><div class="val">{summary['violations']}</div><div class="lbl">Violations</div></div>
    </div>
    <h2>Violations</h2>
    {violations_html}
  </div>
</div>

<script>
const DATA = {data_json};

const width = document.getElementById('graph-container').clientWidth;
const height = document.getElementById('graph-container').clientHeight;

const svg = d3.select('#graph')
  .attr('viewBox', [0, 0, width, height]);

// Arrow markers
svg.append('defs').selectAll('marker')
  .data(['default', 'fail'])
  .join('marker')
    .attr('id', d => `arrow-${{d}}`)
    .attr('viewBox', '0 -5 10 10')
    .attr('refX', 22)
    .attr('refY', 0)
    .attr('markerWidth', 6)
    .attr('markerHeight', 6)
    .attr('orient', 'auto')
  .append('path')
    .attr('d', 'M0,-5L10,0L0,5')
    .attr('fill', d => d === 'fail' ? '#ef4444' : '#475569');

const g = svg.append('g');

// Zoom
svg.call(d3.zoom().scaleExtent([.2, 4]).on('zoom', e => g.attr('transform', e.transform)));

const simulation = d3.forceSimulation(DATA.nodes)
  .force('link', d3.forceLink(DATA.links).id(d => d.id).distance(140))
  .force('charge', d3.forceManyBody().strength(-400))
  .force('center', d3.forceCenter(width / 2, height / 2))
  .force('collide', d3.forceCollide(40));

// Links
const link = g.append('g').selectAll('line')
  .data(DATA.links)
  .join('line')
    .attr('class', 'link')
    .attr('stroke', d => d.ok ? '#475569' : '#ef4444')
    .attr('stroke-width', 1.5)
    .attr('marker-end', d => d.ok ? 'url(#arrow-default)' : 'url(#arrow-fail)');

// Link labels
const linkLabel = g.append('g').selectAll('text')
  .data(DATA.links)
  .join('text')
    .attr('class', 'link-label')
    .text(d => d.label + (d.status ? ` (${{d.status}})` : ''));

// Nodes
const node = g.append('g').selectAll('g')
  .data(DATA.nodes)
  .join('g')
    .attr('class', 'node')
    .call(d3.drag()
      .on('start', (e, d) => {{ if (!e.active) simulation.alphaTarget(.3).restart(); d.fx = d.x; d.fy = d.y; }})
      .on('drag',  (e, d) => {{ d.fx = e.x; d.fy = e.y; }})
      .on('end',   (e, d) => {{ if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }}));

node.append('circle')
  .attr('r', d => d.is_initial ? 20 : 16)
  .attr('fill', d => d.has_violation ? '#7f1d1d' : d.is_initial ? '#1e3a5f' : '#1e293b')
  .attr('stroke', d => d.has_violation ? '#ef4444' : d.is_initial ? '#38bdf8' : '#475569');

node.append('text').text(d => d.label);

// Tooltip
const tooltip = document.getElementById('tooltip');
node.on('mouseover', (event, d) => {{
  let html = `<strong>${{d.id}}</strong><br>Systems: ${{d.observation_systems.join(', ') || 'none'}}`;
  if (d.violations.length) {{
    html += '<br><br><strong style="color:#fca5a5">Violations:</strong>';
    d.violations.forEach(v => {{ html += `<br>• ${{v}}`; }});
  }}
  tooltip.innerHTML = html;
  tooltip.style.opacity = 1;
}}).on('mousemove', event => {{
  tooltip.style.left = (event.offsetX + 12) + 'px';
  tooltip.style.top  = (event.offsetY + 12) + 'px';
}}).on('mouseout', () => {{ tooltip.style.opacity = 0; }});

simulation.on('tick', () => {{
  link
    .attr('x1', d => d.source.x)
    .attr('y1', d => d.source.y)
    .attr('x2', d => d.target.x)
    .attr('y2', d => d.target.y);

  linkLabel
    .attr('x', d => (d.source.x + d.target.x) / 2)
    .attr('y', d => (d.source.y + d.target.y) / 2);

  node.attr('transform', d => `translate(${{d.x}},${{d.y}})`);
}});
</script>
</body>
</html>"""

    def _render_violations_list(self, result: ExplorationResult) -> str:
        if not result.violations:
            return '<div class="no-violations">No violations found ✓</div>'

        cards: list[str] = []
        for v in result.violations:
            path_str = " → ".join(t.action_name for t in v.reproduction_path) if v.reproduction_path else ""
            path_html = f'<div class="v-path">Path: {path_str}</div>' if path_str else ""
            cards.append(f"""<div class="violation-card">
  <div class="v-name">[{v.severity.value.upper()}] {v.invariant_name}</div>
  <div class="v-msg">{v.message or "(no message)"}</div>
  {path_html}
</div>""")
        return "\n".join(cards)
