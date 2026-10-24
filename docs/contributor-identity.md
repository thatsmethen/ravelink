# Project contributor identity

This repository uses a shared project-level author and committer identity at the owner’s request, matching the approach used for Rebase:

```sh
git config --local user.name 'RaveLink Contributors'
git config --local user.email 'contributors@ravelink.invalid'
```

The public branch and release tags were rewritten on 24 October 2026. Every affected commit’s tree, message, timestamp and mapped parent relationships was verified unchanged. New commits use the same identity, and `scripts/push-public.sh` checks it before publishing. Repository ownership and release upload accounts remain visible on GitHub; cached pages and copies previously fetched by others cannot be recalled by a Git rewrite.

Original test artefacts retain their historical source IDs and byte hashes. Their corresponding rewritten Git commits have identical trees. This metadata change does not alter original observations or third-party licence attribution.
