"""
Suite de tests para AutoReporter.

Uso:
  cd news_agents
  python -m pytest tests/ -v
  python -m pytest tests/ -v -k "test_duplicate"   # test específico
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Asegurar que el directorio raíz de news_agents esté en el path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from utils.duplicate_checker import DuplicateChecker
from agents.municipal_agent import MunicipalAgent
from agents.provincial_agent import ProvincialAgent
from agents.nacional_agent import NacionalAgent
from agents.sociedad_agent import SociedadAgent
from agents.horoscopo_agent import HoroscopoAgent
from agents.clima_agent import ClimaAgent


# ====================================================================== #
#  UNIT TESTS                                                              #
# ====================================================================== #

class TestDuplicateDetection(unittest.TestCase):
    """Verifica que el sistema detecta duplicados correctamente."""

    def setUp(self):
        self.checker = DuplicateChecker(threshold=0.85)

    def test_no_duplicate_fresh(self):
        """Una nota nueva no debería ser duplicado."""
        result = self.checker.is_duplicate("Neuquén inaugura nueva plaza en el barrio Progreso")
        self.assertFalse(result, "Una nota nueva no debería marcarse como duplicado.")

    def test_exact_title_duplicate(self):
        """El mismo título exacto debe ser duplicado."""
        titulo = "El gobierno provincial anunció obras por 500 millones"
        self.checker.mark_published(titulo)
        self.assertTrue(self.checker.is_duplicate(titulo))

    def test_similar_title_duplicate(self):
        """Un título muy similar (>85%) debe ser duplicado."""
        original = "El gobierno provincial anunció importantes obras viales"
        similar = "El gobierno provincial anunció obras viales importantes"
        self.checker.mark_published(original)
        self.assertTrue(
            self.checker.is_duplicate(similar),
            "Títulos con ≥85% de similitud deben detectarse como duplicados."
        )

    def test_different_title_not_duplicate(self):
        """Un título completamente diferente no es duplicado."""
        self.checker.mark_published("Clima en Neuquén: máxima de 30°C")
        self.assertFalse(
            self.checker.is_duplicate("Escándalo en el Concejo Deliberante por votación de presupuesto")
        )

    def test_url_duplicate(self):
        """Misma URL fuente = duplicado aunque el título sea diferente."""
        url = "https://www.lmneuquen.com/neuquen/nota-ejemplo"
        self.checker.mark_published("Nota original", source_url=url)
        self.assertTrue(
            self.checker.is_duplicate("Nota con título diferente", source_url=url)
        )

    def test_load_from_wp(self):
        """Carga posts de WP y detecta duplicados contra ellos."""
        posts = [
            {"title": "Corte de agua en barrio Las Américas", "link": "https://wp.example.com/1"},
            {"title": "Horóscopo del día: Lunes 21 de Abril", "link": "https://wp.example.com/2"},
        ]
        self.checker.load_from_wp(posts)
        self.assertTrue(self.checker.is_duplicate("Corte de agua en barrio Las Américas"))
        self.assertFalse(self.checker.is_duplicate("Noticia completamente nueva sobre economía"))

    def test_below_threshold_not_duplicate(self):
        """Similitud por debajo del 85% no es duplicado."""
        self.checker.mark_published("Presupuesto provincial 2026 aprobado por la Legislatura")
        self.assertFalse(
            self.checker.is_duplicate("Semáforos inteligentes llegan a la ciudad de Neuquén")
        )


class TestCategoryMapping(unittest.TestCase):
    """Verifica que cada agente mapea a la categoría correcta."""

    def test_municipal_category(self):
        self.assertEqual(config.AGENT_CATEGORY_MAP["MunicipalAgent"], "MUNICIPALES")

    def test_provincial_category(self):
        self.assertEqual(config.AGENT_CATEGORY_MAP["ProvincialAgent"], "PROVINCIAL")

    def test_nacional_category(self):
        self.assertEqual(config.AGENT_CATEGORY_MAP["NacionalAgent"], "Nacional")

    def test_sociedad_category(self):
        self.assertEqual(config.AGENT_CATEGORY_MAP["SociedadAgent"], "SOCIEDAD")

    def test_horoscopo_category(self):
        self.assertEqual(config.AGENT_CATEGORY_MAP["HoroscopoAgent"], "Generales")

    def test_clima_category(self):
        self.assertEqual(config.AGENT_CATEGORY_MAP["ClimaAgent"], "Generales")

    def test_all_agents_have_category(self):
        """Todos los agentes deben tener una categoría asignada."""
        agent_names = ["MunicipalAgent", "ProvincialAgent", "NacionalAgent",
                       "SociedadAgent", "HoroscopoAgent", "ClimaAgent"]
        for name in agent_names:
            self.assertIn(name, config.AGENT_CATEGORY_MAP, f"{name} sin categoría en config.")


class TestWordPressConnection(unittest.TestCase):
    """Verifica credenciales y conexión a la API de WordPress."""

    def test_credentials_configured(self):
        """Las variables de entorno de WP deben estar configuradas."""
        self.assertTrue(config.WORDPRESS_URL, "WORDPRESS_URL no configurada.")
        self.assertTrue(config.WORDPRESS_USER, "WORDPRESS_USER no configurado.")
        self.assertTrue(config.WORDPRESS_APP_PASSWORD, "WORDPRESS_APP_PASSWORD no configurada.")

    @unittest.skipIf(not config.WORDPRESS_URL, "WP no configurado")
    def test_wp_api_reachable(self):
        """La API de WordPress debe responder correctamente."""
        import requests
        try:
            r = requests.get(
                f"{config.WORDPRESS_URL}/wp-json/wp/v2/categories",
                auth=(config.WORDPRESS_USER, config.WORDPRESS_APP_PASSWORD),
                timeout=10,
            )
            self.assertEqual(r.status_code, 200, f"API WP retornó {r.status_code}")
            cats = r.json()
            self.assertIsInstance(cats, list, "La respuesta de categorías debe ser una lista.")
            self.assertGreater(len(cats), 0, "Debe haber al menos una categoría en WP.")
        except Exception as e:
            self.fail(f"No se pudo conectar a WordPress: {e}")

    @unittest.skipIf(not config.WORDPRESS_URL, "WP no configurado")
    def test_required_categories_exist(self):
        """Las categorías requeridas deben existir en WordPress."""
        import requests
        required = {"MUNICIPALES", "PROVINCIAL", "Nacional", "SOCIEDAD", "Generales"}
        try:
            r = requests.get(
                f"{config.WORDPRESS_URL}/wp-json/wp/v2/categories",
                auth=(config.WORDPRESS_USER, config.WORDPRESS_APP_PASSWORD),
                params={"per_page": 100},
                timeout=10,
            )
            existing = {c["name"] for c in r.json()}
            missing = required - existing
            self.assertEqual(
                len(missing), 0,
                f"Categorías faltantes en WordPress: {missing}"
            )
        except Exception as e:
            self.fail(f"Error verificando categorías: {e}")


class TestAgentsDryRun(unittest.TestCase):
    """Ejecuta cada agente en dry-run y verifica que devuelve contenido válido."""

    def _make_mocks(self):
        wp = MagicMock()
        wp.get_categories.return_value = {
            "MUNICIPALES": 1, "PROVINCIAL": 2, "Nacional": 3,
            "SOCIEDAD": 4, "Generales": 5,
        }
        wp.get_recent_posts.return_value = []
        dup = DuplicateChecker()
        return wp, dup

    def _run_agent_dry(self, AgentClass):
        wp, dup = self._make_mocks()
        agent = AgentClass()
        results = agent.run(wp, dup, category_id=1, dry_run=True)
        return results

    @unittest.skipIf(not config.GEMINI_API_KEY, "GEMINI_API_KEY no configurada")
    def test_municipal_dry_run(self):
        results = self._run_agent_dry(MunicipalAgent)
        self.assertIsInstance(results, list)
        for r in results:
            self.assertIn(r["status"], ["dry_run", "skipped", "error"])

    @unittest.skipIf(not config.GEMINI_API_KEY, "GEMINI_API_KEY no configurada")
    def test_provincial_dry_run(self):
        results = self._run_agent_dry(ProvincialAgent)
        self.assertIsInstance(results, list)

    @unittest.skipIf(not config.GEMINI_API_KEY, "GEMINI_API_KEY no configurada")
    def test_nacional_dry_run(self):
        results = self._run_agent_dry(NacionalAgent)
        self.assertIsInstance(results, list)

    @unittest.skipIf(not config.GEMINI_API_KEY, "GEMINI_API_KEY no configurada")
    def test_sociedad_dry_run(self):
        results = self._run_agent_dry(SociedadAgent)
        self.assertIsInstance(results, list)

    @unittest.skipIf(not config.GEMINI_API_KEY, "GEMINI_API_KEY no configurada")
    def test_horoscopo_dry_run(self):
        results = self._run_agent_dry(HoroscopoAgent)
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) > 0)

    @unittest.skipIf(not config.GEMINI_API_KEY, "GEMINI_API_KEY no configurada")
    def test_clima_dry_run(self):
        results = self._run_agent_dry(ClimaAgent)
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) > 0)


# ====================================================================== #
#  INTEGRATION TEST                                                        #
# ====================================================================== #

class TestFullPipeline(unittest.TestCase):
    """Corre el orquestador completo en dry-run y reporta qué haría."""

    @unittest.skipIf(not config.GEMINI_API_KEY, "GEMINI_API_KEY no configurada")
    def test_full_pipeline_dry_run(self):
        """
        Ejecuta todos los agentes en dry-run.
        Verifica que no haya errores fatales y que el resultado sea coherente.
        """
        from utils.wordpress_client import WordPressClient
        from utils.duplicate_checker import DuplicateChecker

        # Usamos WP real para categorías pero no publicamos nada
        wp = WordPressClient(config.WORDPRESS_URL, config.WORDPRESS_USER, config.WORDPRESS_APP_PASSWORD)
        categories = wp.get_categories()

        dup = DuplicateChecker()
        if config.WORDPRESS_URL:
            recent = wp.get_recent_posts(count=50)
            dup.load_from_wp(recent)

        all_agents = [
            MunicipalAgent(), ProvincialAgent(), NacionalAgent(),
            SociedadAgent(), HoroscopoAgent(), ClimaAgent(),
        ]

        total_new = 0
        total_dup = 0
        total_err = 0

        print("\n" + "=" * 60)
        print("REPORTE DE INTEGRACIÓN — DRY RUN")
        print("=" * 60)

        for agent in all_agents:
            cat_name = config.AGENT_CATEGORY_MAP.get(agent.name, "")
            cat_id = categories.get(cat_name)
            results = agent.run(wp, dup, cat_id, dry_run=True)

            for r in results:
                s = r.get("status")
                if s == "dry_run":
                    total_new += 1
                    print(f"  ✅ [{agent.name}] NUEVA: {r['title'][:60]}")
                elif s == "skipped":
                    total_dup += 1
                    print(f"  ⏭️  [{agent.name}] DUP:  {r['title'][:60]}")
                else:
                    total_err += 1
                    print(f"  ❌ [{agent.name}] ERROR: {r.get('reason','')}")

        print(f"\nNuevas: {total_new} | Duplicadas: {total_dup} | Errores: {total_err}")

        # Al menos algún agente debe poder generar contenido
        self.assertGreater(total_new + total_dup, 0, "Ningún agente generó resultados.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
