# WHITEMOON-ENERGY-CENTINEL

Panel público e **informativo** de la energía en España (no certificado, solo datos públicos y gratuitos). Hermano de RailGuard (WHITEMOON-ADIF-RENFE).

## Qué muestra
- **Alertas de apagón por zona** (banner y cards rojas) a partir de titulares de medios (Google Noticias RSS). Sin confirmar por el operador eléctrico.
- **Demanda peninsular en tiempo real** y prevista, y **demanda diaria** de península, Canarias, Baleares, Ceuta y Melilla (Red Eléctrica · REData).
- **Mix de generación** peninsular y % renovable. Histórico de demanda de 30 días.
- **Caso histórico del 28-A (2025)**: curva horaria de demanda y causas según el informe final de ENTSO-E (resumen de Agencia SINC).

## Límites verificados (2 nov 2026)
- REData: Canarias, Baleares, Ceuta y Melilla solo publican datos diarios con retraso; la demanda en tiempo real solo existe para la península; no hay desglose por isla. Un apagón insular se detecta por los titulares de medios, no por REData.
- Los datos de generación y de los sistemas llegan con 1–3 días de retraso.
- La ficha 28-A no incluye hora exacta de cada fase, MW perdidos ni efectos sobre el transporte (no confirmados).

## Uso
```
python3 server.py --port 8080      # RG_OFFLINE=1 para no consultar fuentes externas
python3 -m pytest -q
```
Endpoints: `/api/resumen`, `/api/alertas`, `/api/sistemas`, `/api/caso/28a`, `/healthz`. Sin dependencias (Python estándar).

## Fuentes y atribución
Red Eléctrica de España (REData, https://www.ree.es/es/datos/apidatos) · titulares: solo título, medio y enlace · ENTSO-E / Agencia SINC para el 28-A.

## Mapa de centrales y red
`grid.py` descarga de OpenStreetMap (Overpass) las centrales (`power=plant`), las líneas de 220 y 400 kV y las subestaciones de 400 kV, y las cachea 30 días en `data/grid_cache.json`. Las nucleares salen de `data/nuclear_seed.json` y se ven aunque OSM no responda. API: `/api/red`. Informativo: no es el inventario oficial de Red Eléctrica.
