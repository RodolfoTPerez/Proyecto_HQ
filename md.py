#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Script de prueba para verificar que el input funciona correctamente."""

import sys

def obtener_input(mensaje):
    """Obtiene input del usuario."""
    sys.stdout.write(mensaje)
    sys.stdout.flush()
    try:
        return sys.stdin.readline().strip().upper()
    except:
        return input(mensaje).strip().upper()

print("=" * 50)
print("PRUEBA DE INPUT")
print("=" * 50)

placa = obtener_input("Ingrese la placa: ")
print(f"Placa ingresada: {placa}")

continuar = obtener_input("Continuar? (s/n): ")
print(f"Respuesta: {continuar}")

print("Prueba completada!")
obtener_input("Presione ENTER para salir...")