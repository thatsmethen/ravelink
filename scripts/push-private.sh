#!/bin/sh
set -eu
repo=thatsmethen/ravelink
if [ "$(gh repo view "$repo" --json isPrivate --jq .isPrivate)" != true ]; then
    echo 'Refusing to push: GitHub repository is not private.' >&2
    exit 1
fi
GIT_CONFIG_GLOBAL=/dev/null git -c http.version=HTTP/1.1 -c http.postBuffer=16777216 -c credential.helper= -c 'credential.helper=!gh auth git-credential' push "https://github.com/$repo.git" "$@"
if [ "$(gh repo view "$repo" --json isPrivate --jq .isPrivate)" != true ]; then
    echo 'Repository privacy changed during push; investigate immediately.' >&2
    exit 1
fi
