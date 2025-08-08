#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de prueba para verificar el procesamiento de fechas
"""

from datetime import datetime
from asana_client import parse_date
from llm_evaluator import evaluate_commitment

def test_parse_dates():
    """Prueba la función parse_date con diferentes formatos"""
    print("=" * 50)
    print("PRUEBAS DE PARSE_DATE")
    print("=" * 50)
    
    test_cases = [
        "hoy",
        "mañana",
        "pasado mañana",
        "lunes",
        "martes",
        "viernes",
        "esta semana",
        "próxima semana",
        "fin de semana",
        "en 3 días",
        "en 5 días",
        "15/08/2025",
        "2025-08-15",
        "15 de agosto",
        "20 de diciembre",
        "ayer",
        "15-08-2025",
        "08/15/2025",
    ]
    
    for test_date in test_cases:
        result = parse_date(test_date)
        print(f"'{test_date}' -> {result}")
    
    print()

def test_llm_evaluator():
    """Prueba el evaluador LLM con mensajes que contienen fechas"""
    print("=" * 50)
    print("PRUEBAS DE EVALUADOR LLM")
    print("=" * 50)
    
    test_messages = [
        "@juan necesito que termines el informe hoy antes de las 5pm",
        "Equipo, revisemos esto mañana por la mañana",
        "@maria podés mandar el reporte el viernes?",
        "Tenemos que entregar esto pasado mañana sin falta",
        "La reunión es el lunes próximo",
        "@pedro mandame el documento esta semana",
        "Necesito que revises esto antes del fin de semana",
        "En 3 días tenemos que tener todo listo",
        "@ana completá la tarea antes del 15/08/2025",
        "Hagamos la demo el 20 de agosto",
    ]
    
    for message in test_messages:
        print(f"\nMensaje: {message}")
        try:
            result = evaluate_commitment(message)
            if result:
                print(f"Resultado: {result}")
                if result.get('fecha_limite'):
                    parsed = parse_date(result['fecha_limite'])
                    print(f"Fecha parseada: {parsed}")
        except Exception as e:
            print(f"Error: {e}")
    
    print()

if __name__ == "__main__":
    print(f"Fecha actual: {datetime.now().strftime('%Y-%m-%d %A')}")
    print()
    
    test_parse_dates()
    test_llm_evaluator()
    
    print("\n✅ Pruebas completadas")