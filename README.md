# Simple Rancher Versions App

Simple app to show all the latest versions of Rancher applications.

GITHUB_TOKEN needs to be set if Github is rate limiting you.

## Docker

```bash
# on a mac
docker run --rm -it --platform linux/amd64 -p 5000:5000 -e GITHUB_TOKEN="" clemenko/dzver

# on x86
docker run --rm -it -p 5000:5000 -e GITHUB_TOKEN="" clemenko/dzver

## mac testing
docker run --rm -it --platform linux/amd64 -p 5000:5000 -e GITHUB_TOKEN="" -v $(pwd):/code python:alpine sh
```

## Compose

```yaml
 dzver:
    image: clemenko/dzver
    container_name: "dzver"
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    environment:
      GITHUB_TOKEN: ""
```

## Kubernetes

https://github.com/clemenko/fleet/blob/main/versions/versions.yaml

Feel Free to create an issue.

Please subscribe https://www.youtube.com/@clemenko/videos