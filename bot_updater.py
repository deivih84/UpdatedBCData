import discord
from github import Github
import re
import json
import datetime
import asyncio

# --- 1. CONFIGURACIÓN ---
DISCORD_TOKEN = 'MTQ0NTQ5Nzk2MzEzOTk2MTAxNA.Gqfcpy.KcE4n11ZRgXA8HblkeqTZowR2xkWmnBGpLR3Wo'
GITHUB_TOKEN = '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'
REPO_NAME = "deivih84/UpdatedBCData"
ARCHIVO_DATOS = "gachas_eventos_actualizados_en.json"
CHANNEL_ID_COMANDOS = 1445468966989332563  # ID del canal donde enviar comandos automáticos

# --- 2. TU DICCIONARIO MAESTRO (Generado desde ejemplos_gachas.json) ---
# El bot necesita saber: "Si leo 'Uberfest', ¿qué imagen y IDs uso?"
PLANTILLAS_GACHA = {
    "The Dynamites": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_dynamites.png",
        "gatos_ids": [42,43,44,57,59,143,427,455,519,617,668,763,912]
    },
    "Elemental Pixies": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_pixies.png",
        "gatos_ids": [359,360,361,401,478,569,631,655,719,817]
    },
    "Dark Heroes": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_heroes.png",
        "gatos_ids": [194,195,196,212,226,261,431,481,533,634,698,774,903]
    },
    "Luga Families": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_lugas.png",
        "gatos_ids": [34,168,169,170,171,240,436,461,546,625,712,781,915]
    },
    "Ultra Souls": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_souls.png",
        "gatos_ids": [134,135,136,137,138,203,322,451,525,633,692,769,908]
    },
    "The Almighties": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_almighties.png",
        "gatos_ids": [257,258,259,271,272,316,439,493,534,642,723,811,911]
    },
    "Girls & Monsters": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_spooky_cuties.png",
        "gatos_ids": [334,335,336,357,358,544,607,682,725,824]
    },
    "Dragon Emperors": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_dragons.png",
        "gatos_ids": [83,84,85,86,87,177,396,450,505,620,660,760]
    },
    "Wargods Vajiras": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_vajiras.png",
        "gatos_ids": [71,72,73,124,125,158,338,448,496,618,649,754,902]
    },
    "Galaxy Gals": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_gals.png",
        "gatos_ids": [75,76,105,106,107,159,351,449,502,619,647,733,830,910]
    },
    "Iron Legion": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_iron.png",
        "gatos_ids": [304,305,306,355,417,463,594,632,674,715,799,909]
    },
    "Red Busters": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_red_busters.png",
        "gatos_ids": [42,43,76,86,87,105,124,136,212,283,305,533,620]
    },
    "Air Busters": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_air_busters.png",
        "gatos_ids": [59,75,83,84,106,107,135,143,196,286]
    },
    "Metal Busters": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_metal_busters.png",
        "gatos_ids": [57,138,170,261,316,358,397,715]
    },
    "Wave Busters": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_wave_busters.png",
        "gatos_ids": [43,72,194,240,258,436,519,559]
    },
    "Colossus Busters": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_colossus_busters.png",
        "gatos_ids": [647,649,655,660,668,674,682,686]
    },
    "Uberfest": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_uberfest.png",
        "gatos_ids": [269,318,380,529,585,641,690,731,779]
    },
    "Epicfest": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_epicfest.png",
        "gatos_ids": [333,378,441,543,609,657,705,738,787]
    },
    "Superfest": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_superfest.png",
        "gatos_ids": [269,318,333,378,380,435,441,484,520,529,543,585,609,641,657,690,705,731,738,758,779,787,810]
    },
    "Busterfest": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_busterfest.png",
        "gatos_ids": [42,43,57,59,72,75,76,83,84,86,87,105,106,107,124,135,136,138,143,170,194,196,212,240,258,261,283,286,305,316,397,436,519,533,559,620,647,649,655,660,668,674,682,686]
    },
    "Royalfest": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_royalfest.png",
        "gatos_ids": [143,212,271,302,330,448,449,450,451,455,461,463,478,481,493,496,544,612,619,633,644,661,682,687,714]
    },
    "Dynastyfest": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_dynastyfest.png",
        "gatos_ids": [229,230,241,242,243,274,275,302,310,330,331,354,438,494,526,563,564,570,584,587,588,595,614,644,648,661,666,683,687,693,699,711,714,736,737,756,759,772,777,786,820]
    },
    "Ultra 4 Selection Gacha": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_ultra4_selection.png",
        "gatos_ids": [306,439,449,451,455,478,607,668]
    },
    "Miracle 4 Selection Gacha": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_miracle4_selection.png",
        "gatos_ids": [71,427,461,481,505,544,619]
    },
    "Excellent 4 Selection Gacha": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_excellent4_selection.png",
        "gatos_ids": [44,136,196,351,448,450,463,493]
    },
    "Neo Best of the Best": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_neo_best_of_the_best.png",
        "gatos_ids": [34,43,87,159,272,334,359,484,496,520,633,674,774,810]
    },
    "Best of the Best": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_best_of_the_best.png",
        "gatos_ids": [76,125,143,168,336,396,435,520,569,642,692,698,715,758]
    },
    "Gals of Summer Sunshine": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_gals_of_summer_sunshine.png",
        "gatos_ids": [354,438,494,563,666,820]
    },
    "Gals of Summer Blue Ocean": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_gals_of_summer_blue_ocean.png",
        "gatos_ids": [274,275,564,614,714,759]
    },
    "Platinum Capsules": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_platinum.png",
        "gatos_ids": [34,42,43,44,57,59,71,72,73,75,76,83,84,85,86,87,105,106,107,124,125,134,135,136,137,138,143,158,159,168,169,170,171,177,194,195,196,203,212,226,240,257,258,259,261,269,271,272,283,286,304,305,306,316,318,322,333,338,351,355,359,360,361,378,380,396,397,401,417,427,431,436,439,441,496,502,505,519,525,529,533,534,543,546,559,569,585,594,609,612,617,618,619,620,625,631,632,633,634,641,642,647,649,655,657,660,668,674,686,690,692,698,705,712,715,719,723,733,754,760,763,769,774,779,781,787,799,811,817]
    },
    "Legend Capsules": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_legend.png",
        "gatos_ids": [34,42,43,44,57,59,71,72,73,75,76,83,84,85,86,87,105,106,107,124,125,134,135,136,137,138,143,158,159,168,169,170,171,177,194,195,196,203,212,226,240,257,258,259,261,269,271,272,283,286,304,305,306,316,318,322,333,338,351,355,359,360,361,378,380,396,397,401,417,427,431,436,439,441,448,449,450,451,455,461,463,478,481,493,496,502,505,519,525,529,533,534,543,546,559,569,585,586,594,609,612,617,618,619,620,625,631,632,633,634,641,642,647,649,655,657,660,668,674,686,690,692,698,705,712,715,719,723,731,733,738,754,760,763,769,774,779,781,787,799,811,817]
    },
    "Mola Mola Collab Gacha": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_mola_mola.png",
        "gatos_ids": [173,174]
    },
    "Halloween Gacha": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_halloween.png",
        "gatos_ids": [229,230,302,570,683,772,773]
    },
    "Halloween Party": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_halloween_party.png",
        "gatos_ids": []
    },
    "Summer Break Survival Capsules": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_summer_break.png",
        "gatos_ids": [766,767,813]
    },
    "Medal King's Palace Capsules": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_medal_king_capsules.png",
        "gatos_ids": [342,375,635,689,726]
    },
    "Summer Break Capsules Paradise": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_summer_break_paradise.png",
        "gatos_ids": [381,615,616]
    },
    "Premium Fair": {
        "imagen_url": "https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/images/gacha/banner_gatcha_premium_fair.png",
        "gatos_ids": []
    },
}

# Configuración de Discord
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# --- UTILIDADES ---
def parsear_fecha(fecha_str):
    # Limpieza: "November 28th" -> "November 28"
    limpia = re.sub(r"(st|nd|rd|th)", "", fecha_str).strip()
    anio = datetime.datetime.now().year
    
    # Si estamos en Diciembre (12) y el evento es en Enero (1), es el año siguiente
    if "January" in limpia and datetime.datetime.now().month == 12:
        anio += 1
        
    try:
        dt = datetime.datetime.strptime(f"{limpia} {anio}", "%B %d %Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return datetime.datetime.now().strftime("%Y-%m-%d")  # Fecha fallback por si falla

def subir_a_github(nuevos_gachas):
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)
    contents = repo.get_contents(ARCHIVO_DATOS)
    
    json_actual = json.loads(contents.decoded_content.decode())
    
    # Añadimos los nuevos gachas a la lista existente (no reemplazamos)
    if "gachas" not in json_actual:
        json_actual["gachas"] = []
    json_actual["gachas"].extend(nuevos_gachas)
    json_actual["ultima_actualizacion"] = datetime.datetime.now().isoformat()
    
    repo.update_file(contents.path, "🤖 Update Gachas", json.dumps(json_actual, indent=2), contents.sha, branch="main")
    print("✅ ¡Subido a GitHub!")

# --- EL CEREBRO DEL BOT ---
@client.event
async def on_ready():
    print(f'✅ Bot conectado como {client.user}')
    
    # 1. Buscamos el canal específico
    channel = client.get_channel(CHANNEL_ID_COMANDOS)
    
    if channel:
        print(f"📢 Enviando comandos al canal: {channel.name}")
        
        # 2. Enviamos el comando de inglés
        await channel.send("p!pe -s -en")
        
        # 3. Esperamos un poquito (5 segundos) para no saturar y dejar que responda
        await asyncio.sleep(5) 
        
        # 4. (Opcional) Enviamos el comando de japonés si lo necesitas
        # await channel.send("p!pe -s -jp") 
        
    else:
        print("❌ Error: No he encontrado el canal. Revisa el ID.")

@client.event
async def on_message(message):
    if message.author == client.user: return

    # --- LIMPIEZA DEL MENSAJE ---
    # PackPack usa bloques de código (```ansi) y códigos de color ANSI, hay que quitarlos
    texto_limpio = message.content.replace("```ansi", "").replace("```", "").strip()
    
    # Eliminar TODOS los códigos de color ANSI 
    # Formatos posibles: \x1b[0;31m, \033[0;31m, o solo 0;31m (sin escape)
    texto_limpio = re.sub(r'\x1b\[[\d;]*m', '', texto_limpio)  # Con caracter escape
    texto_limpio = re.sub(r'\033\[[\d;]*m', '', texto_limpio)  # Formato octal
    texto_limpio = re.sub(r'\d+;\d+m', '', texto_limpio)       # Solo números: 0;31m, 1;34m, etc.
    texto_limpio = re.sub(r'\d+m', '', texto_limpio)           # Solo un número: 0m, 1m, etc.
    
    # Si hay embeds (tarjetas), añadimos su texto también limpio
    if message.embeds:
        for embed in message.embeds:
            if embed.description: 
                desc_limpia = embed.description.replace("```ansi", "").replace("```", "")
                desc_limpia = re.sub(r'\x1b\[[\d;]*m', '', desc_limpia)
                desc_limpia = re.sub(r'\033\[[\d;]*m', '', desc_limpia)
                desc_limpia = re.sub(r'\d+;\d+m', '', desc_limpia)
                desc_limpia = re.sub(r'\d+m', '', desc_limpia)
                texto_limpio += "\n" + desc_limpia
            if embed.title: 
                texto_limpio += "\n" + embed.title

    # --- DETECCIÓN ---
    # Comprobamos si es el mensaje de los Gachas
    if "**Gacha**" in message.content or "G : Guaranteed" in texto_limpio:
        print(f"\n🔎 Analizando mensaje de Gachas de {message.author.name}...")
        
        nuevos_objetos = []
        lines = texto_limpio.split('\n')
        
        # Regex: [Fecha ~ Fecha] Nombre [Tags]
        patron = re.compile(r"\[(.*?) ~ (.*?)\] (.*?) (?:\[(.*?)\])?(?: <.*?>)?$")

        for line in lines:
            line = line.strip()
            if not line: continue # Saltar líneas vacías
            
            match = patron.search(line)
            if match:
                ini, fin, nombre_raw, tags_raw = match.groups()
                
                # Limpiar nombre: "The Almighties (+Victorious Skanda)" -> "The Almighties"
                nombre_limpio = nombre_raw.split(" (+")[0].strip()

                print(f"   ... He leído: '{nombre_limpio}' en las fechas {ini} - {fin}")

                # BUSCAR EN TU DICCIONARIO
                if nombre_limpio in PLANTILLAS_GACHA:
                    plantilla = PLANTILLAS_GACHA[nombre_limpio]
                    
                    nuevo_gacha = {
                        "id": f"{nombre_limpio.replace(' ', '_').lower()}_{parsear_fecha(ini)}",
                        "nombre": nombre_raw, 
                        "imagen_url": plantilla["imagen_url"],
                        "fecha_inicio": parsear_fecha(ini),
                        "fecha_fin": parsear_fecha(fin),
                        "caracteristicas": tags_raw.split("|") if tags_raw else [],
                        "gatos_ids": plantilla["gatos_ids"]
                    }
                    nuevos_objetos.append(nuevo_gacha)
                    print(f"      ✅ ¡Aceptado para subir!")
                else:
                    print(f"      ⚠️ IGNORADO: '{nombre_limpio}' no está en tu diccionario PLANTILLAS_GACHA.")
            else:
                # Esto es útil para ver qué líneas se salta (por si la regex falla)
                # print(f"      [DEBUG] Línea no coincide con patrón: {line}")
                pass

        # --- SUBIDA A GITHUB ---
        if len(nuevos_objetos) > 0:
            print(f"⚙️ Preparando commit con {len(nuevos_objetos)} gachas...")
            try:
                subir_a_github(nuevos_objetos)
                print("🚀 ¡Commit realizado con éxito!")
            except Exception as e:
                print(f"❌ Error fatal subiendo a GitHub: {e}")
        else:
            print("❌ No se ha generado ningún gacha válido (revisa el diccionario).")

client.run(DISCORD_TOKEN)