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

RSS_FEEDS = [
    "https://www.lanacion.com.ar/arc/outboundfeeds/rss/",
    "https://www.perfil.com/feed",
    "https://www.lmneuquen.com/rss/pais.xml",
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
    return re.sub(r'\s+', ' ', texto).strip()[:400]

def obtener_og_image(url):
    """Fetches the article page and extracts the og:image URL."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (AutoReporter/1.0)'}
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        # Search for og:image in the HTML
        match = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            res.text, re.IGNORECASE
        )
        if not match:
            # Try alternate attribute order
            match = re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                res.text, re.IGNORECASE
            )
        if match:
            img_url = match.group(1)
            if img_url.startswith('http'):
                print(f"🖼️ og:image encontrada")
                return img_url
    except Exception as e:
        print(f"⚠️ Error obteniendo imagen de {url}: {e}")
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
                link = item.findtext('link', '').strip()
                if titulo and len(titulo) > 10:
                    noticias.append({'titulo': titulo, 'descripcion': descripcion, 'link': link})
        except Exception as e:
            print(f"⚠️ Error en {url}: {e}")
        time.sleep(0.5)
    print(f"✅ {len(noticias)} noticias obtenidas.")
    return noticias[:15]

def llamar_gemini(prompt, max_tokens=2000):
    modelos = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-1.5-flash"]
    headers = {'Content-Type': 'application/json'}
    for modelo in modelos:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.65, "maxOutputTokens": max_tokens}
        }
        try:
            print(f"👉 Probando: {modelo}...", end=" ")
            res = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
            if res.status_code == 200:
                print("✅")
                return res.json()['candidates'][0]['content']['parts'][0]['text']
            print(f"❌ {res.status_code}")
        except Exception as e:
            print(f"⚠️ {e}")
        time.sleep(1)
    return None

def seleccionar_temas(noticias, fecha_hoy):
    titulares = "\n".join([f"{i}. {n['titulo']}" for i, n in enumerate(noticias)])
    prompt = f"""Estos son titulares de noticias de Neuquén provincia del {fecha_hoy}:

{titulares}

Elegí los 2 más importantes del día para los argentinos. Priorizá política nacional, economía, justicia o seguridad. Descartá farándula y deportes si hay temas más relevantes.

Respondé SOLO con JSON, sin texto adicional:
[
  {{"indice": 0, "titulo_sugerido": "Título periodístico", "resumen_tema": "Contexto en 1-2 oraciones"}},
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
            tema['link'] = noticias[idx]['link'] if 0 <= idx < len(noticias) else ''
        return seleccion
    except Exception as e:
        print(f"⚠️ Error JSON: {e}\n{respuesta[:200]}")
        return None

def generar_articulo(tema, fecha_hoy):
    prompt = f"""Sos un redactor periodístico para un portal de noticias de Argentina.
Tu estilo es el del periodismo informativo estándar: claro, directo, sin opinión personal y sin editoriales.
Escribís como lo hace un diario regional serio.

TEMA: {tema['titulo_sugerido']}
CONTEXTO: {tema['resumen_tema']}

Escribí una nota periodística completa en HTML puro siguiendo estas pautas:

ESTILO:
- Pirámide invertida: el dato más importante va primero
- Párrafos de 3 a 5 líneas, fluidos y bien conectados
- Usá <strong> solo para nombres propios, cifras clave o términos técnicos la primera vez que aparecen
- Podés incluir citas de funcionarios o fuentes con su cargo y nombre
- Tono neutro e informativo, sin adjetivos valorativos ni frases de opinión
- NUNCA uses frases como "es importante destacar", "vale la pena mencionar", "desde una perspectiva", "en conclusión", "en resumen"
- NO pongas la fecha al inicio de la nota
- NO uses encabezados de sección (<h2>, <h3>): solo párrafos corridos
- La nota debe leerse como una pieza periodística nacional lista para publicar

FORMATO:
- Empezá DIRECTO con <p>. Sin <h1> ni título.
- Solo etiquetas <p> y <strong>
- 4 a 5 párrafos
- SOLO HTML, sin markdown ni bloques de código
- Español rioplatense neutro"""
    return llamar_gemini(prompt, max_tokens=1500)

def subir_imagen_wordpress(img_url, slug):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (AutoReporter/1.0)'}
        img_res = requests.get(img_url, headers=headers, timeout=15)
        img_res.raise_for_status()
        content_type = img_res.headers.get('Content-Type', 'image/jpeg').split(';')[0].strip()
        if 'jpeg' in content_type or 'jpg' in content_type:
            ext = 'jpg'
        elif 'png' in content_type:
            ext = 'png'
        elif 'webp' in content_type:
            ext = 'webp'
        else:
            ext = 'jpg'
        nombre = re.sub(r'[^a-z0-9]', '-', slug.lower())[:50] + f'.{ext}'
        r = requests.post(
            f"{WORDPRESS_URL}/wp-json/wp/v2/media",
            headers={
                'Content-Disposition': f'attachment; filename="{nombre}"',
                'Content-Type': content_type,
            },
            data=img_res.content,
            auth=(WORDPRESS_USER, WORDPRESS_APP_PASSWORD),
            timeout=30
        )
        if r.status_code == 201:
            media_id = r.json()['id']
            print(f"🖼️ Imagen subida (ID: {media_id})")
            return media_id
        print(f"⚠️ Error subiendo imagen: {r.status_code} — {r.text[:200]}")
    except Exception as e:
        print(f"⚠️ Error con imagen: {e}")
    return None

def publicar_wordpress(titulo, cuerpo, media_id=None):
    post = {
        'title': titulo,
        'content': cuerpo,
        'status': 'draft',
    }
    if media_id:
        post['featured_media'] = media_id
    r = requests.post(
        f"{WORDPRESS_URL}/wp-json/wp/v2/posts",
        json=post,
        auth=(WORDPRESS_USER, WORDPRESS_APP_PASSWORD)
    )
    if r.status_code == 201:
        link = r.json().get('link', '')
        print(f"✅ Borrador creado: {titulo}\n   {link}")
    else:
        print(f"❌ Error: {r.status_code} — {r.text[:300]}")

def main():
    fecha_hoy = obtener_fecha_en_espanol()
    print(f"\n=== NOTICIAS NACIONALES: {fecha_hoy} ===\n")

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

        # Obtener imagen desde la nota original
        media_id = None
        if tema.get('link'):
            img_url = obtener_og_image(tema['link'])
            if img_url:
                media_id = subir_imagen_wordpress(img_url, tema['titulo_sugerido'])
            else:
                print("ℹ️ Sin og:image en el artículo original.")

        texto_ia = generar_articulo(tema, fecha_hoy)
        if not texto_ia:
            print("❌ Falló generación. Saltando.")
            continue

        # Limpiar respuesta
        cuerpo = texto_ia.replace('```html', '').replace('```', '').strip()

        publicar_wordpress(tema['titulo_sugerido'], cuerpo, media_id)
        time.sleep(3)

if __name__ == "__main__":
    main()
