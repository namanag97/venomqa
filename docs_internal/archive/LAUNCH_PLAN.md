# VenomQA Launch Plan

## Context

VenomQA is a state-based API testing framework. The core feature is **StateGraph** - model your app as nodes (states) and edges (actions), define invariants (rules that must always be true), and VenomQA explores all paths automatically.

**What's Done:**
- Core package built and working (`venomqa-0.2.0`)
- StateGraph feature implemented (`venomqa/core/graph.py`)
- All exports working (`from venomqa import StateGraph, Client, Journey`)
- README updated with StateGraph as primary feature
- Landing page created (`website/index.html`)
- Package builds successfully

---

## Remaining Tasks

### 1. Preview & Polish Website
```bash
cd website
python3 -m http.server 8080
# Open http://localhost:8080
```
- Review the landing page
- Adjust copy if needed
- Test on mobile

### 2. Push to GitHub
```bash
cd /Users/namanagarwal/venomQA
git add -A
git commit -m "v0.2.0: State Graph Testing

- Added StateGraph for state-based testing
- Automatic path exploration
- Invariant checking at every step
- Updated README and documentation
- Added landing page"

git push origin main
```

### 3. Publish to PyPI
```bash
# Test PyPI first (optional)
twine upload --repository testpypi dist/*

# Production PyPI
twine upload dist/*
```

Credentials needed: PyPI API token

### 4. Deploy Website

**Option A: GitHub Pages**
```bash
# In repo settings, enable GitHub Pages from /docs or gh-pages branch
# Copy website/index.html to docs/index.html
mkdir -p docs
cp website/index.html docs/index.html
git add docs && git commit -m "Add GitHub Pages site" && git push
```

**Option B: Vercel**
```bash
cd website
npx vercel
```

**Option C: Netlify**
- Drag and drop `website/` folder to netlify.com

### 5. Deploy Documentation
```bash
# Using MkDocs (already configured)
mkdocs gh-deploy
```

This deploys docs to GitHub Pages at `venomqa.github.io/venomqa`

### 6. Set Up Domain (venomqa.dev)
- Purchase domain if not done
- Point to GitHub Pages or Vercel
- Add CNAME file to website

### 7. Create GitHub Release
```bash
gh release create v0.2.0 dist/* \
  --title "v0.2.0 - State Graph Testing" \
  --notes "
## What's New
- **StateGraph**: Model your app as states and transitions
- **Invariants**: Rules checked after every action
- **Automatic Exploration**: All paths tested automatically

## Install
\`\`\`bash
pip install venomqa
\`\`\`

## Quick Start
\`\`\`python
from venomqa import StateGraph, Client

graph = StateGraph(name='my_app')
graph.add_node('empty', initial=True)
graph.add_node('has_data')
graph.add_edge('empty', 'has_data', action=create_item)
graph.add_invariant('count_ok', check_count)

result = graph.explore(Client(base_url='http://localhost:8000'))
print(result.summary())
\`\`\`
"
```

---

## File Locations

| What | Path |
|------|------|
| Main package | `venomqa/` |
| StateGraph | `venomqa/core/graph.py` |
| Graph loader (YAML) | `venomqa/core/graph_loader.py` |
| Landing page | `website/index.html` |
| README | `README.md` |
| Vision doc | `docs/specs/VISION.md` |
| Examples | `examples/state_graph_tests/` |
| Built package | `dist/venomqa-0.2.0-py3-none-any.whl` |
| Config | `pyproject.toml` |

---

## Testing Commands

```bash
# Verify imports work
python3 -c "from venomqa import StateGraph, Client; print('OK')"

# Run state graph example (todo app must be running)
cd examples/todo_app/docker && docker compose up -d
python3 examples/state_graph_tests/test_state_graph.py

# Run against public API (no setup needed)
python3 examples/state_graph_tests/test_public_api.py
python3 examples/state_graph_tests/test_complex_branches.py
```

---

## Post-Launch

1. **Product Hunt** - Prepare launch post
2. **Hacker News** - "Show HN: VenomQA - State-based API testing"
3. **Reddit** - r/Python, r/programming
4. **Twitter/X** - Announce with demo GIF
5. **Dev.to / Hashnode** - Tutorial post

---

## Key Selling Points

1. **"Test your entire app, not just endpoints"**
2. **State graph = visual understanding of app**
3. **Invariants = rules checked after every action**
4. **Automatic exploration = all paths tested**
5. **Cross-feature consistency = catches real bugs**

---

## Commands Summary

```bash
# Build
python3 -m build

# Test locally
python3 -m http.server 8080 --directory website

# Publish
twine upload dist/*

# Deploy docs
mkdocs gh-deploy

# Create release
gh release create v0.2.0 dist/*
```
