## Pull Request Template

### Description
<!-- What does this PR do? Why is it needed? -->

### Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Refactoring (no functional changes)
- [ ] CI/CD changes
- [ ] Tests

### Linked ADR / Issue
<!-- Link to the ADR or issue this PR addresses -->
- ADR: ADR-XXXX
- Issue: #XXXX

### Testing
<!-- What tests were added/updated? How was this tested? -->
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed (describe below)
- [ ] Golden dataset validated (for metric changes)

**Test Evidence:**
```
<test output or screenshots>
```

### Migration Notes
<!-- If this PR includes database migrations, describe them here -->
- [ ] No migrations needed
- [ ] Migration included (reversible)
- [ ] Migration included (destructive - requires backup)
- [ ] Migration notes for runbook updated

### Rollback Plan
<!-- How to rollback if something goes wrong -->
1. Revert this PR
2. Run `make migrate` (if migrations)
3. Deploy previous image

### Screenshots (UI changes)
<!-- Add screenshots for UI changes -->

### Checklist
- [ ] Code follows project conventions (CLAUDE.md §18)
- [ ] Self-review completed
- [ ] `make ci` passes locally
- [ ] Docs updated (README, ADRs, user guides)
- [ ] `.env.example` updated if config changed
- [ ] No secrets in code, images, or logs
- [ ] Conventional Commit message format used
