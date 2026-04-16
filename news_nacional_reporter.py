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
    return re.sub(r'\s+', ' ', texto).strip()

def obtener_noticias_rss():
    noticias = []
    headers = {'User-Agent': 'Mozilla/5.0 (AutoReporter/1.0)'}
    for url in RSS_FEEDS:
        try:
            print(f"📡 {url}")
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
            root = ET.fromstring(res.content)
            for item in root.findall('.//item')[:6]:
                titulo = item.findtext('title', '').strip()
                link = item.findtext('link', '').strip()
                if titulo and len(titulo) > 10 and link:
                    noticias.append({'titulo': titulo, 'link': link})
        except Exception as e:
            print(f"⚠️ Error en {url}: {e}")
        time.sleep(0.5)
    print(f"✅ {len(noticias)} noticias encontradas.")
    return noticias[:15]

def obtener_articulo_completo(url):
    """
    Descarga el artículo original y extrae:
    - og:image: imagen destacada real de la nota
    - texto: cuerpo completo del artículo para usar como contexto
    """
    og_image = None
    texto_articulo = ""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (AutoReporter/1.0)'}
        res = requests.get(url, headers=headers, timeout=12)
        res.raise_for_status()
        html = res.text

        # --- Extraer og:image ---
        for patron in [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        ]:
            m = re.search(patron, html, re.IGNORECASE)
            if m and m.group(1).startswith('http'):
                og_image = m.group(1)
                print(f"🖼️  og:image: {og_image}")
                break

        if not og_image:
            print("⚠️  No se encontró og:image en el artículo.")

        # --- Extraer texto del artículo ---
        parrafos = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
        textos = [limpiar_html(p) for p in parrafos]
        textos = [t for t in textos if len(t) > 60]  # descartar párrafos cortos/nav
        texto_articulo = '\n\n'.join(textos[:20])
        print(f"📄 Texto extraído: {len(texto_articulo)} caracteres.")

    except Exception as e:
        print(f"⚠️ Error descargando artículo: {e}")

    return og_image, texto_articulo

def llamar_gemini(prompt, max_tokens=1500):
    modelos = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-1.5-flash"]
    headers = {'Content-Type': 'application/json'}
    for modelo in modelos:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.5, "maxOutputTokens": max_tokens}
        }
        try:
            print(f"👉 {modelo}...", end=" ")
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
    prompt = f"""Titulares nacionales del {fecha_hoy}:

{titulares}

Elegí los 2 más importantes del día para los argentinos. Priorizá política nacional, economía, justicia o seguridad. Descartá farándula y deportes si hay temas más relevantes.

Respondé SOLO con JSON válido:
[
  {{"indice": 0, "titulo_sugerido": "Título periodístico"}},
  {{"indice": 1, "titulo_sugerido": "..."}}
]"""
    respuesta = llamar_gemini(prompt, max_tokens=200)
    if not respuesta:
        return None
    try:
        respuesta = re.sub(r'```(?:json)?', '', respuesta).strip()
        seleccion = json.loads(respuesta)
        if not isinstance(seleccion, list):
            return None
        for tema in seleccion:
            idx = tema.get('indice', 0)
            if 0 <= idx < len(noticias):
                tema['link'] = noticias[idx]['link']
                tema['titulo_original'] = noticias[idx]['titulo']
            else:
                tema['link'] = ''
                tema['titulo_original'] = ''
        return seleccion
    except Exception as e:
        print(f"⚠️ Error JSON: {e}\n{respuesta[:200]}")
        return None

def generar_articulo(titulo_sugerido, texto_fuente):
    prompt = f"""Sos un redactor periodístico para un portal de noticias de Argentina.
Tu tarea es redactar una nota periodística basándote EXCLUSIVAMENTE en el texto fuente que te doy.
No inventes datos, cifras, nombres ni hechos que no estén en el texto fuente.
Si el texto fuente tiene citas textuales, podés usarlas.

TEXTO FUENTE (artículo original):
\"\"\"
{texto_fuente[:3000]}
\"\"\"

TÍTULO PARA LA NOTA: {titulo_sugerido}

Redactá la nota en HTML siguiendo estas reglas:

ESTILO:
- Pirámide invertida: el dato más importante primero
- Párrafos de 3 a 5 líneas, fluidos
- Usá <strong> para nombres propios, cifras y términos clave la primera vez
- Podés usar citas del texto fuente con el nombre y cargo de quien habla
- Tono informativo y neutro
- PROHIBIDO: "es importante destacar", "vale la pena mencionar", "desde una perspectiva", "cabe señalar", "en conclusión", "en este contexto", "resulta relevante"
- NO escribas la fecha
- NO uses <h2> ni <h3>, solo párrafos

FORMATO:
- Empezá DIRECTO con <p>. Sin título, sin encabezado.
- Solo etiquetas <p> y <strong>
- 4 a 5 párrafos
- Solo HTML, sin markdown"""
    return llamar_gemini(prompt, max_tokens=1500)

def subir_imagen_wordpress(img_url):
    """Descarga la imagen y la sube a WordPress como media. Devuelve el ID."""
    try:
        print(f"⬇️  Descargando imagen...")
        headers = {'User-Agent': 'Mozilla/5.0 (AutoReporter/1.0)'}
        img_res = requests.get(img_url, headers=headers, timeout=15)
        img_res.raise_for_status()

        # Detectar tipo de imagen
        content_type = img_res.headers.get('Content-Type', '').split(';')[0].strip()
        if not content_type or 'image' not in content_type:
            content_type = 'image/jpeg'
        ext = 'jpg' if 'jpeg' in content_type or 'jpg' in content_type or not content_type else \
              'png' if 'png' in content_type else \
              'webp' if 'webp' in content_type else 'jpg'

        # Nombre de archivo desde la URL
        nombre_desde_url = img_url.split('/')[-1].split('?')[0]
        nombre = nombre_desde_url if nombre_desde_url.endswith(('jpg', 'jpeg', 'png', 'webp')) else f"imagen.{ext}"

        print(f"⬆️  Subiendo a WordPress ({len(img_res.content)} bytes, {content_type})...")
        r = requests.post(
            f"{WORDPRESS_URL}/wp-json/wp/v2/media",
            headers={
                'Content-Disposition': f'attachment; filename="{nombre}"',
                'Content-Type': content_type,
            },
            data=img_res.content,
            auth=(WORDPRESS_USER, WORDPRESS_APP_PASSWORD),
            timeout=60
        )
        print(f"   Respuesta WordPress media: {r.status_code}")
        if r.status_code == 201:
            data = r.json()
            media_id = data['id']
            print(f"✅ Imagen subida OK — ID: {media_id}, URL: {data.get('source_url','')}")
            return media_id
        else:
            print(f"❌ Error subiendo imagen: {r.status_code}\n   {r.text[:400]}")
    except Exception as e:
        print(f"❌ Excepción subiendo imagen: {e}")
    return None

def publicar_wordpress(titulo, cuerpo, media_id=None):
    post = {
        'title': titulo,
        'content': cuerpo,
        'status': 'draft',
    }
    if media_id:
        post['featured_media'] = media_id
        print(f"🖼️  Asignando imagen destacada ID: {media_id}")
    else:
        print("ℹ️  Sin imagen destacada.")

    r = requests.post(
        f"{WORDPRESS_URL}/wp-json/wp/v2/posts",
        json=post,
        auth=(WORDPRESS_USER, WORDPRESS_APP_PASSWORD)
    )
    print(f"   Respuesta WordPress post: {r.status_code}")
    if r.status_code == 201:
        data = r.json()
        print(f"✅ Borrador creado: {titulo}")
        print(f"   ID post: {data['id']} — featured_media en respuesta: {data.get('featured_media', 'N/A')}")
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
        print(f"\n{'='*50}")
        print(f"Nota {i}: {tema['titulo_sugerido']}")
        print(f"Fuente: {tema.get('link','')}")
        print('='*50)

        # 1. Descargar artículo original
        og_image, texto_fuente = obtener_articulo_completo(tema['link'])

        if not texto_fuente:
            print("⚠️ No se pudo obtener el texto del artículo. Usando solo el título.")
            texto_fuente = tema.get('titulo_original', tema['titulo_sugerido'])

        # 2. Subir imagen
        media_id = None
        if og_image:
            media_id = subir_imagen_wordpress(og_image)

        # 3. Generar nota con el texto real
        texto_ia = generar_articulo(tema['titulo_sugerido'], texto_fuente)
        if not texto_ia:
            print("❌ Falló generación. Saltando.")
            continue

        cuerpo = texto_ia.replace('```html', '').replace('```', '').strip()

        # 4. Publicar
        publicar_wordpress(tema['titulo_sugerido'], cuerpo, media_id)
        time.sleep(3)

if __name__ == "__main__":
    main()
