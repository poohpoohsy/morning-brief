# Morning brief

The daily page is published by `.github/workflows/brief.yml`.

## Starting a build

Keep one issue open, pin it, and label it `build-trigger`.

The repository owner starts a build by commenting on that issue. The comment body, with surrounding whitespace removed, must start with `/build`. That is the switch an external scheduler can use. It does not need `workflow_dispatch` or a push.

A comment starts a build only when all of these are true:

- the issue has the `build-trigger` label
- the issue is not a pull request
- the trimmed comment starts with `/build`
- the commenter is the repository owner

Anyone else's comment does not start a build.

The 05:30 HKT schedule is still a fallback. If `data/brief.json` was already generated on today's Hong Kong date, that scheduled run does not build again.
