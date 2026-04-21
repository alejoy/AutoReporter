import config
from agents.base_agent import BaseNewsAgent


class NacionalAgent(BaseNewsAgent):
    CATEGORY_NAME = "Nacional"
    RSS_FEEDS = config.RSS_FEEDS["NacionalAgent"]
    SELECTION_CONTEXT = (
        "Elegí los 2 más importantes del día para los argentinos. Priorizá política nacional, economía, justicia o seguridad. Descartá farándula y deportes si hay temas más relevantes."
    )
    WRITING_CONTEXT = "Sos un redactor periodístico para un portal de noticias de Argentina."
