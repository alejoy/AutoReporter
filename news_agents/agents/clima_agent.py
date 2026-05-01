import json
import re
import time
import requests

import config
from utils.logger import get_logger

LAT, LON = -38.9516, -68.0591  # Neuquén Capital

DIAS_SEMANA = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo",
}
MESES = {
    "January": "Enero", "February": "Febrero", "March": "Marzo", "April": "Abril",
    "May": "Mayo", "June": "Junio", "July": "Julio", "August": "Agosto",
    "September": "Septiembre", "October": "Octubre", "November": "Noviembre", "December": "Diciembre",
}
WMO_MAP = {
    0: ("Despejado", "☀️"), 1: ("Mayormente despejado", "🌤️"), 2: ("Parcialmente nublado", "⛅"),
    3: ("Nublado", "☁️"), 45: ("Niebla", "🌫️"), 48: ("Niebla con escarcha", "🌫️"),
    51: ("Llovizna leve", "🌦️"), 61: ("Lluvia leve", "🌧️"), 63: ("Lluvia moderada", "🌧️"),
    65: ("Lluvia fuerte", "🌧️"), 80: ("Chubascos", "🌦️"), 81: ("Chubascos moderados", "🌦️"),
    95: ("Tormenta", "⛈️"), 96: ("Tormenta con granizo", "⛈️"), 99: ("Tormenta severa", "⛈️"),
}


class ClimaAgent:
    CATEGORY_NAME = "Generales"

    def __init__(self):
        self.name = "ClimaAgent"
        self.log = get_logger(self.name)

    def run(self, wp_client, dup_checker, category_id: int | None, dry_run: bool = False) -> list[dict]:
        from datetime import datetime
        now = datetime.now()
        fecha = f"{DIAS_SEMANA.get(now.strftime('%A'))} {now.day} de {MESES.get(now.strftime('%B'))}"

        self.log.info(f"=== ClimaAgent — {fecha} ===")

        clima = self._obtener_clima()
        if not clima:
            return [{"title": "Clima", "status": "error", "reason": "sin datos Open-Meteo"}]

        alertas = self._obtener_alertas()
        cielo_texto, icono = WMO_MAP.get(clima["codigo_wmo"], ("Variable", "⛅"))

        titulo = self._generar_titulo(clima, cielo_texto, alertas, fecha)
        if dup_checker and dup_checker.is_duplicate(titulo):
            self.log.info("SKIP — clima de hoy ya publicado.")
            return [{"title": titulo, "status": "skipped", "reason": "duplicado"}]

        texto_ia = self._generar_redaccion(clima, cielo_texto, alertas, fecha, icono)
        if not texto_ia:
            return [{"title": titulo, "status": "error", "reason": "fallo IA"}]

        html_final = self._build_html(clima, cielo_texto, icono, alertas, fecha, texto_ia)

        if dry_run:
            self.log.info(f"[DRY-RUN] {titulo}")
            return [{"title": titulo, "status": "dry_run", "reason": "modo dry-run"}]

        # Imagen destacada — obligatoria
        media_id = self._generar_imagen_placa(clima, cielo_texto, icono, alertas, fecha, wp_client)
        if not media_id:
            self.log.warning("SKIP — no se pudo generar/subir imagen de placa.")
            return [{"title": titulo, "status": "error", "reason": "sin imagen destacada"}]

        if wp_client:
            post = wp_client.create_post(
                title=titulo,
                content=html_final,
                category_id=category_id,
                featured_media=media_id,
                status="publish",  # clima se publica directo
            )
            if post:
                if dup_checker:
                    dup_checker.mark_published(titulo)
                return [{"title": titulo, "status": "published", "reason": f"post_id={post['id']}"}]
            return [{"title": titulo, "status": "error", "reason": "fallo WP"}]

        return [{"title": titulo, "status": "error", "reason": "sin wp_client"}]

    def _obtener_clima(self) -> dict | None:
        try:
            self.log.info("Consultando Open-Meteo...")
            res = requests.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": LAT, "longitude": LON,
                "current": "temperature_2m,weather_code,wind_speed_10m,wind_gusts_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,uv_index_max,precipitation_probability_max",
                "timezone": "America/Argentina/Salta", "forecast_days": 1,
            }, timeout=10)
            res.raise_for_status()
            d = res.json()
            cur, day = d["current"], d["daily"]
            return {
                "temp_actual": cur["temperature_2m"],
                "viento_vel": cur["wind_speed_10m"],
                "viento_rafagas": cur["wind_gusts_10m"],
                "temp_max": day["temperature_2m_max"][0],
                "temp_min": day["temperature_2m_min"][0],
                "prob_lluvia": day["precipitation_probability_max"][0],
                "uv_index": day["uv_index_max"][0],
                "codigo_wmo": day["weather_code"][0],
            }
        except Exception as e:
            self.log.error(f"Error Open-Meteo: {e}")
            return None

    # Zonas del SMN que pertenecen a la provincia de Neuquén
    _NEUQUEN_SMN_ZONES = {
        "confluencia", "zapala", "chos malal", "añelo", "pehuenia",
        "loncopué", "picunches", "ñorquín", "minas", "neuquén norte",
        "neuquén sur", "neuquén centro", "neuquén",
    }

    def _obtener_alertas(self) -> list[dict]:
        alertas = []
        try:
            res = requests.get(
                f"https://ws.smn.gob.ar/alerts/type/AL?v={int(time.time())}",
                headers={"User-Agent": "Mozilla/5.0"}, timeout=5,
            )
            for a in res.json():
                if self._es_alerta_neuquen(a):
                    alertas.append({"titulo": a.get("title", ""), "nivel": a.get("severity", "")})
        except Exception:
            pass
        self.log.info(f"{len(alertas)} alertas SMN para Neuquén.")
        return alertas

    def _es_alerta_neuquen(self, a: dict) -> bool:
        """Retorna True solo si la alerta aplica a la provincia de Neuquén."""
        # Revisar campos estructurados de zonas/provincias primero
        for key in ("zones", "zone", "areas", "area", "provinces", "province"):
            val = a.get(key, "")
            if isinstance(val, (list, tuple)):
                val = " ".join(str(v) for v in val)
            elif isinstance(val, dict):
                val = json.dumps(val, ensure_ascii=False)
            val_lower = str(val).lower()
            if any(zona in val_lower for zona in self._NEUQUEN_SMN_ZONES):
                return True
        # Fallback: el título menciona explícitamente Neuquén
        titulo = str(a.get("title", "")).lower()
        return "neuquén" in titulo or "confluencia" in titulo

    def _generar_titulo(self, clima, cielo_texto, alertas, fecha) -> str:
        if alertas:
            return f"⚠️ Alerta meteorológica en Neuquén: {alertas[0]['titulo']}"
        # Incluir la fecha para que cada día sea único y no se detecte como duplicado
        return f"Clima en Neuquén del {fecha}: máxima de {clima['temp_max']}°C y cielo {cielo_texto.lower()}"

    def _generar_redaccion(self, clima, cielo_texto, alertas, fecha, icono) -> str | None:
        datos = {
            "fecha": fecha, "ubicacion": "Neuquén Capital",
            "maxima": f"{clima['temp_max']}°C", "minima": f"{clima['temp_min']}°C",
            "cielo": cielo_texto, "viento_rafagas": f"{clima['viento_rafagas']} km/h",
            "prob_lluvia": f"{clima['prob_lluvia']}%", "uv": clima["uv_index"],
            "alertas": [a["titulo"] for a in alertas] if alertas else "Ninguna",
        }
        prompt = f"""Sos un periodista meteorológico. Redactá una nota de clima para Neuquén Capital.

DATOS OFICIALES:
{json.dumps(datos, ensure_ascii=False, indent=2)}

ESTRUCTURA en HTML:
1. <p> de bajada: resumen del día con los datos más importantes.
2. <p> de desarrollo: temperatura, viento, probabilidad de lluvia. Usá <strong> para los números.
3. <p> de recomendaciones: 2-3 tips útiles según el clima (qué ropa usar, si llevar paraguas, protector solar, etc.).
{"4. <p> de ALERTA: destacar la alerta oficial del SMN con sus implicancias." if alertas else ""}

- Tono directo y útil, como un parte meteorológico profesional
- No inventes datos que no estén arriba
- SOLO HTML con <p> y <strong>, sin markdown"""

        for modelo in config.GEMINI_MODELS:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{modelo}:generateContent?key={config.GEMINI_API_KEY}"
            )
            try:
                res = requests.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 800},
                    },
                    timeout=20,
                )
                if res.status_code == 200:
                    return res.json()["candidates"][0]["content"]["parts"][0]["text"]
            except Exception as e:
                self.log.warning(f"Gemini error: {e}")
            time.sleep(1)
        return None

    def _generar_imagen_placa(self, clima, cielo_texto, icono, alertas, fecha, wp_client) -> int | None:
        """Genera imagen de la placa de clima con imgkit (opcional)."""
        if not wp_client:
            return None
        try:
            import imgkit
            fondo = "linear-gradient(135deg, #f6d365 0%, #fda085 100%)"
            if alertas:
                fondo = "linear-gradient(135deg, #cb2d3e 0%, #ef473a 100%)"
            elif "lluvia" in cielo_texto.lower() or "tormenta" in cielo_texto.lower():
                fondo = "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)"
            elif "nublado" in cielo_texto.lower():
                fondo = "linear-gradient(135deg, #bdc3c7 0%, #2c3e50 100%)"

            alerta_html = ""
            if alertas:
                alerta_html = f"<div style='background:rgba(0,0,0,0.3);padding:10px;border-radius:8px;margin-top:15px;font-weight:bold;text-align:center;'>🚨 {alertas[0]['titulo']}</div>"

            placa_html = f"""<div style="width:800px;padding:40px;box-sizing:border-box;font-family:sans-serif;background:{fondo};color:#fff;border-radius:20px;">
  <div style="display:flex;justify-content:space-between;opacity:0.9;margin-bottom:20px;">
    <span>📍 Neuquén Capital</span><span>📅 {fecha}</span>
  </div>
  <div style="text-align:center;margin:25px 0;">
    <div style="font-size:5em;line-height:1;">{icono}</div>
    <div style="font-size:4.5em;font-weight:800;line-height:1;">{clima['temp_max']}°C <span style="font-size:0.5em;opacity:0.7;">/ {clima['temp_min']}°C</span></div>
    <div style="font-size:1.6em;margin-top:8px;">{cielo_texto}</div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;background:rgba(255,255,255,0.2);border-radius:12px;padding:18px;">
    <div style="text-align:center;"><span style="font-size:1.8em;">💨</span><div>Ráfagas</div><div style="font-weight:bold;">{clima['viento_rafagas']} km/h</div></div>
    <div style="text-align:center;"><span style="font-size:1.8em;">☔</span><div>Prob. lluvia</div><div style="font-weight:bold;">{clima['prob_lluvia']}%</div></div>
    <div style="text-align:center;"><span style="font-size:1.8em;">☀️</span><div>Índice UV</div><div style="font-weight:bold;">{clima['uv_index']}</div></div>
  </div>
  {alerta_html}
</div>"""
            img_bytes = imgkit.from_string(placa_html, False, options={
                "format": "jpg", "width": 840, "disable-smart-width": "", "quality": 90,
            })
            if img_bytes:
                return wp_client.upload_media_bytes(img_bytes, f"clima-{int(time.time())}.jpg")
        except ImportError:
            self.log.warning("imgkit no instalado — sin imagen de placa.")
        except Exception as e:
            self.log.warning(f"Error generando placa: {e}")
        return None

    @staticmethod
    def _build_html(clima, cielo_texto, icono, alertas, fecha, redaccion) -> str:
        redaccion = redaccion.replace("```html", "").replace("```", "").strip()
        return f"""<div style="font-family:'Georgia',serif;font-size:18px;line-height:1.8;max-width:860px;margin:auto;">
  <div style="background:#f0f8ff;border-left:5px solid #4facfe;padding:20px;border-radius:8px;margin-bottom:25px;">
    <strong>📍 Neuquén Capital</strong> — {fecha}<br>
    {icono} <strong>{cielo_texto}</strong> · Máx {clima['temp_max']}°C / Mín {clima['temp_min']}°C ·
    Ráfagas {clima['viento_rafagas']} km/h · Lluvia {clima['prob_lluvia']}% · UV {clima['uv_index']}
  </div>
  {redaccion}
  <div style="margin-top:30px;padding:15px;background:#f4f4f4;font-size:13px;color:#666;">
    ℹ️ Datos: <strong>Open-Meteo</strong> y <strong>SMN Argentina</strong>.
  </div>
</div>"""
