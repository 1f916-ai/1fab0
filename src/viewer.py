#!/usr/bin/env python3
"""
Grant 1FAB0 Connectome Evaluation Viewer & Trial Replayer Server

Standalone HTTP server using Python's standard library http.server:
- Serves docs/ as the web root (docs/index.html on /)
- Routes /results/<path> cleanly to the results/ directory
- Routes /battery/<path> to the battery/ directory
- Provides /api/results listing available result datasets
- Sets CORS and correct MIME types for .jsonl and .json files
"""

import argparse
import http.server
import json
import os
import sys
import urllib.parse
import webbrowser

DEFAULT_PORT = 8080
DEFAULT_HOST = "127.0.0.1"


class ViewerRequestHandler(http.server.SimpleHTTPRequestHandler):
    """
    HTTP request handler routing docs/, results/, and battery/ directories.
    """
    docs_dir = "docs"
    results_dir = "results"
    battery_dir = "battery"

    def __init__(self, *args, docs_dir=None, results_dir=None, battery_dir=None, **kwargs):
        if docs_dir:
            self.docs_dir = os.path.abspath(docs_dir)
        if results_dir:
            self.results_dir = os.path.abspath(results_dir)
        if battery_dir:
            self.battery_dir = os.path.abspath(battery_dir)
        super().__init__(*args, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parsed.path)

        if path == "/api/results":
            self.send_results_list()
            return

        super().do_GET()

    def send_results_list(self):
        files = []
        if os.path.isdir(self.results_dir):
            for entry in sorted(os.listdir(self.results_dir)):
                if entry.endswith((".jsonl", ".json")) and not entry.startswith("."):
                    full_p = os.path.join(self.results_dir, entry)
                    if os.path.isfile(full_p):
                        files.append({
                            "name": entry,
                            "size": os.path.getsize(full_p),
                            "type": "jsonl" if entry.endswith(".jsonl") else "json",
                            "url": f"/results/{entry}"
                        })
        body = json.dumps(files, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def translate_path(self, path):
        parsed = urllib.parse.urlsplit(path)
        clean_path = urllib.parse.unquote(parsed.path)

        if clean_path.startswith("/results/") or clean_path == "/results":
            subpath = clean_path[len("/results/"):].lstrip("/") if clean_path.startswith("/results/") else ""
            target_dir = self.results_dir
        elif clean_path.startswith("/battery/") or clean_path == "/battery":
            subpath = clean_path[len("/battery/"):].lstrip("/") if clean_path.startswith("/battery/") else ""
            target_dir = self.battery_dir
        else:
            subpath = clean_path.lstrip("/")
            target_dir = self.docs_dir

        norm_path = os.path.normpath(subpath)
        if norm_path.startswith("..") or os.path.isabs(norm_path):
            return os.path.join(target_dir, "__nonexistent__")

        full_path = os.path.join(target_dir, norm_path)
        if os.path.isdir(full_path):
            index_path = os.path.join(full_path, "index.html")
            if os.path.exists(index_path):
                return index_path

        return full_path

    def guess_type(self, path):
        if path.endswith(".jsonl"):
            return "application/x-ndjson; charset=utf-8"
        if path.endswith(".json"):
            return "application/json; charset=utf-8"
        if path.endswith(".js"):
            return "application/javascript; charset=utf-8"
        if path.endswith(".css"):
            return "text/css; charset=utf-8"
        if path.endswith(".html"):
            return "text/html; charset=utf-8"
        return super().guess_type(path)


def create_handler(docs_dir, results_dir, battery_dir):
    class ConfiguredHandler(ViewerRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(
                *args,
                docs_dir=docs_dir,
                results_dir=results_dir,
                battery_dir=battery_dir,
                **kwargs
            )
    return ConfiguredHandler


def parse_args(args=None):
    parser = argparse.ArgumentParser(
        description="Grant 1FAB0 Connectome Evaluation Viewer & Trial Replayer",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--port", "-p", type=int, default=DEFAULT_PORT, help="Port to bind server")
    parser.add_argument("--host", "-H", default=DEFAULT_HOST, help="Host / interface to bind server")
    parser.add_argument("--no-browser", action="store_true", help="Do not open web browser automatically")
    parser.add_argument("--docs-dir", default="docs", help="Path to docs directory (static web root)")
    parser.add_argument("--results-dir", default="results", help="Path to results directory")
    parser.add_argument("--battery-dir", default="battery", help="Path to battery directory")
    return parser.parse_args(args)


def run_server(args=None):
    parsed = parse_args(args)
    docs_dir = os.path.abspath(parsed.docs_dir)
    results_dir = os.path.abspath(parsed.results_dir)
    battery_dir = os.path.abspath(parsed.battery_dir)

    handler_cls = create_handler(docs_dir, results_dir, battery_dir)
    server_address = (parsed.host, parsed.port)

    httpd = http.server.ThreadingHTTPServer(server_address, handler_cls)
    url = f"http://{parsed.host}:{parsed.port}/"
    print(f"1FAB0 Connectome Viewer running at: {url}")
    print(f"  Docs root:    {docs_dir}")
    print(f"  Results dir:  {results_dir}")
    print(f"  Battery dir:  {battery_dir}")
    print("Press Ctrl+C to stop.")

    if not parsed.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Server stopped.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run_server()

