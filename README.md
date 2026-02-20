# 📸 Face Finder App — Complete Setup Guide

A Streamlit web app where anyone can take a selfie and instantly find their photos from your Google Drive folder.

---

## 🗂️ Files in this project

```
face_finder_app/
├── app.py               ← Main app code
├── requirements.txt     ← Python dependencies
└── README.md            ← This file
```

---

## ✅ STEP 1 — Create a Google Service Account

This lets the app read your Drive folder without needing anyone to log in.

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click **"New Project"** → name it anything (e.g. `FaceFinder`) → Create
3. In the search bar type **"Google Drive API"** → Click it → Click **Enable**
4. Go to **APIs & Services → Credentials** (left sidebar)
5. Click **"+ Create Credentials"** → **"Service Account"**
6. Name it anything → click **Done**
7. Click on the service account you just created
8. Go to the **"Keys"** tab → **"Add Key"** → **"Create new key"** → choose **JSON** → Download
9. You'll get a `.json` file — this is your `credentials.json` — keep it safe!

---

## ✅ STEP 2 — Share Your Drive Folder With the Service Account

1. Open your `credentials.json` file — find the field `"client_email"` (looks like `something@project.iam.gserviceaccount.com`)
2. Go to **Google Drive** → right-click your photos folder → **Share**
3. Paste that email address → set permission to **Viewer** → Share

---

## ✅ STEP 3 — Get Your Drive Folder ID

1. Open your Google Drive photos folder in the browser
2. The URL looks like: `https://drive.google.com/drive/folders/1ABC_xyz123def456`
3. Copy the part after `/folders/` — that's your **Folder ID**
4. Open `app.py` and paste it here:
   ```python
   DRIVE_FOLDER_ID = "paste_your_folder_id_here"
   ```

---

## ✅ STEP 4 — Deploy to Streamlit Cloud (Free, gives you a public URL)

1. Create a free account at [github.com](https://github.com) if you don't have one
2. Create a **new repository** (click `+` → New repository) → name it `face-finder` → Public → Create
3. Upload your `app.py` and `requirements.txt` to the repo (drag & drop on GitHub)
4. Go to [share.streamlit.io](https://share.streamlit.io) → Sign in with GitHub
5. Click **"New app"** → select your repo → branch: `main` → Main file: `app.py` → Deploy

### 🔐 Add your credentials securely (don't upload credentials.json to GitHub!)

1. In Streamlit Cloud → your app → **"Settings"** (⚙️) → **"Secrets"**
2. Paste the **entire contents** of your `credentials.json` file like this:

```toml
[google_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "abc123"
private_key = "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n"
client_email = "your-service-account@project.iam.gserviceaccount.com"
client_id = "123456789"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/..."
```

> Copy each value from your downloaded JSON file and fill them in above.

3. Click **Save** → your app will restart

---

## ✅ STEP 5 — Share the URL!

After deployment Streamlit gives you a URL like:
```
https://your-app-name.streamlit.app
```

Share this with anyone! They can open it on their phone, take a selfie, and find their photos.

---

## 🧪 Running Locally (optional, for testing)

```bash
pip install -r requirements.txt
# Place credentials.json in the same folder as app.py
python -m streamlit run app.py
```

---

## ⚙️ Tips

| Situation | Fix |
|---|---|
| First load is slow | Normal — it's scanning & indexing all Drive photos. After that it's fast (cached). |
| No matches found | Try moving the **Match Sensitivity** slider left in the sidebar |
| Wrong matches | Try moving the slider right (stricter) |
| Added new photos to Drive | Click **"Rescan Drive"** in the sidebar |
| App says no faces found | Make sure photos have clear, visible faces (not tiny/blurry) |

---

## 💡 How It Works

1. On first load, the app downloads every image from your Drive folder and extracts face "fingerprints" (128-number vectors) — then caches them
2. When someone takes a selfie, their face fingerprint is computed
3. It compares the selfie fingerprint against all cached fingerprints using a distance metric
4. Photos where the distance is below the tolerance threshold are shown as matches
