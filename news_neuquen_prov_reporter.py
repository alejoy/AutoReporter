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

# --- FUENTES RSS NEUQUÉN PROVINCIA ---
RSS_FEEDS = [
    "https://www.lmneuquen.com/rss/neuquen.xml",
    "https://www.rionegro.com.ar/feed/",
    "https://www.lmneuquen.com/rss/ultimas-noticias.xml",
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

def obtener_noticias_rss():
    noticias = []
    headers = {'User-Agent': 'Mozilla/5.0 (AutoReporter/1.0)'}
    for url in RSS_FEEDS:
        try:
            print(f"📡 Obteniendo: {url}")
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
            root = ET.fromstring(res.content)
            for item in root.findall('.//item')[:6]:
                titulo = item.findtext('title', '').strip()
                descripcion = limpiar_html(item.findtext('description', ''))
                if titulo and len(titulo) > 10:
                    noticias.append(f"TITULAR: {titulo}\nCONTEXTO: {descripcion}")
        except Exception as e:
            print(f"⚠️ Error en {url}: {e}")
        time.sleep(0.5)
    print(f"✅ {len(noticias)} noticias obtenidas.")
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
    """Pide a Gemini que elija los 2 temas más relevantes de la provincia."""
    titulares = "\n".join([n.split("\n")[0].replace("TITULAR: ", "") for n in noticias])
    prompt = f"""Analizá estos titulares de noticias de la provincia de Neuquén del {fecha_hoy}:

{titulares}

Seleccioná los 2 temas más importantes e informativamente relevantes del día para los neuquinos.
Preferí noticias sobre política provincial, economía, obras, salud, educación o seguridad.

Respondé ÚNICAMENTE con este JSON válido, sin texto adicional ni bloques de código:
[
  {{
    "titulo_sugerido": "Título periodístico atractivo para el artículo",
    "resumen_tema": "Descripción breve del tema en 1-2 oraciones",
    "keywords_imagen": "2 o 3 palabras clave en INGLÉS para buscar foto (ej: patagonia argentina government)"
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
    """Genera un artículo periodístico sobre un tema de Neuquén provincia."""
    prompt = f"""Sos un periodista de la provincia de Neuquén, independiente y analítico.
Conocés la realidad provincial: la actividad petrolera, la política del MPN, las obras públicas,
la situación de los municipios del interior y los desafíos cotidianos de los neuquinos.
Escribís con claridad, sin panfletos: señalás los problemas cuando existen y reconocés los avances.
Tu mirada prioriza el impacto real en la gente, el uso transparente de los recursos y el desarrollo provincial.

FECHA: {fecha_hoy}
TEMA: {tema['titulo_sugerido']}
CONTEXTO: {tema['resumen_tema']}

Escribí una nota periodística completa en HTML sobre este tema provincial. La nota debe:
- Explicar el tema con contexto claro para el lector neuquino
- Analizar qué impacto tiene en la provincia o en sus habitantes
- Aportar perspectiva sobre la importancia del tema en el contexto patagónico
- Cerrar con una reflexión o dato que invite a seguir informado

REGLAS:
- NO saludes ni te presentes. Empezá DIRECTO con <h1>.
- TÍTULO en <h1>: El título sugerido o uno mejor
- Usá <h2> para secciones, <p> para párrafos, <strong> para destacar datos
- Extensión: 4 a 6 párrafos bien desarrollados
- SOLO HTML, sin markdown
- Español rioplatense, claro y cercano al lector neuquino"""
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
        titulo = f"Neuquén provincia hoy — {obtener_fecha_en_espanol()}"
        cuerpo = texto
    return titulo, cuerpo

def publicar_wordpress(titulo, cuerpo, fecha_hoy, media_id=None):
    html_final = f"""
<div style="font-family: 'Georgia', serif; font-size: 18px; line-height: 1.8; color: #1a1a2e; max-width: 860px; margin: auto;">

  <div style="background: linear-gradient(135deg, #1b4332 0%, #2d6a4f 60%, #40916c 100%); color: white; padding: 35px; border-radius: 12px; margin-bottom: 35px; box-shadow: 0 4px 20px rgba(0,0,0,0.25);">
    <p style="text-transform: uppercase; letter-spacing: 3px; font-size: 12px; margin: 0 0 8px; opacity: 0.6; font-family: sans-serif;">Noticias · Provincia de Neuquén</p>
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
    print(f"\n=== NOTICIAS NEUQUÉN PROVINCIA: {fecha_hoy} ===\n")

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
