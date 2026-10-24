#!/bin/sh
set -eu
repo=thatsmethen/ravelink
# Project-level identity is intentional; never inherit a personal global email.
if [ "$(git config --local user.name)" != 'RaveLink Contributors' ] ||
   [ "$(git config --local user.email)" != 'contributors@ravelink.invalid' ]; then
    echo 'Refusing to push: configure the documented RaveLink contributor identity.' >&2
    exit 1
fi
if git log --format='%an <%ae>|%cn <%ce>' HEAD |
   LC_ALL=C grep -vFx 'RaveLink Contributors <contributors@ravelink.invalid>|RaveLink Contributors <contributors@ravelink.invalid>' >/dev/null; then
    echo 'Refusing to push: personal contributor metadata remains in the current history.' >&2
    exit 1
fi
if [ "$(gh repo view "$repo" --json visibility --jq .visibility)" != PUBLIC ]; then
    echo 'Refusing to push: GitHub repository is not public as requested.' >&2
    exit 1
fi
# HTTP/1.1 uploads repeatedly timed out on the preserved PCM evidence pack;
# HTTP/2 completed the same unmodified commits. Keep credentials out of config.
GIT_CONFIG_GLOBAL=/dev/null git -c http.version=HTTP/2 -c http.postBuffer=67108864 -c credential.helper= -c 'credential.helper=!gh auth git-credential' push "https://github.com/$repo.git" "$@"
if [ "$(gh repo view "$repo" --json visibility --jq .visibility)" != PUBLIC ]; then
    echo 'Repository visibility changed during push; investigate immediately.' >&2
    exit 1
fi
