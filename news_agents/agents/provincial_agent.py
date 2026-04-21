import config
from agents.base_agent import BaseNewsAgent


class ProvincialAgent(BaseNewsAgent):
    CATEGORY_NAME = "PROVINCIAL"
    RSS_FEEDS = config.RSS_FEEDS["ProvincialAgent"]
    SELECTION_CONTEXT = (
        "Elegí los 2 más relevantes para los neuquinos. Priorizá política provincial, economía, obras, salud o seguridad."
    )
    WRITING_CONTEXT = "Sos un redactor periodístico para un portal de noticias de la provincia de Neuquén, Argentina."
