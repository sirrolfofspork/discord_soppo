#!/usr/bin/env python3
"""Local stdlib HTTP UI for reviewing SOPPO memory queue candidates.

Usage:
  .venv/bin/python tools/serve_memory_review.py
  .venv/bin/python tools/serve_memory_review.py --host 127.0.0.1 --port 8765
  .venv/bin/python tools/serve_memory_review.py --lan
"""

from __future__ import annotations

import argparse
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
from pathlib import Path
import sys
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.process_memory_review_queue import (  # noqa: E402
    apply_approved,
    apply_review_decisions,
    assert_safe_to_apply_memories,
    filter_reviewable_items,
    load_queue,
    queue_status_counts,
    summarize_queue,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def discover_lan_addresses() -> list[str]:
    """Return likely LAN IPv4 addresses for operator-friendly URLs."""
    addresses: set[str] = set()
    try:
        hostname = socket.gethostname()
        for family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
            if family != socket.AF_INET:
                continue
            ip = str(sockaddr[0])
            if ip.startswith(("10.", "172.", "192.168.")):
                addresses.add(ip)
    except OSError:
        pass

    # UDP connect does not send packets; it asks the OS which source address
    # would be used for an ordinary outbound LAN/internet route.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                addresses.add(ip)
    except OSError:
        pass
    return sorted(addresses)


def access_urls(*, host: str, port: int) -> list[str]:
    if host in {"0.0.0.0", ""}:
        urls = [f"http://127.0.0.1:{port}/"]
        urls.extend(f"http://{ip}:{port}/" for ip in discover_lan_addresses())
        return urls
    return [f"http://{host}:{port}/"]


def format_conflicts(conflicts: Any) -> str:
    if not isinstance(conflicts, list):
        return "unspecified"
    parts: list[str] = []
    for conflict in conflicts:
        if not isinstance(conflict, dict):
            continue
        kind = str(conflict.get("kind", "unknown"))
        detail = conflict.get("detail") or conflict.get("existing_text") or ""
        if detail:
            parts.append(f"{kind}: {detail}")
        else:
            parts.append(kind)
    return "; ".join(parts) if parts else "unspecified"


def parse_review_submission(body: bytes) -> dict[str, str]:
    """Parse application/x-www-form-urlencoded review decisions."""
    raw = body.decode("utf-8", errors="replace")
    fields = parse_qs(raw, keep_blank_values=False)
    decisions: dict[str, str] = {}
    for key, values in fields.items():
        if not key.startswith("decision_") or not values:
            continue
        item_id = key[len("decision_") :]
        decision = values[0].strip().lower()
        if decision == "approve":
            decisions[item_id] = "approved"
        elif decision == "reject":
            decisions[item_id] = "rejected"
    return decisions


def run_apply_approved(
    *,
    queue_path: Path,
    memory_store_path: Path,
    force: bool = False,
    hot: bool = False,
    is_active_runner: Any | None = None,
) -> tuple[bool, str]:
    warning = assert_safe_to_apply_memories(force=force, hot=hot, is_active_runner=is_active_runner)
    if warning:
        return False, warning
    applied, errors = apply_approved(queue_path=queue_path, memory_store_path=memory_store_path)
    parts = [f"Applied {applied} approved item(s)."]
    if errors:
        parts.append("Errors: " + ", ".join(errors))
    parts.append("")
    parts.append(summarize_queue(queue_path))
    return True, "\n".join(parts)


def render_index_page(
    *,
    items: list[dict[str, Any]],
    show_all: bool,
    message: str = "",
    queue_path: Path | None = None,
) -> str:
    counts = queue_status_counts(items)
    pending_items = filter_reviewable_items(items, show_all=False)
    visible_items = filter_reviewable_items(items, show_all=show_all)
    queue_label = escape(str(queue_path or "memory_review_queue.jsonl"))

    status_bits = ", ".join(
        f"{escape(status)}: {count}" for status, count in sorted(counts.items())
    )
    toggle_href = "/?show=all" if not show_all else "/"
    toggle_label = "Show all queue entries" if not show_all else "Show pending only"

    blocks: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>SOPPO Memory Review</title>",
        "<style>",
        "body { font-family: system-ui, sans-serif; margin: 1.5rem; max-width: 960px; }",
        "h1 { margin-bottom: 0.25rem; }",
        ".meta { color: #444; margin-bottom: 1rem; }",
        ".message { background: #f4f8ff; border: 1px solid #c9dafc; padding: 0.75rem; white-space: pre-wrap; }",
        ".item { border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin: 1rem 0; }",
        ".candidate { background: #fafafa; padding: 0.75rem; border-radius: 6px; white-space: pre-wrap; }",
        ".conflicts { color: #7a4; }",
        ".actions { margin-top: 1.5rem; display: flex; gap: 1rem; flex-wrap: wrap; }",
        "button { padding: 0.5rem 1rem; }",
        "dl { display: grid; grid-template-columns: 9rem 1fr; gap: 0.25rem 0.75rem; margin: 0 0 0.75rem; }",
        "dt { font-weight: 600; }",
        "</style>",
        "</head>",
        "<body>",
        "<h1>SOPPO Memory Review</h1>",
        f'<p class="meta">Queue: {queue_label}<br>Status counts: {status_bits}<br>',
        f'Pending for review: {len(pending_items)} | <a href="{toggle_href}">{escape(toggle_label)}</a></p>',
    ]

    if message:
        blocks.append(f'<pre class="message">{escape(message)}</pre>')

    if visible_items:
        blocks.extend(
            [
                '<form method="post" action="/review">',
                "<h2>Review decisions</h2>",
            ]
        )
        for item in visible_items:
            item_id = str(item.get("id", ""))
            candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
            source = item.get("source") if isinstance(item.get("source"), dict) else {}
            status = str(item.get("status", "unknown"))
            blocks.append('<section class="item">')
            blocks.append(f"<h3>{escape(item_id)}</h3>")
            blocks.append("<dl>")
            blocks.append(f"<dt>Status</dt><dd>{escape(status)}</dd>")
            blocks.append(f"<dt>Namespace</dt><dd>{escape(str(item.get('namespace', '')))}</dd>")
            blocks.append(f"<dt>Type</dt><dd>{escape(str(candidate.get('type', '')))}</dd>")
            blocks.append(f"<dt>Scope</dt><dd>{escape(str(candidate.get('scope', '')))}</dd>")
            blocks.append(
                f"<dt>Confidence</dt><dd>{escape(str(candidate.get('confidence', '')))}</dd>"
            )
            blocks.append(
                f"<dt>Importance</dt><dd>{escape(str(candidate.get('importance', '')))}</dd>"
            )
            blocks.append(f"<dt>Created</dt><dd>{escape(str(item.get('created_at', '')))}</dd>")
            if source:
                source_bits = []
                for key in ("source", "channel_id", "guild_id", "source_id", "category"):
                    if key in source:
                        source_bits.append(f"{key}={source[key]}")
                if source_bits:
                    blocks.append(f"<dt>Source</dt><dd>{escape(', '.join(map(str, source_bits)))}</dd>")
            blocks.append("</dl>")
            blocks.append(
                f'<p class="conflicts"><strong>Conflicts:</strong> {escape(format_conflicts(item.get("conflicts")))}</p>'
            )
            blocks.append(
                f'<p class="candidate">{escape(str(candidate.get("text", "")))}</p>'
            )
            if status == "pending":
                safe_id = escape(item_id, quote=True)
                blocks.extend(
                    [
                        "<p>",
                        f'<label><input type="radio" name="decision_{safe_id}" value="approve"> Approve</label> ',
                        f'<label><input type="radio" name="decision_{safe_id}" value="reject"> Reject</label>',
                        "</p>",
                    ]
                )
            blocks.append("</section>")
        blocks.extend(
            [
                '<div class="actions"><button type="submit">Save review decisions</button></div>',
                "</form>",
            ]
        )
    else:
        blocks.append("<p>No queue entries to display for the current filter.</p>")

    blocks.extend(
        [
            '<form method="post" action="/apply">',
            '<div class="actions">',
            '<label><input type="checkbox" name="hot" value="1"> '
            "Hot-apply while SOPPO is running</label>",
            "<button type=\"submit\">Apply approved memories</button>",
            "</div>",
            "<p><small>Applies entries marked approved via this UI or manual JSONL edits. "
            "If <code>soppo-discord.service</code> is active, check hot-apply to rely on the "
            "bot's runtime disk refresh before the next memory retrieval. CLI alternatives: "
            "<code>--hot</code> or <code>--force</code>.</small></p>",
            "</form>",
            "</body>",
            "</html>",
        ]
    )
    return "\n".join(blocks)


def create_handler(
    *,
    queue_path: Path,
    memory_store_path: Path,
    is_active_runner: Any | None = None,
) -> type[BaseHTTPRequestHandler]:
    class MemoryReviewHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            sys.stderr.write("%s - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))

        def _send_html(self, status: HTTPStatus, html: str) -> None:
            encoded = html.encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _redirect(self, location: str) -> None:
            self.send_response(HTTPStatus.SEE_OTHER.value)
            self.send_header("Location", location)
            self.end_headers()

        def _render(self, *, show_all: bool, message: str = "") -> None:
            items = load_queue(queue_path)
            html = render_index_page(
                items=items,
                show_all=show_all,
                message=message,
                queue_path=queue_path,
            )
            self._send_html(HTTPStatus.OK, html)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/":
                self.send_error(HTTPStatus.NOT_FOUND.value, "Not found")
                return
            query = parse_qs(parsed.query)
            show_all = query.get("show", [""])[0] == "all"
            message = query.get("msg", [""])[0]
            self._render(show_all=show_all, message=message)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b""
            show_all = parse_qs(parsed.query).get("show", [""])[0] == "all"

            if parsed.path == "/review":
                decisions = parse_review_submission(body)
                if not decisions:
                    self._render(show_all=show_all, message="No review decisions were submitted.")
                    return
                updated, skipped = apply_review_decisions(
                    queue_path=queue_path,
                    decisions=decisions,
                    reviewed_by="web",
                )
                message = f"Updated {updated} pending item(s)."
                if skipped:
                    message += f" Skipped {skipped} non-pending selection(s)."
                params = {"msg": message}
                if show_all:
                    params["show"] = "all"
                self._redirect("/?" + urlencode(params))
                return

            if parsed.path == "/apply":
                fields = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=False)
                ok, message = run_apply_approved(
                    queue_path=queue_path,
                    memory_store_path=memory_store_path,
                    force=False,
                    hot=fields.get("hot", [""])[0] == "1",
                    is_active_runner=is_active_runner,
                )
                self._render(show_all=show_all, message=message if ok or message else "Apply failed.")
                return

            self.send_error(HTTPStatus.NOT_FOUND.value, "Not found")

    return MemoryReviewHandler


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve local SOPPO memory review UI.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--lan",
        action="store_true",
        help="Listen on all interfaces so phones/devices on the home LAN can connect.",
    )
    parser.add_argument("--queue", default=str(ROOT / "memory_review_queue.jsonl"))
    parser.add_argument("--memory-store", default=str(ROOT / "memory_store.json"))
    args = parser.parse_args()

    host = "0.0.0.0" if args.lan else args.host
    queue_path = Path(args.queue)
    memory_store_path = Path(args.memory_store)
    handler = create_handler(queue_path=queue_path, memory_store_path=memory_store_path)
    server = ThreadingHTTPServer((host, args.port), handler)
    print("SOPPO memory review UI URLs:")
    for url in access_urls(host=host, port=args.port):
        print(f"  {url}")
    if host in {"0.0.0.0", ""}:
        print("LAN mode: accessible to devices that can reach this machine on the local network.")
        print("Security: stop the server when finished; it has no login page.")
    print(f"Queue: {queue_path}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
