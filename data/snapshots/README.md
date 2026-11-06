# Instantáneas de REData

Cada 4 h (GitHub Actions) se guarda lo que Red Eléctrica publica y solo si cambió. `INFORME.txt` se regenera con `python3 tools/revisions.py`:
correcciones entre la primera publicación y la última, y comprobación del factor de CO2.

Observaciones previas, tomadas a mano del propio panel (no de estas instantáneas):
- 04/11: primera lectura vista 704.297 MWh, ciclo combinado 24,4 %, 86.751 t CO2 → 06/11: 723.123 MWh, 29,1 %, 100.924 t.
- 05/11: primera lectura vista 729.529 MWh, ciclo combinado 33,6 %, 116.897 t CO2 → 06/11: 741.990 MWh, 38,4 %, 131.311 t.
- Factor tCO2/MWh del 01 al 05/11 desplazado en el tiempo respecto al total de emisiones (REE, verificado el 06/11).
