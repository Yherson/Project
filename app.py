from flask import Flask, render_template, request, send_from_directory
from werkzeug.utils import secure_filename
from httpcore import ReadTimeout
from time import sleep
from googletrans import Translator, LANGUAGES
from pysrt import open as open_srt
import os
import json
import re
import sqlite3
import gc
import time


app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/traducir', methods=["GET", "POST"])
def traducir():
    ruta_db = 'subtitulos.db'
    if request.method == 'POST':
        archivo = request.files['archivo']
        nombre_archivo = secure_filename(archivo.filename)
        ruta_archivo_origen = os.path.join('static', nombre_archivo)
        archivo.save(ruta_archivo_origen)

        idioma_destino = request.form['idioma']
        ruta_archivo_destino = os.path.join('static', 'traducido_' + nombre_archivo)

        # Comprueba la extensión del archivo para determinar qué función de traducción usar
        extension = os.path.splitext(nombre_archivo)[1]
        
        convertir_srt_like_txt_a_db(ruta_archivo_origen, ruta_db)
        traducir_texto(ruta_db, idioma_destino)
        generar_archivo_traducido(ruta_db, ruta_archivo_destino)
        
        response = send_from_directory('static', 'traducido_' + nombre_archivo, as_attachment=True)
        
        gc.collect()  # Llama al recolector de basura para cerrar todas las conexiones a la base de datos
        eliminar_db(ruta_db)
        
        return response

def eliminar_db(ruta_db):
    for _ in range(10):  # Intenta eliminar la base de datos hasta 10 veces
        try:
            if os.path.exists(ruta_db):
                os.remove(ruta_db)
            break  # Si se pudo eliminar la base de datos, sale del bucle
        except PermissionError:
            time.sleep(1)  # Si no se pudo eliminar la base de datos, espera 1 segundo y luego reintenta


# Crear una base de datos SQLite a partir de un archivo de subtítulos SRT o similar
def convertir_srt_like_txt_a_db(ruta_archivo_origen, ruta_db):
    conn = sqlite3.connect(ruta_db)
    c = conn.cursor()
    c.execute('DROP TABLE IF EXISTS Subtitulos')
    c.execute('CREATE TABLE Subtitulos (id INTEGER PRIMARY KEY, inicio TEXT, fin TEXT, texto TEXT, texto_traducido TEXT)')

    with open(ruta_archivo_origen, 'r', encoding='utf-8') as archivo:
        contenido = archivo.read()

    bloques = contenido.split('\n\n')
    for bloque in bloques:
        lineas = bloque.split('\n')
        if len(lineas) >= 2:
            id = lineas[0]
            tiempo = lineas[1].strip()
            texto = ' '.join(lineas[2:]) if len(lineas) > 2 else ''  # Si no hay líneas de texto, el texto es una cadena vacía
            coincidencias = re.findall(r'(\d{2}:\d{2}:\d{2},\d{3})', tiempo)
            if len(coincidencias) == 2:
                inicio, fin = coincidencias
                c.execute('INSERT INTO Subtitulos (id, inicio, fin, texto) VALUES (?, ?, ?, ?)', (id, inicio, fin, texto))

    conn.commit()
    conn.close()


# Traducir el texto de la base de datos SQLite
def traducir_texto(ruta_db, idioma_destino):
    translator = Translator()

    conn = sqlite3.connect(ruta_db)
    c = conn.cursor()
    c.execute('SELECT id, texto FROM Subtitulos WHERE texto_traducido IS NULL OR texto_traducido = ""')
    rows = c.fetchall()
    if rows:
        for id, texto in rows:
            if texto:  # Solo traducir si el texto no está vacío
                traduccion = translator.translate(texto, dest=idioma_destino)
                if traduccion is not None:
                    c.execute('UPDATE Subtitulos SET texto_traducido = ? WHERE id = ?', (traduccion.text, id))
            else:
                c.execute('UPDATE Subtitulos SET texto_traducido = "" WHERE id = ?', (id,))  # Si el texto está vacío, establecer la traducción como vacía
        conn.commit()
    else:
        print("No hay subtítulos para traducir.")

    conn.close()


# Generar un archivo de subtítulos SRT o similar a partir de la base de datos SQLite
def generar_archivo_traducido(ruta_db, ruta_archivo_destino):
    conn = sqlite3.connect(ruta_db)
    c = conn.cursor()
    c.execute('SELECT inicio, fin, texto_traducido FROM Subtitulos ORDER BY id')

    with open(ruta_archivo_destino, 'w', encoding='utf-8') as archivo_destino:
        for i, (inicio, fin, texto_traducido) in enumerate(c.fetchall(), start=1):
            archivo_destino.write(f'{i}\n{inicio} --> {fin}\n{texto_traducido}\n\n')

    conn.close()
    