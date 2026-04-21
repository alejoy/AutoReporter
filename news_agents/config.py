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
        "https://www.lmneuquen.com/rss/neuquen.xml",
        "https://www.rionegro.com.ar/feed/",
        "https://www.lmneuquen.com/rss/ultimas-noticias.xml",
    ],
    "MunicipalAgent": [
        "https://www.lmneuquen.com/rss/ultimas-noticias.xml",
        "https://www.lmneuquen.com/rss/home.xml",
        "https://www.rionegro.com.ar/feed/",
    ],
    "SociedadAgent": [
        "https://www.perfil.com/feed",
        "https://www.lmneuquen.com/rss/ultimas-noticias.xml",
        "https://www.rionegro.com.ar/feed/",
    ],
}

# --- Prompts por agente (contexto para selección y redacción) ---
AGENT_PROMPTS = {
    "NacionalAgent": {
        "seleccion": "Elegí los 2 más importantes del día para los argentinos. Priorizá política nacional, economía, justicia o seguridad. Descartá farándula y deportes si hay temas más relevantes.",
        "redaccion": "Sos un redactor periodístico para un portal de noticias de Argentina.",
    },
    "ProvincialAgent": {
        "seleccion": "Elegí los 2 más relevantes para los neuquinos. Priorizá política provincial, economía, obras, salud o seguridad.",
        "redaccion": "Sos un redactor periodístico para un portal de noticias de la provincia de Neuquén, Argentina.",
    },
    "MunicipalAgent": {
        "seleccion": "Elegí los 2 más relevantes para los vecinos de la ciudad de Neuquén capital. Priorizá servicios municipales, obras, transporte, seguridad o economía local.",
        "redaccion": "Sos un redactor periodístico para un portal de noticias de la ciudad de Neuquén capital.",
    },
    "SociedadAgent": {
        "seleccion": "Elegí los 2 más relevantes en cuanto a interés humano y social: historias de personas, comunidad, educación, salud, cultura o fenómenos sociales. Descartá política pura y deportes.",
        "redaccion": "Sos un redactor periodístico para un portal de noticias de interés social y humano.",
    },
}
