import os
import requests
import json
import time
import re
from datetime import datetime
import xml.etree.ElementTree as ET

# --- CONFIGURACIÓN ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WORDPRESS_USER = os.environ.get("WORDPRESS_USER")
WORDPRESS_APP_PASSWORD = os.environ.get("WORDPRESS_APP_PASSWORD")
WORDPRESS_URL = os.environ.get("WORDPRESS_URL").rstrip('/')

# --- FUENTES RSS NACIONALES ---
RSS_FEEDS = [
    "https://www.lanacion.com.ar/arc/outboundfeeds/rss/",
    "https://www.perfil.com/feed",
    "https://www.lmneuquen.com/rss/pais.xml",
]

# --- TRADUCCIÓN DE FECHAS ---
DIAS_SEMANA = {
    'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
    'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
}
MESES = {
    'January': 'Enero', 'February': 'Febrero', 'March': 'Marzo', 'April': 'Abril',
    'May': 'Mayo', 'June': 'Junio', 'July': 'Julio', 'August': 'Agosto',
    'September': 'Septiembre', 'October': 'Octubre', 'November': 'Noviembre', 'December': 'Diciembre'
}

def obtener_fecha_en_espanol():
    now = datetime.now()
    dia_es = DIAS_SEMANA.get(now.strftime("%A"), now.strftime("%A"))
    mes_es = MESES.get(now.strftime("%B"), now.strftime("%B"))
    return f"{dia_es} {now.strftime('%d')} de {mes_es} de {now.strftime('%Y')}"

def limpiar_html(texto):
    """Elimina etiquetas HTML y recorta el texto."""
    texto = re.sub(r'<[^>]+>', '', texto or '')
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto[:400]

def obtener_noticias_rss():
    """Obtiene titulares de múltiples feeds RSS nacionales."""
    noticias = []
    headers = {'User-Agent': 'Mozilla/5.0 (AutoReporter/1.0)'}

    for url in RSS_FEEDS:
        try:
            print(f"📡 Obteniendo: {url}")
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()

            root = ET.fromstring(res.content)
            items = root.findall('.//item')

            for item in items[:5]:
                titulo = item.findtext('title', '').strip()
                descripcion = limpiar_html(item.findtext('description', ''))
                if titulo and len(titulo) > 10:
                    noticias.append(f"TITULAR: {titulo}\nCONTEXTO: {descripcion}")

        except Exception as e:
            print(f"⚠️ Error en {url}: {e}")
        time.sleep(0.5)

    print(f"✅ {len(noticias)} noticias obtenidas.")
    return noticias[:12]

def llamar_gemini(prompt):
    """Llama a la API de Gemini con fallback entre modelos."""
    modelos = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-1.5-flash"]
    headers = {'Content-Type': 'application/json'}

    for modelo in modelos:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.75, "maxOutputTokens": 2500}
        }
        try:
            print(f"👉 Probando modelo: {modelo}...", end=" ")
            res = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
            if res.status_code == 200:
                print("✅")
                return res.json()['candidates'][0]['content']['parts'][0]['text']
            else:
                print(f"❌ Error {res.status_code}")
        except Exception as e:
            print(f"⚠️ Error de red: {e}")
        time.sleep(1)

    return None

def generar_nota(noticias, fecha_hoy):
    """Genera la nota periodística con tono libertario usando Gemini."""
    titulares_texto = "\n\n".join(noticias)

    prompt = f"""Sos un periodista argentino con una clara perspectiva liberal-libertaria.
Tu estilo es directo, sin rodeos, crítico del estado, del gasto público y de la casta política.
Valorás la libertad individual, el libre mercado y la meritocracia.
No le tenés miedo a decir lo que otros callan. Tu pluma es contundente.

HOY ES: {fecha_hoy}

TITULARES DEL DÍA:
{titulares_texto}

TU TAREA:
1. Seleccioná las 3 a 5 noticias más relevantes del día.
2. Escribí una nota periodística completa en HTML.
3. Analizá cada noticia con tu mirada editorial libertaria: qué implica para la libertad, el bolsillo y el futuro de los argentinos.
4. Cerrá con un párrafo editorial contundente.

REGLAS ESTRICTAS:
- NO saludes ni te presentes. Empezá DIRECTO con la etiqueta <h1>.
- TÍTULO en <h1>: Debe ser impactante y reflejar el tono editorial (ej: "La casta sigue gastando: lo que el Estado te quita cada día")
- Usá <h2> para cada noticia analizada, <p> para el desarrollo, <strong> para énfasis.
- SOLO HTML, sin markdown ni bloques de código.
- Español rioplatense. Tono: crítico, directo, libertario, sin concesiones al progresismo ni al estatismo.
"""
    return llamar_gemini(prompt)

def limpiar_respuesta(texto):
    """Extrae título y cuerpo del HTML generado."""
    texto = texto.replace('```html', '').replace('```', '').strip()
    if "<h1>" in texto:
        texto = texto[texto.find("<h1>"):]

    titulo_match = re.search(r'<h1>(.*?)</h1>', texto, re.IGNORECASE | re.DOTALL)
    if titulo_match:
        titulo = re.sub(r'<[^>]+>', '', titulo_match.group(1)).strip()
        cuerpo = re.sub(r'<h1>.*?</h1>', '', texto, count=1, flags=re.IGNORECASE | re.DOTALL).strip()
    else:
        titulo = f"Argentina hoy: el análisis del día — {obtener_fecha_en_espanol()}"
        cuerpo = texto

    return titulo, cuerpo

def publicar_wordpress(titulo, cuerpo, fecha_hoy):
    """Publica la nota en WordPress."""
    html_final = f"""
<div style="font-family: 'Georgia', serif; font-size: 18px; line-height: 1.8; color: #1a1a2e; max-width: 860px; margin: auto;">

  <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%); color: white; padding: 40px 35px; border-radius: 12px; margin-bottom: 35px; box-shadow: 0 6px 25px rgba(0,0,0,0.35);">
    <p style="text-transform: uppercase; letter-spacing: 3px; font-size: 12px; margin: 0 0 8px; opacity: 0.65; font-family: sans-serif;">Análisis Nacional · Perspectiva Liberal</p>
    <h2 style="font-size: 26px; margin: 0 0 10px; font-family: sans-serif; font-weight: 700;">Argentina al día</h2>
    <div style="font-size: 15px; opacity: 0.75;">{fecha_hoy}</div>
  </div>

  <div style="background: white; padding: 10px 5px;">
    {cuerpo}
  </div>

  <div style="margin-top: 45px; padding: 20px 25px; background: #f0f0f0; border-left: 5px solid #0f3460; font-size: 14px; color: #444; font-style: italic;">
    "En Argentina, cada peso que gasta el Estado es un peso que le sacan al que trabaja."
  </div>

</div>
"""
    auth = (WORDPRESS_USER, WORDPRESS_APP_PASSWORD)
    post = {
        'title': titulo,
        'content': html_final,
        'status': 'publish'
    }
    r = requests.post(f"{WORDPRESS_URL}/wp-json/wp/v2/posts", json=post, auth=auth)
    if r.status_code == 201:
        print(f"✅ Publicado en WordPress: {titulo}")
    else:
        print(f"❌ Error al publicar: {r.status_code} — {r.text[:300]}")

def main():
    fecha_hoy = obtener_fecha_en_espanol()
    print(f"\n=== NOTICIAS NACIONALES: {fecha_hoy} ===\n")

    noticias = obtener_noticias_rss()
    if not noticias:
        print("❌ No se obtuvieron noticias. Abortando.")
        return

    texto_ia = generar_nota(noticias, fecha_hoy)
    if not texto_ia:
        print("❌ La IA no generó contenido. Abortando.")
        return

    titulo, cuerpo = limpiar_respuesta(texto_ia)
    publicar_wordpress(titulo, cuerpo, fecha_hoy)

if __name__ == "__main__":
    main()
