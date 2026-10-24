# Project contributor identity

This repository uses a shared project-level author and committer identity at the owner’s request, matching the approach used for Rebase:

```sh
git config --local user.name 'ReLink Contributors'
git config --local user.email 'contributors@relink.invalid'
```

The public branch and release tags were anonymised on 24 October 2026 using `RaveLink Contributors <contributors@ravelink.invalid>`. Every affected commit’s tree, message, timestamp and mapped parent relationships was verified unchanged. The product was subsequently renamed ReLink; new commits use the identity above while historical commits keep their existing anonymous identity. `scripts/push-public.sh` permits only these two exact project identities and requires the current one for new work. Repository ownership and release upload accounts remain visible on GitHub; cached pages and copies previously fetched by others cannot be recalled by a Git rewrite.

Original test artefacts retain their historical source IDs and byte hashes. Their corresponding rewritten Git commits have identical trees. This metadata change does not alter original observations or third-party licence attribution.
