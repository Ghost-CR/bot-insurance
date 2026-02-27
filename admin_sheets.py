import gspread
import os
import json
import base64
import re
from dotenv import load_dotenv
from openai import OpenAI
from google.oauth2.service_account import Credentials

load_dotenv()

# ─── Cliente OpenAI ───────────────────────────────────────────────────────────
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

EXPECTED_COLS = ["Date", "Status", "Name", "Phone Number", "Quoted", "Sold", "Carrier", "Ready to call", "Notes", "Info Missing" ]

# ─── Google Sheets ────────────────────────────────────────────────────────────
def get_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials-sheets.json", scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open("Juan's Quotes").sheet1


def get_data(sheet):
    try:
        return sheet.get_all_records(expected_headers=EXPECTED_COLS)
    except Exception as e:
        print(f"[Error leyendo hoja] {e}")
        return []


# ─── Acciones sobre la hoja ───────────────────────────────────────────────────
def execute_actions(sheet, actions: list):
    """
    Ejecuta una lista de acciones sobre la hoja.
    Acciones soportadas:
      - add:    añade una fila al final
      - update: actualiza una celda específica buscando por nombre
      - delete: elimina una fila buscando por nombre
    """
    data = sheet.get_all_values()
    headers = data[0] if data else []

    for action in actions:
        tipo = action.get("action")

        # ── ADD ──────────────────────────────────────────────────────────────
        if tipo == "add":
            row = action.get("row", [])
            sheet.append_row(row)
            print(f"  ✅ Fila añadida: {row}")

        # ── UPDATE ────────────────────────────────────────────────────────────
        elif tipo == "update":
            search_col = action.get("search_col", "Name")
            search_val = action.get("search_value", "")
            target_col = action.get("column")
            new_value  = action.get("value")

            if search_col not in headers or target_col not in headers:
                print(f"  ⚠️  Columna no encontrada: {search_col} / {target_col}")
                continue

            col_idx_search = headers.index(search_col) + 1
            col_idx_target = headers.index(target_col) + 1

            found = False
            for i, row in enumerate(data[1:], start=2):
                if len(row) >= col_idx_search and row[col_idx_search - 1].strip().lower() == search_val.strip().lower():
                    sheet.update_cell(i, col_idx_target, new_value)
                    print(f"  ✅ Actualizado '{target_col}' de '{search_val}' → '{new_value}' (fila {i})")
                    found = True
                    break

            if not found:
                print(f"  ⚠️  No se encontró '{search_val}' en la columna '{search_col}'")

        # ── DELETE ────────────────────────────────────────────────────────────
        elif tipo == "delete":
            search_col = action.get("search_col", "Name")
            search_val = action.get("search_value", "")

            if search_col not in headers:
                print(f"  ⚠️  Columna no encontrada: {search_col}")
                continue

            col_idx = headers.index(search_col) + 1
            found = False
            for i, row in enumerate(data[1:], start=2):
                if len(row) >= col_idx and row[col_idx - 1].strip().lower() == search_val.strip().lower():
                    sheet.delete_rows(i)
                    print(f"  ✅ Fila eliminada ('{search_val}', fila {i})")
                    found = True
                    break

            if not found:
                print(f"  ⚠️  No se encontró '{search_val}' para eliminar")

        else:
            print(f"  ⚠️  Acción desconocida: {tipo}")


# ─── Parseo de respuesta ──────────────────────────────────────────────────────
def parse_response(answer: str):
    """
    Intenta extraer uno o varios JSONs de la respuesta.
    Maneja bloques ```json ... ``` o JSON directo.
    """
    json_pattern = re.search(r"```json\s*([\s\S]*?)\s*```|(\[[\s\S]*\]|\{[\s\S]*\})", answer)
    if not json_pattern:
        return None, answer

    raw = (json_pattern.group(1) or json_pattern.group(2) or "").strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            parsed = [parsed]
        return parsed, None
    except json.JSONDecodeError:
        return None, answer


# ─── Procesamiento de imagen ──────────────────────────────────────────────────
def encode_image(path: str) -> tuple[str, str]:
    """Convierte una imagen a base64 y detecta su tipo MIME."""
    ext = path.lower().split(".")[-1]
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
    mime = mime_map.get(ext, "image/jpeg")
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8"), mime


def analyze_image(image_path: str, user_instruction: str, sheet_data: list) -> str:
    """
    Envía la imagen a GPT-4 con instrucciones específicas del usuario
    para extraer solo la información relevante.
    """
    b64, mime = encode_image(image_path)

    system_msg = f"""
Eres un asistente experto en extracción de datos de imágenes para una hoja de cálculo.

La hoja se llama 'Juan's Quotes' y tiene estas columnas:
{', '.join(EXPECTED_COLS)}

Datos actuales de la hoja:
{json.dumps(sheet_data, indent=2)}

Tu tarea es analizar la imagen y, según la instrucción del usuario, extraer SOLO la información solicitada.

Si el usuario pide añadir datos, devuelve ÚNICAMENTE un JSON con este formato exacto, sin texto adicional:
[
  {{"action": "add", "row": ["valor_Date", "valor_Status", "valor_Name", "valor_Phone", "valor_Quoted", "valor_Sold", "valor_Carrier", "valor_ReadyToCall", "valor_Notes"]}}
]

Si el usuario pide actualizar datos existentes, devuelve ÚNICAMENTE:
[
  {{"action": "update", "search_col": "Name", "search_value": "nombre", "column": "columna_a_cambiar", "value": "nuevo_valor"}}
]

Si solo pide información (sin modificar la hoja), responde con texto natural.
Usa "" para campos vacíos o desconocidos. NO inventes datos que no estén en la imagen.
IMPORTANTE: Cuando devuelvas JSON, no añadas ningún texto antes ni después. Solo el JSON.
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=2048,
        messages=[
            {"role": "system", "content": system_msg},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"}
                    },
                    {"type": "text", "text": user_instruction}
                ]
            }
        ]
    )
    return response.choices[0].message.content


# ─── Consulta de texto normal ─────────────────────────────────────────────────
def query_text(prompt: str, sheet_data: list) -> str:
    system_msg = f"""
Eres un asistente experto en gestión de la hoja 'Juan's Quotes'.

Columnas disponibles: {', '.join(EXPECTED_COLS)}
Datos actuales: {json.dumps(sheet_data)}

Cuando el usuario pida MODIFICAR la hoja (añadir, actualizar, eliminar), responde ÚNICAMENTE con JSON puro, sin texto adicional, sin explicaciones, sin bloques de código:
- Añadir fila:   [{{"action": "add", "row": [...]}}]
- Actualizar:    [{{"action": "update", "search_col": "Name", "search_value": "...", "column": "...", "value": "..."}}]
- Eliminar:      [{{"action": "delete", "search_col": "Name", "search_value": "..."}}]
- Múltiples:     Una lista con varias acciones juntas.

Cuando el usuario SOLO pida información, responde con texto natural claro y conciso.
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content


# ─── Bucle principal ──────────────────────────────────────────────────────────
def asistente_consola():
    sheet = get_sheet()
    print("═" * 55)
    print("  Asistente IA — Juan's Quotes (Google Sheets)")
    print("═" * 55)
    print("Comandos especiales:")
    print("  imagen <ruta>   → analizar imagen y actuar")
    print("  salir           → cerrar el asistente")
    print("─" * 55)

    while True:
        prompt = input("\n📝 Instrucción: ").strip()

        if not prompt:
            continue
        if prompt.lower() == "salir":
            print("Hasta luego 👋")
            break

        sheet_data = get_data(sheet)

        # ── Modo imagen ───────────────────────────────────────────────────────
        if prompt.lower().startswith("imagen "):
            parts = prompt.split(" ", 2)
            if len(parts) < 2:
                print("  Uso: imagen <ruta_archivo> [instrucción opcional]")
                continue

            image_path = parts[1]
            instruction = parts[2] if len(parts) > 2 else "Extrae toda la información visible y añádela a la hoja."

            if not os.path.exists(image_path):
                print(f"  ⚠️  Archivo no encontrado: {image_path}")
                continue

            print(f"  🔍 Analizando imagen: {image_path}")
            answer = analyze_image(image_path, instruction, sheet_data)

        # ── Modo texto ────────────────────────────────────────────────────────
        else:
            answer = query_text(prompt, sheet_data)

        # ── Ejecutar acciones o mostrar respuesta ─────────────────────────────
        actions, text_response = parse_response(answer)

        if actions:
            print(f"\n  🤖 Ejecutando {len(actions)} acción(es)...")
            execute_actions(sheet, actions)
        else:
            print(f"\n🤖 Bot: {text_response or answer}")


if __name__ == "__main__":
    asistente_consola()