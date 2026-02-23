from flask import Flask, render_template, jsonify
from flask_caching import Cache
import os
import json
import asyncio
import httpx
from threading import Thread
from time import sleep
from typing import Dict

# ----------------------------
# App configuration
# ----------------------------
version = "2.1"
app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})

# GitHub API configuration
GITHUB_TOKEN = os.getenv('GITHUB2_TOKEN')
HEADERS = {'Authorization': f'Bearer {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}

# Store the latest version data in memory
version_cache: Dict[str, str] = {}

# ----------------------------
# Async API Helper Functions
# ----------------------------
async def fetch_github_release(client: httpx.AsyncClient, repo: str) -> str:
    """Fetch the latest GitHub release tag for a given repo."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json().get('tag_name', '') or "no release found"
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        app.logger.error(f"GitHub API error for {repo}: {e}")
        return "error fetching release"

async def fetch_channel_version(client: httpx.AsyncClient, channel: str) -> str:
    """Fetch the latest stable version from the channel API."""
    url = f"https://update.{channel}.io/v1-release/channels"
    try:
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        head, _, _ = json.dumps(data["data"][0]["latest"]).replace('"', '').partition('+')
        return head
    except (httpx.RequestError, httpx.HTTPStatusError, json.JSONDecodeError, KeyError, IndexError) as e:
        app.logger.error(f"Channel API error for {channel}: {e}")
        return "upstream server issue"

async def fetch_dockerhub_tags(client: httpx.AsyncClient, repo: str, name_filter: str = "version") -> str:
    """Fetch the highest version tag from Docker Hub for a given repository, excluding tags containing 'EA', 'ppc', 'dev', or 'beta'."""
    url = f"https://hub.docker.com/v2/repositories/{repo}/tags?name={name_filter}&page_size=100"

    def parse_version(tag_name: str) -> tuple:
        """Parse a version string into a tuple of integers for comparison."""
        parts = []
        for part in tag_name.split('.'):
            digits = ''.join(c for c in part if c.isdigit())
            parts.append(int(digits) if digits else 0)
        return tuple(parts)

    try:
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get('results') and len(data['results']) > 0:
            excluded = {'ppc', 'dev', 'beta', 'ea'}
            valid_tags = [
                tag.get('name', '')
                for tag in data['results']
                if tag.get('name', '') and not any(ex in tag.get('name', '').lower() for ex in excluded)
            ]
            if valid_tags:
                return max(valid_tags, key=parse_version)
            return "no valid tags found"
        return "no tags found"
    except (httpx.RequestError, httpx.HTTPStatusError, json.JSONDecodeError, KeyError, IndexError) as e:
        app.logger.error(f"Docker Hub API error for {repo}: {e}")
        return "error fetching tags"
        
# ----------------------------
# Version Aggregation
# ----------------------------
async def get_versions_async() -> Dict[str, str]:
    """Fetch versions for all monitored applications in parallel."""
    sources = {
        "rancher": ("github", "rancher/rancher"),
        "rke2-stable": ("channel", "rke2"),
        "k3s-stable": ("channel", "k3s"),
        "longhorn": ("github", "longhorn/longhorn"),
        "cert-manager": ("github", "cert-manager/cert-manager"),
        "harvester": ("github", "harvester/harvester"),
        "hauler": ("github", "hauler-dev/hauler"),
        "portworx": ("dockerhub", "portworx/px-pure-csi-driver", {"name_filter": "25"}),
        "px_oper": ("dockerhub", "portworx/px-operator", {"name_filter": "25"}),
        "stork": ("dockerhub", "openstorage/stork", {"name_filter": "25"}),
        "pxenterprise": ("dockerhub", "portworx/px-enterprise", {"name_filter": "3"}),
    }

    async with httpx.AsyncClient(headers=HEADERS) as client:
        tasks = []
        for _, source_data in sources.items():
            source_type = source_data[0]
            identifier = source_data[1]
            options = source_data[2] if len(source_data) > 2 else {}
            
            if source_type == "github":
                tasks.append(fetch_github_release(client, identifier))
            elif source_type == "channel":
                tasks.append(fetch_channel_version(client, identifier))
            elif source_type == "dockerhub":
                tasks.append(fetch_dockerhub_tags(client, identifier, **options))
        
        results = await asyncio.gather(*tasks)

    return dict(zip(sources.keys(), results))

# ----------------------------
# Background Cache Refresher
# ----------------------------
def refresh_versions(interval: int = 1800):
    """Refresh the in-memory cache every `interval` seconds."""
    global version_cache
    while True:
        app.logger.info("Refreshing version cache...")
        try:
            version_cache = asyncio.run(get_versions_async())
            app.logger.info(f"Cache updated: {version_cache}")
        except Exception as e:
            app.logger.error(f"Error refreshing version cache: {e}")
        sleep(interval)

# Start background refresh thread
Thread(target=refresh_versions, daemon=True).start()

# ----------------------------
# Flask Routes
# ----------------------------
@app.route('/json', methods=['GET'])
def json_all_the_things():
    return jsonify(version_cache), 200

@app.route('/', methods=['GET'])
def curl_all_the_things():
    return render_template('index.html', **{
        "rancher_ver": version_cache.get("rancher", "loading..."),
        "rke_ver": version_cache.get("rke2-stable", "loading..."),
        "k3s_ver": version_cache.get("k3s-stable", "loading..."),
        "longhorn_ver": version_cache.get("longhorn", "loading..."),
        "cert_ver": version_cache.get("cert-manager", "loading..."),
        "harv_ver": version_cache.get("harvester", "loading..."),
        "hauler_ver": version_cache.get("hauler", "loading..."),
        "portworx_ver": version_cache.get("portworx", "loading..."),
        "pxe_ver": version_cache.get("pxenterprise", "loading..."),
        "px_oper_ver": version_cache.get("px_oper", "loading..."),
        "stork_ver": version_cache.get("stork", "loading..."),
    })

# ----------------------------
# Entrypoint
# ----------------------------
if __name__ == '__main__':
    # Warm up cache before first request
    version_cache = asyncio.run(get_versions_async())
    app.run(host='0.0.0.0', debug=False)