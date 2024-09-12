#!/bin/bash

# Detener el contenedor
./stop.sh

# Esperar un momento para asegurar que todo se ha detenido correctamente
sleep 2

# Iniciar el contenedor
./start.sh

echo "El contenedor ha sido reiniciado."