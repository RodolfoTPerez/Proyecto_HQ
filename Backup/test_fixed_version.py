#!/usr/bin/env python3
"""
Script para probar la version corregida del bot y verificar
que ya no hay duplicacion de datos.
"""

import sys
import os
import json
import pandas as pd
from datetime import datetime, timedelta
import requests

# Importar las funciones del bot corregido
sys.path.append('.')
from hq_telegram_bot_v4_fixed import (
    _safe_get,
    HEADERS,
    HQ_API_BASE,
    LOCATION_MAP,
    fetch_reservations_range,
    fetch_returns_range
)

def test_fixed_functions():
    """
    Prueba las funciones corregidas para verificar que no hay duplicacion.
    """
    print("PRUEBA DE FUNCIONES CORREGIDAS")
    print("=" * 50)
    
    # Fechas de prueba
    fecha_desde = "2026-04-01"
    fecha_hasta = "2026-04-07"
    
    resultados = {}
    
    for brand_id in LOCATION_MAP:
        location = LOCATION_MAP.get(brand_id, "Unknown")
        print(f"\nProbando {location} (Brand ID: {brand_id})")
        print("-" * 30)
        
        # Probar fetch_reservations_range corregido
        print("Testing fetch_reservations_range...")
        df_reservations = fetch_reservations_range(fecha_desde, fecha_hasta, brand_id)
        
        # Verificar duplicados
        if not df_reservations.empty and 'id' in df_reservations.columns:
            unique_ids = df_reservations['id'].nunique()
            total_records = len(df_reservations)
            reservations_ok = total_records == unique_ids
            print(f"   Reservations: {total_records} registros, {unique_ids} IDs únicos - {'OK' if reservations_ok else 'ERROR'}")
        else:
            reservations_ok = True
            print(f"   Reservations: Sin datos - OK")
        
        # Probar fetch_returns_range corregido
        print("Testing fetch_returns_range...")
        df_returns = fetch_returns_range(fecha_desde, fecha_hasta, brand_id)
        
        # Verificar duplicados
        if not df_returns.empty and 'id' in df_returns.columns:
            unique_ids = df_returns['id'].nunique()
            total_records = len(df_returns)
            returns_ok = total_records == unique_ids
            print(f"   Returns: {total_records} registros, {unique_ids} IDs únicos - {'OK' if returns_ok else 'ERROR'}")
        else:
            returns_ok = True
            print(f"   Returns: Sin datos - OK")
        
        resultados[brand_id] = {
            'location': location,
            'reservations_ok': reservations_ok,
            'returns_ok': returns_ok,
            'reservations_count': len(df_reservations),
            'returns_count': len(df_returns)
        }
    
    # Resumen final
    print(f"\nRESUMEN FINAL")
    print("=" * 50)
    
    hay_problemas = False
    for brand_id, result in resultados.items():
        status = "OK" if (result['reservations_ok'] and result['returns_ok']) else "ERROR"
        print(f"{result['location']}: {status}")
        print(f"   Reservations: {result['reservations_count']} registros")
        print(f"   Returns: {result['returns_count']} registros")
        
        if not (result['reservations_ok'] and result['returns_ok']):
            hay_problemas = True
    
    print(f"\nRESULTADO: {'TODO OK' if not hay_problemas else 'HAY PROBLEMAS'}")
    
    return not hay_problemas, resultados

if __name__ == "__main__":
    try:
        todo_ok, resultados = test_fixed_functions()
        
        if todo_ok:
            print(f"\n✓ La version corregida funciona correctamente")
            sys.exit(0)
        else:
            print(f"\n✗ Aun hay problemas en la version corregida")
            sys.exit(1)
            
    except Exception as e:
        print(f"\nError en la prueba: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
