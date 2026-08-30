# 🚀 KineForge Cloud Pipeline: Render en la Nube & Subida a YouTube

Sistema automatizado para renderizar proyectos `.kineforge` en la nube utilizando **GitHub Actions** (runners gratuitos de Ubuntu con minutos ilimitados en repos públicos) y subida directa a **YouTube**.

---

## 🛡️ Sistema de Auto-Destrucción (Repositorios Públicos Limpios)

Para disfrutar de **minutos ilimitados y gratuitos** en un repositorio público sin dejar archivos de vídeo ni assets almacenados en GitHub:

1. **Ramas Efímeras**: KineForge sube los assets del capítulo a una rama temporal (ej. `temp-render-ep1`).
2. **Render & Upload**: La máquina virtual de GitHub Actions compila el vídeo y lo sube directamente a YouTube.
3. **💥 Auto-Destrucción**: Al terminar el job (incluso si fallara), el runner elimina la rama temporal automáticamente usando la GitHub API. **El repositorio queda 100% limpio**.

---

## ⚙️ Guía de Configuración Paso a Paso

### 1️⃣ Crear el Repositorio en GitHub
1. Ve a GitHub y crea un repositorio **público** (ejemplo: `kineforge-cloud-render`).
2. Sube la carpeta `cloud-pipeline/` a la raíz de ese repositorio para que el archivo `.github/workflows/render_and_upload.yml` quede activo.

---

### 2️⃣ Configurar Google Cloud Console (1 vez por canal)
1. Entra en [Google Cloud Console](https://console.cloud.google.com/).
2. Crea un proyecto con el nombre de tu canal (ej. `Canal-DrLuffycs`).
3. En **APIs & Services > Library**, busca y habilita **YouTube Data API v3**.
4. En **OAuth consent screen**:
   - Tipo de usuario: **External** (Externo).
   - Añade el correo electrónico de tu canal en la lista de **Test users** (Usuarios de prueba).
5. En **Credentials > Create Credentials > OAuth client ID**:
   - Tipo de aplicación: **Desktop App** (Aplicación de escritorio).
   - Guarda el **Client ID** y el **Client Secret**.

---

### 3️⃣ Obtener el Refresh Token de YouTube
En tu terminal local ejecuta:
```bash
python cloud-pipeline/tools/get_youtube_token.py
```
Introduce el `Client ID` y `Client Secret`. Se abrirá tu navegador para iniciar sesión con la cuenta de YouTube del canal y conceder permisos. El script te devolverá tu `YT_REFRESH_TOKEN`.

---

### 4️⃣ Configurar Environments y Secrets en GitHub
En tu repositorio de GitHub:
1. Ve a **Settings > Environments > New environment**.
2. Nómbralo con el identificador del canal (ejemplo: `canal1`).
3. Añade los 3 **Environment Secrets**:
   - `YT_CLIENT_ID`
   - `YT_CLIENT_SECRET`
   - `YT_REFRESH_TOKEN`

---

## 🎬 Cómo Disparar el Pipeline

### Vía GitHub Web (Manual / Test)
1. Ve a la pestaña **Actions** en tu repositorio de GitHub.
2. Selecciona **KineForge Cloud Render & YouTube Upload** y haz clic en **Run workflow**.
3. Pega el JSON con tus proyectos:

```json
[
  {
    "channel": "canal1",
    "project": "capitulo_01",
    "branch": "temp-render-capitulo-01"
  }
]
```

---

## 👥 ¿Cómo lo usa tu amigo sin interferir?
1. Tu amigo entra a tu repositorio público y pulsa el botón **Fork**.
2. En su propio Fork, él crea sus **Environments** con sus propios Secrets de YouTube.
3. Sus jobs correrán de forma 100% independiente en su cuenta, sin gastar tus cuotas ni interferir en tus canales.
