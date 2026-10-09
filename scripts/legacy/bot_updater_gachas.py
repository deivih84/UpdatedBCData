import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
# DEPRECADO: Este script ya no se utiliza. Se mantiene aquí solo como referencia histórica de cómo se hizo la primera versión del bot de actualización de gachas. Para la versión actualizada y en mantenimiento, ver fetch_bc_schedule.py.

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
ARCHIVO_STATIC_DATA = str(ROOT / 'all_gachas_en.json')
CHANNEL_ID_COMANDOS = 1445468966989332563

# Variable global para trackear la región actual detectada
region_actual = None

# --- 2. GESTIÓN DE PLANTILLAS ---
PLANTILLAS_GACHA = {}

def cargar_plantillas():
    global PLANTILLAS_GACHA
    try:
        with open(ARCHIVO_STATIC_DATA, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Mapea cada alias al nombre canónico del gacha
            PLANTILLAS_GACHA = {}
            for g in data['gachas']:
                nombre = g['nombre']
                for alias in g.get('aliases', [nombre]):
                    PLANTILLAS_GACHA[alias] = nombre
        print(f"✅ Plantillas Gachas cargadas: {len(PLANTILLAS_GACHA)} aliases ({len(data['gachas'])} gachas)")
    except Exception as e:
        print(f"❌ Error cargando plantillas gacha: {e}")
        PLANTILLAS_GACHA = {}

# Cargamos al iniciar el script
cargar_plantillas()

# Configuración de Discord
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

def obtener_ids_existentes(archivo_datos, tipo="gachas"):
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

def subir_a_github(nuevos_items, archivo_datos, tipo="gachas", mensaje_commit="Update"):
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
    print(f'✅ [GACHAS] Conectado como {client.user}')
    channel = client.get_channel(CHANNEL_ID_COMANDOS)
    if channel:
        print(f"📢 [GACHAS] Esperando mensaje...")
        # await channel.send("Esperando Gachas... 😺")
    else:
        print("❌ Error canal.")

@client.event
async def on_message(message):
    global region_actual
    if message.author == client.user: return

    if "🌏 EN Event Data Found 🌏" in message.content:
        region_actual = "EN"
        print(f"\n🌏 [GACHAS] Detectada región: EN")
        return
    if "🇯🇵 JP Event Data Found 🇯🇵" in message.content:
        region_actual = "JP"
        print(f"\n🇯🇵 [GACHAS] Detectada región: JP")
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

    # --- SOLO GACHAS ---
    if "**Gacha**" in message.content or "G : Guaranteed" in texto_limpio:
        if region_actual == "JP":
            archivo_datos = ARCHIVO_DATOS_JP
        else:
            archivo_datos = ARCHIVO_DATOS_EN # Default fallback

        print(f"\n🔎 [GACHAS] Procesando...")
        ids_existentes = obtener_ids_existentes(archivo_datos, "gachas")
        candidatos_raw = []
        lines = texto_limpio.split('\n')
        # Ajuste regex: El espacio antes de los tags opcionales ahora es parte del grupo opcional o flexible
        patron = re.compile(r"\[(.*?) (?:~|-) (.*?)\] (.*?)(?: \[(.*?)\])?(?: <.*?>)?$")

        no_reconocidos = []
        for line in lines:
            line = line.strip()
            if not line: continue
            match = patron.search(line)
            if match:
                ini, fin, nombre_raw, tags_raw = match.groups()
                nombre_limpio = nombre_raw.split(" (+")[0].strip()
                if nombre_limpio in PLANTILLAS_GACHA:
                    nombre_canonico = PLANTILLAS_GACHA[nombre_limpio]
                    dt_ini = parsear_fecha(ini)
                    dt_fin = parsear_fecha(fin, mes_referencia=dt_ini)
                    candidatos_raw.append({
                        "nombre_limpio": nombre_canonico,
                        "nombre_raw": nombre_raw,
                        "fecha_inicio_dt": dt_ini,
                        "fecha_fin_dt": dt_fin,
                        "caracteristicas": tags_raw.split("|") if tags_raw else []
                    })
                    print(f"      📥 Gacha: {nombre_limpio} → {nombre_canonico}")
                else:
                    no_reconocidos.append(nombre_limpio)
                    print(f"      ❓ No reconocido: '{nombre_limpio}'")

        candidatos_raw.sort(key=lambda x: (x['nombre_limpio'], x['fecha_inicio_dt']))
        nuevos = []

        for i in range(len(candidatos_raw)):
            actual = candidatos_raw[i]
            if i + 1 < len(candidatos_raw):
                siguiente = candidatos_raw[i+1]
                if actual['nombre_limpio'] == siguiente['nombre_limpio']:
                    if actual['fecha_fin_dt'] > siguiente['fecha_inicio_dt']:
                        actual['fecha_fin_dt'] = siguiente['fecha_inicio_dt']

            f_ini_str = actual['fecha_inicio_dt'].strftime("%Y-%m-%d")
            f_fin_str = actual['fecha_fin_dt'].strftime("%Y-%m-%d")
            gid = f"{actual['nombre_limpio'].replace(' ', '_').lower()}_{f_ini_str}"

            if gid in ids_existentes:
                print(f"      ⏭️ Ya existe: {actual['nombre_limpio']} ({f_ini_str})")
                continue

            nuevos.append({
                "id": gid,
                "nombre": actual['nombre_limpio'],
                "fecha_inicio": f_ini_str,
                "fecha_fin": f_fin_str,
                "caracteristicas": actual['caracteristicas']
            })

        # Resumen de banners no añadidos
        ya_existian = [c for c in candidatos_raw
                       if f"{c['nombre_limpio'].replace(' ', '_').lower()}_{c['fecha_inicio_dt'].strftime('%Y-%m-%d')}" in ids_existentes]
        if no_reconocidos:
            print(f"\n❓ Banners leídos pero NO reconocidos ({len(no_reconocidos)}):")
            for n in no_reconocidos:
                print(f"      - {n}")
        if ya_existian:
            print(f"\n⏭️ Banners reconocidos pero YA EXISTÍAN ({len(ya_existian)}):")
            for c in ya_existian:
                print(f"      - {c['nombre_limpio']} ({c['fecha_inicio_dt'].strftime('%Y-%m-%d')})")

        if len(nuevos) > 0:
            print(f"\n✅ Banners a subir ({len(nuevos)}):")
            for n in nuevos:
                print(f"      - {n['nombre']} ({n['fecha_inicio']})")
            print(f"⚙️ Subiendo {len(nuevos)} Gachas...")
            try:
                subir_a_github(nuevos, archivo_datos, tipo="gachas", mensaje_commit="Update Gachas")
            except Exception as e:
                print(f"❌ Error subiendo: {e}")
        else:
            print("⚠️ No hay gachas nuevas.")

        print("🏁 Terminado trabajo de Gachas. Cerrando.")
        try:
             await client.close()
        except: pass

if __name__ == "__main__":
    if not DISCORD_TOKEN or not GITHUB_TOKEN:
        raise SystemExit("Set DISCORD_TOKEN and GITHUB_TOKEN before starting a legacy bot")
    client.run(DISCORD_TOKEN)
