FROM mcr.microsoft.com/devcontainers/python:1-3.12

ARG USER_UID
ARG USER_GID

# Modificar el UID y GID del usuario vscode
RUN usermod -u ${USER_UID} vscode && groupmod -g ${USER_GID} vscode

# Asegurarse de que los directorios de trabajo pertenezcan al usuario vscode
RUN mkdir -p /workspaces/melmacia-system-dashboard && chown vscode:vscode /workspaces/melmacia-system-dashboard

# Crear el directorio .ssh y establecer los permisos correctos
RUN mkdir -p /home/vscode/.ssh && chown vscode:vscode /home/vscode/.ssh && chmod 700 /home/vscode/.ssh

# Instalar dependencias del proyecto
COPY requirements.txt /tmp/
RUN pip install -r /tmp/requirements.txt

USER vscode