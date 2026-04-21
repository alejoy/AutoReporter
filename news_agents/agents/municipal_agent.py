import config
from agents.base_agent import BaseNewsAgent


class MunicipalAgent(BaseNewsAgent):
    CATEGORY_NAME = "MUNICIPALES"
    RSS_FEEDS = config.RSS_FEEDS["MunicipalAgent"]
    SELECTION_CONTEXT = (
        "Elegí los 2 más relevantes para los vecinos de la ciudad de Neuquén capital. Priorizá servicios municipales, obras, transporte, seguridad o economía local."
    )
    WRITING_CONTEXT = "Sos un redactor periodístico para un portal de noticias de la ciudad de Neuquén capital."
