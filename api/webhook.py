from http.server import BaseHTTPRequestHandler
import urllib.parse
import json

class handler(BaseHTTPRequestHandler):
    # This is the token you will put in the Meta Dashboard
    VERIFY_TOKEN = "api_webhook_token"

    def do_GET(self):
        # Verification process for Meta (Handshake)
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        mode = params.get('hub.mode', [None])[0]
        token = params.get('hub.verify_token', [None])[0]
        challenge = params.get('hub.challenge', [None])[0]

        if mode == 'subscribe' and token == self.VERIFY_TOKEN:
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(challenge.encode())
        else:
            self.send_response(403)
            self.end_headers()

    def do_POST(self):
        # This part will receive the messages later
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "received"}).encode())