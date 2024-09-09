FROM mcr.microsoft.com/devcontainers/python:1-3.12

ARG USER_UID=1000
ARG USER_GID=1000

# Instalar sudo
RUN apt-get update && apt-get install -y sudo

# Modificar el UID y GID del usuario vscode
RUN usermod -u ${USER_UID} vscode && groupmod -g ${USER_GID} vscode

# Agregar el usuario vscode al grupo sudo
RUN usermod -aG sudo vscode

# Permitir que vscode use sudo sin contraseña
RUN echo "vscode ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Asegurarse de que los directorios de trabajo pertenezcan al usuario vscode
RUN mkdir -p /workspaces/melmacia-system-dashboard && chown vscode:vscode /workspaces/melmacia-system-dashboard