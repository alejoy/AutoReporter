import re
import time
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from abc import ABC, abstractmethod

import config
from utils.logger import get_logger

NS_MEDIA = "http://search.yahoo.com/mrss/"
NS_CONTENT = "http://purl.org/rss/1.0/modules/content/"

DIAS_SEMANA = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo",
}
MESES = {
    "January": "Enero", "February": "Febrero", "March": "Marzo", "April": "Abril",
    "May": "Mayo", "June": "Junio", "July": "Julio", "August": "Agosto",
    "September": "Septiembre", "October": "Octubre", "November": "Noviembre", "December": "Diciembre",
}

PROMPT_REDACCION = """Basándote EXCLUSIVAMENTE en el texto fuente que te doy, redactá una nota periodística.
No inventes datos, cifras, nombres ni hechos que no estén en el texto fuente.
Si el texto fuente tiene citas textuales, podés usarlas con el nombre y cargo de quien habla.

TEXTO FUENTE:
\"\"\"
{texto_fuente}
\"\"\"

TÍTULO PARA LA NOTA: {titulo}

{contexto_redactor}

REGLAS DE ESTILO:
- Pirámide invertida: el dato más importante primero
- Párrafos de 3 a 5 líneas, fluidos y bien conectados
- Usá <strong> para nombres propios, cifras y términos clave la primera vez que aparecen
- Tono informativo y neutro
- PROHIBIDO: "es importante destacar", "vale la pena mencionar", "desde una perspectiva",
  "cabe señalar", "en conclusión", "en este contexto", "resulta relevante", "sin lugar a dudas"
- NO escribas la fecha al inicio
- NO uses <h2> ni <h3>, solo párrafos

FORMATO:
- Empezá DIRECTO con <p>. Sin título ni encabezado.
- Solo etiquetas <p> y <strong>
- 4 a 5 párrafos
- Solo HTML, sin markdown ni bloques de código
- Español rioplatense"""


class BaseNewsAgent(ABC):
    """Clase base para todos los agentes de noticias RSS."""

    CATEGORY_NAME: str = ""
    RSS_FEEDS: list[str] = []
    SELECTION_CONTEXT: str = ""
    WRITING_CONTEXT: str = ""

    def __init__(self):
        self.name = self.__class__.__name__
        self.log = get_logger(self.name)

    # ------------------------------------------------------------------ #
    #  Método principal                                                     #
    # ------------------------------------------------------------------ #
    def run(self, wp_client, dup_checker, category_id: int | None, dry_run: bool = False) -> list[dict]:
        """
        Ejecuta el agente completo.
        Devuelve lista de resultados: [{title, status, reason}]
        """
        fecha_hoy = self._fecha_hoy()
        self.log.info(f"=== {self.name} — {fecha_hoy} ===")
        results = []

        noticias = self._fetch_rss()
        if not noticias:
            self.log.warning("Sin noticias disponibles.")
            return results

        temas = self._select_topics(noticias, fecha_hoy)
        if not temas:
            self.log.warning("No se pudieron seleccionar temas.")
            return results

        for tema in temas:
            result = self._process_topic(tema, fecha_hoy, wp_client, dup_checker, category_id, dry_run)
            results.append(result)
            time.sleep(2)

        return results

    def _process_topic(self, tema, fecha_hoy, wp_client, dup_checker, category_id, dry_run) -> dict:
        titulo = tema.get("titulo_sugerido", "Sin título")
        link = tema.get("link", "")
        self.log.info(f"Procesando: {titulo[:70]}")

        # Duplicate check
        if dup_checker and dup_checker.is_duplicate(titulo, link):
            self.log.info(f"SKIP — duplicado.")
            return {"title": titulo, "status": "skipped", "reason": "duplicado"}

        # Obtener artículo fuente
        og_image, texto_fuente = self._fetch_article(link)
        if not texto_fuente:
            self.log.warning("Sin texto fuente — usando solo el título.")
            texto_fuente = titulo

        # Generar nota
        html_nota = self._generate_article(titulo, texto_fuente)
        if not html_nota:
            return {"title": titulo, "status": "error", "reason": "fallo generación IA"}

        html_nota = html_nota.replace("```html", "").replace("```", "").strip()

        if dry_run:
            extracto = re.sub(r"<[^>]+>", "", html_nota)[:200]
            self.log.info(f"[DRY-RUN] Título: {titulo}\nExtracto: {extracto}...")
            return {"title": titulo, "status": "dry_run", "reason": "modo dry-run"}

        # Subir imagen
        media_id = None
        if og_image and wp_client:
            media_id = wp_client.upload_media(og_image)

        # Publicar
        if wp_client:
            post = wp_client.create_post(
                title=titulo,
                content=html_nota,
                category_id=category_id,
                featured_media=media_id,
                status="draft",
            )
            if post:
                if dup_checker:
                    dup_checker.mark_published(titulo, link)
                return {"title": titulo, "status": "published", "reason": f"post_id={post['id']}"}
            return {"title": titulo, "status": "error", "reason": "fallo publicación WP"}

        return {"title": titulo, "status": "error", "reason": "sin wp_client"}

    # ------------------------------------------------------------------ #
    #  RSS                                                                  #
    # ------------------------------------------------------------------ #
    def _fetch_rss(self) -> list[dict]:
        noticias = []
        headers = {"User-Agent": "Mozilla/5.0 (AutoReporter/2.0)"}
        for url in self.RSS_FEEDS:
            try:
                self.log.info(f"RSS: {url}")
                res = requests.get(url, headers=headers, timeout=10)
                res.raise_for_status()
                root = ET.fromstring(res.content)
                for item in root.findall(".//item")[:6]:
                    titulo = item.findtext("title", "").strip()
                    link = item.findtext("link", "").strip()
                    if titulo and len(titulo) > 10 and link:
                        noticias.append({"titulo": titulo, "link": link})
            except Exception as e:
                self.log.warning(f"Error en {url}: {e}")
            time.sleep(0.4)
        self.log.info(f"{len(noticias)} noticias obtenidas.")
        return noticias[:15]

    # ------------------------------------------------------------------ #
    #  Artículo fuente (og:image + texto)                                   #
    # ------------------------------------------------------------------ #
    def _fetch_article(self, url: str) -> tuple[str | None, str]:
        og_image = None
        texto = ""
        if not url:
            return og_image, texto
        try:
            headers = {"User-Agent": "Mozilla/5.0 (AutoReporter/2.0)"}
            res = requests.get(url, headers=headers, timeout=12)
            res.raise_for_status()
            html = res.text

            # og:image
            for patron in [
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            ]:
                m = re.search(patron, html, re.IGNORECASE)
                if m and m.group(1).startswith("http"):
                    og_image = m.group(1)
                    self.log.info(f"og:image: {og_image}")
                    break

            if not og_image:
                self.log.warning("Sin og:image en el artículo.")

            # Texto del artículo
            parrafos = re.findall(r"<p[^>]*>(.*?)</p>", html, re.DOTALL | re.IGNORECASE)
            limpios = [self._strip_html(p) for p in parrafos]
            limpios = [t for t in limpios if len(t) > 60]
            texto = "\n\n".join(limpios[:20])
            self.log.info(f"Texto extraído: {len(texto)} caracteres.")

        except Exception as e:
            self.log.warning(f"Error descargando artículo {url}: {e}")

        return og_image, texto

    # ------------------------------------------------------------------ #
    #  Selección de temas con Gemini                                        #
    # ------------------------------------------------------------------ #
    def _select_topics(self, noticias: list[dict], fecha_hoy: str) -> list[dict] | None:
        titulares = "\n".join([f"{i}. {n['titulo']}" for i, n in enumerate(noticias)])
        prompt = f"""Titulares del {fecha_hoy}:

{titulares}

{self.SELECTION_CONTEXT}

Respondé SOLO con JSON válido, sin texto adicional:
[
  {{"indice": 0, "titulo_sugerido": "Título periodístico"}},
  {{"indice": 1, "titulo_sugerido": "..."}}
]"""
        respuesta = self._call_gemini(prompt, max_tokens=200)
        if not respuesta:
            return None
        try:
            respuesta = re.sub(r"```(?:json)?", "", respuesta).strip()
            seleccion = json.loads(respuesta)
            if not isinstance(seleccion, list):
                return None
            for tema in seleccion:
                idx = tema.get("indice", 0)
                if 0 <= idx < len(noticias):
                    tema["link"] = noticias[idx]["link"]
                    tema["titulo_original"] = noticias[idx]["titulo"]
                else:
                    tema["link"] = ""
                    tema["titulo_original"] = ""
            return seleccion
        except Exception as e:
            self.log.warning(f"Error parseando JSON de temas: {e}\n{respuesta[:200]}")
            return None

    # ------------------------------------------------------------------ #
    #  Generación de artículo con Gemini                                    #
    # ------------------------------------------------------------------ #
    def _generate_article(self, titulo: str, texto_fuente: str) -> str | None:
        prompt = PROMPT_REDACCION.format(
            texto_fuente=texto_fuente[:3000],
            titulo=titulo,
            contexto_redactor=self.WRITING_CONTEXT,
        )
        return self._call_gemini(prompt, max_tokens=1500)

    # ------------------------------------------------------------------ #
    #  Gemini con fallback de modelos y retry                               #
    # ------------------------------------------------------------------ #
    def _call_gemini(self, prompt: str, max_tokens: int = 1500) -> str | None:
        headers = {"Content-Type": "application/json"}
        for modelo in config.GEMINI_MODELS:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{modelo}:generateContent?key={config.GEMINI_API_KEY}"
            )
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": config.GEMINI_TEMPERATURE,
                    "maxOutputTokens": max_tokens,
                },
            }
            for attempt in range(3):
                try:
                    self.log.info(f"Gemini [{modelo}] intento {attempt+1}...")
                    res = requests.post(url, headers=headers, json=payload, timeout=30)
                    if res.status_code == 200:
                        return res.json()["candidates"][0]["content"]["parts"][0]["text"]
                    self.log.warning(f"Gemini HTTP {res.status_code}")
                    break  # no reintentar el mismo modelo si el error es 4xx
                except Exception as e:
                    self.log.warning(f"Gemini error intento {attempt+1}: {e}")
                    time.sleep(2 ** attempt)
        return None

    # ------------------------------------------------------------------ #
    #  Helpers                                                              #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _fecha_hoy() -> str:
        now = datetime.now()
        dia = DIAS_SEMANA.get(now.strftime("%A"), now.strftime("%A"))
        mes = MESES.get(now.strftime("%B"), now.strftime("%B"))
        return f"{dia} {now.strftime('%d')} de {mes} de {now.strftime('%Y')}"

    @staticmethod
    def _strip_html(texto: str) -> str:
        texto = re.sub(r"<[^>]+>", "", texto or "")
        return re.sub(r"\s+", " ", texto).strip()
