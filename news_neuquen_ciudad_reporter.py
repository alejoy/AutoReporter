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

# --- FUENTES RSS NEUQUÉN CIUDAD ---
RSS_FEEDS = [
    "https://www.lmneuquen.com/rss/feed.xml",
    "https://www.anb.com.ar/feed/",
    "https://www.neuquen.gov.ar/feed/",
    "https://www.diarioadn.com/feed/",
]

# --- PALABRAS CLAVE PARA FILTRAR NOTICIAS DE LA CIUDAD ---
PALABRAS_CIUDAD = [
    'neuquén capital', 'ciudad de neuquén', 'municipio', 'intendente',
    'concejo deliberante', 'vecinos', 'barrio', 'calle', 'plaza',
    'transporte urbano', 'obra pública', 'ciudad', 'neuquén capital'
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
    texto = re.sub(r'<[^>]+>', '', texto or '')
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto[:400]

def es_noticia_de_ciudad(titulo, descripcion):
    """Filtra noticias que sean relevantes para la ciudad de Neuquén."""
    texto = (titulo + " " + descripcion).lower()
    return any(palabra in texto for palabra in PALABRAS_CIUDAD)

def obtener_noticias_rss():
    """Obtiene titulares de medios locales de la ciudad de Neuquén."""
    noticias = []
    noticias_generales = []
    headers = {'User-Agent': 'Mozilla/5.0 (AutoReporter/1.0)'}

    for url in RSS_FEEDS:
        try:
            print(f"📡 Obteniendo: {url}")
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()

            root = ET.fromstring(res.content)
            items = root.findall('.//item')

            for item in items[:8]:
                titulo = item.findtext('title', '').strip()
                descripcion = limpiar_html(item.findtext('description', ''))
                if titulo and len(titulo) > 10:
                    entrada = f"TITULAR: {titulo}\nCONTEXTO: {descripcion}"
                    if es_noticia_de_ciudad(titulo, descripcion):
                        noticias.append(entrada)
                    else:
                        noticias_generales.append(entrada)

        except Exception as e:
            print(f"⚠️ Error en {url}: {e}")
        time.sleep(0.5)

    # Si hay pocas noticias específicas de ciudad, completar con generales
    if len(noticias) < 5:
        noticias += noticias_generales[:8 - len(noticias)]

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
    """Genera la nota periodística con tono libertario y foco en la ciudad de Neuquén."""
    titulares_texto = "\n\n".join(noticias)

    prompt = f"""Sos un periodista de la ciudad de Neuquén capital con una clara perspectiva liberal-libertaria municipal.
Conocés la realidad cotidiana de los neuquinos: el tránsito, los servicios públicos, el gasto municipal,
las decisiones del Concejo Deliberante y las obras que se hacen (o no se hacen) en los barrios.
Tu mirada es la del vecino común que paga impuestos y exige resultados concretos.
Sos crítico del gasto innecesario, la burocracia y la politización de los servicios básicos.

HOY ES: {fecha_hoy}

TITULARES DEL DÍA EN LA CIUDAD DE NEUQUÉN:
{titulares_texto}

TU TAREA:
1. Seleccioná las 3 a 5 noticias más relevantes para los vecinos de la ciudad.
2. Escribí una nota periodística completa en HTML con perspectiva liberal-libertaria municipal.
3. Analizá cada noticia desde el punto de vista del vecino: ¿qué cambia en su vida cotidiana? ¿cuánto cuesta? ¿quién lo paga?
4. Cerrá con un párrafo editorial directo, orientado al vecino neuquino.

REGLAS ESTRICTAS:
- NO saludes ni te presentes. Empezá DIRECTO con la etiqueta <h1>.
- TÍTULO en <h1>: Cercano, directo, orientado al vecino (ej: "Neuquén ciudad: lo que pasa en tu barrio y en tu bolsillo")
- Usá <h2> para cada noticia analizada, <p> para el desarrollo, <strong> para énfasis.
- SOLO HTML, sin markdown ni bloques de código.
- Español rioplatense con referencias locales de la ciudad. Tono: crítico, vecinal, libertario, sin eufemismos.
"""
    return llamar_gemini(prompt)

def limpiar_respuesta(texto):
    texto = texto.replace('```html', '').replace('```', '').strip()
    if "<h1>" in texto:
        texto = texto[texto.find("<h1>"):]

    titulo_match = re.search(r'<h1>(.*?)</h1>', texto, re.IGNORECASE | re.DOTALL)
    if titulo_match:
        titulo = re.sub(r'<[^>]+>', '', titulo_match.group(1)).strip()
        cuerpo = re.sub(r'<h1>.*?</h1>', '', texto, count=1, flags=re.IGNORECASE | re.DOTALL).strip()
    else:
        titulo = f"Ciudad de Neuquén hoy — {obtener_fecha_en_espanol()}"
        cuerpo = texto

    return titulo, cuerpo

def publicar_wordpress(titulo, cuerpo, fecha_hoy):
    html_final = f"""
<div style="font-family: 'Georgia', serif; font-size: 18px; line-height: 1.8; color: #1a1a2e; max-width: 860px; margin: auto;">

  <div style="background: linear-gradient(135deg, #7b2d00 0%, #c45e00 60%, #e07b39 100%); color: white; padding: 40px 35px; border-radius: 12px; margin-bottom: 35px; box-shadow: 0 6px 25px rgba(0,0,0,0.3);">
    <p style="text-transform: uppercase; letter-spacing: 3px; font-size: 12px; margin: 0 0 8px; opacity: 0.65; font-family: sans-serif;">Análisis Municipal · Ciudad de Neuquén</p>
    <h2 style="font-size: 26px; margin: 0 0 10px; font-family: sans-serif; font-weight: 700;">Neuquén Ciudad al día</h2>
    <div style="font-size: 15px; opacity: 0.75;">{fecha_hoy}</div>
  </div>

  <div style="background: white; padding: 10px 5px;">
    {cuerpo}
  </div>

  <div style="margin-top: 45px; padding: 20px 25px; background: #fff8f0; border-left: 5px solid #c45e00; font-size: 14px; color: #444; font-style: italic;">
    "El mejor gobierno municipal es el que menos te molesta y más te deja vivir en paz."
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
    print(f"\n=== NOTICIAS CIUDAD DE NEUQUÉN: {fecha_hoy} ===\n")

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
