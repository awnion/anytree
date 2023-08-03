import hashlib
import os
import requests
import toml
import uuid
import json
import subprocess
from urllib.parse import urlparse

# Load Cargo.lock
with open('Cargo.lock') as f:
    cargo_lock = toml.load(f)

# Load existing BOM
with open('initial-sbom.json') as f:
    bom = json.load(f)

def get_hashes(file_path):
    with open(file_path,"rb") as f:
        bytes = f.read() # Read file bytes
        return {
            "MD5": hashlib.md5(bytes).hexdigest(),
            "SHA-1": hashlib.sha1(bytes).hexdigest(),
            "SHA-256": hashlib.sha256(bytes).hexdigest(),
            "SHA-512": hashlib.sha512(bytes).hexdigest(),
        }

def download_file(url, target_path):
    print(f"Downloading file from {url}")
    r = requests.get(url, stream=True)
    if r.status_code == 200:
        with open(target_path, 'wb') as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)
        print(f"Downloaded file to {target_path}")

def clone_and_archive(url, commit, target_path):
    print(f"Cloning repository from {url}")
    url = url.replace('git+', '') # remove 'git+' from URL
    subprocess.run(['git', 'clone', url, 'repo'], check=True)
    os.chdir('repo')
    subprocess.run(['git', 'checkout', commit], check=True)
    subprocess.run(['git', 'archive', '-o', target_path, 'HEAD'], check=True)
    os.chdir('../')
    subprocess.run(['rm', '-rf', 'repo'], check=True)
    print(f"Cloned repository and created archive at {target_path}")

for package in cargo_lock['package']:
    name = package['name']
    version = package['version']
    
    if 'source' not in package:
        print(f"Warning: Skipping package {name} due to lack of source")
        continue

    source = package['source']
    tmp_file = os.path.abspath('tmp_file')

    try:
        if "git" in source and '#' in source:
            mime_type = "cargo/git"
            url, commit = source.split('#')
            url = url.split('?')[0]
            clone_and_archive(url, commit, tmp_file)
            hashes = get_hashes(tmp_file)
            external_references = [{"url": url, "type": "distribution"}]
            properties = [{"name": "commit", "value": commit}]
        else:
            mime_type = "cargo/registry"
            url = f"https://crates.io/api/v1/crates/{name}/{version}/download"
            download_file(url, tmp_file)
            hashes = get_hashes(tmp_file)
            external_references = [{"url": url, "type": "distribution"}]
            properties = []

        component = {
            "bom-ref": f"{name}_{version.replace('.', '_')}_{uuid.uuid4()}",
            "type": "library",
            "name": name,
            "version": version,
            "mime-type": mime_type,
            "externalReferences": external_references,
            "hashes": [{"alg": alg, "content": content} for alg, content in hashes.items()],
        }
        if properties:
            component["properties"] = properties
        bom["components"].append(component)
    finally:
        if os.path.isfile(tmp_file):
            os.remove(tmp_file)

# Write SBOM back to the same file
with open('sbom.json', 'w') as f:
    json.dump(bom, f, indent=2)
    print(f"Updated SBOM written to sbom.json")