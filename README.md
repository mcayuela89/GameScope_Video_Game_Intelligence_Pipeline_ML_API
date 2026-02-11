# 🎮 GameScope_Video_Intelligence_Pipeline_ML_API #

**Plataforma End-to-End de Datos y Machine Learning para Videojuegos**

## 📌 Visión General
GameScope Video Intelligence Pipeline ML API es un proyecto que simula un entorno real de producción en la nube para la ingesta, procesamiento, análisis y exposición de datos de videojuegos obtenidos desde la API de RAWG.

Integra **Data Engineering**, **Machine Learning** y **APIs modernas**, aplicando buenas prácticas de arquitectura, automatización y despliegue.

---

## 🧠 Funcionalidades Principales
- **Pipelines de datos automatizados**
  - Carga masiva inicial
  - Actualizaciones incrementales diarias
- **Arquitectura Cloud**
  - Amazon S3 como Data Lake
  - PostgreSQL (Amazon RDS) como almacenamiento estructurado
- **Machine Learning**
  - Modelo de clasificación para predecir el éxito de videojuegos
  - Métricas: ROC-AUC, precision, recall
- **API Avanzada**
  - Predicciones en tiempo real
  - Consultas analíticas en lenguaje natural (Text-to-SQL)
  - Visualizaciones dinámicas
- **Despliegue en Producción**
  - FastAPI desplegada en AWS EC2
  - Documentación automática con Swagger (OpenAPI)

---

## 🏗️ Arquitectura del Sistema

RAWG API  

→ AWS Lambda (Extracción)  
→ Amazon S3 (Datos en bruto)  
→ AWS Lambda (Procesamiento)  
→ Amazon RDS (PostgreSQL)  
→ Modelo de Machine Learning  
→ FastAPI (AWS EC2)

---

## 📂 Estructura del Proyecto

GameScope_Video_Intelligence_Pipeline_ML_API/

├── api/ # Aplicación FastAPI

│ └── app.py

├── lambdas/ # Funciones AWS Lambda

│ ├── extract_rawg.py

│ └── process_rawg.py

├── model/ # Entrenamiento y artefactos ML

│ ├── train.py

│ └── artifacts/

├── data/ 

│ ├── raw/

│ └── processed/

├── scripts/ 

│ ├── create_tables.sql

│ └── views.sql

├── notebooks/ 

├── requirements.txt

├── .gitignore

└── README.md

---

## 🚀 Endpoints de la API

### `/predict`
Predice la probabilidad de éxito de un videojuego.

**Entrada**
(JSON)

{
  "rating": 4.5,
  "metacritic": 88,
  "ratings_count": 1200
}

**Salida**
{
  "success_probability": 0.87,
  "prediction": "success"
}

---

/Ask-text

Consultas analíticas en lenguaje natural (Text-to-SQL).
Ejemplo:

¿Qué desarrollador tiene la mejor puntuación media?

---

/Ask-visual

Generación dinámica de visualizaciones.
Ejemplo:

Top 10 géneros por número de juegos

---

📖 Documentación

Swagger UI: /docs

OpenAPI: /openapi.json

---

🚢 Despliegue

- uvicorn api.app:app --reload -

---

🔐 Variables de Entorno

Archivo .env.example:

RAWG_API_KEY=your_rawg_key 

DB_HOST=localhost 

DB_NAME=rawg 

DB_USER=user 

DB_PASSWORD=password 

DB_PORT=5432 

MODEL_PATH=model/artifacts/model.joblib 

HF_TOKEN=your_huggingface_token 


---

🧩 Tecnologías Utilizadas :

Python

FastAPI

AWS (Lambda, S3, RDS, EC2, EventBridge)

PostgreSQL

LightGBM

Hugging Face

Pandas / NumPy

Matplotlib / Seaborn

---

👤 Autores :

- Daniel Cosmin Nedelcu
- Doru Catalin Cristian
- Miguel Ángel Cayuela Sanjuan
- Christian Monzon Iribarren 

