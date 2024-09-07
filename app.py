"""
Este módulo contiene la aplicación Flask que sirve el dashboard de monitoreo.
"""

#-----------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.
#-----------------------------------------------------------------------------------------

from flask import Flask, render_template
import dashboard

app = Flask(__name__)
app.config['DEBUG'] = True

# Inicializar la base de datos al iniciar la aplicación
dashboard.init_db()

@app.route('/')
def hello():
    """
    Ruta principal que renderiza el dashboard.
    
    Returns:
        str: HTML renderizado del dashboard.
    """
    dashboard_data = dashboard.get_dashboard_data()
    return render_template("dashboard.html", 
                           status=dashboard_data, 
                           servers=dashboard.SERVERS, 
                           apis=dashboard.APIS,
                           config=dashboard.GENERAL_CONFIG)

if __name__ == '__main__':
    app.run(debug=True)