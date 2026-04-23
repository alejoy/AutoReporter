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
    "ProvincialAgent": "PROVINCIAL",
    "NacionalAgent":   "Nacional",
    "SociedadAgent":   "SOCIEDAD",
    "HoroscopoAgent":  "Generales",
    "ClimaAgent":      "Generales",
}

# --- RSS por agente ---
RSS_FEEDS = {
    "NacionalAgent": [
        "https://www.lanacion.com.ar/arc/outboundfeeds/rss/",
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
        # Últimas noticias y home de LM Neuquén (más enfocado en ciudad)
        "https://www.lmneuquen.com/rss/ultimas-noticias.xml",
        "https://www.lmneuquen.com/rss/home.xml",
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
    "SociedadAgent":   ["neuquén", "neuquen", "neuquino", "neuquina"],
    "NacionalAgent":   None,  # noticias nacionales: sin filtro geográfico
}

# --- Prompts por agente (contexto para selección y redacción) ---
AGENT_PROMPTS = {
    "NacionalAgent": {
        "seleccion": "Elegí los 2 más importantes del día para los argentinos. Priorizá política nacional, economía, justicia o seguridad. Descartá farándula y deportes si hay temas más relevantes.",
        "redaccion": "Sos un redactor periodístico para un portal de noticias de Argentina.",
    },
    "ProvincialAgent": {
        "seleccion": (
            "Elegí los 2 más relevantes EXCLUSIVAMENTE sobre la provincia de Neuquén: "
            "política provincial, economía, obras, salud o seguridad. "
            "DESCARTÁ cualquier noticia de Río Negro, Chubut, Bariloche, Cipolletti o cualquier otra provincia. "
            "Si no hay noticias claras de Neuquén, devolvé una lista vacía []."
        ),
        "redaccion": "Sos un redactor periodístico para un portal de noticias de la provincia de Neuquén, Argentina.",
    },
    "MunicipalAgent": {
        "seleccion": (
            "Elegí los 2 más relevantes EXCLUSIVAMENTE sobre la ciudad de Neuquén capital: "
            "servicios municipales, obras, transporte, seguridad o economía local. "
            "DESCARTÁ cualquier noticia de otras ciudades o provincias (Río Negro, Chubut, Bariloche, Cipolletti, etc.). "
            "Si no hay noticias claras de la ciudad de Neuquén capital, devolvé una lista vacía []."
        ),
        "redaccion": "Sos un redactor periodístico para un portal de noticias de la ciudad de Neuquén capital.",
    },
    "SociedadAgent": {
        "seleccion": (
            "Elegí los 2 más relevantes en cuanto a interés humano y social en Neuquén: "
            "historias de personas, comunidad, educación, salud, cultura o fenómenos sociales. "
            "Priorizá noticias de Neuquén provincia o capital. "
            "Descartá política pura, deportes y noticias que no mencionen Neuquén."
        ),
        "redaccion": "Sos un redactor periodístico para un portal de noticias de interés social y humano de Neuquén.",
    },
}
