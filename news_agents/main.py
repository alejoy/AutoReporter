#!/usr/bin/env python3
"""
AutoReporter — Orquestador principal.

Uso:
  python main.py             # Ejecuta todos los agentes habilitados
  python main.py --dry-run   # Simula sin publicar nada en WordPress
  python main.py --agents ClimaAgent HoroscopoAgent   # Sólo agentes específicos
"""

import sys
import time
import argparse

import config
from utils.logger import get_logger
from utils.wordpress_client import WordPressClient
from utils.duplicate_checker import DuplicateChecker

from agents.municipal_agent import MunicipalAgent
from agents.provincial_agent import ProvincialAgent
from agents.nacional_agent import NacionalAgent
from agents.sociedad_agent import SociedadAgent
from agents.horoscopo_agent import HoroscopoAgent
from agents.clima_agent import ClimaAgent

log = get_logger("Orchestrator")

ALL_AGENTS = {
    "MunicipalAgent":  MunicipalAgent,
    "ProvincialAgent": ProvincialAgent,
    "NacionalAgent":   NacionalAgent,
    "SociedadAgent":   SociedadAgent,
    "HoroscopoAgent":  HoroscopoAgent,
    "ClimaAgent":      ClimaAgent,
}


def parse_args():
    parser = argparse.ArgumentParser(description="AutoReporter — Orquestador de noticias")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Ejecuta sin publicar en WordPress. Muestra qué se publicaría.",
    )
    parser.add_argument(
        "--agents", nargs="+", metavar="AGENT",
        help="Nombres de agentes a ejecutar (ej: ClimaAgent HoroscopoAgent). "
             "Por defecto se ejecutan todos los habilitados en config.py.",
    )
    return parser.parse_args()


def validate_config() -> bool:
    ok = True
    if not config.WORDPRESS_URL:
        log.error("WORDPRESS_URL no configurada.")
        ok = False
    if not config.WORDPRESS_USER:
        log.error("WORDPRESS_USER no configurado.")
        ok = False
    if not config.WORDPRESS_APP_PASSWORD:
        log.error("WORDPRESS_APP_PASSWORD no configurada.")
        ok = False
    if not config.GEMINI_API_KEY:
        log.error("GEMINI_API_KEY no configurada.")
        ok = False
    return ok


def main():
    args = parse_args()
    dry_run = args.dry_run

    log.info("=" * 60)
    log.info(f"AutoReporter arrancando {'[DRY-RUN]' if dry_run else '[PUBLICACIÓN REAL]'}")
    log.info("=" * 60)

    if not validate_config():
        log.error("Configuración incompleta. Abortando.")
        sys.exit(1)

    # Inicializar WordPress client
    wp = WordPressClient(config.WORDPRESS_URL, config.WORDPRESS_USER, config.WORDPRESS_APP_PASSWORD)

    # Cargar categorías
    categories = wp.get_categories()
    if not categories:
        log.error("No se pudieron cargar las categorías de WordPress.")
        sys.exit(1)

    # Inicializar duplicate checker con los posts recientes de WP
    dup_checker = DuplicateChecker(threshold=config.DUPLICATE_SIMILARITY_THRESHOLD)
    recent_posts = wp.get_recent_posts(count=config.DUPLICATE_WP_CHECK_COUNT)
    dup_checker.load_from_wp(recent_posts)

    # Determinar agentes a ejecutar
    if args.agents:
        agents_to_run = {name: cls for name, cls in ALL_AGENTS.items() if name in args.agents}
        if not agents_to_run:
            log.error(f"Ningún agente válido en: {args.agents}. Opciones: {list(ALL_AGENTS.keys())}")
            sys.exit(1)
    else:
        agents_to_run = {name: cls for name, cls in ALL_AGENTS.items() if config.AGENTS_ENABLED.get(name)}

    log.info(f"Agentes a ejecutar: {list(agents_to_run.keys())}")

    # Resultados globales
    all_results: dict[str, list[dict]] = {}

    for agent_name, AgentClass in agents_to_run.items():
        log.info(f"\n{'─'*50}\nIniciando {agent_name}\n{'─'*50}")

        category_name = config.AGENT_CATEGORY_MAP.get(agent_name, "")
        category_id = categories.get(category_name)
        if not category_id:
            log.warning(f"Categoría '{category_name}' no encontrada en WP. Se publicará sin categoría.")

        try:
            agent = AgentClass()
            results = agent.run(wp, dup_checker, category_id, dry_run=dry_run)
            all_results[agent_name] = results
        except Exception as e:
            log.error(f"Error fatal en {agent_name}: {e}", exc_info=True)
            all_results[agent_name] = [{"title": "N/A", "status": "error", "reason": str(e)}]

        time.sleep(3)

    # Reporte final
    _print_report(all_results, dry_run)


def _print_report(all_results: dict, dry_run: bool):
    log.info("\n" + "=" * 60)
    log.info(f"REPORTE FINAL {'[DRY-RUN]' if dry_run else ''}")
    log.info("=" * 60)

    totals = {"published": 0, "skipped": 0, "error": 0, "dry_run": 0}

    for agent_name, results in all_results.items():
        log.info(f"\n{agent_name}:")
        for r in results:
            status = r.get("status", "?")
            emoji = {"published": "✅", "skipped": "⏭️", "error": "❌", "dry_run": "🔍"}.get(status, "?")
            log.info(f"  {emoji} [{status.upper()}] {r.get('title','')[:70]} — {r.get('reason','')}")
            totals[status] = totals.get(status, 0) + 1

    log.info(
        f"\nTOTAL → Publicadas: {totals['published']} | "
        f"Duplicadas (skip): {totals['skipped']} | "
        f"Errores: {totals['error']} | "
        f"Dry-run: {totals['dry_run']}"
    )


if __name__ == "__main__":
    main()
