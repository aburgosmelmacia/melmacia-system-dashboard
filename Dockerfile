FROM mcr.microsoft.com/devcontainers/python:1-3.12

# Instalar sudo
RUN apt-get update && apt-get install -y sudo

# Agregar el usuario vscode al grupo sudo
RUN usermod -aG sudo vscode

# Permitir que vscode use sudo sin contraseña
RUN echo "vscode ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers