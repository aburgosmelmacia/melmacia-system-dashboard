#!/bin/bash
HOST_UID=$(id -u) HOST_GID=$(id -g) docker-compose up --build -d
echo "El contenedor ha sido iniciado."