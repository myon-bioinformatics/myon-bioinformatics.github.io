#!/usr/bin/env python3
"""Build the optional Tone.js subset for the composition studio (Node 26, esbuild; nothing is checked in).

npm ci --prefix tools/build/studio-audio --ignore-scripts
python -S tools/build/studio-audio/build.py build/site/vendor

Writes tone-studio.min.js, tone-studio.LICENSE.txt (every bundled package) and tone-studio.build.json
(sizes and hashes). Python owns the entry, the licence list and the receipt; Node only runs esbuild.
"""
import argparse, hashlib, json, os, re, subprocess, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _node(*argv, **kwargs):
    done = subprocess.run(["node", *argv], capture_output=True, text=True, timeout=120, **kwargs)
    if done.returncode:
        raise SystemExit(done.stderr or done.stdout)
    return done.stdout


def build(out):
    """Bundle the four exports the studio uses and return the receipt written beside them."""
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    pins = json.loads((HERE / "package.json").read_text(encoding="utf-8"))
    exports = ["Synth", "start", "now", "getContext"]  # a monophonic sine voice only: no samples, effects or Transport UI
    os.chdir(HERE)  # esbuild resolves the stdin entry's 'tone' from the working directory
    with tempfile.TemporaryDirectory() as tmp:
        meta = Path(tmp) / "meta.json"
        _node("node_modules/esbuild/bin/esbuild", "--bundle", "--minify", "--format=esm", "--platform=browser", "--target=es2022",
              "--legal-comments=eof", "--log-level=warning", f"--metafile={meta}", f"--outfile={out / 'tone-studio.min.js'}",
              input="export {" + ", ".join(exports) + "} from 'tone';\n")
        inputs = json.loads(meta.read_text(encoding="utf-8"))["inputs"]
    packages = sorted({m.group(1) for m in (re.search(r"node_modules/((?:@[^/]+/)?[^/]+)", name) for name in inputs) if m})
    licenses = []
    for name in packages:
        root = HERE / "node_modules" / name
        package = json.loads((root / "package.json").read_text(encoding="utf-8"))
        found = next((root / c for c in ("LICENSE.md", "LICENSE", "LICENSE.txt", "license", "license.md") if (root / c).is_file()), None)
        text = found.read_bytes().decode("utf-8", "replace") if found else ""
        if not text:
            raise SystemExit("license missing for " + name)
        licenses.append(f"{name}@{package['version']} ({package['license']})\n{text}")
    (out / "tone-studio.LICENSE.txt").write_bytes("\n\n----------------\n\n".join(licenses).encode("utf-8"))

    files = [out / "tone-studio.min.js", HERE / "node_modules/tone/build/Tone.js"]
    # Node measures gzip so the receipt keeps Node's zlib numbers (Python's zlib packs these files a little differently).
    node, *gzip_bytes = json.loads(_node("-p", "JSON.stringify([process.versions.node,...process.argv.slice(1).map(f=>require('zlib')"
                                         ".gzipSync(require('fs').readFileSync(f)).length)])", *files))
    subset, full_umd = ({"bytes": len(data), "gzip_bytes": size, "sha256": hashlib.sha256(data).hexdigest()}
                        for data, size in zip((f.read_bytes() for f in files), gzip_bytes))
    report = {"schema": "web-ui-audio-build/1", "node": node, "tone": pins["dependencies"]["tone"], "esbuild": pins["devDependencies"]["esbuild"],
              "exports": exports, "packages": packages, "subset": subset, "full_umd": full_umd,
              "lock_sha256": hashlib.sha256((HERE / "package-lock.json").read_bytes()).hexdigest()}
    (out / "tone-studio.build.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", nargs="?", default="build/site/vendor", type=Path, help="folder for the three tone-studio.* files")
    print(json.dumps(build(parser.parse_args(argv).out), separators=(",", ":")))


if __name__ == "__main__":
    main()
