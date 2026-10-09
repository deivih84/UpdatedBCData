import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import discord
from github import Github, Auth
import re
import json
import datetime
import asyncio
import sys

# Fix para el error "Event loop is closed" en Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# --- 1. CONFIGURACIÓN ---
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO_NAME = "deivih84/UpdatedBCData"
ARCHIVO_DATOS_EN = "gachas_eventos_actualizados_en1.json"
ARCHIVO_DATOS_JP = "gachas_eventos_actualizados_jp1.json"
ARCHIVO_STATIC_EVENTS = str(ROOT / 'all_events.json')
CHANNEL_ID_COMANDOS = 1445468966989332563

region_actual = None
PLANTILLAS_EVENTOS = {}

def cargar_plantillas():
    global PLANTILLAS_EVENTOS
    try:
        with open(ARCHIVO_STATIC_EVENTS, 'r', encoding='utf-8') as f:
            data_ev = json.load(f)
            PLANTILLAS_EVENTOS = { e['nombre']: e for e in data_ev['events'] }
        print(f"✅ Plantillas Eventos cargadas: {len(PLANTILLAS_EVENTOS)}")
    except Exception as e:
        print(f"❌ Error cargando plantillas eventos: {e}")
        PLANTILLAS_EVENTOS = {}

cargar_plantillas()

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# --- UTILIDADES ---
def parsear_fecha(fecha_str, mes_referencia=None):
    limpia = re.sub(r"(st|nd|rd|th)", "", fecha_str).strip()
    try:
        dt = datetime.datetime.strptime(limpia, "%Y %B %d")
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    except ValueError:
        pass

    anio = datetime.datetime.now().year
    if "January" in limpia and datetime.datetime.now().month == 12:
        anio += 1

    dt = None
    try:
        dt = datetime.datetime.strptime(f"{limpia} {anio}", "%B %d %Y")
    except ValueError:
        pass

    if not dt and mes_referencia:
        try:
            if isinstance(mes_referencia, str):
                ref_date = datetime.datetime.strptime(mes_referencia, "%Y-%m-%d")
            else:
                ref_date = mes_referencia
            dia = int(limpia)
            siguiente_mes = ref_date.month + 1 if ref_date.month < 12 else 1
            siguiente_anio = ref_date.year if ref_date.month < 12 else ref_date.year + 1
            if dia < ref_date.day:
                dt = datetime.datetime(siguiente_anio, siguiente_mes, dia)
            else:
                dt = datetime.datetime(ref_date.year, ref_date.month, dia)
        except ValueError:
            pass
    if not dt:
        print(f"      ⚠️ No pude parsear la fecha: '{fecha_str}', uso hoy.")
        dt = datetime.datetime.now()
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)

def obtener_ids_existentes(archivo_datos, tipo="eventos"):
    try:
        auth = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(archivo_datos)
        json_actual = json.loads(contents.decoded_content.decode())
        if tipo in json_actual:
            return {item["id"] for item in json_actual[tipo]}
        return set()
    except Exception as e:
        print(f"⚠️ Error ({tipo}): {e}")
        return set()

def subir_a_github(nuevos_items, archivo_datos, tipo="eventos", mensaje_commit="Update"):
    auth = Auth.Token(GITHUB_TOKEN)
    g = Github(auth=auth)
    repo = g.get_repo(REPO_NAME)
    contents = repo.get_contents(archivo_datos)
    json_actual = json.loads(contents.decoded_content.decode())
    if tipo not in json_actual:
        json_actual[tipo] = []
    json_actual[tipo].extend(nuevos_items)
    json_actual["ultima_actualizacion"] = datetime.datetime.now().isoformat()
    repo.update_file(contents.path, f"🤖 {mensaje_commit}", json.dumps(json_actual, indent=2), contents.sha, branch="main")
    print(f"✅ ¡Subido a GitHub ({tipo})!")

# --- BOT LOGIC ---
@client.event
async def on_ready():
    print(f'✅ [EVENTOS] Conectado como {client.user}')
    channel = client.get_channel(CHANNEL_ID_COMANDOS)
    if channel:
        print(f"📢 [EVENTOS] Esperando mensaje...")
        # await channel.send("Esperando Eventos... 🗓️")
    else:
        print("❌ Error canal.")

@client.event
async def on_message(message):
    global region_actual
    if message.author == client.user: return

    if "🌏 EN Event Data Found 🌏" in message.content:
        region_actual = "EN"
        print(f"\n🌏 [EVENTOS] Detectada región: EN")
        return
    if "🇯🇵 JP Event Data Found 🇯🇵" in message.content:
        region_actual = "JP"
        print(f"\n🇯🇵 [EVENTOS] Detectada región: JP")
        return

    texto_limpio = message.content.replace("```ansi", "").replace("```", "").strip()
    texto_limpio = re.sub(r'\x1b\[[\d;]*m', '', texto_limpio)
    texto_limpio = re.sub(r'\033\[[\d;]*m', '', texto_limpio)
    texto_limpio = re.sub(r'\d+;\d+m', '', texto_limpio)
    texto_limpio = re.sub(r'\d+m', '', texto_limpio)

    if message.embeds:
        for embed in message.embeds:
            if embed.description:
                desc_limpia = re.sub(r'\x1b\[[\d;]*m', '', embed.description)
                desc_limpia = re.sub(r'\d+;\d+m', '', desc_limpia)
                desc_limpia = re.sub(r'\d+m', '', desc_limpia)
                texto_limpio += "\n" + desc_limpia.replace("```ansi", "").replace("```", "")
            if embed.title:
                texto_limpio += "\n" + embed.title

    # --- SOLO EVENTOS ---
    if "Stage/Event" in texto_limpio:
        if region_actual == "JP":
            archivo_datos = ARCHIVO_DATOS_JP
        else:
            archivo_datos = ARCHIVO_DATOS_EN

        print(f"\n🔎 [EVENTOS] Procesando...")
        ids_existentes_ev = obtener_ids_existentes(archivo_datos, "eventos")

        lines = texto_limpio.split('\n')
        # Regex mejorada
        patron_ev = re.compile(r"\[(.+?)\s*[~-]\s*(.+?)\]\s*(.+?)(?=\s*\[|\s*<|$)")
        nuevos_eventos = []

        for line in lines:
            line = line.strip()
            if not line: continue
            if "Stage/Event" in line or "Schedule" in line: continue

            match = patron_ev.search(line)
            if match:
                ini, fin, nombre_evt_raw = match.groups()
                nombre_evt_limpio = nombre_evt_raw.strip()

                plantilla_encontrada = None
                nombre_final = nombre_evt_limpio
                descripcion = "No description available."

                dt_ini = parsear_fecha(ini)
                dt_fin = parsear_fecha(fin, mes_referencia=dt_ini)
                f_ini_str = dt_ini.strftime("%Y-%m-%d")
                f_fin_str = dt_fin.strftime("%Y-%m-%d")

                if nombre_evt_limpio in PLANTILLAS_EVENTOS:
                     plantilla_encontrada = PLANTILLAS_EVENTOS[nombre_evt_limpio]
                     nombre_final = plantilla_encontrada.get("nombre", nombre_evt_limpio)
                     descripcion = plantilla_encontrada.get("descripcion", descripcion)

                evento_id = f"{nombre_final.replace(' ', '_').lower()}_{f_ini_str}"
                if evento_id in ids_existentes_ev: continue

                nuevo_evento = {
                    "id": evento_id,
                    "nombre": nombre_final,
                    "caracteristicas": [descripcion],
                    "fecha_inicio": f_ini_str,
                    "fecha_fin": f_fin_str
                }
                nuevos_eventos.append(nuevo_evento)
                print(f"      📥 Evento: {nombre_final}")
            else:
                 if "[" in line and "]" in line and len(line) > 10:
                        print(f"      ⚠️ Regex falló en: {line}")

        if len(nuevos_eventos) > 0:
            print(f"⚙️ Subiendo {len(nuevos_eventos)} EVENTOS...")
            try:
                subir_a_github(nuevos_eventos, archivo_datos, tipo="eventos", mensaje_commit="Update Eventos")
            except Exception as e:
                print(f"❌ Error subiendo: {e}")
        else:
             print("⚠️ No hay eventos nuevos.")

        print("🏁 Terminado trabajo de Eventos. Cerrando.")
        try:
             await client.close()
        except: pass

if __name__ == "__main__":
    if not DISCORD_TOKEN or not GITHUB_TOKEN:
        raise SystemExit("Set DISCORD_TOKEN and GITHUB_TOKEN before starting a legacy bot")
    client.run(DISCORD_TOKEN)
