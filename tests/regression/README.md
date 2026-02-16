# Regression Testing Strategy for VenomQA

## Why This Matters

When AI modifies code, it can also modify tests to match incorrect behavior.
Traditional unit tests become unreliable gatekeepers.

This regression suite uses **multiple independent validation strategies**
that are harder to "game" because they:

1. Check properties, not examples
2. Use external/generated reference data
3. Track behavioral fingerprints
4. Measure performance characteristics
5. Compare against known-good versions

## Test Layers

### Layer 1: Property-Based Tests (properties/)
Uses Hypothesis to generate thousands of random inputs.
Tests INVARIANTS that must ALWAYS hold:
- Path reconstruction matches direct computation
- Memory stays bounded
- Results are deterministic for same seed
- No paths are skipped during exploration

### Layer 2: Golden File Tests (golden/)
Stores expected outputs as files.
Any change to behavior shows up in git diff.
Requires explicit human approval to update.

### Layer 3: Performance Regression (benchmarks/)
Tracks timing, memory, throughput.
Detects silent degradation.
Uses statistical comparison (not just "slower = fail").

### Layer 4: Behavioral Fingerprints (fingerprints/)
Hashes deterministic outputs.
Any behavioral change breaks the hash.
Cannot be "fixed" without acknowledging the change.

### Layer 5: Differential Testing (differential/)
Runs same inputs against pinned "known good" version.
Compares outputs byte-for-byte.
Detects ANY behavioral drift.

## How to Run

```bash
# Full regression suite
pytest tests/regression/ -v

# Just property tests
pytest tests/regression/properties/ -v

# Just golden file tests
pytest tests/regression/golden/ -v

# Update golden files (requires explicit flag)
pytest tests/regression/golden/ -v --update-golden

# Performance benchmarks
pytest tests/regression/benchmarks/ -v --benchmark
```

## Adding New Regression Tests

1. Property tests: Add invariants to `properties/test_invariants.py`
2. Golden files: Add test + expected output to `golden/`
3. Fingerprints: Add hash to `fingerprints/known_hashes.json`
