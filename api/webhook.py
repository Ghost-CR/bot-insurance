from http.server import BaseHTTPRequestHandler
import urllib.parse
import json
import os
from dotenv import load_dotenv
from openai import OpenAI

# Initialize the OpenAI client
# Ensure OPENAI_API_KEY is set in your Vercel Environment Variables
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class handler(BaseHTTPRequestHandler):
    # Verification token for WhatsApp Webhook setup
    VERIFY_TOKEN = "api_webhook_token"

    def do_GET(self):
        # Handle the dynamic verification from Meta (Challenge)
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
        # Handle incoming events from WhatsApp (Event-Driven)
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            payload = json.loads(post_data.decode())
            
            # Orchestration: Navigate the JSON structure from Meta
            if 'entry' in payload and payload['entry'][0]['changes'][0]['value'].get('messages'):
                message_data = payload['entry'][0]['changes'][0]['value']['messages'][0]
                sender_phone = message_data['from']
                
                # Intelligence Layer: Process text messages with OpenAI
                if message_data['type'] == 'text':
                    user_text = message_data['text']['body']
                    print(f"Incoming message from {sender_phone}: {user_text}")

                    # Call OpenAI to extract structured data for EZLynx
                    ai_completion = client.chat.completions.create(
                        model="gpt-4",
                        messages=[
                            {
                                "role": "system", 
                                "content": """You are an insurance data assistant. 
                                Extract data in JSON format with these exact keys:
                                - first_name
                                - last_name
                                - vin
                                - dln (driver license)
                                - car_year
                                - car_model
                                If information is missing, set the value to null."""
                            },
                            {"role": "user", "content": user_text}
                        ],
                        response_format={ "type": "json_object" }
                    )

                    # Extracted data ready for Integration Layer
                    extracted_json = ai_completion.choices[0].message.content
                    print(f"Data Extracted for EZLynx: {extracted_json}")
                    
                    # LOGIC: Here we will later add the POST request to EZLynx API

        except Exception as e:
            # Log errors for debugging in Vercel Runtime Logs
            print(f"Error processing webhook: {e}")

        # Respond to Meta to acknowledge receipt (200 OK)
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "event_received"}).encode())