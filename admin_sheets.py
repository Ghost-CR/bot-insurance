import gspread
import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from google.oauth2.service_account import Credentials

#load environment variables from .env
load_dotenv()

# Initialize OpenAI
# Replace with your key or use environment variables
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_sheet():
    # Path to your JSON credentials file downloaded from Google Cloud
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file('credentials-sheets.json', scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open("Juan's Quotes").sheet1

def asistente_consola():
    sheet = get_sheet()
    print("--- Asistente de Gestión: Juan's Quotes ---")
    # Define exactly which columns we want to read
    expected_cols = ["Date", "Status", "Name", "Phone Number", "Quoted", "Sold", "Carrier", "Ready to call", "Notes"]
    
    while True:
        prompt = input("\nEscribe tu instrucción (o 'salir'): ")
        if prompt.lower() == 'salir':
            break
            
        try:
            # Using expected_headers ignores empty columns at the end of the sheet
            data = sheet.get_all_records(expected_headers=expected_cols)
        except Exception as e:
            print(f"Error fetching data: {e}")
            print("Tip: Check if your Sheet headers match the code exactly.")
            continue
        
        # System instructions with your specific columns
        system_msg = f"""
        You are an expert manager for the spreadsheet 'Juan's Quotes'.
        Current Data: {json.dumps(data)}
        
        Columns: Date, Status, Name, Phone Number, Quoted, Sold, Carrier, Ready to call, Notes.
        
        Instructions:
        1. To ADD a new row, return ONLY a JSON: {{"action": "add", "row": ["value1", "value2", ...]}}
        2. To ANSWER questions (e.g., 'Who is pending?'), respond with natural text.
        3. Notes column contains prices like 'NGI: 422'.
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ]
        )
        
        answer = response.choices[0].message.content

        # Logic to execute the action in Google Sheets
        if '"action": "add"' in answer:
            try:
                action_data = json.loads(answer)
                sheet.append_row(action_data['row'])
                print(">> Sistema: Fila agregada correctamente a Google Sheets.")
            except Exception as e:
                print(f">> Error al actualizar: {e}")
        else:
            print(f"\nBot: {answer}")

if __name__ == "__main__":
    # Ensure you have 'credentials.json' in the same folder
    asistente_consola()