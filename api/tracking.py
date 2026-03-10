"""
Japan Post 追跡 API (Vercel Serverless Function)

GET /api/tracking?number=1234567890123
GET /api/tracking?number=1234567890123,123456789012
"""

import json
import sys
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from japanpost_tracker import track, track_multi, TrackingError


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        numbers = params.get("number", [])

        if not numbers:
            self._json(400, {
                "error": "number パラメータが必要です",
                "usage": "GET /api/tracking?number=1234567890123",
            })
            return

        tracking_numbers = []
        for n in numbers:
            tracking_numbers.extend(n.split(","))
        tracking_numbers = [n.strip() for n in tracking_numbers if n.strip()]

        if len(tracking_numbers) > 10:
            self._json(400, {"error": "一度に10件まで"})
            return

        if len(tracking_numbers) == 1:
            try:
                result = track(tracking_numbers[0])
                self._json(200, result.to_dict())
            except TrackingError as e:
                self._json(404, {"error": str(e)})
        else:
            results = track_multi(tracking_numbers)
            out = []
            for r in results:
                if isinstance(r, TrackingError):
                    out.append({"error": str(r)})
                else:
                    out.append(r.to_dict())
            self._json(200, {"results": out, "count": len(out)})

    def _json(self, status: int, data: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=300, stale-while-revalidate=60")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()
