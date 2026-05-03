#!/usr/bin/env python3
"""
Script de prueba para verificar duplicación de datos en rangos de fechas
del bot de Telegram HQ Car Rental.
"""

import sys
import os
import json
import pandas as pd
from datetime import datetime, timedelta
import requests

# Importar las funciones del bot original
sys.path.append('.')
from hq_telegram_bot_v4 import (
    _safe_get,
    HEADERS,
    HQ_API_BASE,
    LOCATION_MAP
)

def test_fetch_reservations_range_detailed(fecha_desde: str, fecha_hasta: str, brand_id: int):
    """
    Versión modificada de fetch_reservations_range para detectar duplicados.
    """
    print(f"\n🔍 Probando fetch_reservations_range para {LOCATION_MAP.get(brand_id, 'Unknown')}")
    print(f"📅 Rango: {fecha_desde} a {fecha_hasta}")
    
    url = f"{HQ_API_BASE}/car-rental/reservations"
    
    all_data = []
    all_ids = set()  # Para detectar duplicados por ID
    offset = 0
    page_size = 100
    max_pages = 4
    
    print(f"\n📄 Analizando página por página:")
    
    for page in range(max_pages):
        params = {
            "filters": json.dumps([
                {"type": "string", "column": "brand_id",    "operator": "equals",  "value": str(brand_id)},
                {"type": "date",   "column": "pick_up_date","operator": "between", "value": [fecha_desde, fecha_hasta]},
            ]),
            "limit": page_size,
            "offset": offset
        }
        
        data = _safe_get(url, params)
        page_data = data.get("data", [])
        
        print(f"   Página {page + 1}: {len(page_data)} registros (offset: {offset})")
        
        if not page_data:
            print(f"   No hay más datos en la página {page + 1}")
            break
        
        # Verificar duplicados en esta página
        page_ids = set()
        duplicates_in_page = 0
        
        for item in page_data:
            item_id = item.get('id')
            if item_id in page_ids:
                duplicates_in_page += 1
                print(f"   ⚠️ DUPLICADO EN PÁGINA {page + 1}: ID {item_id}")
            else:
                page_ids.add(item_id)
            
            # Verificar duplicados con páginas anteriores
            if item_id in all_ids:
                print(f"   ⚠️ DUPLICADO ENTRE PÁGINAS: ID {item_id} (visto antes)")
            else:
                all_ids.add(item_id)
        
        if duplicates_in_page > 0:
            print(f"   ❌ Se encontraron {duplicates_in_page} duplicados EN la página {page + 1}")
        
        all_data.extend(page_data)
        
        if len(page_data) < page_size:
            print(f"   Última página alcanzada")
            break
            
        offset += page_size
        
        if len(all_data) >= 300:
            print(f"   Límite mínimo alcanzado")
            break
    
    # Análisis final
    df = pd.DataFrame(all_data)
    unique_ids = len(all_ids)
    total_records = len(all_data)
    
    print(f"\n📊 ANÁLISIS FINAL:")
    print(f"   Total registros obtenidos: {total_records}")
    print(f"   IDs únicos: {unique_ids}")
    print(f"   Duplicados totales: {total_records - unique_ids}")
    
    if total_records > unique_ids:
        print(f"   ❌ HAY DUPLICACIÓN DE DATOS")
        return False, df
    else:
        print(f"   ✅ NO HAY DUPLICACIÓN")
        return True, df

def test_fetch_returns_range_detailed(fecha_desde: str, fecha_hasta: str, brand_id: int):
    """
    Versión modificada de fetch_returns_range para detectar duplicados.
    """
    print(f"\n🔍 Probando fetch_returns_range para {LOCATION_MAP.get(brand_id, 'Unknown')}")
    print(f"📅 Rango: {fecha_desde} a {fecha_hasta}")
    
    url = f"{HQ_API_BASE}/car-rental/reservations"
    
    all_data = []
    all_ids = set()
    offset = 0
    page_size = 100
    max_pages = 4
    
    print(f"\n📄 Analizando página por página:")
    
    for page in range(max_pages):
        params = {
            "filters": json.dumps([
                {"type": "string", "column": "brand_id",   "operator": "equals",  "value": str(brand_id)},
                {"type": "date",   "column": "return_date","operator": "between", "value": [fecha_desde, fecha_hasta]},
            ]),
            "fields": "status,return_date,pick_up_date,total_days,total_paid,cancellation_reason_id",
            "limit": page_size,
            "offset": offset
        } 
        
        data = _safe_get(url, params)
        page_data = data.get("data", [])
        
        print(f"   Returns Página {page + 1}: {len(page_data)} registros (offset: {offset})")
        
        if not page_data:
            print(f"   No hay más datos en la página {page + 1}")
            break
        
        # Verificar duplicados
        page_ids = set()
        duplicates_in_page = 0
        
        for item in page_data:
            item_id = item.get('id')
            if item_id in page_ids:
                duplicates_in_page += 1
                print(f"   ⚠️ DUPLICADO EN PÁGINA {page + 1}: ID {item_id}")
            else:
                page_ids.add(item_id)
            
            if item_id in all_ids:
                print(f"   ⚠️ DUPLICADO ENTRE PÁGINAS: ID {item_id} (visto antes)")
            else:
                all_ids.add(item_id)
        
        if duplicates_in_page > 0:
            print(f"   ❌ Se encontraron {duplicates_in_page} duplicados EN la página {page + 1}")
        
        all_data.extend(page_data)
        
        if len(page_data) < page_size:
            print(f"   Returns última página alcanzada")
            break
            
        offset += page_size
        
        if len(all_data) >= 300:
            print(f"   Returns límite mínimo alcanzado")
            break
    
    # Análisis final
    df = pd.DataFrame(all_data)
    unique_ids = len(all_ids)
    total_records = len(all_data)
    
    print(f"\n📊 ANÁLISIS FINAL RETURNS:")
    print(f"   Total registros obtenidos: {total_records}")
    print(f"   IDs únicos: {unique_ids}")
    print(f"   Duplicados totales: {total_records - unique_ids}")
    
    if total_records > unique_ids:
        print(f"   ❌ HAY DUPLICACIÓN DE DATOS")
        return False, df
    else:
        print(f"   ✅ NO HAY DUPLICACIÓN")
        return True, df

def test_rango_completo():
    """
    Prueba completa para verificar duplicación en un rango de fechas.
    """
    print("🚀 INICIANDO PRUEBA DE DUPLICACIÓN DE DATOS")
    print("=" * 60)
    
    # Fechas de prueba (ajustar según necesidad)
    fecha_desde = "2026-04-01"
    fecha_hasta = "2026-04-07"
    
    resultados = {}
    
    for brand_id in LOCATION_MAP:
        location = LOCATION_MAP.get(brand_id, "Unknown")
        print(f"\n📍 PROBANDO LOCATION: {location} (Brand ID: {brand_id})")
        print("-" * 40)
        
        # Probar fetch_reservations_range
        reservations_ok, df_reservations = test_fetch_reservations_range_detailed(
            fecha_desde, fecha_hasta, brand_id
        )
        
        # Probar fetch_returns_range
        returns_ok, df_returns = test_fetch_returns_range_detailed(
            fecha_desde, fecha_hasta, brand_id
        )
        
        resultados[brand_id] = {
            'location': location,
            'reservations_ok': reservations_ok,
            'returns_ok': returns_ok,
            'reservations_count': len(df_reservations),
            'returns_count': len(df_returns)
        }
    
    # Resumen final
    print(f"\n📋 RESUMEN FINAL DE PRUEBAS")
    print("=" * 60)
    
    hay_problemas = False
    for brand_id, result in resultados.items():
        status = "✅ OK" if (result['reservations_ok'] and result['returns_ok']) else "❌ PROBLEMA"
        print(f"📍 {result['location']}: {status}")
        print(f"   Reservations: {result['reservations_count']} registros - {'✅' if result['reservations_ok'] else '❌'}")
        print(f"   Returns: {result['returns_count']} registros - {'✅' if result['returns_ok'] else '❌'}")
        
        if not (result['reservations_ok'] and result['returns_ok']):
            hay_problemas = True
    
    print(f"\n🎯 RESULTADO GLOBAL: {'❌ SE DETECTARON PROBLEMAS DE DUPLICACIÓN' if hay_problemas else '✅ NO HAY PROBLEMAS DE DUPLICACIÓN'}")
    
    return hay_problemas, resultados

if __name__ == "__main__":
    try:
        problemas, resultados = test_rango_completo()
        
        if problemas:
            print(f"\n⚠️ SE ENCONTRARON PROBLEMAS - Revisar el código fuente")
            sys.exit(1)
        else:
            print(f"\n✅ TODAS LAS PRUEBAS PASARON - No hay duplicación")
            sys.exit(0)
            
    except Exception as e:
        print(f"\n❌ ERROR EN LA PRUEBA: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
