# Governance

PicGen Console is an open collaboration project. Anyone can fork the repository and submit a pull request. Merge authority is intentionally narrower than contribution authority.

## Roles

### Contributors

- Anyone who opens issues, comments, or submits pull requests
- Can propose code, design, UX, documentation, and workflow changes

### Maintainers

- People with direct write access to the repository
- Responsible for review quality, merge decisions, release direction, and project stability
- Initial maintainer: `@Minorli`

## Review and merge policy

- All changes to `main` should land through pull requests
- At least one maintainer review is expected before merge
- Large UX, API, or workflow changes should include rationale and validation notes
- Maintainers may request changes for product clarity, technical risk, or insufficient verification
- Maintainers are responsible for rejecting scope creep inside otherwise good PRs

## Decision principles

- User workflow comes first
- Prompt handling must stay literal unless the user explicitly opts into transformation
- The app should preserve continuity across generate, extend, edit, compare, and export flows
- Public interfaces should remain simple and defensible
- New complexity must earn its place

## Protected branch recommendations

The following settings should be enabled in GitHub repository settings for `main`:

- Require a pull request before merging
- Require at least 1 approval
- Dismiss stale approvals when new commits are pushed
- Require conversation resolution before merging
- Restrict direct pushes to maintainers only

These settings are not stored in git and must be configured in GitHub manually.

## Becoming a maintainer

- Demonstrate repeated, high-signal contributions
- Show sound judgment on review quality and scope control
- Understand the product direction and interaction standards of the project

Maintainer access is granted by existing maintainers.
