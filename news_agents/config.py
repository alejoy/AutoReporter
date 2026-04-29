import os

# --- WordPress ---
WORDPRESS_URL = os.environ.get("WORDPRESS_URL", "").rstrip("/")
WORDPRESS_USER = os.environ.get("WORDPRESS_USER", "")
WORDPRESS_APP_PASSWORD = os.environ.get("WORDPRESS_APP_PASSWORD", "")

# --- Gemini ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-1.5-flash"]
GEMINI_TEMPERATURE = 0.5

# --- Duplicate detection ---
DUPLICATE_SIMILARITY_THRESHOLD = 0.85
DUPLICATE_WP_CHECK_COUNT = 100   # últimos N posts de WP a revisar

# --- Agentes habilitados (True/False para activar/desactivar) ---
AGENTS_ENABLED = {
    "MunicipalAgent":  True,
    "ProvincialAgent": True,
    "NacionalAgent":   True,
    "SociedadAgent":   True,
    "HoroscopoAgent":  True,
    "ClimaAgent":      True,
}

# --- Categorías WordPress (nombre exacto → ID se obtiene de la API al arrancar) ---
AGENT_CATEGORY_MAP = {
    "MunicipalAgent":  "MUNICIPALES",
    "ProvincialAgent": "PROVINCIA",
    "NacionalAgent":   "Nacional",
    "SociedadAgent":   "SOCIEDAD",
    "HoroscopoAgent":  "Generales",
    "ClimaAgent":      "Generales",
}

# --- RSS por agente ---
RSS_FEEDS = {
    "NacionalAgent": [
        "https://www.lanacion.com.ar/arc/outboundfeeds/rss/",
        "https://www.infobae.com/feeds/rss/",
        "https://www.perfil.com/feed",
        "https://www.lmneuquen.com/rss/pais.xml",
    ],
    "ProvincialAgent": [
        # Sección provincial de LM Neuquén (política provincial, gobernación, legislatura)
        "https://www.lmneuquen.com/rss/neuquen.xml",
        # Río Negro cubre Neuquén provincia — filtrado por keyword
        "https://www.rionegro.com.ar/feed/",
    ],
    "MunicipalAgent": [
        "https://www.lmneuquen.com/rss/ultimas-noticias.xml",
        "https://www.lmneuquen.com/rss/neuquen.xml",
        # Río Negro cubre Neuquén capital — keyword filter activo
        "https://www.rionegro.com.ar/feed/",
    ],
    "SociedadAgent": [
        "https://www.perfil.com/feed",
        "https://www.lmneuquen.com/rss/ultimas-noticias.xml",
    ],
}

# --- Filtro de palabras clave por agente (None = sin filtro) ---
# Si está definido, solo pasan los titulares que contengan al menos una de las palabras.
RSS_REQUIRED_KEYWORDS = {
    "ProvincialAgent": ["neuquén", "neuquen", "neuquino", "neuquina"],
    "MunicipalAgent":  ["neuquén", "neuquen", "neuquino", "neuquina"],
    "SociedadAgent":   None,  # Sociedad acepta también interés humano nacional
    "NacionalAgent":   None,
}

# --- Candidatos máximos por agente (cuántos temas selecciona Gemini por ejecución) ---
AGENT_MAX_TOPICS = {
    "MunicipalAgent":  3,
    "ProvincialAgent": 3,
    "NacionalAgent":   3,
    "SociedadAgent":   2,
}

# Frase antispam que se inyecta en todos los prompts de selección
_ANTISPAM = (
    "DESCARTÁ siempre: contenido claramente publicitario, notas de prensa de marcas "
    "comerciales, gacetillas institucionales o artículos patrocinados. "
    "Elegí temas DISTINTOS entre sí: si varios titulares tratan el mismo evento o fenómeno "
    "(aunque desde ángulos diferentes), contá solo como uno y elegí el más completo."
)

# --- Prompts por agente (contexto para selección y redacción) ---
AGENT_PROMPTS = {
    "NacionalAgent": {
        "seleccion": (
            f"Elegí los 3 más importantes del día para los argentinos. "
            "Priorizá política nacional, economía, justicia o seguridad. "
            f"Descartá farándula y deportes si hay temas más relevantes. {_ANTISPAM}"
        ),
        "redaccion": "Sos un redactor periodístico para un portal de noticias de Argentina.",
    },
    "ProvincialAgent": {
        "seleccion": (
            "Elegí los 3 más relevantes EXCLUSIVAMENTE sobre la provincia de Neuquén: "
            "política provincial, economía, obras, salud o seguridad. "
            "DESCARTÁ cualquier noticia de Río Negro, Chubut, Bariloche, Cipolletti o cualquier otra provincia. "
            f"Si no hay 3 noticias claras de Neuquén, devolvé las que haya (puede ser menos). {_ANTISPAM}"
        ),
        "redaccion": "Sos un redactor periodístico para un portal de noticias de la provincia de Neuquén, Argentina.",
    },
    "MunicipalAgent": {
        "seleccion": (
            "Elegí los 3 más relevantes EXCLUSIVAMENTE sobre la ciudad de Neuquén capital: "
            "servicios municipales, obras, transporte, seguridad o economía local. "
            "DESCARTÁ cualquier noticia de otras ciudades o provincias (Río Negro, Chubut, Bariloche, Cipolletti, etc.). "
            f"Si no hay 3 noticias claras de la ciudad de Neuquén capital, devolvé las que haya. {_ANTISPAM}"
        ),
        "redaccion": "Sos un redactor periodístico para un portal de noticias de la ciudad de Neuquén capital.",
    },
    "SociedadAgent": {
        "seleccion": (
            "Elegí los 2 más relevantes de interés humano y social: "
            "historias de personas, comunidad, educación, salud, cultura o fenómenos sociales. "
            "Priorizá noticias de Neuquén, pero si no hay suficientes también podés incluir "
            f"historias nacionales de alto impacto social. Descartá política pura y deportes. {_ANTISPAM}"
        ),
        "redaccion": "Sos un redactor periodístico para un portal de noticias de interés social y humano de Neuquén.",
    },
}
