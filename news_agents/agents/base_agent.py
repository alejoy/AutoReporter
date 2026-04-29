import re
import time
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from abc import ABC, abstractmethod
from html import unescape as html_unescape

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

        # Validar que Gemini generó una nota real y no un mensaje de rechazo
        if self._es_rechazo_ia(html_nota):
            self.log.warning(f"SKIP — IA no pudo generar nota válida: {titulo[:60]}")
            return {"title": titulo, "status": "error", "reason": "contenido fuente inválido (IA rechazó)"}

        if dry_run:
            extracto = re.sub(r"<[^>]+>", "", html_nota)[:200]
            tiene_imagen = "✓ imagen" if og_image else "✗ sin imagen"
            self.log.info(f"[DRY-RUN] {tiene_imagen} | Título: {titulo}\nExtracto: {extracto}...")
            return {"title": titulo, "status": "dry_run", "reason": "modo dry-run"}

        # Imagen destacada — obligatoria
        if not og_image:
            self.log.warning(f"SKIP — sin imagen destacada: {titulo[:60]}")
            return {"title": titulo, "status": "error", "reason": "sin imagen destacada en el artículo fuente"}

        media_id = None
        if wp_client:
            media_id = wp_client.upload_media(og_image)
        if not media_id:
            self.log.warning(f"SKIP — no se pudo subir la imagen: {titulo[:60]}")
            return {"title": titulo, "status": "error", "reason": "fallo al subir imagen destacada"}

        # Publicar
        if wp_client:
            post = wp_client.create_post(
                title=titulo,
                content=html_nota,
                category_id=category_id,
                featured_media=media_id,
                status="publish",
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
        required_kw = config.RSS_REQUIRED_KEYWORDS.get(self.name)  # list or None
        skip_kw = config.RSS_SKIP_KEYWORDS  # artículos dinámicos/en vivo

        for url in self.RSS_FEEDS:
            try:
                self.log.info(f"RSS: {url}")
                res = requests.get(url, headers=headers, timeout=10)
                res.raise_for_status()
                root = ET.fromstring(res.content)
                for item in root.findall(".//item")[:6]:
                    titulo = item.findtext("title", "").strip()
                    link = item.findtext("link", "").strip()
                    if not titulo or len(titulo) <= 10 or not link:
                        continue
                    titulo_lower = titulo.lower()
                    # Excluir artículos de cobertura dinámica (minuto a minuto, en vivo)
                    if any(kw in titulo_lower for kw in skip_kw):
                        self.log.debug(f"Filtrado (contenido dinámico): {titulo[:60]}")
                        continue
                    # Filtro geográfico por agente
                    if required_kw and not any(kw in titulo_lower for kw in required_kw):
                        self.log.debug(f"Filtrado (no es Neuquén): {titulo[:60]}")
                        continue
                    noticias.append({"titulo": titulo, "link": link})
            except Exception as e:
                self.log.warning(f"Error en {url}: {e}")
            time.sleep(0.4)
        self.log.info(f"{len(noticias)} noticias obtenidas (filtradas).")
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

            # og:image — decodificar entidades HTML (&amp; → &, etc.)
            for patron in [
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            ]:
                m = re.search(patron, html, re.IGNORECASE)
                if m:
                    candidate = html_unescape(m.group(1))
                    if candidate.startswith("http"):
                        og_image = candidate
                        self.log.info(f"og:image: {og_image}")
                        break

            if not og_image:
                self.log.warning("Sin og:image en el artículo.")

            # Texto del artículo — solo párrafos con contenido periodístico real
            parrafos = re.findall(r"<p[^>]*>(.*?)</p>", html, re.DOTALL | re.IGNORECASE)
            limpios = [self._strip_html(p) for p in parrafos]
            limpios = [t for t in limpios if self._es_parrafo_noticia(t)]
            texto = "\n\n".join(limpios[:20])
            if texto:
                self.log.info(f"Texto extraído: {len(texto)} caracteres ({len(limpios)} párrafos).")
            else:
                self.log.warning("Texto extraído vacío o solo código — posible artículo dinámico.")

        except Exception as e:
            self.log.warning(f"Error descargando artículo {url}: {e}")

        return og_image, texto

    # ------------------------------------------------------------------ #
    #  Selección de temas con Gemini                                        #
    # ------------------------------------------------------------------ #
    def _select_topics(self, noticias: list[dict], fecha_hoy: str) -> list[dict] | None:
        max_topics = config.AGENT_MAX_TOPICS.get(self.name, 2)
        titulares = "\n".join([f"{i}. {n['titulo']}" for i, n in enumerate(noticias)])
        prompt = f"""Titulares del {fecha_hoy}:

{titulares}

{self.SELECTION_CONTEXT}

Seleccioná como máximo {max_topics} titulares. Respondé SOLO con JSON válido, sin texto adicional:
[
  {{"indice": 0, "titulo_sugerido": "Título periodístico"}},
  {{"indice": 1, "titulo_sugerido": "..."}}
]"""
        respuesta = self._call_gemini(prompt, max_tokens=300)
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

    @staticmethod
    def _es_parrafo_noticia(texto: str) -> bool:
        """Devuelve True si el texto parece prosa periodística, no código CSS/JS."""
        if len(texto) < 60:
            return False
        # Rechazar párrafos con alta densidad de caracteres de código
        code_chars = texto.count("{") + texto.count("}") + texto.count(";")
        if code_chars / max(len(texto), 1) > 0.02:
            return False
        # Rechazar si tiene poca proporción de letras (código tiene muchos símbolos)
        alpha = sum(c.isalpha() or c.isspace() for c in texto) / len(texto)
        return alpha > 0.65

    # Frases que indican que Gemini no pudo generar una nota real
    _REFUSAL_SIGNALS = (
        "no es posible redactar",
        "no es posible generar",
        "no puedo redactar",
        "no puedo generar",
        "definiciones de propiedades css",
        "propiedades css",
        "sin contenido periodístico",
        "no contiene información periodística",
        "el texto fuente no contiene",
        "texto fuente consiste en",
        "texto fuente proporcionado consiste",
        "no hay hechos",
        "no se puede redactar",
    )

    @classmethod
    def _es_rechazo_ia(cls, html_nota: str) -> bool:
        """Devuelve True si Gemini devolvió un mensaje de rechazo en lugar de una nota."""
        texto_plano = re.sub(r"<[^>]+>", "", html_nota).lower()
        return any(signal in texto_plano for signal in cls._REFUSAL_SIGNALS)
