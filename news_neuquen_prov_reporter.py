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
    "https://www.lmneuquen.com/rss/neuquen.xml",
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

NS_MEDIA = 'http://search.yahoo.com/mrss/'
NS_CONTENT = 'http://purl.org/rss/1.0/modules/content/'

def obtener_fecha_en_espanol():
    now = datetime.now()
    dia_es = DIAS_SEMANA.get(now.strftime("%A"), now.strftime("%A"))
    mes_es = MESES.get(now.strftime("%B"), now.strftime("%B"))
    return f"{dia_es} {now.strftime('%d')} de {mes_es} de {now.strftime('%Y')}"

def limpiar_html(texto):
    texto = re.sub(r'<[^>]+>', '', texto or '')
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto[:400]

def extraer_imagen_item(item):
    """Extrae la URL de imagen de un item RSS por múltiples métodos."""
    # 1. media:content
    el = item.find(f'{{{NS_MEDIA}}}content')
    if el is not None and el.get('url', ''):
        return el.get('url')
    # 2. media:thumbnail
    el = item.find(f'{{{NS_MEDIA}}}thumbnail')
    if el is not None and el.get('url', ''):
        return el.get('url')
    # 3. enclosure
    enclosure = item.find('enclosure')
    if enclosure is not None and 'image' in enclosure.get('type', ''):
        return enclosure.get('url', '')
    # 4. <img> dentro de description o content:encoded
    for tag in ['description', f'{{{NS_CONTENT}}}encoded']:
        texto = item.findtext(tag, '')
        if texto:
            match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', texto)
            if match and match.group(1).startswith('http'):
                return match.group(1)
    return None

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
                img_url = extraer_imagen_item(item)
                if titulo and len(titulo) > 10:
                    noticias.append({'titulo': titulo, 'descripcion': descripcion, 'img_url': img_url})
        except Exception as e:
            print(f"⚠️ Error en {url}: {e}")
        time.sleep(0.5)
    con_imagen = sum(1 for n in noticias if n['img_url'])
    print(f"✅ {len(noticias)} noticias ({con_imagen} con imagen).")
    return noticias[:15]

def llamar_gemini(prompt, max_tokens=2500):
    modelos = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-1.5-flash"]
    headers = {'Content-Type': 'application/json'}
    for modelo in modelos:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.7, "maxOutputTokens": max_tokens}}
        try:
            print(f"👉 Probando: {modelo}...", end=" ")
            res = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
            if res.status_code == 200:
                print("✅")
                return res.json()['candidates'][0]['content']['parts'][0]['text']
            else:
                print(f"❌ {res.status_code}")
        except Exception as e:
            print(f"⚠️ {e}")
        time.sleep(1)
    return None

def seleccionar_temas(noticias, fecha_hoy):
    titulares = "\n".join([f"{i}. {n['titulo']}" for i, n in enumerate(noticias)])
    prompt = f"""Analizá estos titulares de noticias argentinas del {fecha_hoy}:

{titulares}

Seleccioná los 2 más importantes para los neuquinos. Preferí noticias provinciales: política, economía, obras, salud o seguridad.

Respondé ÚNICAMENTE con JSON válido, sin texto adicional:
[
  {{"indice": 0, "titulo_sugerido": "Título periodístico atractivo", "resumen_tema": "Descripción en 1-2 oraciones"}},
  {{"indice": 1, "titulo_sugerido": "...", "resumen_tema": "..."}}
]"""
    respuesta = llamar_gemini(prompt, max_tokens=400)
    if not respuesta:
        return None
    try:
        respuesta = re.sub(r'```(?:json)?', '', respuesta).strip()
        seleccion = json.loads(respuesta)
        if not isinstance(seleccion, list):
            return None
        for tema in seleccion:
            idx = tema.get('indice', 0)
            tema['img_url'] = noticias[idx]['img_url'] if 0 <= idx < len(noticias) else None
        return seleccion
    except json.JSONDecodeError as e:
        print(f"⚠️ Error JSON: {e}\n{respuesta[:300]}")
        return None

def generar_articulo(tema, fecha_hoy):
    prompt = f"""Sos un periodista de la provincia de Neuquén, independiente y analítico.
Conocés la realidad provincial: la actividad petrolera, la política, las obras y los desafíos cotidianos.
Señalás los problemas cuando existen y reconocés los avances sin hacer propaganda.
Tu mirada prioriza el impacto real en la gente y el desarrollo patagónico.

FECHA: {fecha_hoy}
TEMA: {tema['titulo_sugerido']}
CONTEXTO: {tema['resumen_tema']}

Escribí una nota periodística completa en HTML:
- Explicar el tema con contexto claro
- Analizar el impacto en los argentinos con datos concretos si los conocés
- Perspectiva editorial que valore la eficiencia y la transparencia
- Cerrar con una reflexión que invite a pensar

REGLAS:
- NO saludes. Empezá DIRECTO con <h1>.
- Usá <h2>, <p>, <strong>
- 4 a 6 párrafos bien desarrollados
- SOLO HTML, sin markdown. Español rioplatense."""
    return llamar_gemini(prompt, max_tokens=2000)

def subir_imagen_wordpress(img_url, slug):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (AutoReporter/1.0)'}
        img_res = requests.get(img_url, headers=headers, timeout=15)
        img_res.raise_for_status()
        content_type = img_res.headers.get('Content-Type', 'image/jpeg').split(';')[0]
        ext = 'jpg' if 'jpeg' in content_type or 'jpg' in content_type else \
              'png' if 'png' in content_type else 'webp' if 'webp' in content_type else 'jpg'
        nombre = re.sub(r'[^a-z0-9]', '-', slug.lower())[:40] + f'.{ext}'
        r = requests.post(
            f"{WORDPRESS_URL}/wp-json/wp/v2/media",
            headers={'Content-Disposition': f'attachment; filename="{nombre}"', 'Content-Type': content_type},
            data=img_res.content,
            auth=(WORDPRESS_USER, WORDPRESS_APP_PASSWORD),
            timeout=30
        )
        if r.status_code == 201:
            media_id = r.json()['id']
            print(f"🖼️ Imagen subida (ID: {media_id})")
            return media_id
        else:
            print(f"⚠️ Error subiendo imagen: {r.status_code}")
    except Exception as e:
        print(f"⚠️ Error con imagen: {e}")
    return None

def limpiar_respuesta(texto):
    texto = texto.replace('```html', '').replace('```', '').strip()
    if "<h1>" in texto:
        texto = texto[texto.find("<h1>"):]
    m = re.search(r'<h1>(.*?)</h1>', texto, re.IGNORECASE | re.DOTALL)
    titulo = re.sub(r'<[^>]+>', '', m.group(1)).strip() if m else f"Neuquén provincia hoy — {obtener_fecha_en_espanol()}"
    cuerpo = re.sub(r'<h1>.*?</h1>', '', texto, count=1, flags=re.IGNORECASE | re.DOTALL).strip() if m else texto
    return titulo, cuerpo

def publicar_wordpress(titulo, cuerpo, fecha_hoy, media_id=None):
    html_final = f"""
<div style="font-family: 'Georgia', serif; font-size: 18px; line-height: 1.8; color: #1a1a2e; max-width: 860px; margin: auto;">
  <div style="background: linear-gradient(135deg, #1b4332 0%, #2d6a4f 60%, #40916c 100%); color: white; padding: 35px; border-radius: 12px; margin-bottom: 35px;">
    <p style="text-transform: uppercase; letter-spacing: 3px; font-size: 12px; margin: 0 0 8px; opacity: 0.6; font-family: sans-serif;">Noticias · Provincia de Neuquén</p>
    <div style="font-size: 15px; opacity: 0.7;">{fecha_hoy}</div>
  </div>
  <div style="padding: 10px 5px;">{cuerpo}</div>
</div>"""
    post = {'title': titulo, 'content': html_final, 'status': 'draft'}
    if media_id:
        post['featured_media'] = media_id
    r = requests.post(f"{WORDPRESS_URL}/wp-json/wp/v2/posts", json=post, auth=(WORDPRESS_USER, WORDPRESS_APP_PASSWORD))
    if r.status_code == 201:
        print(f"✅ Borrador creado: {titulo}")
    else:
        print(f"❌ Error: {r.status_code} — {r.text[:300]}")

def main():
    fecha_hoy = obtener_fecha_en_espanol()
    print(f"\n=== NOTICIAS NEUQUÉN PROVINCIA: {fecha_hoy} ===\n")
    noticias = obtener_noticias_rss()
    if not noticias:
        print("❌ Sin noticias. Abortando.")
        return
    temas = seleccionar_temas(noticias, fecha_hoy)
    if not temas:
        print("❌ Sin temas seleccionados. Abortando.")
        return
    for i, tema in enumerate(temas, 1):
        print(f"\n--- Nota {i}: {tema['titulo_sugerido']} ---")
        texto_ia = generar_articulo(tema, fecha_hoy)
        if not texto_ia:
            print("❌ Falló generación. Saltando.")
            continue
        titulo, cuerpo = limpiar_respuesta(texto_ia)
        media_id = None
        if tema.get('img_url'):
            print(f"🖼️ Imagen: {tema['img_url']}")
            media_id = subir_imagen_wordpress(tema['img_url'], titulo)
        else:
            print("ℹ️ Sin imagen en el feed para esta noticia.")
        publicar_wordpress(titulo, cuerpo, fecha_hoy, media_id)
        time.sleep(3)

if __name__ == "__main__":
    main()
