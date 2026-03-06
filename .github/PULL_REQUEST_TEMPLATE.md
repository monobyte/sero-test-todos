# Pull Request

## Description

Brief description of the changes in this PR.

Fixes #(issue)

## Type of Change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Refactoring (no functional changes)
- [ ] Performance improvement
- [ ] Test coverage improvement

## Changes Made

### Backend
- [ ] Added new endpoint: `...`
- [ ] Modified service: `...`
- [ ] Updated models: `...`
- [ ] Fixed bug in: `...`
- [ ] Other: `...`

### Frontend
- [ ] Added component: `...`
- [ ] Updated UI: `...`
- [ ] Fixed bug in: `...`
- [ ] Other: `...`

## Testing

### Backend Tests
```bash
# Commands run to test backend changes
cd backend
pytest
pytest --cov=.
```

- [ ] All existing tests pass
- [ ] Added new tests for new features
- [ ] Coverage maintained or improved

### Frontend Tests
```bash
# Commands run to test frontend changes
cd frontend
npm test
```

- [ ] All existing tests pass
- [ ] Added new tests for new features
- [ ] Coverage maintained or improved

### Manual Testing

Describe the manual testing you performed:

1. Tested scenario 1:
   - Expected: ...
   - Result: ✅ Passed

2. Tested scenario 2:
   - Expected: ...
   - Result: ✅ Passed

## Screenshots (if applicable)

Add screenshots for UI changes.

**Before:**
<!-- Add screenshot or write "N/A" -->

**After:**
<!-- Add screenshot or write "N/A" -->

## API Changes

If this PR modifies the API:

### New Endpoints
```
GET /api/new-endpoint
POST /api/another-endpoint
```

### Modified Endpoints
```
GET /api/existing-endpoint
- Added query parameter: ...
- Changed response format: ...
```

### Breaking Changes
- List any breaking changes
- Migration guide for users

## Documentation

- [ ] Updated README.md
- [ ] Updated API_DOCUMENTATION.md
- [ ] Updated code comments/docstrings
- [ ] Updated CHANGELOG.md
- [ ] No documentation needed

## Performance Impact

Describe any performance implications:

- [ ] No performance impact
- [ ] Improves performance (explain how)
- [ ] May reduce performance (explain why it's acceptable)
- [ ] Needs performance testing

## Security Considerations

- [ ] No security implications
- [ ] Added authentication/authorization
- [ ] Handles user input safely
- [ ] Reviewed for common vulnerabilities (SQL injection, XSS, CSRF, etc.)

## Deployment Notes

Any special deployment steps needed:

- [ ] No special steps needed
- [ ] Environment variables added/changed (documented in .env.example)
- [ ] Database migration required
- [ ] Dependencies updated (requirements.txt / package.json)
- [ ] Other: `...`

## Checklist

- [ ] Code follows project style guidelines
- [ ] Self-reviewed my own code
- [ ] Commented hard-to-understand areas
- [ ] Made corresponding documentation changes
- [ ] No new warnings generated
- [ ] Tests added that prove fix/feature works
- [ ] All tests pass locally
- [ ] Dependent changes merged and published
- [ ] Checked for merge conflicts
- [ ] Updated CHANGELOG.md

## Related Issues/PRs

- Closes #
- Related to #
- Depends on #

## Additional Notes

Any additional information for reviewers.
