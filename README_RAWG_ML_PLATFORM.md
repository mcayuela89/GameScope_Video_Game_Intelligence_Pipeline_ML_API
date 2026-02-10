# 🎮 RAWG ML Platform — Plataforma End‑to‑End de Datos y Machine Learning

## 📌 Visión General

**RAWG ML Platform** es un proyecto completo de **Data Engineering, Machine Learning y desarrollo de APIs** cuyo objetivo es ingerir, procesar, analizar y servir datos de videojuegos obtenidos desde la **API de RAWG**.

El sistema simula un **entorno real de producción en la nube**, aplicando buenas prácticas de arquitectura, automatización y despliegue.

La plataforma permite:
- Ingestar datos de forma automática y escalable
- Almacenar información estructurada en una base de datos relacional
- Entrenar un modelo de Machine Learning para predecir el éxito de un videojuego
- Exponer estas capacidades mediante una API REST moderna

---

## 🧠 Funcionalidades Principales

- **Pipelines de Datos Automatizados**
  - Carga masiva inicial de videojuegos
  - Actualizaciones incrementales diarias
- **Arquitectura Cloud**
  - Amazon S3 como Data Lake
  - PostgreSQL (Amazon RDS) como almacenamiento estructurado
- **Machine Learning**
  - Modelo de clasificación para predicción de éxito
- **API Avanzada**
  - Endpoint de predicción
  - Consultas analíticas en lenguaje natural
  - Generación dinámica de visualizaciones
- **Despliegue en Producción**
  - FastAPI desplegada en AWS EC2
  - Documentación automática con Swagger

---

## 🏗️ Arquitectura del Sistema

```
RAWG API
   │
   ▼
AWS Lambda (Extracción)
   │
   ▼
Amazon S3 (Datos en bruto)
   │
   ▼
AWS Lambda (Procesamiento)
   │
   ▼
Amazon RDS (PostgreSQL)
   │
   ▼
Modelo de Machine Learning
   │
   ▼
FastAPI (AWS EC2)
```

---

## 📂 Estructura del Proyecto

```
rawg-ml-platform/
├── api/                 # Aplicación FastAPI
│   └── app.py
├── lambdas/             # Funciones AWS Lambda
│   ├── extract_rawg.py
│   └── process_rawg.py
├── model/               # Entrenamiento y artefactos ML
│   ├── train.py
│   └── artifacts/
├── data/                # Datos (excluidos de Git)
│   ├── raw/
│   └── processed/
├── scripts/             # Scripts SQL y utilidades
│   ├── create_tables.sql
│   └── views.sql
├── notebooks/           # Análisis exploratorio
├── tests/               # Tests
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## ⚙️ Pipeline de Datos

### 1️⃣ Extracción
- AWS Lambda consume la API de RAWG.
- Los datos se almacenan en formato JSON en Amazon S3.
- Ejecución programada mediante Amazon EventBridge.

### 2️⃣ Procesamiento y Carga
- Lambda activada por eventos de S3.
- Normalización y validación de datos.
- Inserción y actualización incremental en PostgreSQL (RDS).

---

## 🤖 Machine Learning

### Objetivo
Predecir si un videojuego será considerado un **éxito** basándose en métricas de popularidad, puntuaciones y metadatos.

### Modelo
- Algoritmo: **XGBoost / LightGBM**
- Tipo: Clasificación binaria
- Métricas: ROC‑AUC, precision, recall

### Resultados
- Modelo entrenado serializado (`.joblib`)
- Métricas y metadatos almacenados

---

## 🚀 Endpoints de la API

### `/predict`
Predice la probabilidad de éxito de un videojuego.

**Entrada**
```json
{
  "rating": 4.5,
  "metacritic": 88,
  "ratings_count": 1200
}
```

**Salida**
```json
{
  "success_probability": 0.87,
  "prediction": "success"
}
```

---

### `/ask-text`
Consultas analíticas en lenguaje natural usando un modelo Text‑to‑SQL.

**Ejemplo**
> ¿Qué desarrollador tiene la mejor puntuación media?

---

### `/ask-visual`
Genera visualizaciones dinámicas a partir de preguntas analíticas.

**Ejemplo**
> Top 10 géneros por número de juegos

---

## 📖 Documentación

- Swagger UI: `/docs`
- OpenAPI: `/openapi.json`

---

## 🚢 Despliegue

- API desplegada en **AWS EC2**
- Servidor ASGI: Uvicorn

```bash
uvicorn api.app:app --reload
```

---

## 🔐 Variables de Entorno

Archivo `.env.example`:

```env
RAWG_API_KEY=your_rawg_key
DB_HOST=localhost
DB_NAME=rawg
DB_USER=user
DB_PASSWORD=password
DB_PORT=5432
MODEL_PATH=model/artifacts/model.joblib
HF_TOKEN=your_huggingface_token
```

---

## 🧩 Tecnologías Utilizadas

- Python
- FastAPI
- AWS (Lambda, S3, RDS, EC2, EventBridge)
- PostgreSQL
- XGBoost / LightGBM
- Hugging Face
- Pandas / NumPy
- Matplotlib / Seaborn

---


## 👤 Autores

**Doru , Miguel , Daniel Y Cristian**

