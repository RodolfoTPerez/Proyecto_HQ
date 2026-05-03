# ============================================================
# HQ Car Rental  Bot de Telegram para reportes de reservas
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
from datetime import datetime, time as dtime, timedelta

import sys
import io

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

# 
# CARGA DE ENTORNO
# 
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

# Horario: reportes automticos de 8:00 AM a 9:00 PM
REPORT_INTERVAL_MINUTES = int(os.getenv("REPORT_INTERVAL_MINUTES", "30"))
REPORT_HOUR_START       = 8   # primer reporte del da: 8:00 AM
REPORT_HOUR_END         = 21  # ltimo reporte del da: 9:00 PM

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


# 
# LOGGING (Configuración simplificada para evitar bloqueos)
# 
# Configuramos el logging para que TODO vaya al archivo hq_bot.log
# y NADA (ni siquiera INFO) vaya a la consola automáticamente.
# Así solo se verán tus mensajes con emojis (los 'print').
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s  %(message)s",
    handlers=[
        logging.FileHandler("hq_bot.log", encoding="utf-8")
    ]
)
log = logging.getLogger(__name__)

# Silenciar librerías ruidosas (por si acaso)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logging.getLogger("realtime").setLevel(logging.WARNING)
logging.getLogger("supabase").setLevel(logging.WARNING)
logging.getLogger("postgrest").setLevel(logging.WARNING)

# 
# SUPABASE CLIENT
# 
supabase: Client | None = None

def init_supabase() -> bool:
    """Inicializa el cliente de Supabase. Retorna True si ok."""
    global supabase
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.warning("SUPABASE_URL o SUPABASE_KEY no definidos  Supabase desactivado.")
        print("[ERROR] Supabase: No configurado (variables de entorno faltantes)")
        return False
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        safe_print("✅ Supabase: Conectado exitosamente")
        return True
    except Exception as e:
        log.error("Error conectando Supabase: %s", e)
        safe_print(f"❌ Supabase: Error de conexion - {e}")
        return False


def clear_reportes_hq() -> None:
    """
    OBSOLETO: Ya no borramos toda la tabla porque dejaba el dashboard en blanco.
    Se utiliza borrado selectivo en delete_location_fecha_report.
    """
    pass

def delete_location_fecha_report(location: str, fecha: str) -> None:
    """
    Borra nicamente el registro de una ubicacin y fecha especfica milisegundos
    antes de insertar la nueva data. Esto evita el "downtime" visual en la web.
    """
    if supabase is None:
        return
    
    try:
        resp = requests.delete(
            f"{SUPABASE_URL}/rest/v1/reportes_hq?location=eq.{location}&fecha=eq.{fecha}",
            headers={
                "apikey":        SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Prefer":        "return=minimal",
            },
            timeout=15,
        )
        if resp.status_code not in (200, 204):
            log.error("Error borrando dato viejo %s %s: %s", location, fecha, resp.text)
    except Exception as e:
        log.error("Error borrando selectivamente: %s", e)


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
            log.info("Supabase  %s | %s-%s guardado correctamente", location, fecha_desde, fecha_hasta)
        else:
            log.error("Supabase error %d (%s): %s", resp.status_code, location, resp.text)
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
    return_next_day: int,  #  NUEVO PARMETRO: returns con status=rental para maana
    turo: int,  #  NUEVO PARMETRO: status='turo'
) -> None:
    """
    Inserta una fila en la tabla reportes_hq de Supabase.
    Cada llamada al reporte genera un INSERT  as queda historial completo.
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
        "return_next_day":     return_next_day,  #  NUEVO CAMPO
        "turo":                turo,  #  NUEVO CAMPO
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
            log.info("Supabase  %s | %s guardado correctamente", location, fecha)
        else:
            log.error("Supabase error %d (%s): %s", resp.status_code, location, resp.text)
    except Exception as e:
        log.error("Error insertando en Supabase (%s): %s", location, e)


# 
# ESTADO GLOBAL  IDs de mensajes del ltimo reporte
# 
_last_report_message_ids: list[int] = []

# 
# ESTADO DE CONVERSACIN (NUEVO)
# 
_user_states: dict[int, dict] = {}  # {user_id: {"mode": "hoy|fechas", "step": 1|2, "data": {...}}}

# 
# CALENDARIO INLINE
# 
def create_calendar(year: int, month: int, user_id: int, calendar_type: str) -> InlineKeyboardMarkup:
    """
    Crea un calendario inline para un mes especfico.
    calendar_type: 'desde' o 'hasta'
    """
    # Obtener el primer da del mes y cuntos das tiene
    first_day = datetime(year, month, 1)
    days_in_month = (datetime(year, month + 1, 1) - first_day).days if month < 12 else (datetime(year + 1, 1, 1) - first_day).days
    
    # Da de la semana del primer da (0 = lunes, 6 = domingo)
    start_weekday = first_day.weekday()
    
    # Obtener fechas seleccionadas del estado del usuario
    user_state = _user_states.get(user_id, {})
    selected_desde = user_state.get("data", {}).get("fecha_desde")
    selected_hasta = user_state.get("data", {}).get("fecha_hasta")
    
    keyboard = []
    
    # Encabezado con navegacin de meses
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    
    header_row = [
        InlineKeyboardButton("", callback_data=f"calendar_{user_id}_{calendar_type}_{prev_year}_{prev_month:02d}"),
        InlineKeyboardButton(f"{first_day.strftime('%B %Y')}", callback_data="calendar_ignore"),
        InlineKeyboardButton("", callback_data=f"calendar_{user_id}_{calendar_type}_{next_year}_{next_month:02d}")
    ]
    keyboard.append(header_row)
    
    # Das de la semana
    week_days = ["L", "M", "X", "J", "V", "S", "D"]
    keyboard.append([InlineKeyboardButton(day, callback_data="calendar_ignore") for day in week_days])
    
    # Calendario
    current_day = 1
    for week in range(6):  # Mximo 6 semanas en un mes
        row = []
        for weekday in range(7):  # 7 das de la semana
            if week == 0 and weekday < start_weekday:
                # Das vacos antes del primer da del mes
                row.append(InlineKeyboardButton(" ", callback_data="calendar_ignore"))
            elif current_day <= days_in_month:
                # Das del mes con diferenciacin visual
                date_str = f"{year:04d}-{month:02d}-{current_day:02d}"
                callback_data = f"calendar_{user_id}_{calendar_type}_select_{date_str}"
                
                # Determinar el estilo del da
                day_display = str(current_day)
                
                if date_str == selected_desde:
                    # Fecha desde - emoji verde
                    day_display = f"{current_day}"
                elif date_str == selected_hasta:
                    # Fecha hasta - emoji rojo
                    day_display = f"{current_day}"
                elif selected_desde and selected_hasta:
                    # Verificar si est en el rango
                    desde_dt = datetime.strptime(selected_desde, "%Y-%m-%d")
                    hasta_dt = datetime.strptime(selected_hasta, "%Y-%m-%d")
                    current_dt = datetime.strptime(date_str, "%Y-%m-%d")
                    if desde_dt < current_dt < hasta_dt:
                        # Dentro del rango - emoji amarillo
                        day_display = f"{current_day}"
                
                row.append(InlineKeyboardButton(day_display, callback_data=callback_data))
                current_day += 1
            else:
                # Das vacos despus del ltimo da del mes
                row.append(InlineKeyboardButton(" ", callback_data="calendar_ignore"))
        
        if current_day > days_in_month and week > 0:
            # Si ya pasamos todos los das y no estamos en la primera semana, terminamos
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


# 
# FECHA
# 
def get_current_date() -> tuple[str, str]:
    """Retorna (fecha_display MM/DD/YYYY, fecha_api YYYY-MM-DD)"""
    today = datetime.now()
    return today.strftime("%m/%d/%Y"), today.strftime("%Y-%m-%d")


# 
# API  RANGO DE FECHAS (NUEVO)
# 
def fetch_reservations_range(fecha_desde: str, fecha_hasta: str, brand_id: int) -> pd.DataFrame:
    """
    Reservas cuyo pick_up_date est en el rango [fecha_desde, fecha_hasta] para brand_id.
    Ejecuta por cada da del rango para obtener 100 registros por da.
    """
    
    
    # Convertir fechas a datetime para calcular el rango
    start_date = datetime.strptime(fecha_desde, "%Y-%m-%d")
    end_date = datetime.strptime(fecha_hasta, "%Y-%m-%d")
    
    all_data = []
    current_date = start_date
    
    while current_date <= end_date:
        day_str = current_date.strftime("%Y-%m-%d")
        # safe_print(f"   Procesando día: {day_str}")
        
        url = f"{HQ_API_BASE}/car-rental/reservations"
        params = {
            "filters": json.dumps([
                {"type": "string", "column": "brand_id",    "operator": "equals",  "value": str(brand_id)},
                {"type": "date",   "column": "pick_up_date","operator": "between", "value": [day_str, day_str]},
            ]),
            "limit":100
        }
        data = _safe_get(url, params)
        day_data = data.get("data", [])
        
        # safe_print(f"   Día {day_str}: {len(day_data)} registros")
        all_data.extend(day_data)
        
        current_date += timedelta(days=1)
    
    # safe_print(f"   Total de registros obtenidos: {len(all_data)}")
    return pd.DataFrame(all_data)
   
 

def fetch_returns_range(fecha_desde: str, fecha_hasta: str, brand_id: int) -> pd.DataFrame:
    """Reservas cuyo return_date est en el rango [fecha_desde, fecha_hasta] para brand_id.
    Ejecuta por cada da del rango para obtener 100 registros por da."""
    
    # Convertir fechas a datetime para calcular el rango
    start_date = datetime.strptime(fecha_desde, "%Y-%m-%d")
    end_date = datetime.strptime(fecha_hasta, "%Y-%m-%d")
    
    all_data = []
    current_date = start_date
    
    while current_date <= end_date:
        day_str = current_date.strftime("%Y-%m-%d")
        # safe_print(f"   Procesando returns día: {day_str}")
        
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
        
        # safe_print(f"   Returns día {day_str}: {len(day_data)} registros")
        all_data.extend(day_data)
        
        current_date += timedelta(days=1)
    
    # safe_print(f"   Returns total de registros obtenidos: {len(all_data)}")
    return pd.DataFrame(all_data)



# 
# API  con manejo de errores robusto
# 
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
        log.error("HTTP error %s  %s", e.response.status_code, url)
    except requests.exceptions.ConnectionError:
        log.error("Error de conexin con %s", url)
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
    Obtiene reservas con status='open' cuyo pick_up_date es MAANA.
    fecha_hoy: formato YYYY-MM-DD (hoy)
    """
    try:
        hoy = datetime.strptime(fecha_hoy, "%Y-%m-%d")
        maana = (hoy + timedelta(days=1)).strftime("%Y-%m-%d")
        
        url = f"{HQ_API_BASE}/car-rental/reservations"
        params = {
            "filters": json.dumps([
                {"type": "string", "column": "brand_id",     "operator": "equals",  "value": str(brand_id)},
                {"type": "string", "column": "status",       "operator": "equals",  "value": "open"},
                {"type": "date",   "column": "pick_up_date", "operator": "between", "value": [maana, maana]},
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
    Obtiene reservas con status='rental' cuyo return_date es MAANA.
    fecha_hoy: formato YYYY-MM-DD (hoy)
    """
    try:
        hoy = datetime.strptime(fecha_hoy, "%Y-%m-%d")
        maana = (hoy + timedelta(days=1)).strftime("%Y-%m-%d")
        
        url = f"{HQ_API_BASE}/car-rental/reservations"
        params = {
            "filters": json.dumps([
                {"type": "string", "column": "brand_id",     "operator": "equals",  "value": str(brand_id)},
                {"type": "string", "column": "status",       "operator": "equals",  "value": "rental"},
                {"type": "date",   "column": "return_date",  "operator": "between", "value": [maana, maana]},
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
    Obtiene todos los vehculos y normaliza vehicle_class en columnas separadas
    para evitar lambdas frgiles sobre dicts en el filtrado posterior.
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


# 
# REPORTE POR RANGO DE FECHAS (NUEVO)
# 
def generate_range_report(
    fecha_desde_str: str,
    fecha_hasta_str: str,
    fecha_desde: str,
    fecha_hasta: str,
    brand_id: int,
    vehicles: pd.DataFrame,
) -> str:
    location = LOCATION_MAP.get(brand_id, "Desconocida")
    
    

    data_reserva  = fetch_reservations_range(fecha_desde, fecha_hasta, brand_id)
    data_reserva2 = fetch_returns_range(fecha_desde, fecha_hasta, brand_id)

    if data_reserva.empty:
        log.warning("Sin datos de reservas para %s (%s-%s)", location, fecha_desde, fecha_hasta)
        return (
            f"\n"
            f" *Location:* {location}\n"
            f" *Reporte del perodo:* {fecha_desde_str} al {fecha_hasta_str}\n\n"
            f" No se obtuvieron reservas para {location} en este perodo."
        )

    # Normalizar columnas numricas con seguridad
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
    turo   = len(data_reserva[data_reserva["status"] == "turo"])
    
    
  

    # Cancelaciones  solo si existe la columna
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

    # Mtricas financieras (solo reservas en rental)
    rentals_df        = data_reserva[data_reserva["status"] == "rental"]
    total_rental_days = rentals_df["total_days"].sum()
    total_paid        = rentals_df["total_paid"].sum()
    avg_rate          = total_paid / total_rental_days if total_rental_days else 0.0

    # Returns del perodo
    returns = len(data_reserva2[data_reserva2["status"].isin(["completed", "rental"])]) if not data_reserva2.empty else 0
    completed = len(data_reserva2[data_reserva2['status'] == 'completed'])




    # Vehculos disponibles (usar datos actuales)
    if not vehicles.empty and "vc_brand_id" in vehicles.columns:
        vehicles_available = len(
            vehicles[
                (vehicles["status"] == "available") &
                (vehicles["vc_brand_id"] == brand_id)
            ]
        )
    else:
        vehicles_available = 0

    # Para reportes de rango, no calculamos proyecciones
    reservas_next_day = 0
    return_next_day = 0

    log.info(
        "Reporte RANGO %s | %s-%s total=%d onrent=%d open=%d noshow=%d unqualified=%d "
        "cancel=%d turo=%d returns=%d days=%.1f avg=$%.2f avail=%d",
        location, fecha_desde, fecha_hasta, total_reservations, onrent, openr, noshow,
        unqualified, cancellations, turo, returns,
        total_rental_days, avg_rate, vehicles_available,
    )

    #  Guardar en Supabase (tabla reportes_hq_s) 
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
        reservas_next_day=reservas_next_day,
        return_next_day=return_next_day,
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


# 
# REPORTE POR UBICACIN
# 
def generate_report(
    fecha_str: str,
    fecha: str,
    brand_id: int,
    vehicles: pd.DataFrame,
) -> str:
    location = LOCATION_MAP.get(brand_id, "Desconocida")

    data_reserva  = fetch_reservations(fecha, brand_id)
    data_reserva2 = fetch_returns(fecha, brand_id)
    
    #  Fetch de reservas open para maana
    next_day_open = fetch_next_day_open_reservations(fecha, brand_id)
    reservas_next_day = len(next_day_open) if not next_day_open.empty else 0
    
    #  NUEVO: Fetch de returns con status=rental para maana
    next_day_rentals = fetch_next_day_rental_returns(fecha, brand_id)
    return_next_day = len(next_day_rentals) if not next_day_rentals.empty else 0

    if data_reserva.empty:
        log.warning("Sin datos de reservas para %s (%s)", location, fecha)
        return (
            f"\n"
            f" *Location:* {location}\n"
            f" *Reporte del da:* {fecha_str}\n\n"
            f" No se obtuvieron reservas para {location}."
        )

    # Normalizar columnas numricas con seguridad
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
    turo   = len(data_reserva[data_reserva["status"] == "turo"])  #  NUEVO: status='turo'

    # Cancelaciones  solo si existe la columna
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

    total_reservations = onrent + unqualified + cancellations + noshow + openr + turo  #  INCLUIDO TURO

    # Mtricas financieras (solo reservas en rental)
    rentals_df        = data_reserva[data_reserva["status"] == "rental"]
    total_rental_days = rentals_df["total_days"].sum()
    total_paid        = rentals_df["total_paid"].sum()
    avg_rate          = total_paid / total_rental_days if total_rental_days else 0.0

    # Returns del da
    returns = len(data_reserva2[data_reserva2["status"].isin(["completed", "rental"])]) if not data_reserva2.empty else 0
    completed = len(data_reserva2[data_reserva2['status'] == 'completed'])

    # Vehculos disponibles
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

    #  Borrar dato viejo (previene duplicados sin vaciar la tabla completa) 
    delete_location_fecha_report(location, fecha)

    #  Guardar en Supabase 
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
        return_next_day=return_next_day,  #  NUEVO ARGUMENTO
        turo=turo,  #  NUEVO ARGUMENTO
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


# 
# BORRAR MENSAJES ANTERIORES
# 
async def delete_last_report(bot) -> None:
    """
    Borra del chat los mensajes del ltimo reporte enviado.
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


# 
# ENVO COMPLETO A TELEGRAM - RANGO DE FECHAS (NUEVO)
# 
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

    safe_print(f"\n🗓️ === INICIANDO REPORTE POR RANGO ===")
    safe_print(f"👤 Usuario: {username}")
    safe_print(f"🆔 User ID: {user_id}")
    safe_print(f"📅 Período: {fecha_desde_str} al {fecha_hasta_str}")
    safe_print(f"📊 Generando reporte para todas las ubicaciones...\n")

    #  Paso 1: mostrar aviso de procesamiento 
    try:
        msg_procesando = await app.bot.send_message(
            chat_id=CHAT_ID,
            text=" *Procesando reporte por rango...*",
            parse_mode="Markdown",
        )
        safe_print("⏳ Mensaje de procesamiento enviado a Telegram")
    except Exception as e:
        log.warning("No se pudo enviar aviso de procesamiento: %s", e)
        msg_procesando = None

    #  Paso 2: borrar mensaje de procesamiento 
    if msg_procesando:
        try:
            await app.bot.delete_message(chat_id=CHAT_ID, message_id=msg_procesando.message_id)
        except Exception as e:
            log.warning("No se pudo borrar aviso de procesamiento: %s", e)

    #  Paso 3: mostrar encabezado del reporte 
    texto_encabezado = (
        f" *Reporte por Rango de Fechas*\n\n"
        f" *Usuario:* {username}\n"
        f" *User ID:* `{user_id}`\n"
        f" *Perodo:* {fecha_desde_str} al {fecha_hasta_str}\n\n"
        f" Generando informacin..."
    )
    nuevos_ids = []
    try:
        sent_encabezado = await app.bot.send_message(
            chat_id=CHAT_ID,
            text=texto_encabezado,
            parse_mode="Markdown",
        )
        nuevos_ids.append(sent_encabezado.message_id)
        safe_print(f"✅ Encabezado enviado a {username}")
    except Exception as e:
        log.error("Error enviando encabezado: %s", e)

    #  Paso 4: limpiar datos viejos de Supabase 
    safe_print("🧹 Limpiando datos viejos de reportes_hq_s...")
    clear_reportes_hq_s()

    #  Paso 5: cargar vehculos 
        safe_print("🚚 Cargando información de vehículos...")
        vehicles = fetch_vehicles()
        safe_print(f"📦 Vehículos cargados: {len(vehicles)} registros")
    except Exception as e:
        log.error("Error crítico al cargar vehículos: %s", e)
        vehicles = pd.DataFrame()
        safe_print("❌ Error cargando vehículos")

    #  Paso 6: enviar reportes y guardar en Supabase 
    safe_print("📝 Generando reportes por ubicación:")
    for brand_id in LOCATION_MAP:
        location = LOCATION_MAP.get(brand_id, "Desconocida")
        safe_print(f"    ⏳ Procesando {location} (Brand ID: {brand_id})...")
        
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
            # Extraer info clave para pantalla
            res_info = "0"
            for line in reporte.split('\n'):
                if "Total Reservations:" in line:
                    res_info = line.replace("🔹 Total Reservations:", "").strip()
            
            safe_print(f"    ✅ [ENVIADO] {location} -> Reservas: {res_info}")
        except Exception as e:
            log.error("Error enviando reporte rango brand_id=%d: %s", brand_id, e)
            safe_print(f"    ❌ Error enviando reporte de {location}")

    #  Paso 6: mensaje final 
    texto_final = (
        f" *Reporte por Rango Completado*\n\n"
        f" *Perodo:* {fecha_desde_str} al {fecha_hasta_str}\n"
        f" *Datos guardados* en tabla `reportes_hq_s`\n"
        f" *Ver detalles* en la web de reportes por rango\n\n"
        f" *Total mensajes:* {len(nuevos_ids)}\n"
        f" *Proceso finalizado*"
    )
    
    try:
        sent_final = await app.bot.send_message(
            chat_id=CHAT_ID,
            text=texto_final,
            parse_mode="Markdown",
        )
        nuevos_ids.append(sent_final.message_id)
        safe_print(f"✅ Mensaje final enviado a {username}")
    except Exception as e:
        log.error("Error enviando mensaje final: %s", e)

    _last_report_message_ids = nuevos_ids
    safe_print(f"\n🏁 === REPORTE POR RANGO FINALIZADO ===")
    safe_print(f"📨 Total mensajes enviados: {len(nuevos_ids)}")
    safe_print(f"💾 Datos guardados en reportes_hq_s")
    safe_print(f"🌐 Disponible para consulta web\n")


# 
# ENVO COMPLETO A TELEGRAM
# 
async def send_full_report(app, username: str = "Usuario", user_id: int = 0) -> None:
    """
    Flujo completo:
    1. Muestra "Borrando data anterior..."
    2. Borra ese mensaje + todo el ciclo anterior
    3. Muestra bienvenida NOVA  queda visible
    4. Enva los 3 reportes  quedan visibles
    5. Guarda en Supabase (dentro de generate_report)
    Todo se borra en el siguiente ciclo.
    """
    global _last_report_message_ids

    safe_print(f"\n🚀 === INICIANDO REPORTE COMPLETO ===")
    safe_print(f"👤 Usuario: {username}")
    safe_print(f"🆔 User ID: {user_id}")
    safe_print(f"📊 Generando reporte para todas las ubicaciones...\n")

    fecha_str, fecha = get_current_date()
    log.info("Iniciando envío de reporte completo - %s", fecha_str)

    #  Paso 1: mostrar aviso de limpieza 
    try:
        msg_borrando = await app.bot.send_message(
            chat_id=CHAT_ID,
            text=" 🧹 *Borrando data anterior...*",
            parse_mode="Markdown",
        )
        safe_print("🧹 Mensaje de limpieza enviado a Telegram")
    except Exception as e:
        log.warning("No se pudo enviar aviso de limpieza: %s", e)
        msg_borrando = None

    #  Paso 2: Ya NO borramos la tabla entera aquí 
    safe_print("⚡ El borrado ahora es selectivo y ultrarrápido por locación.")
    # clear_reportes_hq() <- Eliminado para evitar downtime en web

    #  Paso 3: borrar todo el ciclo anterior 
    await delete_last_report(app.bot)

    #  Paso 4: borrar el aviso "borrando" 
    if msg_borrando:
        try:
            await app.bot.delete_message(chat_id=CHAT_ID, message_id=msg_borrando.message_id)
        except Exception as e:
            log.warning("No se pudo borrar aviso de limpieza: %s", e)

    #  Paso 5: mostrar bienvenida (queda visible) 
    hora = datetime.now().hour
    if hora < 12:
        saludo = "☀️ Buenos días!"
    elif hora < 18:
        saludo = "🌤️ Buenas tardes!"
    else:
        saludo = "🌙 Buenas noches!"

    texto_bienvenida = (
        f"{saludo} *{username}*\n\n"
        f" Soy 🤖 *NOVA*, tu Asistente Virtual\n"
        f" *¡Bienvenido al Sistema de Reservas!* 🚗\n\n"
        f" 🆔 *User ID:* `{user_id}`\n"
        f" 🔄 Actualizando información..."
    )
    nuevos_ids = []
    try:
        sent_bienvenida = await app.bot.send_message(
            chat_id=CHAT_ID,
            text=texto_bienvenida,
            parse_mode="Markdown",
        )
        nuevos_ids.append(sent_bienvenida.message_id)
        safe_print(f"✅ Bienvenida enviada a {username} (ID: {user_id})")
    except Exception as e:
        log.error("Error enviando bienvenida: %s", e)

    #  Paso 5: cargar vehículos 
    safe_print("🚚 Cargando información de vehículos...")
    try:
        vehicles = fetch_vehicles()
        safe_print(f"📦 Vehículos cargados: {len(vehicles)} registros")
    except Exception as e:
        log.error("Error crítico al cargar vehículos: %s", e)
        vehicles = pd.DataFrame()
        safe_print("❌ Error cargando vehículos")

    #  Paso 6: enviar reportes y guardar en Supabase 
    safe_print("📝 Generando reportes por ubicación:")
    for brand_id in LOCATION_MAP:
        location = LOCATION_MAP.get(brand_id, "Desconocida")
        safe_print(f"    ⏳ Procesando {location} (Brand ID: {brand_id})...")
        
        try:
            reporte = generate_report(
                fecha_str,
                fecha,
                brand_id,
                vehicles
            )
            sent = await app.bot.send_message(
                chat_id=CHAT_ID,
                text=reporte,
                parse_mode="Markdown",
            )
            nuevos_ids.append(sent.message_id)
            
            # Extraer info clave del reporte para mostrar en pantalla
            lines = reporte.split('\n')
            loc_info = location
            res_info = "0"
            for line in lines:
                if "Location:" in line:
                    loc_info = line.replace("*", "").replace("📍 Location:", "").strip()
                if "Total Reservations:" in line:
                    res_info = line.replace("🔹 Total Reservations:", "").strip()
            
            safe_print(f"    ✅ [ENVIADO] {loc_info} -> Reservas: {res_info}")
        except Exception as e:
            log.error("Error enviando reporte brand_id=%d: %s", brand_id, e)
            safe_print(f"    ❌ Error enviando reporte de {location}")

    _last_report_message_ids = nuevos_ids
    safe_print(f"\n🏁 === REPORTE COMPLETO FINALIZADO ===")
    safe_print(f"📨 Total mensajes enviados: {len(nuevos_ids)}")
    safe_print(f"💾 Datos guardados en Supabase (reportes_hq)")
    safe_print(f"⏲️ Próximo reporte en {REPORT_INTERVAL_MINUTES} minutos\n")

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
# SCHEDULER JOBS
# 
_first_run_done = False

async def scheduled_report_job(context: CallbackContext) -> None:
    """
    Se ejecuta cada REPORT_INTERVAL_MINUTES minutos.
    Solo envía reporte si la hora actual está entre 8:00 AM y 9:00 PM inclusive.
    NOTA: El primer reporte al arrancar se envía SIEMPRE.
    """
    global _first_run_done
    current_hour = datetime.now().hour
    
    # El primer reporte tras encender el bot se envía siempre para confirmar que funciona
    if not _first_run_done:
        _first_run_done = True
        safe_print("🚀 Primer reporte de arranque iniciado...")
    elif not (REPORT_HOUR_START <= current_hour <= REPORT_HOUR_END):
        safe_print(f"💤 Reporte automático omitido: fuera de horario ({current_hour}:00)")
        return

    safe_print("📅 Ejecutando reporte automático programado...")
    await send_full_report(context.application, username="Sistema Automático", user_id=0)


async def midnight_cleanup_job(context: CallbackContext) -> None:
    """
    Se ejecuta todos los días a las 12:00 AM (medianoche).
    Borra todos los mensajes del último reporte para dejar el chat limpio.
    """
    safe_print("🌙 Limpieza de medianoche: borrando mensajes del día...")
    await delete_last_report(context.bot)
    safe_print("✨ Chat limpiado a medianoche correctamente.")

# 
# WEBSOCKETS LISTENER (TRUE REALTIME)
# 

async def process_realtime_command(cmd_id, cmd_text, app, async_supabase):
    try:
        # Si no tenemos cliente async, lo creamos
        if async_supabase is None:
            from supabase import create_async_client
            async_supabase = await create_async_client(SUPABASE_URL, SUPABASE_KEY)

        # Marcar como processing
        await async_supabase.table("comandos_bot").update({"status": "processing"}).eq("id", cmd_id).execute()
        
        # Ejecutar sincronizacin
        await send_full_report(app, username="Dashboard Web (Realtime)", user_id=0)
        
        # Enviar confirmación a Telegram
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text="✅ *Sincronización vía Web realizada exitosamente*",
            parse_mode="Markdown"
        )
        safe_print("✅ SINCRONIZACIÓN REALIZADA POR LA WEB")
        
        # Marcar como completed
        await async_supabase.table("comandos_bot").update({"status": "completed"}).eq("id", cmd_id).execute()
    except Exception as e:
        log.error("Error procesando comando realtime: %s", e)

async def realtime_listener_job(context: CallbackContext) -> None:
    """
    Se conecta a Supabase a travs de WebSockets (Supabase Realtime).
    Cero trfico de red innecesario, escucha eventos pasivamente.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return

    safe_print("🔌 Iniciando conexión WebSocket (Realtime) a Supabase...")
    try:
        async_supabase = await create_async_client(SUPABASE_URL, SUPABASE_KEY)
        
        def on_insert(payload):
            log.info(f" DEBUG: Payload Realtime recibido: {payload}")
            try:
                nuevo = payload.get("record", {}) or payload.get("new", {})
                cmd_id = nuevo.get("id")
                cmd_text = nuevo.get("comando")
                
                if cmd_text == "sync_now" and nuevo.get("status") == "pending":
                    safe_print(f"🚀 Comando Realtime recibido desde la Web! (ID: {cmd_id})")
                    # Crear tarea en el event loop actual
                    loop = asyncio.get_event_loop()
                    loop.create_task(process_realtime_command(cmd_id, cmd_text, context.application, async_supabase))
            except Exception as e:
                log.error(f"Error procesando payload Realtime: {e}")

        channel = async_supabase.channel("comandos_bot_channel")
        channel.on_postgres_changes(
            event="INSERT", 
            schema="public", 
            table="comandos_bot", 
            callback=on_insert
        )
        await channel.subscribe()
        safe_print("📡 Listener Realtime listo y escuchando INSERTs en comandos_bot.")
        
        # Mantener viva la conexin con chequeo de errores
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            log.warning("Realtime listener task cancelled.")
    except Exception as e:
        log.error(f"Error en realtime_listener_job: {e}")

async def check_pending_commands_job(context: CallbackContext) -> None:
    """
    Fallback: Revisa cada 10s si hay comandos 'pending' que el Realtime haya perdido.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
        
    try:
        # Usamos requests para un chequeo rpido (sincrnico pero en job)
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
            for cmd in pendientes:
                cmd_id = cmd.get("id")
                cmd_text = cmd.get("comando")
                if cmd_text == "sync_now":
                    safe_print(f"🔄 Fallback: Procesando comando pendiente (ID: {cmd_id})")
                    # Ejecutar en segundo plano
                    asyncio.create_task(process_realtime_command(cmd_id, cmd_text, context.application, None))
    except Exception as e:
        log.error("Error en check_pending_commands_job: %s", e)

# 
# HANDLER DE CALENDARIO
# 
async def handle_calendar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja las selecciones del calendario inline.
    """
    query = update.callback_query
    safe_print(f" Calendario callback recibido: {query.data}")
    
    try:
        await query.answer()
    except Exception as e:
        safe_print(f"⚠️ Error en query.answer(): {e}")
        return
    
    callback_data = query.data
    user_id = update.effective_user.id
    # safe_print(f"👤 Usuario ID: {user_id}, Callback: {callback_data}")
    
    # Parsear callback_data
    parts = callback_data.split('_')
    # log.debug(f" Parts: {parts}")
    
    if not parts or len(parts) < 2:
        return
    
    if parts[0] == "calendar":
        if len(parts) >= 2 and parts[1] == str(user_id):  # Verificar que sea del usuario correcto
            if len(parts) >= 3:
                calendar_type = parts[2]  # 'desde' o 'hasta'
                
                if len(parts) >= 4:
                    action = parts[3]
                    
                    if action == "ignore":
                        return
                    
                    elif action == "select" and len(parts) >= 5:
                        # Seleccin de fecha
                        date_str = parts[4]  # YYYY-MM-DD
                        date_display = format_date_display(date_str)
                        
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
                                    f" *Fecha desde:* {date_display}\n\n"
                                    f" *Selecciona fecha hasta:*",
                                    reply_markup=calendar_markup,
                                    parse_mode="Markdown"
                                )
                            
                            elif calendar_type == "hasta":
                                # Validar y guardar fecha hasta
                                user_state = _user_states.get(user_id, {})
                                if not user_state or "fecha_desde" not in user_state.get("data", {}):
                                    await query.edit_message_text(
                                        " Error: Por favor selecciona primero la fecha 'desde'."
                                    )
                                    return
                                
                                fecha_desde = user_state["data"]["fecha_desde"]
                                fecha_hasta = date_str
                                
                                # Validar que fecha hasta sea posterior o igual a fecha desde
                                desde_dt = datetime.strptime(fecha_desde, "%Y-%m-%d")
                                hasta_dt = datetime.strptime(fecha_hasta, "%Y-%m-%d")
                                
                                if hasta_dt < desde_dt:
                                    await query.edit_message_text(
                                        " La fecha 'hasta' no puede ser anterior a la fecha 'desde'.\n\n"
                                        f"Por favor selecciona una fecha igual o posterior a {format_date_display(fecha_desde)}.",
                                        reply_markup=create_calendar(hasta_dt.year, hasta_dt.month, user_id, "hasta")
                                    )
                                    return
                                
                                # Generar reporte de rango
                                await query.edit_message_text(
                                    f" *Fecha desde:* {format_date_display(fecha_desde)}\n"
                                    f" *Fecha hasta:* {date_display}\n\n"
                                    f" Generando reporte..."
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
                            log.error(f" Error procesando seleccin: {e}")
                            await query.edit_message_text(f" Error: {e}")
                            return
                    
                    else:
                        # Navegacin de mes
                        try:
                            year = int(parts[3])
                            month = int(parts[4])
                            
                            calendar_markup = create_calendar(year, month, user_id, calendar_type)
                            
                            if calendar_type == "desde":
                                text = " *Selecciona fecha desde:*"
                            else:
                                text = f" *Selecciona fecha hasta:*"
                            
                            await query.edit_message_text(
                                text,
                                reply_markup=calendar_markup,
                                parse_mode="Markdown"
                            )
                        except Exception as e:
                            log.error(f" Error en navegacin: {e}")

# 
# COMANDO MANUAL POR MENSAJE
# 
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja mensajes de texto con men interactivo.
    Flujo:
    1. "reservas@"  muestra men con botones "Hoy" y "Fechas"
    2. "Hoy"  reporte diario normal
    3. "Fechas"  solicita fecha desde
    4. [fecha desde]  solicita fecha hasta
    5. [fecha hasta]  genera reporte de rango
    """
    global _last_report_message_ids

    if not update.message:
        return

    user_id  = update.message.from_user.id
    username = update.message.from_user.first_name or "Usuario"
    text     = (update.message.text or "").strip()  # Removido .lower()

    safe_print(f"\n📩 MENSAJE RECIBIDO:")
    safe_print(f"👤 Usuario: {username}")
    safe_print(f"🆔 User ID: {user_id}")
    safe_print(f"💬 Mensaje: '{text}'")

    if user_id not in AUTHORIZED_USERS:
        log.warning("Usuario no autorizado intentó usar el bot: %d", user_id)
        safe_print(f"🚫 USUARIO NO AUTORIZADO")
        await update.message.reply_text(" No autorizado")
        return

    # Obtener estado del usuario
    user_state = _user_states.get(user_id, {})

    # Primer mensaje: "reservas@"
    if text == "reservas@" and not user_state:
        # Mostrar men interactivo
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
            "¿Qué tipo de reporte necesitas? 🤔",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        # Guardar estado inicial
        _user_states[user_id] = {"mode": None, "step": 0, "data": {}}
        safe_print(f" ✅ Menú interactivo enviado a {username}")
        return

    # Botón "Hoy" presionado
    elif text == "📅 Hoy":
        reset_user_state(user_id)
        safe_print(f" 📅 Reporte diario solicitado por {username}")
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
            " 📆 *Reporte por Rango de Fechas*\n\n"
            " *Selecciona fecha desde:* 👇",
            reply_markup=calendar_markup,
            parse_mode="Markdown"
        )
        safe_print(f" 📆 Iniciando selección de fechas con calendario para {username}")
        return

    # Comando no reconocido
    else:
        safe_print(f" Comando no reconocido: '{text}'")
        await update.message.reply_text(
            " No entiendo ese comando.\n\n"
            "Usa 'reservas@' para iniciar el sistema de reportes."
        )


# 
# MAIN
# 
def main() -> None:
    safe_print("\n[BOT] NOVA - Bot de Rent-A-Car HQ")
    safe_print("=" * 40)
    
    if not BOT_TOKEN:
        safe_print("[ERROR] BOT_TOKEN no configurado")
        return
    if not CHAT_ID:
        safe_print("[ERROR] CHAT_ID no configurado")
        return
    if not AUTHORIZED_USERS:
        safe_print("[WARNING] No hay usuarios autorizados")

    safe_print(f"[OK] Configuracion OK")
    safe_print(f"Chat: {CHAT_ID}")
    safe_print(f"Reportes: cada {REPORT_INTERVAL_MINUTES} min")

    # Inicializar Supabase al arrancar
    supabase_status = init_supabase()

    safe_print("Iniciando bot...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Add error handler
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        safe_print(f"[ERROR] {context.error}")
        if "Conflict: terminated by other getUpdates request" in str(context.error):
            safe_print("[CONFLICTO] Ya hay otra instancia del bot corriendo")
            safe_print("Solucion: Cierra la otra instancia o espera 30 segundos")

    app.add_error_handler(error_handler)

    #  Handler de calendario inline 
    app.add_handler(CallbackQueryHandler(handle_calendar_callback))
    
    #  Handler de mensajes manuales 
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    interval_seconds = REPORT_INTERVAL_MINUTES * 60

    #  Job 1: reporte automático (Arranca de inmediato al primer segundo)
    app.job_queue.run_repeating(
        scheduled_report_job,
        interval=interval_seconds,
        first=1,
        name="auto_report",
    )

    #  Job 2: limpieza a medianoche 
    app.job_queue.run_daily(
        midnight_cleanup_job,
        time=dtime(hour=0, minute=0, second=0),
        name="midnight_cleanup",
    )

    #  Job 3: listener WebSockets Realtime 
    app.job_queue.run_once(
        realtime_listener_job,
        when=2,  # Ejecutar a los 2 segundos de arrancar
        name="realtime_listener",
    )

    # Fallback: Revisar comandos pendientes cada 10 segundos
    app.job_queue.run_repeating(
        check_pending_commands_job,
        interval=10,
        first=5,
        name="pending_commands_fallback"
    )

    # Notificación inmediata de arranque
    app.job_queue.run_once(startup_notification_job, when=1)

    safe_print(f"\n✅ [OK] Bot iniciado - Esperando comandos")
    safe_print(f"👉 Escribe 'reservas@' para reporte manual")
    safe_print("=" * 40)
    
    try:
        app.run_polling()
    except KeyboardInterrupt:
        safe_print("\n[STOP] Bot detenido por el usuario")
    except Exception as e:
        safe_print(f"\n[ERROR CRITICO] {e}")
        if "Conflict" in str(e):
            safe_print("Solucion: Cierra otras instancias del bot e intenta de nuevo")


if __name__ == "__main__":
    main()
