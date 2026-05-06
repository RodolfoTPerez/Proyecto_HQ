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
import asyncio
import sys
import io
from datetime import datetime, time as dtime, timedelta

# Forzar encoding UTF-8 en la consola de Windows para evitar errores con emojis
if sys.platform == "win32":
    import sys
    import io
    if hasattr(sys.stdout, 'reconfigure'):
        # Usamos errors='replace' para que si un emoji falla, no crashee el bot
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

def safe_print(msg):
    """Imprime mensajes de forma segura, evitando errores de encoding."""
    try:
        print(msg, flush=True)
    except:
        try:
            # Si falla, intentamos limpiar caracteres no compatibles
            print(msg.encode('ascii', 'replace').decode('ascii'), flush=True)
        except:
            pass

import requests
import pandas as pd
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    CallbackContext,
)

from supabase import create_client, Client, create_async_client

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
REPORT_INTERVAL_MINUTES = int(os.getenv("REPORT_INTERVAL_MINUTES", "60"))
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


def clear_reportes_hq() -> None:
    """
    Borra todos los datos de la tabla reportes_hq antes de guardar nuevos datos.
    """
    if supabase is None:
        return
    
    try:
        # Borrar todos los registros de la tabla reportes_hq (con WHERE clause)
        resp = requests.delete(
            f"{SUPABASE_URL}/rest/v1/reportes_hq?id=gt.0",  # WHERE id > 0
            headers={
                "apikey":        SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Prefer":        "return=minimal",
            },
            timeout=15,
        )
        if resp.status_code in (200, 204):
            log.info("Datos viejos de reportes_hq borrados correctamente")
        else:
            log.error("Error borrando datos viejos de reportes_hq: %d - %s", resp.status_code, resp.text)
    except Exception as e:
        log.error("Error borrando datos de reportes_hq: %s", e)


def clear_reportes_hq_s() -> None:
    """
    Borra todos los datos de la tabla reportes_hq_s antes de guardar nuevos datos.
    """
    if supabase is None:
        return
    
    try:
        # Borrar todos los registros de la tabla reportes_hq_s (con WHERE clause)
        resp = requests.delete(
            f"{SUPABASE_URL}/rest/v1/reportes_hq_s?id=gt.0",  # WHERE id > 0
            headers={
                "apikey":        SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Prefer":        "return=minimal",
            },
            timeout=15,
        )
        if resp.status_code in (200, 204):
            log.info("Datos viejos de reportes_hq_s borrados correctamente")
        else:
            log.error("Error borrando datos viejos de reportes_hq_s: %d - %s", resp.status_code, resp.text)
    except Exception as e:
        log.error("Error borrando datos de reportes_hq_s: %s", e)


def save_to_supabase_range(
    fecha_desde: str,
    fecha_hasta: str,
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
    return_next_day: int,
    turo: int,
) -> None:
    """
    Inserta una fila en la tabla reportes_hq_s de Supabase (reportes por rango).
    Ahora incluye los campos fecha_desde y fecha_hasta reales.
    """
    if supabase is None:
        return

    row = {
        "fecha":              fecha_desde,
        "fecha_desde":        fecha_desde,  # Nuevo campo
        "fecha_hasta":        fecha_hasta,  # Nuevo campo
        "hora_reporte":       datetime.now().isoformat(),
        "location":           location,
        "brand_id":           brand_id,
        "total_reservations": total_reservations,
        "on_rent":            on_rent,
        "open":               openr,
        "no_show":            no_show,
        "unqualified":        unqualified,
        "cancellations":      cancellations,
        "returns":            returns,
        "return_completed":   return_completed,
        "total_rental_days":  round(float(total_rental_days), 2),
        "avg_rate_day":       round(float(avg_rate_day), 2),
        "vehicles_available": vehicles_available,
        "reservas_next_day":  reservas_next_day,
        "return_next_day":    return_next_day,
        "turo":               turo,
    }

    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/reportes_hq_s",
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
            log.info("Supabase ← %s | %s-%s guardado correctamente", location, fecha_desde, fecha_hasta)
            print(f"✅ GUARDADO EXITOSO: {location} | {fecha_desde} a {fecha_hasta}")
        else:
            log.error("Supabase error %d (%s): %s", resp.status_code, location, resp.text)
            print(f"❌ ERROR GUARDANDO: Status {resp.status_code} | {resp.text}")
    except Exception as e:
        log.error("Error insertando en Supabase (%s): %s", location, e)


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
# ESTADO DE CONVERSACIÓN (NUEVO)
# ─────────────────────────────────────────────
_user_states: dict[int, dict] = {}  # {user_id: {"mode": "hoy|fechas", "step": 1|2, "data": {...}}}

# ─────────────────────────────────────────────
# CALENDARIO INLINE
# ─────────────────────────────────────────────
def create_calendar(year: int, month: int, user_id: int, calendar_type: str) -> InlineKeyboardMarkup:
    """
    Crea un calendario inline para un mes específico.
    calendar_type: 'desde' o 'hasta'
    """
    # Obtener el primer día del mes y cuántos días tiene
    first_day = datetime(year, month, 1)
    days_in_month = (datetime(year, month + 1, 1) - first_day).days if month < 12 else (datetime(year + 1, 1, 1) - first_day).days
    
    # Día de la semana del primer día (0 = lunes, 6 = domingo)
    start_weekday = first_day.weekday()
    
    keyboard = []
    
    # Encabezado con navegación de meses
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    
    header_row = [
        InlineKeyboardButton("◀️", callback_data=f"calendar_{user_id}_{calendar_type}_{prev_year}_{prev_month:02d}"),
        InlineKeyboardButton(f"{first_day.strftime('%B %Y')}", callback_data="calendar_ignore"),
        InlineKeyboardButton("▶️", callback_data=f"calendar_{user_id}_{calendar_type}_{next_year}_{next_month:02d}")
    ]
    keyboard.append(header_row)
    
    # Días de la semana
    week_days = ["L", "M", "X", "J", "V", "S", "D"]
    keyboard.append([InlineKeyboardButton(day, callback_data="calendar_ignore") for day in week_days])
    
    # Calendario
    current_day = 1
    for week in range(6):  # Máximo 6 semanas en un mes
        row = []
        for weekday in range(7):  # 7 días de la semana
            if week == 0 and weekday < start_weekday:
                # Días vacíos antes del primer día del mes
                row.append(InlineKeyboardButton(" ", callback_data="calendar_ignore"))
            elif current_day <= days_in_month:
                # Días del mes
                date_str = f"{year:04d}-{month:02d}-{current_day:02d}"
                callback_data = f"calendar_{user_id}_{calendar_type}_select_{date_str}"
                row.append(InlineKeyboardButton(str(current_day), callback_data=callback_data))
                current_day += 1
            else:
                # Días vacíos después del último día del mes
                row.append(InlineKeyboardButton(" ", callback_data="calendar_ignore"))
        
        if current_day > days_in_month and week > 0:
            # Si ya pasamos todos los días y no estamos en la primera semana, terminamos
            break
        
        keyboard.append(row)
    
    return InlineKeyboardMarkup(keyboard)

def format_date_display(date_str: str) -> str:
    """Convierte YYYY-MM-DD a MM/DD/YYYY"""
    year, month, day = date_str.split('-')
    return f"{month}/{day}/{year}"

def reset_user_state(user_id: int) -> None:
    """Reinicia el estado de un usuario."""
    if user_id in _user_states:
        del _user_states[user_id]


# ─────────────────────────────────────────────
# FECHA
# ─────────────────────────────────────────────
def get_current_date() -> tuple[str, str]:
    """Retorna (fecha_display MM/DD/YYYY, fecha_api YYYY-MM-DD)"""
    today = datetime.now()
    return today.strftime("%m/%d/%Y"), today.strftime("%Y-%m-%d")


# ─────────────────────────────────────────────
# API — RANGO DE FECHAS (NUEVO)
# ─────────────────────────────────────────────
def fetch_reservations_range(fecha_desde: str, fecha_hasta: str, brand_id: int) -> pd.DataFrame:
    """
    Reservas cuyo pick_up_date está en el rango [fecha_desde, fecha_hasta] para brand_id.
    Ejecuta por cada día del rango para obtener 100 registros por día.
    """
    
    # Convertir fechas a datetime para calcular el rango
    start_date = datetime.strptime(fecha_desde, "%Y-%m-%d")
    end_date = datetime.strptime(fecha_hasta, "%Y-%m-%d")
    
    all_data = []
    current_date = start_date
    
    while current_date <= end_date:
        day_str = current_date.strftime("%Y-%m-%d")
        
        url = f"{HQ_API_BASE}/car-rental/reservations"
        params = {
            "filters": json.dumps([
                {"type": "string", "column": "brand_id",    "operator": "equals",  "value": str(brand_id)},
                {"type": "date",   "column": "pick_up_date","operator": "between", "value": [day_str, day_str]},
            ]),
            "fields": "status,pick_up_date,total_days,total_paid,cancellation_reason_id,f600",
            "limit":100
        }
        data = _safe_get(url, params)
        day_data = data.get("data", [])
        
        all_data.extend(day_data)
        
        current_date += timedelta(days=1)
    
    return pd.DataFrame(all_data)
   

 

def fetch_returns_range(fecha_desde: str, fecha_hasta: str, brand_id: int) -> pd.DataFrame:
    """Reservas cuyo return_date está en el rango [fecha_desde, fecha_hasta] para brand_id.
    Ejecuta por cada día del rango para obtener 100 registros por día."""
    
    # Convertir fechas a datetime para calcular el rango
    start_date = datetime.strptime(fecha_desde, "%Y-%m-%d")
    end_date = datetime.strptime(fecha_hasta, "%Y-%m-%d")
    
    all_data = []
    current_date = start_date
    
    while current_date <= end_date:
        day_str = current_date.strftime("%Y-%m-%d")
        
        url = f"{HQ_API_BASE}/car-rental/reservations"
        params = {
            "filters": json.dumps([
                {"type": "string", "column": "brand_id",   "operator": "equals",  "value": str(brand_id)},
                {"type": "date",   "column": "return_date","operator": "between", "value": [day_str, day_str]},
            ]),
            "fields": "status,return_date,pick_up_date,total_days,total_paid,cancellation_reason_id",
            "limit":100
        } 
        data = _safe_get(url, params)
        day_data = data.get("data", [])
        
        all_data.extend(day_data)
        
        current_date += timedelta(days=1)
    
    return pd.DataFrame(all_data)



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
    Incluye campo f600 para contar registros Turo.
    """
    url = f"{HQ_API_BASE}/car-rental/reservations"
    params = {
        "filters": json.dumps([
            {"type": "string", "column": "brand_id",    "operator": "equals",  "value": str(brand_id)},
            {"type": "date",   "column": "pick_up_date","operator": "between", "value": [fecha, fecha]},
        ]),
        "fields": "status,pick_up_date,total_days,total_paid,cancellation_reason_id,f600",
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
# REPORTE POR RANGO DE FECHAS (NUEVO)
# ─────────────────────────────────────────────
def generate_range_report(
    fecha_desde_str: str,
    fecha_hasta_str: str,
    fecha_desde: str,
    fecha_hasta: str,
    brand_id: int,
    vehicles: pd.DataFrame,
) -> str:
    location = LOCATION_MAP.get(brand_id, "Desconocida")
    
    
    print(fecha_desde, fecha_hasta, brand_id)

    data_reserva  = fetch_reservations_range(fecha_desde, fecha_hasta, brand_id)
    data_reserva2 = fetch_returns_range(fecha_desde, fecha_hasta, brand_id)

    if data_reserva.empty:
        log.warning("Sin datos de reservas para %s (%s-%s)", location, fecha_desde, fecha_hasta)
        return (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 *Location:* {location}\n"
            f"📅 *Reporte del período:* {fecha_desde_str} al {fecha_hasta_str}\n\n"
            f"❌ No se obtuvieron reservas para {location} en este período."
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
    # TURO: contar registros donde f600="turo" (campo personalizado HQ)
    turo   = len(data_reserva[data_reserva.get("f600", "") == "turo"])

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

    total_reservations = onrent + unqualified + cancellations + noshow + openr + turo

    # Métricas financieras (solo reservas en rental)
    rentals_df        = data_reserva[data_reserva["status"] == "rental"]
    total_rental_days = rentals_df["total_days"].sum()
    total_paid        = rentals_df["total_paid"].sum()
    avg_rate          = total_paid / total_rental_days if total_rental_days else 0.0

    # Returns del período
    returns = len(data_reserva2[data_reserva2["status"].isin(["completed", "rental"])]) if not data_reserva2.empty else 0
    completed = len(data_reserva2[data_reserva2['status'] == 'completed'])

    # Vehículos disponibles (usar datos actuales)
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
        "Reporte RANGO %s | %s-%s total=%d onrent=%d open=%d noshow=%d unqualified=%d "
        "cancel=%d turo=%d returns=%d days=%.1f avg=$%.2f avail=%d",
        location, fecha_desde, fecha_hasta, total_reservations, onrent, openr, noshow,
        unqualified, cancellations, turo, returns,
        total_rental_days, avg_rate, vehicles_available,
    )

    # ── Guardar en Supabase (tabla reportes_hq_s) ──
    save_to_supabase_range(
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
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
        reservas_next_day=0,
        return_next_day=0,
        turo=turo,
    )

    return (
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 *Location:* {location}\n"
        f"📅 *Rep. Período:* {fecha_desde_str} al {fecha_hasta_str}\n\n"
        f"🔹 Total Reservations: {total_reservations}\n"
        f"🔹 ON RENT: {onrent}\n"
        f"🔹 UNQUALIFIED: {unqualified}\n"
        f"🔹 CANCELLATIONS (Pre-Arrival): {cancellations}\n"
        f"🔹 NO SHOW: {noshow}\n"
        f"🔹 OPEN: {openr}\n"
        f"🔹 TURO: {turo}\n\n"
        f"🔁 RETURNS: {completed} / {returns}\n\n"
        f"📊 Total Rental Days: {total_rental_days:.1f}\n"
        f"💰 Avg Rate/Day: ${avg_rate:.2f}\n"
        f"🚘 Vehicles Available: {vehicles_available}\n\n"
        f"🌐 *Ver detalles web:* [Reportes por Rango]"
    )


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
    # TURO: contar registros donde f600="turo" (campo personalizado HQ)
    turo   = len(data_reserva[data_reserva.get("f600", "") == "turo"])

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
        f"🔮 Reservas Return para mañana: {return_next_day}\n\n"
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
# ENVÍO COMPLETO A TELEGRAM - RANGO DE FECHAS (NUEVO)
# ─────────────────────────────────────────────
async def send_range_report(
    app, 
    username: str = "Usuario", 
    user_id: int = 0,
    fecha_desde_str: str = "",
    fecha_hasta_str: str = "",
    fecha_desde: str = "",
    fecha_hasta: str = ""
) -> None:
    """
    Flujo completo para reportes por rango de fechas.
    """
    global _last_report_message_ids

    print(f"\n📆 === INICIANDO REPORTE POR RANGO ===")
    print(f"👤 Usuario: {username}")
    print(f"🆔 User ID: {user_id}")
    print(f"📅 Período: {fecha_desde_str} al {fecha_hasta_str}")
    print(f"📊 Generando reporte para todas las ubicaciones...\n")

    # ── Paso 1: mostrar aviso de procesamiento ──
    try:
        msg_procesando = await app.bot.send_message(
            chat_id=CHAT_ID,
            text="⏳ *Procesando reporte por rango...*",
            parse_mode="Markdown",
        )
        print("✅ Mensaje de procesamiento enviado")
    except Exception as e:
        log.warning("No se pudo enviar aviso de procesamiento: %s", e)
        msg_procesando = None

    # ── Paso 2: borrar mensaje de procesamiento ──
    if msg_procesando:
        try:
            await app.bot.delete_message(chat_id=CHAT_ID, message_id=msg_procesando.message_id)
        except Exception as e:
            log.warning("No se pudo borrar aviso de procesamiento: %s", e)

    # ── Paso 3: mostrar encabezado del reporte ──
    texto_encabezado = (
        f"📆 *Reporte por Rango de Fechas*\n\n"
        f"👤 *Usuario:* {username}\n"
        f"🆔 *User ID:* `{user_id}`\n"
        f"📅 *Período:* {fecha_desde_str} al {fecha_hasta_str}\n\n"
        f"📊 Generando información..."
    )
    nuevos_ids = []
    try:
        sent_encabezado = await app.bot.send_message(
            chat_id=CHAT_ID,
            text=texto_encabezado,
            parse_mode="Markdown",
        )
        nuevos_ids.append(sent_encabezado.message_id)
        print(f"✅ Encabezado enviado a {username}")
    except Exception as e:
        log.error("Error enviando encabezado: %s", e)

    # ── Paso 4: limpiar datos viejos de Supabase ──
    print("🗑️ Limpiando datos viejos de reportes_hq_s...")
    clear_reportes_hq_s()

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
            reporte = generate_range_report(
                fecha_desde_str, fecha_hasta_str, 
                fecha_desde, fecha_hasta, 
                brand_id, vehicles
            )
            sent = await app.bot.send_message(
                chat_id=CHAT_ID,
                text=reporte,
                parse_mode="Markdown",
            )
            nuevos_ids.append(sent.message_id)
            print(f"   ✅ Reporte de {location} enviado")
        except Exception as e:
            log.error("Error enviando reporte rango brand_id=%d: %s", brand_id, e)
            print(f"   ❌ Error enviando reporte de {location}")

    # ── Paso 6: mensaje final ──
    texto_final = (
        f"🎉 *Reporte por Rango Completado*\n\n"
        f"📊 *Período:* {fecha_desde_str} al {fecha_hasta_str}\n"
        f"💾 *Datos guardados* en tabla `reportes_hq_s`\n"
        f"🌐 *Ver detalles* en la web de reportes por rango\n\n"
        f"📨 *Total mensajes:* {len(nuevos_ids)}\n"
        f"✅ *Proceso finalizado*"
    )
    
    try:
        sent_final = await app.bot.send_message(
            chat_id=CHAT_ID,
            text=texto_final,
            parse_mode="Markdown",
        )
        nuevos_ids.append(sent_final.message_id)
        print(f"✅ Mensaje final enviado")
    except Exception as e:
        log.error("Error enviando mensaje final: %s", e)

    _last_report_message_ids = nuevos_ids
    print(f"\n🎉 === REPORTE POR RANGO FINALIZADO ===")
    print(f"📨 Total mensajes enviados: {len(nuevos_ids)}")
    print(f"💾 Datos guardados en reportes_hq_s")
    print(f"🌐 Disponible para consulta web\n")


async def send_range_report_with_progress(
    app,
    cmd_id,
    username="Dashboard Web (Rango)",
    user_id=0,
    fecha_desde_str="",
    fecha_hasta_str="",
    fecha_desde="",
    fecha_hasta=""
):
    """
    Ejecuta reporte por rango con actualización dinámica de progreso por cada location.
    """
    safe_print(f"🚀 INICIANDO REPORTE POR RANGO CON PROGRESO")
    safe_print(f"📅 Fechas: {fecha_desde} a {fecha_hasta}")
    safe_print(f"🆔 Comando ID: {cmd_id}")
    
    # Enviar logs al dashboard
    print("🚀 INICIANDO REPORTE POR RANGO CON PROGRESO")
    print(f"📅 Fechas: {fecha_desde} a {fecha_hasta}")
    print(f"🆔 Comando ID: {cmd_id}")
    
    try:
        vehicles = fetch_vehicles()
        print(f"🚗 Vehículos cargados: {len(vehicles)}")
    except Exception as e:
        print(f"❌ ERROR cargando vehículos: {e}")
        return
    
    locations = LOCATION_MAP.items()
    total_locations = len(locations)
    print(f"📍 Total locations: {total_locations}")
    
    for i, (brand_id, location) in enumerate(locations, 1):
        # Calcular progreso (ej: 33%, 66%, 99%)
        progress = int((i / total_locations) * 99)
        
        print(f"🔄 Procesando {location} ({i}/{total_locations}) - Progreso: {progress}%")
        
        # Actualizar progreso en Supabase
        try:
            await update_progress_in_supabase(
                cmd_id, 
                progress, 
                f"Procesando {location} ({i}/{total_locations})"
            )
        except Exception as e:
            print(f"❌ ERROR actualizando progreso: {e}")
        
        # Pequeña pausa para que la web vea la actualización
        await asyncio.sleep(0.5)
        
        # Generar reporte para esta location
        try:
            print(f"📊 Generando reporte para {location}...")
            
            report = generate_range_report(
                fecha_desde_str, fecha_hasta_str, fecha_desde, fecha_hasta, brand_id, vehicles
            )
            
            print(f"✅ Reporte generado para {location} - Progreso: {progress}%")
            
            # Extraer número de reservas del reporte para el dashboard
            import re
            match = re.search(r'Total Reservations: (\d+)', report)
            reservations = int(match.group(1)) if match else 0
            
            # Reporte guardado para dashboard
            print(f"💾 Reporte guardado: {location} ({fecha_desde} al {fecha_hasta})")
            
        except Exception as e:
            print(f"❌ Error en {location}: {e}")
            continue
    
    # Marcar como completed
    try:
        # Usar el cliente async que ya tenemos disponible
        from supabase import create_async_client
        async_supabase = await create_async_client(SUPABASE_URL, SUPABASE_KEY)
        await async_supabase.table("comandos_bot").update({"status": "completed"}).eq("id", cmd_id).execute()
        print(f"✅ COMANDO MARCADO COMO COMPLETED")
    except Exception as e:
        print(f"❌ ERROR marcando como completed: {e}")
    
    print(f"🎉 REPORTE POR RANGO FINALIZADO")
    print(f"✅ SINCRONIZACIÓN POR RANGO REALIZADA: {fecha_desde_str} al {fecha_hasta_str}")


async def send_full_report(app, username: str = "Usuario", user_id: int = 0) -> None:
    """
    Flujo completo para reportes diarios con logs al dashboard.
    """
    global _last_report_message_ids

    print(f"\n🤖 === INICIANDO REPORTE COMPLETO ===")
    print(f"👤 Usuario: {username}")
    print(f"🆔 User ID: {user_id}")
    print(f"📊 Generando reporte para todas las ubicaciones...\n")

    fecha_str, fecha = get_current_date()
    log.info("Iniciando envío de reporte completo — %s", fecha_str)

    # Logs del dashboard (capturados automáticamente por print)
    print("🤖 === INICIANDO REPORTE COMPLETO ===")
    print(f"👤 Usuario: {username}")
    print(f"🆔 User ID: {user_id}")
    print("📊 Generando reporte para todas las ubicaciones...")

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

    # ── Paso 2: limpiar datos viejos de Supabase ──
    print("🗑️ Limpiando datos viejos de reportes_hq...")
    clear_reportes_hq()

    # ── Paso 3: borrar todo el ciclo anterior ──
    await delete_last_report(app.bot)

    # ── Paso 4: borrar el aviso "borrando" ──
    if msg_borrando:
        try:
            await app.bot.delete_message(chat_id=CHAT_ID, message_id=msg_borrando.message_id)
        except Exception as e:
            log.warning("No se pudo borrar aviso de limpieza: %s", e)

    # ── Paso 5: mostrar bienvenida (queda visible) ──
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

    # ── Paso 6: cargar vehículos ──
    print("🚗 Cargando información de vehículos...")
    
    try:
        vehicles = fetch_vehicles()
        vehicles_count = len(vehicles)
        print(f"✅ Vehículos cargados: {vehicles_count} registros")
        
        # Datos de vehículos para dashboard
        for location in LOCATION_MAP.values():
            print(f"🚗 Cargando información de vehículos en {location}...")
            
    except Exception as e:
        log.error("Error crítico al cargar vehículos: %s", e)
        vehicles = pd.DataFrame()
        print("❌ Error cargando vehículos")

    # ── Paso 7: enviar reportes y guardar en Supabase ──
    print("📊 Generando reportes por ubicación:")
    
    for brand_id in LOCATION_MAP:
        location = LOCATION_MAP.get(brand_id, "Desconocida")
        print(f"   📍 Procesando {location} (Brand ID: {brand_id})...")
        
        try:
            reporte = generate_report(
                fecha_str,
                fecha,
                brand_id,
                vehicles
            )
            
            # Extraer datos del reporte para el dashboard
            import re
            reservations_match = re.search(r'Total Reservations: (\d+)', reporte)
            onrent_match = re.search(r'ON RENT: (\d+)', reporte)
            avg_rate_match = re.search(r'Avg Rate/Day: \$(\d+\.?\d*)', reporte)
            vehicles_available_match = re.search(r'Vehicles Available: (\d+)', reporte)
            
            reservations = int(reservations_match.group(1)) if reservations_match else 0
            onrent = int(onrent_match.group(1)) if onrent_match else 0
            avg_rate = float(avg_rate_match.group(1)) if avg_rate_match else 0
            vehicles_available = int(vehicles_available_match.group(1)) if vehicles_available_match else 0
            revenue = round(reservations * avg_rate, 2)
            
            # Datos del reporte para dashboard
            print(f"✅ Reporte generado para {location}")
            print(f"📊 Reservas: {reservations}, Ingresos: ${revenue}")
            
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
    print(f"💾 Datos guardados en reportes_hq")
    print(f"🔄 Próximo reporte en {REPORT_INTERVAL_MINUTES} minutos")
    log.info("Ciclo completo — %d mensajes visibles guardados para próxima limpieza", len(nuevos_ids))
    
    # Logs finales (capturados automáticamente)
    print("🎉 === REPORTE COMPLETO FINALIZADO ===")
    print(f"📨 Total mensajes enviados: {len(nuevos_ids)}")
    print("💾 Datos guardados en reportes_hq")
    print(f"🔄 Próximo reporte en {REPORT_INTERVAL_MINUTES} minutos")
    
    # Determinar fuente de sincronización
    source = "telegram" if username != "Sistema Automático" else "automated"
    print(f"✅ SINCRONIZACIÓN COMPLETADA: {source.upper()}")
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
# HANDLER DE CALENDARIO
# ─────────────────────────────────────────────
async def handle_calendar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja las selecciones del calendario inline.
    """
    query = update.callback_query
    print(f"📅 Calendario callback recibido: {query.data}")
    
    try:
        await query.answer()
    except Exception as e:
        print(f"❌ Error en query.answer(): {e}")
        return
    
    callback_data = query.data
    user_id = update.effective_user.id
    print(f"👤 Usuario ID: {user_id}, Callback: {callback_data}")
    
    # Parsear callback_data
    parts = callback_data.split('_')
    print(f"🔍 Parts: {parts}")
    
    if not parts or len(parts) < 2:
        print("❌ Callback data inválido")
        return
    
    if parts[0] == "calendar":
        if len(parts) >= 2 and parts[1] == str(user_id):  # Verificar que sea del usuario correcto
            print(f"✅ Callback válido para usuario {user_id}")
            
            if len(parts) >= 3:
                calendar_type = parts[2]  # 'desde' o 'hasta'
                print(f"📋 Calendar type: {calendar_type}")
                
                if len(parts) >= 4:
                    action = parts[3]
                    print(f"⚡ Action: {action}")
                    
                    if action == "ignore":
                        print("🚫 Ignorando clic en elemento no seleccionable")
                        return
                    
                    elif action == "select" and len(parts) >= 5:
                        # Selección de fecha
                        date_str = parts[4]  # YYYY-MM-DD
                        date_display = format_date_display(date_str)
                        print(f"🗓️ Fecha seleccionada: {date_str} ({date_display})")
                        
                        try:
                            if calendar_type == "desde":
                                # Guardar fecha desde
                                _user_states[user_id] = {
                                    "mode": "fechas",
                                    "step": 2,
                                    "data": {
                                        "fecha_desde": date_str,
                                        "fecha_desde_str": date_display
                                    }
                                }
                                
                                # Mostrar calendario para fecha hasta
                                today = datetime.now()
                                calendar_markup = create_calendar(today.year, today.month, user_id, "hasta")
                                
                                await query.edit_message_text(
                                    f"✅ *Fecha desde:* {date_display}\n\n"
                                    f"📆 *Selecciona fecha hasta:*",
                                    reply_markup=calendar_markup,
                                    parse_mode="Markdown"
                                )
                                print(f"📅 Fecha desde guardada: {date_display}")
                            
                            elif calendar_type == "hasta":
                                # Validar y guardar fecha hasta
                                user_state = _user_states.get(user_id, {})
                                if not user_state or "fecha_desde" not in user_state.get("data", {}):
                                    await query.edit_message_text(
                                        "❌ Error: Por favor selecciona primero la fecha 'desde'."
                                    )
                                    return
                                
                                fecha_desde = user_state["data"]["fecha_desde"]
                                fecha_hasta = date_str
                                
                                # Validar que fecha hasta sea posterior o igual a fecha desde
                                desde_dt = datetime.strptime(fecha_desde, "%Y-%m-%d")
                                hasta_dt = datetime.strptime(fecha_hasta, "%Y-%m-%d")
                                
                                if hasta_dt < desde_dt:
                                    await query.edit_message_text(
                                        "❌ La fecha 'hasta' no puede ser anterior a la fecha 'desde'.\n\n"
                                        f"Por favor selecciona una fecha igual o posterior a {format_date_display(fecha_desde)}.",
                                        reply_markup=create_calendar(hasta_dt.year, hasta_dt.month, user_id, "hasta")
                                    )
                                    return
                                
                                # Generar reporte de rango
                                await query.edit_message_text(
                                    f"✅ *Fecha desde:* {format_date_display(fecha_desde)}\n"
                                    f"✅ *Fecha hasta:* {date_display}\n\n"
                                    f"📊 Generando reporte..."
                                )
                                
                                username = update.effective_user.first_name or "Usuario"
                                await send_range_report(
                                    context.application,
                                    username=username,
                                    user_id=user_id,
                                    fecha_desde_str=user_state["data"]["fecha_desde_str"],
                                    fecha_hasta_str=date_display,
                                    fecha_desde=fecha_desde,
                                    fecha_hasta=fecha_hasta
                                )
                                
                                # Limpiar estado
                                reset_user_state(user_id)
                        
                        except Exception as e:
                            print(f"❌ Error procesando selección: {e}")
                            await query.edit_message_text(f"❌ Error: {e}")
                            return
                    
                    else:
                        # Navegación de mes
                        try:
                            year = int(parts[3])
                            month = int(parts[4])
                            
                            calendar_markup = create_calendar(year, month, user_id, calendar_type)
                            
                            if calendar_type == "desde":
                                text = "📆 *Selecciona fecha desde:*"
                            else:
                                text = f"📆 *Selecciona fecha hasta:*"
                            
                            await query.edit_message_text(
                                text,
                                reply_markup=calendar_markup,
                                parse_mode="Markdown"
                            )
                            print(f"📅 Navegando a {year}-{month}")
                        except Exception as e:
                            print(f"❌ Error en navegación: {e}")
                else:
                    print("❌ Estructura de callback inválida")
            else:
                print("❌ No hay suficientes partes en el callback")
        else:
            print(f"❌ Usuario no coincide: {parts[1]} != {user_id}")
    else:
        print(f"❌ Callback no empieza con 'calendar': {callback_data}")
    
    print("✅ Callback procesado")

# ─────────────────────────────────────────────
# COMANDO MANUAL POR MENSAJE
# ─────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja mensajes de texto con menú interactivo.
    Flujo:
    1. "reservas@" → muestra menú con botones "Hoy" y "Fechas"
    2. "Hoy" → reporte diario normal
    3. "Fechas" → solicita fecha desde
    4. [fecha desde] → solicita fecha hasta
    5. [fecha hasta] → genera reporte de rango
    """
    global _last_report_message_ids

    if not update.message:
        return

    user_id  = update.message.from_user.id
    username = update.message.from_user.first_name or "Usuario"
    text     = (update.message.text or "").strip()  # Removido .lower()

    print(f"\n💬 MENSAJE RECIBIDO:")
    print(f"👤 Usuario: {username}")
    print(f"🆔 User ID: {user_id}")
    print(f"📝 Mensaje: '{text}'")

    if user_id not in AUTHORIZED_USERS:
        log.warning("Usuario no autorizado intentó usar el bot: %d", user_id)
        print(f"❌ USUARIO NO AUTORIZADO")
        await update.message.reply_text("⛔ No autorizado")
        return

    # Obtener estado del usuario
    user_state = _user_states.get(user_id, {})

    # Primer mensaje: "reservas@"
    if text == "reservas@" and not user_state:
        # Mostrar menú interactivo
        keyboard = ReplyKeyboardMarkup(
            [
                ["📅 Hoy"],
                ["📆 Fechas"]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        
        await update.message.reply_text(
            "🤖 *NOVA - Sistema de Reportes*\n\n"
            "¿Qué tipo de reporte necesitas?",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        # Guardar estado inicial
        _user_states[user_id] = {"mode": None, "step": 0, "data": {}}
        print(f"✅ Menú interactivo enviado a {username}")
        return

    # Botón "Hoy" presionado
    elif text == "📅 Hoy":
        reset_user_state(user_id)
        print(f"✅ Reporte diario solicitado por {username}")
        _last_report_message_ids.append(update.message.message_id)
        await send_full_report(context.application, username=username, user_id=user_id)
        return

    # Botón "Fechas" presionado - iniciar flujo de fechas con calendario
    elif text == "📆 Fechas":
        _user_states[user_id] = {"mode": "fechas", "step": 1, "data": {}}
        
        # Mostrar calendario para fecha desde
        today = datetime.now()
        calendar_markup = create_calendar(today.year, today.month, user_id, "desde")
        
        await update.message.reply_text(
            "📆 *Reporte por Rango de Fechas*\n\n"
            "📅 *Selecciona fecha desde:*",
            reply_markup=calendar_markup,
            parse_mode="Markdown"
        )
        print(f"📆 Iniciando selección de fechas con calendario para {username}")
        return

    # Comando no reconocido
    else:
        print(f"⚠️ Comando no reconocido: '{text}'")
        await update.message.reply_text(
            "❌ No entiendo ese comando.\n\n"
            "Usa 'reservas@' para iniciar el sistema de reportes."
        )

async def update_progress_in_supabase(cmd_id, progress_percent, status_message):
    """Actualiza el progreso en la tabla comandos_bot"""
    try:
        # Crear cliente async cada vez para evitar problemas de contexto
        from supabase import create_async_client
        client = await create_async_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Actualizar solo con status (la columna progreso no existe)
        await client.table("comandos_bot").update({
            "status": f"processing_{progress_percent}"
        }).eq("id", cmd_id).execute()
        
        safe_print(f"📊 Progreso actualizado: {progress_percent}% - {status_message}")
    except Exception as e:
        safe_print(f"❌ Error actualizando progreso: {e}")

async def process_realtime_command(cmd_id, cmd_text, app, async_supabase):
    try:
        # Si no tenemos cliente async, lo creamos
        from supabase import create_async_client
        client = await create_async_client(SUPABASE_URL, SUPABASE_KEY)
        if async_supabase is None:
            from supabase import create_async_client
            async_supabase = await create_async_client(SUPABASE_URL, SUPABASE_KEY)

        # Marcar como processing
        await async_supabase.table("comandos_bot").update({"status": "processing"}).eq("id", cmd_id).execute()
        
        # Verificar tipo de comando
        if cmd_text.startswith("sync_range_"):
            # Extraer fechas: sync_range_YYYY-MM-DD_YYYY-MM-DD
            partes = cmd_text.split("_")
            if len(partes) >= 4:
                fecha_desde = partes[2]
                fecha_hasta = partes[3]

                # Formatear fechas para display en MM/DD/YYYY
                fecha_desde_display = f"{fecha_desde[5:7]}/{fecha_desde[8:10]}/{fecha_desde[0:4]}"
                fecha_hasta_display = f"{fecha_hasta[5:7]}/{fecha_hasta[8:10]}/{fecha_hasta[0:4]}"

                safe_print(f"🔄 RECIBIDO COMANDO RANGO: {fecha_desde} a {fecha_hasta}")

                # Enviar mensaje de selección de fechas con emojis
                await app.bot.send_message(
                    chat_id=CHAT_ID,
                    text=f"🗓️ *SELECCIÓN DE FECHA VÍA WEB*\n\n"
                         f"📅 *Fecha Desde:* {fecha_desde_display}\n"
                         f"📅 *Fecha Hasta:* {fecha_hasta_display}\n"
                         f"🌐 *Origen:* Dashboard Web\n"
                         f"⏳ *Estado:* Iniciando procesamiento...",
                    parse_mode="Markdown"
                )

                # Ejecutar reporte por rango con progreso dinámico
                await send_range_report_with_progress(
                    app,
                    cmd_id,
                    username="Dashboard Web (Rango)",
                    user_id=0,
                    fecha_desde_str=fecha_desde_display,
                    fecha_hasta_str=fecha_hasta_display,
                    fecha_desde=fecha_desde,
                    fecha_hasta=fecha_hasta
                )

                # Enviar confirmación final a Telegram
                await app.bot.send_message(
                    chat_id=CHAT_ID,
                    text=f"✅ *SINCRONIZACIÓN POR RANGO COMPLETADA*\n\n"
                         f"📅 *Período:* {fecha_desde_display} al {fecha_hasta_display}\n"
                         f"👤 *Solicitado por:* Dashboard Web\n"
                         f"📈 *Reporte generado exitosamente*",
                    parse_mode="Markdown"
                )
                safe_print(f"✅ SINCRONIZACIÓN POR RANGO REALIZADA: {fecha_desde_display} al {fecha_hasta_display}")
            else:
                raise Exception("Formato de comando sync_range inválido")
        else:
            # Comando normal de sincronización
            await send_full_report(app, username="Dashboard Web (Realtime)", user_id=0)
            
            # Enviar confirmación a Telegram
            await app.bot.send_message(
                chat_id=CHAT_ID,
                text="✅ *Sincronización vía Web realizada exitosamente*",
                parse_mode="Markdown"
            )
            safe_print("✅ SINCRONIZACIÓN NORMAL REALIZADA POR LA WEB")
        
        # Marcar como completed
        await async_supabase.table("comandos_bot").update({"status": "completed"}).eq("id", cmd_id).execute()
    except Exception as e:
        log.error("Error procesando comando realtime: %s", e)
        # Marcar como error para que la web sepa que falló
        try:
            if async_supabase:
                await async_supabase.table("comandos_bot").update({"status": "error"}).eq("id", cmd_id).execute()
        except:
            pass

async def realtime_listener_job(context: CallbackContext) -> None:
    """
    Se conecta a Supabase a través de WebSockets (Supabase Realtime).
    Cero tráfico de red innecesario, escucha eventos pasivamente.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return

    safe_print("🔌 Iniciando conexión WebSocket (Realtime) a Supabase...")
    try:
        async_supabase = await create_async_client(SUPABASE_URL, SUPABASE_KEY)
        
        def on_insert(payload):
            try:
                # Validar payload básico
                if not payload or not isinstance(payload, dict):
                    safe_print("⚠️ Payload nulo o no es diccionario, ignorando...")
                    return
                
                # Manejar diferentes estructuras de payload de Supabase
                nuevo = None
                
                # Estructura estándar: payload.record
                if "record" in payload and payload["record"] and isinstance(payload["record"], dict):
                    nuevo = payload["record"]
                # Estructura alternativa: payload.new
                elif "new" in payload and payload["new"] and isinstance(payload["new"], dict):
                    nuevo = payload["new"]
                # Estructura directa: el payload mismo contiene los datos
                elif "id" in payload and "comando" in payload and "status" in payload:
                    nuevo = payload
                else:
                    # Si no encontramos datos válidos, ignoramos silenciosamente
                    safe_print("⚠️ Estructura de payload no reconocida, ignorando...")
                    return
                
                # Validar que tengamos un diccionario con datos
                if not isinstance(nuevo, dict):
                    safe_print("⚠️ Datos del payload no son diccionario, ignorando...")
                    return
                
                # Extraer campos con validación
                cmd_id = nuevo.get("id")
                cmd_text = nuevo.get("comando")
                status = nuevo.get("status")
                
                # Validar que los campos existan y no sean None/vacíos
                if not cmd_id or not cmd_text or not status:
                    safe_print(f"⚠️ Campos incompletos o nulos - ID: {cmd_id}, Comando: {cmd_text}, Status: {status}")
                    return
                
                # Validar tipo de comando y estado
                if status != "pending":
                    safe_print(f"⚠️ Comando no está pendiente: {cmd_text} - {status}")
                    return
                
                if cmd_text not in ["sync_now"] and not cmd_text.startswith("sync_range_"):
                    safe_print(f"⚠️ Comando no reconocido: {cmd_text}")
                    return
                
                # Procesar comando válido
                safe_print(f"🚀 Comando Realtime recibido desde la Web! (ID: {cmd_id}, Comando: {cmd_text})")
                
                # Crear tarea en el event loop actual
                loop = asyncio.get_event_loop()
                loop.create_task(process_realtime_command(cmd_id, cmd_text, context.application, async_supabase))
                
            except Exception as e:
                log.error(f"Error procesando payload Realtime: {e}")
                safe_print(f"❌ Error en procesamiento de payload: {e}")

        channel = async_supabase.channel("comandos_bot_channel")
        channel.on_postgres_changes(
            event="INSERT", 
            schema="public", 
            table="comandos_bot", 
            callback=on_insert
        )
        await channel.subscribe()
        safe_print("📡 Listener Realtime listo y escuchando INSERTs en comandos_bot.")
        
        # Mantener viva la conexión con chequeo de errores
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            log.warning("Realtime listener task cancelled.")
    except Exception as e:
        log.error(f"Error en realtime_listener_job: {e}")

async def check_pending_commands_job(context: CallbackContext) -> None:
    """
    Fallback: Revisa cada 30s si hay comandos 'pending' que el Realtime haya perdido.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
        
    try:
        # Usamos requests para un chequeo rápido (sincrónico pero en job)
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/comandos_bot?status=eq.pending&select=*",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}"
            },
            timeout=5
        )
        if resp.status_code == 200:
            pendientes = resp.json()
            # Ordenar por ID descendente para tomar el más reciente primero
            pendientes.sort(key=lambda x: x.get("id", 0), reverse=True)
            
            # Procesar solo el comando más reciente de cada tipo
            procesados = set()
            for cmd in pendientes:
                cmd_id = cmd.get("id")
                cmd_text = cmd.get("comando")
                
                # Determinar tipo de comando
                cmd_tipo = "sync_now" if cmd_text == "sync_now" else "sync_range"
                
                # Si ya procesamos un comando de este tipo, saltar
                if cmd_tipo in procesados:
                    continue
                    
                if cmd_text == "sync_now" or cmd_text.startswith("sync_range_"):
                    safe_print(f"🔄 Fallback: Procesando comando pendiente (ID: {cmd_id}) - {cmd_text}")
                    procesados.add(cmd_tipo)
                    # Ejecutar en segundo plano
                    asyncio.create_task(process_realtime_command(cmd_id, cmd_text, context.application, None))
    except Exception as e:
        log.error("Error en check_pending_commands_job: %s", e)

async def midnight_cleanup_job(context: CallbackContext) -> None:
    """
    Se ejecuta todos los días a las 12:00 AM (medianoche).
    Borra todos los mensajes del último reporte para dejar el chat limpio.
    """
    log.info("Limpieza de medianoche — borrando mensajes del día...")
    await delete_last_report(context.bot)
    log.info("Chat limpiado a medianoche correctamente.")

async def startup_notification_job(context: CallbackContext) -> None:
    """Envía un mensaje de sistema al arrancar."""
    try:
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text="🚀 *Sistema NOVA Online*\n\n"
                 "El bot ha arrancado correctamente.\n"
                 "Presiona /start o escribe `reservas@` para ver el menú.",
            parse_mode="Markdown"
        )
        safe_print("📢 Notificación de arranque enviada a Telegram")
        
    except Exception as e:
        log.error("Error en notificación de arranque: %s", e)

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

    # ── Handler de calendario inline ──
    app.add_handler(CallbackQueryHandler(handle_calendar_callback))
    
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

    # ── Job 3: listener WebSockets Realtime ──
    app.job_queue.run_once(
        realtime_listener_job,
        when=2,  # Ejecutar a los 2 segundos de arrancar
        name="realtime_listener",
    )

    # Fallback: Revisar comandos pendientes cada 30 segundos
    app.job_queue.run_repeating(
        check_pending_commands_job,
        interval=30,
        first=5,
        name="pending_commands_fallback"
    )

    # Notificación inmediata de arranque
    app.job_queue.run_once(startup_notification_job, when=1)

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