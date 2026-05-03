# ============================================================
# HQ Car Rental — Bot de Telegram para reportes de reservas
# ============================================================
# Requiere en .env:
#   BOT_TOKEN, CHAT_ID, HQ_AUTH, AUTHORIZED_USERS
#   SUPABASE_URL, SUPABASE_KEY
#
# Instalar dependencias:
#   pip install python-telegram-bot[job-queue] requests pandas python-dotenv supabase
# ============================================================

import logging
import json
import os
from datetime import datetime, time as dtime, timedelta

import requests
import pandas as pd
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackContext,
)

from supabase import create_client, Client

# ─────────────────────────────────────────────
# CARGA DE ENTORNO
# ─────────────────────────────────────────────
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID   = os.getenv("CHAT_ID", "")
HQ_AUTH   = os.getenv("HQ_AUTH", "")

# IDs autorizados separados por coma en .env: AUTHORIZED_USERS=123456789,987654321
_raw_users       = os.getenv("AUTHORIZED_USERS", "")
AUTHORIZED_USERS = {
    int(uid.strip()) for uid in _raw_users.split(",") if uid.strip().isdigit()
}

HEADERS = {"Authorization": f"Basic {HQ_AUTH}"}

HQ_API_BASE = "https://api-america-miami.us4.hqrentals.app/api-america-miami"

LOCATION_MAP = {1: "Miami", 2: "NC", 3: "Nashville"}

# Horario: reportes automáticos de 8:00 AM a 9:00 PM
REPORT_INTERVAL_MINUTES = int(os.getenv("REPORT_INTERVAL_MINUTES", "30"))
REPORT_HOUR_START       = 8   # primer reporte del día: 8:00 AM
REPORT_HOUR_END         = 21  # último reporte del día: 9:00 PM

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,  # Changed from INFO to WARNING to reduce noise
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler("hq_bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)

# Silencia el polling constante de httpx (getUpdates cada ~10s)
logging.getLogger("httpx").setLevel(logging.WARNING)
# Silencia APScheduler
logging.getLogger("apscheduler").setLevel(logging.WARNING)
# Silencia telegram.ext
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

# ─────────────────────────────────────────────
# SUPABASE CLIENT
# ─────────────────────────────────────────────
supabase: Client | None = None

def init_supabase() -> bool:
    """Inicializa el cliente de Supabase. Retorna True si ok."""
    global supabase
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.warning("SUPABASE_URL o SUPABASE_KEY no definidos — Supabase desactivado.")
        print("❌ Supabase: No configurado (variables de entorno faltantes)")
        return False
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        log.info("Supabase conectado correctamente.")
        print("✅ Supabase: Conectado exitosamente")
        return True
    except Exception as e:
        log.error("Error conectando Supabase: %s", e)
        print(f"❌ Supabase: Error de conexión - {e}")
        return False


def save_to_supabase(
    fecha: str,
    brand_id: int,
    location: str,
    total_reservations: int,
    on_rent: int,
    openr: int,
    no_show: int,
    unqualified: int,
    cancellations: int,
    returns: int,
    return_completed: int,
    total_rental_days: float,
    avg_rate_day: float,
    vehicles_available: int,
    reservas_next_day: int,
    return_next_day: int,  # ← NUEVO PARÁMETRO: returns con status=rental para mañana
    turo: int,  # ← NUEVO PARÁMETRO: status='turo'
) -> None:
    """
    Inserta una fila en la tabla reportes_hq de Supabase.
    Cada llamada al reporte genera un INSERT — así queda historial completo.
    """
    if supabase is None:
        return

    row = {
        "fecha":               fecha,
        "hora_reporte":        datetime.now().isoformat(),
        "location":            location,
        "brand_id":            brand_id,
        "total_reservations":  total_reservations,
        "on_rent":             on_rent,
        "open":                openr,
        "no_show":             no_show,
        "unqualified":         unqualified,
        "cancellations":       cancellations,
        "returns":             returns,
        "return_completed":    return_completed,
        "total_rental_days":   round(float(total_rental_days), 2),
        "avg_rate_day":        round(float(avg_rate_day), 2),
        "vehicles_available":  vehicles_available,
        "reservas_next_day":   reservas_next_day,
        "return_next_day":     return_next_day,  # ← NUEVO CAMPO
        "turo":                turo,  # ← NUEVO CAMPO
    }

    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/reportes_hq",
            headers={
                "apikey":        SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type":  "application/json",
                "Prefer":        "return=minimal",
            },
            json=row,
            timeout=15,
        )
        if resp.status_code in (200, 201):
            log.info("Supabase ← %s | %s guardado correctamente", location, fecha)
        else:
            log.error("Supabase error %d (%s): %s", resp.status_code, location, resp.text)
    except Exception as e:
        log.error("Error insertando en Supabase (%s): %s", location, e)


# ─────────────────────────────────────────────
# ESTADO GLOBAL — IDs de mensajes del último reporte
# ─────────────────────────────────────────────
_last_report_message_ids: list[int] = []


# ─────────────────────────────────────────────
# FECHA
# ─────────────────────────────────────────────
def get_current_date() -> tuple[str, str]:
    """Retorna (fecha_display MM/DD/YYYY, fecha_api YYYY-MM-DD)"""
    today = datetime.now()
    return today.strftime("%m/%d/%Y"), today.strftime("%Y-%m-%d")


# ─────────────────────────────────────────────
# API — con manejo de errores robusto
# ─────────────────────────────────────────────
def _safe_get(url: str, params: dict = None) -> dict:
    """
    Wrapper para GET con timeout, raise_for_status y logging de errores.
    Retorna el JSON parseado o {} si falla.
    """
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        log.error("Timeout al conectar con %s", url)
    except requests.exceptions.HTTPError as e:
        log.error("HTTP error %s — %s", e.response.status_code, url)
    except requests.exceptions.ConnectionError:
        log.error("Error de conexión con %s", url)
    except (ValueError, KeyError) as e:
        log.error("Error parseando JSON de %s: %s", url, e)
    return {}


def fetch_reservations(fecha: str, brand_id: int) -> pd.DataFrame:
    """
    Reservas cuyo pick_up_date es `fecha` para `brand_id`.
    Sin filtro de fields para obtener total_days, total_paid y cancellation_reason_id.
    """
    url = f"{HQ_API_BASE}/car-rental/reservations"
    params = {
        "filters": json.dumps([
            {"type": "string", "column": "brand_id",    "operator": "equals",  "value": str(brand_id)},
            {"type": "date",   "column": "pick_up_date","operator": "between", "value": [fecha, fecha]},
        ]),
    }
    data = _safe_get(url, params)
    return pd.DataFrame(data.get("data", []))


def fetch_returns(fecha: str, brand_id: int) -> pd.DataFrame:
    """Reservas cuyo return_date es `fecha` para `brand_id`."""
    url = f"{HQ_API_BASE}/car-rental/reservations"
    params = {
        "filters": json.dumps([
            {"type": "string", "column": "brand_id",   "operator": "equals",  "value": str(brand_id)},
            {"type": "date",   "column": "return_date","operator": "between", "value": [fecha, fecha]},
        ]),
        "fields": "status,return_date",
    }
    data = _safe_get(url, params)
    return pd.DataFrame(data.get("data", []))


def fetch_next_day_open_reservations(fecha_hoy: str, brand_id: int) -> pd.DataFrame:
    """
    Obtiene reservas con status='open' cuyo pick_up_date es MAÑANA.
    fecha_hoy: formato YYYY-MM-DD (hoy)
    """
    try:
        hoy = datetime.strptime(fecha_hoy, "%Y-%m-%d")
        mañana = (hoy + timedelta(days=1)).strftime("%Y-%m-%d")
        
        url = f"{HQ_API_BASE}/car-rental/reservations"
        params = {
            "filters": json.dumps([
                {"type": "string", "column": "brand_id",     "operator": "equals",  "value": str(brand_id)},
                {"type": "string", "column": "status",       "operator": "equals",  "value": "open"},
                {"type": "date",   "column": "pick_up_date", "operator": "between", "value": [mañana, mañana]},
            ]),
            "fields": "id,status,pick_up_date",
        }
        data = _safe_get(url, params)
        return pd.DataFrame(data.get("data", []))
    except Exception as e:
        log.warning("Error fetching next-day open reservations: %s", e)
        return pd.DataFrame()


def fetch_next_day_rental_returns(fecha_hoy: str, brand_id: int) -> pd.DataFrame:
    """
    Obtiene reservas con status='rental' cuyo return_date es MAÑANA.
    fecha_hoy: formato YYYY-MM-DD (hoy)
    """
    try:
        hoy = datetime.strptime(fecha_hoy, "%Y-%m-%d")
        mañana = (hoy + timedelta(days=1)).strftime("%Y-%m-%d")
        
        url = f"{HQ_API_BASE}/car-rental/reservations"
        params = {
            "filters": json.dumps([
                {"type": "string", "column": "brand_id",     "operator": "equals",  "value": str(brand_id)},
                {"type": "string", "column": "status",       "operator": "equals",  "value": "rental"},
                {"type": "date",   "column": "return_date",  "operator": "between", "value": [mañana, mañana]},
            ]),
            "fields": "id,status,return_date",
        }
        data = _safe_get(url, params)
        return pd.DataFrame(data.get("data", []))
    except Exception as e:
        log.warning("Error fetching next-day rental returns: %s", e)
        return pd.DataFrame()


def fetch_vehicles() -> pd.DataFrame:
    """
    Obtiene todos los vehículos y normaliza vehicle_class en columnas separadas
    para evitar lambdas frágiles sobre dicts en el filtrado posterior.
    """
    url  = f"{HQ_API_BASE}/fleets/vehicles"
    data = _safe_get(url)
    raw  = data.get("data", [])

    if not raw:
        return pd.DataFrame()

    df = pd.DataFrame(raw)

    if "vehicle_class" in df.columns:
        vc = df["vehicle_class"].apply(lambda x: x if isinstance(x, dict) else {})
        df["vc_brand_id"] = vc.apply(lambda x: x.get("brand_id"))
        df["vc_label"]    = vc.apply(lambda x: x.get("label", ""))

    return df


# ─────────────────────────────────────────────
# REPORTE POR UBICACIÓN
# ─────────────────────────────────────────────
def generate_report(
    fecha_str: str,
    fecha: str,
    brand_id: int,
    vehicles: pd.DataFrame,
) -> str:
    location = LOCATION_MAP.get(brand_id, "Desconocida")

    data_reserva  = fetch_reservations(fecha, brand_id)
    data_reserva2 = fetch_returns(fecha, brand_id)
    
    # 🔹 Fetch de reservas open para mañana
    next_day_open = fetch_next_day_open_reservations(fecha, brand_id)
    reservas_next_day = len(next_day_open) if not next_day_open.empty else 0
    
    # 🔹 NUEVO: Fetch de returns con status=rental para mañana
    next_day_rentals = fetch_next_day_rental_returns(fecha, brand_id)
    return_next_day = len(next_day_rentals) if not next_day_rentals.empty else 0

    if data_reserva.empty:
        log.warning("Sin datos de reservas para %s (%s)", location, fecha)
        return (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 *Location:* {location}\n"
            f"📅 *Reporte del día:* {fecha_str}\n\n"
            f"❌ No se obtuvieron reservas para {location}."
        )

    # Normalizar columnas numéricas con seguridad
    data_reserva["total_days"] = pd.to_numeric(
        data_reserva.get("total_days", 0), errors="coerce"
    ).fillna(0)
    data_reserva["total_paid"] = pd.to_numeric(
        data_reserva.get("total_paid", 0), errors="coerce"
    ).fillna(0)

    # Conteos de estado
    onrent = len(data_reserva[data_reserva["status"] == "rental"])
    openr  = len(data_reserva[data_reserva["status"] == "open"])
    noshow = len(data_reserva[data_reserva["status"] == "no-show"])
    turo   = len(data_reserva[data_reserva["status"] == "turo"])  # ← NUEVO: status='turo'

    # Cancelaciones — solo si existe la columna
    if "cancellation_reason_id" in data_reserva.columns:
        unqualified = len(data_reserva[
            (data_reserva["status"] == "cancelled") &
            (data_reserva["cancellation_reason_id"].isin([1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]))
        ])
        cancellations = len(data_reserva[
            (data_reserva["status"] == "cancelled") &
            (data_reserva["cancellation_reason_id"] == 2)
        ])
    else:
        unqualified   = 0
        cancellations = 0

    total_reservations = onrent + unqualified + cancellations + noshow + openr + turo  # ← INCLUIDO TURO

    # Métricas financieras (solo reservas en rental)
    rentals_df        = data_reserva[data_reserva["status"] == "rental"]
    total_rental_days = rentals_df["total_days"].sum()
    total_paid        = rentals_df["total_paid"].sum()
    avg_rate          = total_paid / total_rental_days if total_rental_days else 0.0

    # Returns del día
    returns = len(data_reserva2[data_reserva2["status"].isin(["completed", "rental"])]) if not data_reserva2.empty else 0
    completed = len(data_reserva2[data_reserva2['status'] == 'completed'])

    # Vehículos disponibles
    if not vehicles.empty and "vc_brand_id" in vehicles.columns:
        vehicles_available = len(
            vehicles[
                (vehicles["status"] == "available") &
                (vehicles["vc_brand_id"] == brand_id)
            ]
        )
    else:
        vehicles_available = 0

    log.info(
        "Reporte %s | total=%d onrent=%d open=%d noshow=%d unqualified=%d "
        "cancel=%d turo=%d returns=%d days=%.1f avg=$%.2f avail=%d next_day=%d ret_next=%d",
        location, total_reservations, onrent, openr, noshow,
        unqualified, cancellations, turo, returns,
        total_rental_days, avg_rate, vehicles_available, reservas_next_day, return_next_day,
    )

    # ── Guardar en Supabase ──
    save_to_supabase(
        fecha=fecha,
        brand_id=brand_id,
        location=location,
        total_reservations=total_reservations,
        on_rent=onrent,
        openr=openr,
        no_show=noshow,
        unqualified=unqualified,
        cancellations=cancellations,
        returns=returns,
        return_completed=completed,
        total_rental_days=float(total_rental_days),
        avg_rate_day=float(avg_rate),
        vehicles_available=vehicles_available,
        reservas_next_day=reservas_next_day,
        return_next_day=return_next_day,  # ← NUEVO ARGUMENTO
        turo=turo,  # ← NUEVO ARGUMENTO
    )

    return (
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 *Location:* {location}\n"
        f"📅 *Reporte del día:* {fecha_str}\n\n"
        f"🔹 Total Reservations: {total_reservations}\n"
        f"🔹 ON RENT: {onrent}\n"
        f"🔹 UNQUALIFIED: {unqualified}\n"
        f"🔹 CANCELLATIONS (Pre-Arrival): {cancellations}\n"
        f"🔹 NO SHOW: {noshow}\n"
        f"🔹 OPEN: {openr}\n"
        f"🔹 TURO: {turo}\n\n"
        f"🔁 RETURNS: {completed} / {returns}\n\n"
        f"📅 Reservas Open para mañana: {reservas_next_day}\n"
        f"🔮 Returns (rental) programados para mañana: {return_next_day}\n\n"
        f"📊 Total Rental Days: {total_rental_days:.1f}\n"
        f"💰 Avg Rate/Day: ${avg_rate:.2f}\n"
        f"🚘 Vehicles Available: {vehicles_available}"
    )


# ─────────────────────────────────────────────
# BORRAR MENSAJES ANTERIORES
# ─────────────────────────────────────────────
async def delete_last_report(bot) -> None:
    """
    Borra del chat los mensajes del último reporte enviado.
    Telegram solo permite borrar mensajes de menos de 48 horas.
    """
    global _last_report_message_ids

    if not _last_report_message_ids:
        return

    log.info("Borrando %d mensajes del reporte anterior...", len(_last_report_message_ids))
    for msg_id in _last_report_message_ids:
        try:
            await bot.delete_message(chat_id=CHAT_ID, message_id=msg_id)
        except Exception as e:
            log.warning("No se pudo borrar mensaje %d: %s", msg_id, e)

    _last_report_message_ids = []


# ─────────────────────────────────────────────
# ENVÍO COMPLETO A TELEGRAM
# ─────────────────────────────────────────────
async def send_full_report(app, username: str = "Usuario", user_id: int = 0) -> None:
    """
    Flujo completo:
    1. Muestra "Borrando data anterior..."
    2. Borra ese mensaje + todo el ciclo anterior
    3. Muestra bienvenida NOVA — queda visible
    4. Envía los 3 reportes — quedan visibles
    5. Guarda en Supabase (dentro de generate_report)
    Todo se borra en el siguiente ciclo.
    """
    global _last_report_message_ids

    print(f"\n🤖 === INICIANDO REPORTE COMPLETO ===")
    print(f"👤 Usuario: {username}")
    print(f"🆔 User ID: {user_id}")
    print(f"📊 Generando reporte para todas las ubicaciones...\n")

    fecha_str, fecha = get_current_date()
    log.info("Iniciando envío de reporte completo — %s", fecha_str)

    # ── Paso 1: mostrar aviso de limpieza ──
    try:
        msg_borrando = await app.bot.send_message(
            chat_id=CHAT_ID,
            text="🗑 *Borrando data anterior...*",
            parse_mode="Markdown",
        )
        print("✅ Mensaje de limpieza enviado")
    except Exception as e:
        log.warning("No se pudo enviar aviso de limpieza: %s", e)
        msg_borrando = None

    # ── Paso 2: borrar todo el ciclo anterior ──
    await delete_last_report(app.bot)

    # ── Paso 3: borrar el aviso "borrando" ──
    if msg_borrando:
        try:
            await app.bot.delete_message(chat_id=CHAT_ID, message_id=msg_borrando.message_id)
        except Exception as e:
            log.warning("No se pudo borrar aviso de limpieza: %s", e)

    # ── Paso 4: mostrar bienvenida (queda visible) ──
    hora = datetime.now().hour
    if hora < 12:
        saludo = "🌅 ¡Buenos días!"
    elif hora < 18:
        saludo = "☀️ ¡Buenas tardes!"
    else:
        saludo = "🌙 ¡Buenas noches!"

    texto_bienvenida = (
        f"{saludo} *{username}*\n\n"
        f"🤖 Soy *NOVA*, tu Asistente Virtual\n"
        f"*¡Bienvenido al Sistema de Reservas!* 🚗\n\n"
        f"🆔 *User ID:* `{user_id}`\n"
        f"📊 Actualizando información..."
    )
    nuevos_ids = []
    try:
        sent_bienvenida = await app.bot.send_message(
            chat_id=CHAT_ID,
            text=texto_bienvenida,
            parse_mode="Markdown",
        )
        nuevos_ids.append(sent_bienvenida.message_id)
        print(f"✅ Bienvenida enviada a {username} (ID: {user_id})")
    except Exception as e:
        log.error("Error enviando bienvenida: %s", e)

    # ── Paso 5: cargar vehículos ──
    print("🚗 Cargando información de vehículos...")
    try:
        vehicles = fetch_vehicles()
        print(f"✅ Vehículos cargados: {len(vehicles)} registros")
    except Exception as e:
        log.error("Error crítico al cargar vehículos: %s", e)
        vehicles = pd.DataFrame()
        print("❌ Error cargando vehículos")

    # ── Paso 6: enviar reportes y guardar en Supabase ──
    print("📊 Generando reportes por ubicación:")
    for brand_id in LOCATION_MAP:
        location = LOCATION_MAP.get(brand_id, "Desconocida")
        print(f"   📍 Procesando {location} (Brand ID: {brand_id})...")
        
        try:
            reporte = generate_report(fecha_str, fecha, brand_id, vehicles)
            sent = await app.bot.send_message(
                chat_id=CHAT_ID,
                text=reporte,
                parse_mode="Markdown",
            )
            nuevos_ids.append(sent.message_id)
            print(f"   ✅ Reporte de {location} enviado")
        except Exception as e:
            log.error("Error enviando reporte brand_id=%d: %s", brand_id, e)
            print(f"   ❌ Error enviando reporte de {location}")

    _last_report_message_ids = nuevos_ids
    print(f"\n🎉 === REPORTE COMPLETO FINALIZADO ===")
    print(f"📨 Total mensajes enviados: {len(nuevos_ids)}")
    print(f"💾 Datos guardados en Supabase")
    print(f"🔄 Próximo reporte en {REPORT_INTERVAL_MINUTES} minutos\n")
    log.info("Ciclo completo — %d mensajes visibles guardados para próxima limpieza", len(nuevos_ids))


# ─────────────────────────────────────────────
# SCHEDULER JOBS
# ─────────────────────────────────────────────
async def scheduled_report_job(context: CallbackContext) -> None:
    """
    Se ejecuta cada REPORT_INTERVAL_MINUTES minutos.
    Solo envía reporte si la hora actual está entre 8:00 AM y 9:00 PM inclusive.
    """
    current_hour = datetime.now().hour
    if not (REPORT_HOUR_START <= current_hour <= REPORT_HOUR_END):
        log.info(
            "Reporte omitido — fuera de horario (%d:xx, rango %d:00–%d:00)",
            current_hour, REPORT_HOUR_START, REPORT_HOUR_END,
        )
        return

    log.info("Ejecutando reporte automático programado...")
    await send_full_report(context.application, username="Sistema Automático", user_id=0)


async def midnight_cleanup_job(context: CallbackContext) -> None:
    """
    Se ejecuta todos los días a las 12:00 AM (medianoche).
    Borra todos los mensajes del último reporte para dejar el chat limpio.
    """
    log.info("Limpieza de medianoche — borrando mensajes del día...")
    await delete_last_report(context.bot)
    log.info("Chat limpiado a medianoche correctamente.")


# ─────────────────────────────────────────────
# COMANDO MANUAL POR MENSAJE
# ─────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Escucha mensajes de texto.
    Comando: "reservas@" → genera reporte inmediato (solo usuarios autorizados).
    """
    global _last_report_message_ids

    if not update.message:
        return

    user_id  = update.message.from_user.id
    username = update.message.from_user.first_name or "Usuario"
    text     = (update.message.text or "").lower().strip()

    print(f"\n💬 MENSAJE RECIBIDO:")
    print(f"👤 Usuario: {username}")
    print(f"🆔 User ID: {user_id}")
    print(f"📝 Mensaje: '{text}'")

    if text == "reservas@":
        if user_id not in AUTHORIZED_USERS:
            log.warning("Usuario no autorizado intentó usar el bot: %d", user_id)
            print(f"❌ USUARIO NO AUTORIZADO")
            await update.message.reply_text("⛔ No autorizado")
            return

        print(f"✅ USUARIO AUTORIZADO - Generando reporte manual...")
        log.info("Reporte manual solicitado por user_id=%d (%s)", user_id, username)
        _last_report_message_ids.append(update.message.message_id)
        await send_full_report(context.application, username=username, user_id=user_id)
    else:
        print(f"⚠️ Comando no reconocido: '{text}'")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main() -> None:
    print("\n🤖 NOVA - Bot de Rent-A-Car HQ")
    print("=" * 40)
    
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN no configurado")
        return
    if not CHAT_ID:
        print("❌ ERROR: CHAT_ID no configurado")
        return
    if not AUTHORIZED_USERS:
        print("⚠️ ADVERTENCIA: No hay usuarios autorizados")

    print(f"✅ Configuración OK")
    print(f"📱 Chat: {CHAT_ID}")
    print(f"🔄 Reportes: cada {REPORT_INTERVAL_MINUTES} min")

    # Inicializar Supabase al arrancar
    supabase_status = init_supabase()

    print("📡 Iniciando bot...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Add error handler
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        print(f"⚠️ Error: {context.error}")
        if "Conflict: terminated by other getUpdates request" in str(context.error):
            print("❌ ERROR: Ya hay otra instancia del bot corriendo")
            print("💡 Solución: Cierra la otra instancia o espera 30 segundos")

    app.add_error_handler(error_handler)

    # ── Handler de mensajes manuales ──
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    interval_seconds = REPORT_INTERVAL_MINUTES * 60

    # ── Job 1: reporte automático ──
    app.job_queue.run_repeating(
        scheduled_report_job,
        interval=interval_seconds,
        first=10,
        name="auto_report",
    )

    # ── Job 2: limpieza a medianoche ──
    app.job_queue.run_daily(
        midnight_cleanup_job,
        time=dtime(hour=0, minute=0, second=0),
        name="midnight_cleanup",
    )

    print(f"✅ Bot iniciado - Esperando comandos")
    print(f"💬 Escribe 'reservas@' para reporte manual")
    print("=" * 40)
    
    try:
        app.run_polling()
    except KeyboardInterrupt:
        print("\n👋 Bot detenido por el usuario")
    except Exception as e:
        print(f"\n❌ Error crítico: {e}")
        if "Conflict" in str(e):
            print("💡 Cierra otras instancias del bot e intenta de nuevo")


if __name__ == "__main__":
    main()