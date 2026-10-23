#!/bin/sh
set -eu
repo=thatsmethen/ravelink
if [ "$(gh repo view "$repo" --json isPrivate --jq .isPrivate)" != true ]; then
    echo 'Refusing to push: GitHub repository is not private.' >&2
    exit 1
fi
# HTTP/1.1 uploads repeatedly timed out on the preserved PCM evidence pack;
# HTTP/2 completed the same unmodified commits. Keep credentials out of config.
GIT_CONFIG_GLOBAL=/dev/null git -c http.version=HTTP/2 -c http.postBuffer=67108864 -c credential.helper= -c 'credential.helper=!gh auth git-credential' push "https://github.com/$repo.git" "$@"
if [ "$(gh repo view "$repo" --json isPrivate --jq .isPrivate)" != true ]; then
    echo 'Repository privacy changed during push; investigate immediately.' >&2
    exit 1
fi
