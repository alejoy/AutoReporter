import os
import requests
import json
import time
import re
from datetime import datetime
import xml.etree.ElementTree as ET

# --- CONFIGURACIÓN ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY")
WORDPRESS_USER = os.environ.get("WORDPRESS_USER")
WORDPRESS_APP_PASSWORD = os.environ.get("WORDPRESS_APP_PASSWORD")
WORDPRESS_URL = os.environ.get("WORDPRESS_URL").rstrip('/')

# --- FUENTES RSS NEUQUÉN CIUDAD ---
RSS_FEEDS = [
    "https://www.lmneuquen.com/rss/ultimas-noticias.xml",
    "https://www.lmneuquen.com/rss/home.xml",
    "https://www.rionegro.com.ar/feed/",
]

# Palabras clave para priorizar noticias de la ciudad capital
PALABRAS_CIUDAD = [
    'neuquén capital', 'ciudad de neuquén', 'municipio', 'intendente',
    'concejo deliberante', 'vecinos', 'barrio', 'calle', 'plaza',
    'transporte urbano', 'ciudad', 'neuquén city', 'capital neuquina'
]

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
    texto = (titulo + " " + descripcion).lower()
    return any(palabra in texto for palabra in PALABRAS_CIUDAD)

def obtener_noticias_rss():
    noticias_ciudad = []
    noticias_generales = []
    headers = {'User-Agent': 'Mozilla/5.0 (AutoReporter/1.0)'}
    for url in RSS_FEEDS:
        try:
            print(f"📡 Obteniendo: {url}")
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
            root = ET.fromstring(res.content)
            for item in root.findall('.//item')[:8]:
                titulo = item.findtext('title', '').strip()
                descripcion = limpiar_html(item.findtext('description', ''))
                if titulo and len(titulo) > 10:
                    entrada = f"TITULAR: {titulo}\nCONTEXTO: {descripcion}"
                    if es_noticia_de_ciudad(titulo, descripcion):
                        noticias_ciudad.append(entrada)
                    else:
                        noticias_generales.append(entrada)
        except Exception as e:
            print(f"⚠️ Error en {url}: {e}")
        time.sleep(0.5)

    # Completar con generales si hay pocas de ciudad
    noticias = noticias_ciudad + noticias_generales[:max(0, 10 - len(noticias_ciudad))]
    print(f"✅ {len(noticias)} noticias obtenidas ({len(noticias_ciudad)} de ciudad).")
    return noticias[:15]

def llamar_gemini(prompt, max_tokens=2500):
    modelos = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-1.5-flash"]
    headers = {'Content-Type': 'application/json'}
    for modelo in modelos:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": max_tokens}
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

def seleccionar_temas(noticias, fecha_hoy):
    """Pide a Gemini que elija los 2 temas más relevantes para la ciudad de Neuquén."""
    titulares = "\n".join([n.split("\n")[0].replace("TITULAR: ", "") for n in noticias])
    prompt = f"""Analizá estos titulares de noticias del {fecha_hoy}, enfocados en la ciudad de Neuquén capital:

{titulares}

Seleccioná los 2 temas más relevantes para los vecinos de la ciudad de Neuquén.
Preferí noticias sobre servicios municipales, obras, transporte, seguridad, cultura o economía local.
Si no hay noticias específicamente de la ciudad, elegí las más relevantes de la región.

Respondé ÚNICAMENTE con este JSON válido, sin texto adicional ni bloques de código:
[
  {{
    "titulo_sugerido": "Título periodístico atractivo para el artículo",
    "resumen_tema": "Descripción breve del tema en 1-2 oraciones",
    "keywords_imagen": "2 o 3 palabras clave en INGLÉS para buscar foto (ej: city argentina urban street)"
  }},
  {{
    "titulo_sugerido": "...",
    "resumen_tema": "...",
    "keywords_imagen": "..."
  }}
]"""
    respuesta = llamar_gemini(prompt, max_tokens=500)
    if not respuesta:
        return None
    try:
        respuesta = re.sub(r'```(?:json)?', '', respuesta).strip()
        temas = json.loads(respuesta)
        return temas if isinstance(temas, list) else None
    except json.JSONDecodeError as e:
        print(f"⚠️ Error al parsear JSON de temas: {e}")
        print(f"Respuesta recibida: {respuesta[:300]}")
        return None

def generar_articulo(tema, fecha_hoy):
    """Genera un artículo periodístico sobre un tema de la ciudad de Neuquén."""
    prompt = f"""Sos un periodista de la ciudad de Neuquén, cercano a los vecinos y al día con la realidad local.
Escribís sobre lo que afecta la vida cotidiana de los neuquinos: el transporte, los servicios, las obras,
el Concejo Deliberante, la gestión municipal y los barrios.
Tu tono es directo y honesto: hablás de los problemas sin catastrofismo, y de las soluciones sin hacer
propaganda. Le hablás al vecino común, que quiere entender qué pasa en su ciudad.

FECHA: {fecha_hoy}
TEMA: {tema['titulo_sugerido']}
CONTEXTO: {tema['resumen_tema']}

Escribí una nota periodística completa en HTML sobre este tema de la ciudad. La nota debe:
- Explicar el tema con claridad para cualquier vecino de Neuquén
- Describir el impacto concreto en la vida cotidiana de los habitantes
- Aportar contexto local (barrios, calles, instituciones conocidas si corresponde)
- Cerrar con información útil o una pregunta que invite a la participación ciudadana

REGLAS:
- NO saludes ni te presentes. Empezá DIRECTO con <h1>.
- TÍTULO en <h1>: El título sugerido o uno más atractivo
- Usá <h2> para secciones, <p> para párrafos, <strong> para destacar datos
- Extensión: 4 a 6 párrafos bien desarrollados
- SOLO HTML, sin markdown
- Español rioplatense, tono cercano y vecinal"""
    return llamar_gemini(prompt, max_tokens=2000)

def buscar_imagen_pixabay(keywords):
    if not PIXABAY_API_KEY:
        print("⚠️ PIXABAY_API_KEY no configurada, se omite imagen.")
        return None
    try:
        url = "https://pixabay.com/api/"
        params = {
            'key': PIXABAY_API_KEY,
            'q': keywords,
            'image_type': 'photo',
            'orientation': 'horizontal',
            'per_page': 5,
            'safesearch': 'true',
            'min_width': 800,
        }
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 200:
            hits = res.json().get('hits', [])
            if hits:
                print(f"🖼️ Imagen encontrada: {hits[0]['pageURL']}")
                return hits[0]['webformatURL']
        print(f"⚠️ Pixabay sin resultados para: {keywords}")
    except Exception as e:
        print(f"⚠️ Error buscando imagen: {e}")
    return None

def subir_imagen_wordpress(img_url, slug):
    try:
        img_data = requests.get(img_url, timeout=15).content
        nombre_archivo = re.sub(r'[^a-z0-9]', '-', slug.lower())[:40] + '.jpg'
        auth = (WORDPRESS_USER, WORDPRESS_APP_PASSWORD)
        headers = {
            'Content-Disposition': f'attachment; filename="{nombre_archivo}"',
            'Content-Type': 'image/jpeg',
        }
        r = requests.post(
            f"{WORDPRESS_URL}/wp-json/wp/v2/media",
            headers=headers,
            data=img_data,
            auth=auth,
            timeout=30
        )
        if r.status_code == 201:
            media_id = r.json()['id']
            print(f"🖼️ Imagen subida a WordPress (ID: {media_id})")
            return media_id
        else:
            print(f"⚠️ Error subiendo imagen: {r.status_code}")
    except Exception as e:
        print(f"⚠️ Error subiendo imagen: {e}")
    return None

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

def publicar_wordpress(titulo, cuerpo, fecha_hoy, media_id=None):
    html_final = f"""
<div style="font-family: 'Georgia', serif; font-size: 18px; line-height: 1.8; color: #1a1a2e; max-width: 860px; margin: auto;">

  <div style="background: linear-gradient(135deg, #7b2d00 0%, #c45e00 60%, #e07b39 100%); color: white; padding: 35px; border-radius: 12px; margin-bottom: 35px; box-shadow: 0 4px 20px rgba(0,0,0,0.25);">
    <p style="text-transform: uppercase; letter-spacing: 3px; font-size: 12px; margin: 0 0 8px; opacity: 0.6; font-family: sans-serif;">Noticias · Ciudad de Neuquén</p>
    <div style="font-size: 15px; opacity: 0.7;">{fecha_hoy}</div>
  </div>

  <div style="background: white; padding: 10px 5px;">
    {cuerpo}
  </div>

</div>
"""
    auth = (WORDPRESS_USER, WORDPRESS_APP_PASSWORD)
    post = {
        'title': titulo,
        'content': html_final,
        'status': 'draft',
    }
    if media_id:
        post['featured_media'] = media_id

    r = requests.post(f"{WORDPRESS_URL}/wp-json/wp/v2/posts", json=post, auth=auth)
    if r.status_code == 201:
        print(f"✅ Borrador creado: {titulo}")
    else:
        print(f"❌ Error al publicar: {r.status_code} — {r.text[:300]}")

def main():
    fecha_hoy = obtener_fecha_en_espanol()
    print(f"\n=== NOTICIAS CIUDAD DE NEUQUÉN: {fecha_hoy} ===\n")

    noticias = obtener_noticias_rss()
    if not noticias:
        print("❌ No se obtuvieron noticias. Abortando.")
        return

    temas = seleccionar_temas(noticias, fecha_hoy)
    if not temas:
        print("❌ No se pudieron seleccionar temas. Abortando.")
        return

    print(f"📋 {len(temas)} temas seleccionados.")

    for i, tema in enumerate(temas, 1):
        print(f"\n--- Procesando nota {i}/{len(temas)}: {tema['titulo_sugerido']} ---")

        texto_ia = generar_articulo(tema, fecha_hoy)
        if not texto_ia:
            print("❌ Falló la generación del artículo. Saltando.")
            continue

        titulo, cuerpo = limpiar_respuesta(texto_ia)

        media_id = None
        if tema.get('keywords_imagen'):
            img_url = buscar_imagen_pixabay(tema['keywords_imagen'])
            if img_url:
                media_id = subir_imagen_wordpress(img_url, titulo)

        publicar_wordpress(titulo, cuerpo, fecha_hoy, media_id)
        time.sleep(3)

if __name__ == "__main__":
    main()
