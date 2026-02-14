## Description

<!-- Provide a brief description of your changes. What does this PR accomplish? -->

## Type of Change

<!-- Mark the relevant option with an 'x' -->

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Performance improvement
- [ ] Code refactoring (no functional changes)
- [ ] Test improvements
- [ ] Chore (dependency updates, CI changes, etc.)

## Related Issues

<!-- Link to any related issues. Use "Closes #123" to auto-close on merge -->

- Fixes #
- Related to #

## Changes Made

<!-- List the key changes in this PR -->

-
-
-

## Testing

<!-- Describe how you tested these changes -->

### Test Coverage

- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] All existing tests pass

### Test Commands

```bash
# Run relevant tests
pytest tests/

# Run with coverage
pytest --cov=venomqa

# Run linting
ruff check .
ruff format . --check

# Run type checking
mypy venomqa
```

## Test Plan

<!-- Describe your plan for testing this change -->

| Scenario | Steps | Expected Result | Status |
|----------|-------|-----------------|--------|
| Example  | Run `venomqa run my_journey` | Journey completes | [ ] |

## Screenshots / Output

<!-- If applicable, add screenshots or example output -->

## Breaking Changes

<!-- If this is a breaking change, describe the migration path -->

### Before

```python
# Old usage
```

### After

```python
# New usage
```

## Documentation

- [ ] Documentation updated (if applicable)
- [ ] CHANGELOG.md updated
- [ ] API docs updated (if new public API)

## Checklist

<!-- Mark completed items with an 'x' -->

### Code Quality

- [ ] Code follows project style guidelines (ruff passes)
- [ ] Type hints added for new functions/methods
- [ ] Docstrings added/updated (Google style)
- [ ] No unnecessary code duplication

### Testing

- [ ] Tests added for new functionality
- [ ] All tests pass locally (`pytest`)
- [ ] Test coverage maintained or improved

### Documentation

- [ ] In-code comments added where necessary
- [ ] Documentation updated for user-facing changes
- [ ] CHANGELOG.md entry added

### Review

- [ ] Self-review completed
- [ ] Commit messages follow convention (see CONTRIBUTING.md)
- [ ] Branch is up to date with main

## Additional Notes

<!-- Any additional information for reviewers -->

---

## For Maintainers

- [ ] Labels applied
- [ ] Milestone set
- [ ] Reviewers assigned
