import config
from agents.base_agent import BaseNewsAgent


class SociedadAgent(BaseNewsAgent):
    CATEGORY_NAME = "SOCIEDAD"
    RSS_FEEDS = config.RSS_FEEDS["SociedadAgent"]
    SELECTION_CONTEXT = (
        "Elegí los 2 más relevantes en cuanto a interés humano y social: historias de personas, comunidad, educación, salud, cultura o fenómenos sociales. Descartá política pura y deportes."
    )
    WRITING_CONTEXT = "Sos un redactor periodístico para un portal de noticias de interés social y humano."
